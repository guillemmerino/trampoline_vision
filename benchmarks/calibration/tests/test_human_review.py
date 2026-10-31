"""Persistence, input binding and re-evaluation of explicit human frame decisions."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from benchmarks.calibration.common import atomic_json, digest, read_json, sha256
from benchmarks.calibration.human_review import empty_state, make_server, reassess, save_state, validate_state


def fixture_bundle():
    frames = []
    for i in range(2):
        visible = i == 0
        reference = dict(state="visible" if visible else "ambiguous", bbox_xyxy=[10, 10, 30, 50] if visible else None)
        variants = {}
        for name in ("primary", "control"):
            boxes = [dict(det_id=0, bbox_xyxy=[10., 10., 20., 20.], confidence=.004)]
            if name == "primary":
                boxes.append(dict(det_id=1, bbox_xyxy=[10., 10., 30., 50.], confidence=.0015))
            available = visible and name == "primary"
            variants[name] = dict(boxes=boxes, evaluation=dict(detector_available=available if visible else None,
                localization_source="iou_rule" if visible else "reference_state",
                localization_class="sufficient" if available else "needs_review" if visible else "excluded"))
        frames.append(dict(key=f"clip:{i}", case_id="clip", frame_index=i, width=100, height=80,
                           reference=reference, variants=variants, image=f"images/{i}.png"))
    return dict(schema_version="1.0", run_signature="fixed-run", frames=frames,
                detectors={"primary": {}, "control": {}})


def review_entry(presence="visible"):
    return dict(presence=presence, reference=dict(verdict="pending", bbox_xyxy=None, source="none", candidate=None),
                detectors={}, notes="Human decision", updated_at="2026-10-30T17:00:00+00:00")


class HumanReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "review"
        self.root.mkdir()
        self.bundle = fixture_bundle()
        atomic_json(self.root / "bundle.json", self.bundle)
        atomic_json(self.root / "review-state.json", empty_state(self.bundle))
        (self.root / "index.html").write_text("review")
        atomic_json(self.root / "checksums.json", {"bundle.json": sha256(self.root / "bundle.json"), "index.html": sha256(self.root / "index.html")})

    def test_candidate_and_run_binding_rejects_mismatched_or_invented_decisions(self):
        state = empty_state(self.bundle)
        entry = review_entry()
        entry["detectors"]["primary"] = dict(verdict="sufficient", candidate_id=1)
        state["entries"]["clip:1"] = entry
        self.assertEqual(validate_state(state, self.bundle), state)
        for field, value in [("run_signature", "other"), ("bundle_sha256", "other")]:
            changed = copy.deepcopy(state)
            changed[field] = value
            with self.assertRaises(ValueError):
                validate_state(changed, self.bundle)
        changed = copy.deepcopy(state)
        changed["entries"]["clip:1"]["detectors"]["primary"]["candidate_id"] = 99
        with self.assertRaisesRegex(ValueError, "candidate"):
            validate_state(changed, self.bundle)
        changed = copy.deepcopy(state)
        changed["entries"]["clip:1"]["presence"] = "absent"
        with self.assertRaisesRegex(ValueError, "visible presence"):
            validate_state(changed, self.bundle)

    def test_reference_correction_must_be_bounded_and_detector_source_exact(self):
        state = empty_state(self.bundle)
        entry = review_entry()
        state["entries"]["clip:1"] = entry
        entry["reference"] = dict(verdict="corrected", bbox_xyxy=[10., 10., 30., 50.], source="detector",
                                  candidate=dict(detector="primary", det_id=1))
        validate_state(state, self.bundle)
        entry["reference"]["bbox_xyxy"][2] = 31.
        with self.assertRaisesRegex(ValueError, "candidate changed"):
            validate_state(state, self.bundle)
        entry["reference"] = dict(verdict="corrected", bbox_xyxy=[0, 0, 101, 30], source="manual", candidate=None)
        with self.assertRaisesRegex(ValueError, "original-pixel"):
            validate_state(state, self.bundle)
        entry["reference"] = dict(verdict="approved", bbox_xyxy=[10, 10, 30, 50], source="original", candidate=None)
        with self.assertRaisesRegex(ValueError, "unchanged original"):
            validate_state(state, self.bundle)

    def test_atomic_persistence_preserves_revisions_and_rejects_stale_tabs(self):
        state = empty_state(self.bundle)
        state["entries"]["clip:0"] = review_entry()
        first = save_state(self.root, self.bundle, state, 0)
        self.assertEqual(first["revision"], 1)
        self.assertEqual(read_json(self.root / "review-state.json"), first)
        event = read_json(self.root / "history/000001.json")
        self.assertEqual(event["next_sha256"], digest(first))
        with self.assertRaises(FileExistsError):
            save_state(self.root, self.bundle, state, 0)
        self.assertEqual(read_json(self.root / "review-state.json"), first)
        next_state = copy.deepcopy(first)
        next_state["entries"]["clip:0"]["notes"] = "Updated"
        second = save_state(self.root, self.bundle, next_state, 1)
        self.assertEqual(second["revision"], 2)
        self.assertEqual(read_json(self.root / "history/000002.json")["previous_sha256"], digest(first))

    def test_reassessment_includes_visible_without_reference_and_selected_partial(self):
        state = empty_state(self.bundle)
        entry = review_entry()
        entry["reference"]["verdict"] = "missing"
        entry["detectors"] = {"primary": dict(verdict="sufficient", candidate_id=1),
                              "control": dict(verdict="partial", candidate_id=0)}
        state["entries"]["clip:1"] = entry
        atomic_json(self.root / "review-state.json", state)
        totals = reassess(self.root, self.root / "review-state.json", self.root.parent / "assessment")
        self.assertEqual(totals["primary"]["geometric_visible"], 1)
        self.assertEqual((totals["primary"]["human_visible"], totals["primary"]["human_sufficient"]), (1, 1))
        self.assertEqual(totals["control"]["human_partial"], 1)
        samples = read_json(self.root.parent / "assessment/result.json")["samples"]
        selected = next(s for s in samples if s["frame_index"] == 1 and s["detector"] == "control")
        self.assertEqual((selected["candidate_id"], selected["reference_source"]), (0, "human_visible_without_bbox"))
        self.assertIsNone(selected["revised_available"])

    def test_rejected_reference_is_excluded_and_drawn_reference_can_restore_it(self):
        original = (self.root / "bundle.json").read_bytes()
        state = empty_state(self.bundle)
        state["entries"]["clip:0"] = review_entry()
        state["entries"]["clip:0"]["reference"]["verdict"] = "rejected"
        atomic_json(self.root / "review-state.json", state)
        totals = reassess(self.root, self.root / "review-state.json", self.root.parent / "rejected")
        self.assertEqual(totals["primary"]["geometric_visible"], 0)
        state["entries"]["clip:0"]["reference"] = dict(verdict="corrected", bbox_xyxy=[10, 10, 20, 20], source="manual", candidate=None)
        atomic_json(self.root / "review-state.json", state)
        totals = reassess(self.root, self.root / "review-state.json", self.root.parent / "corrected")
        self.assertEqual((totals["control"]["geometric_visible"], totals["control"]["geometric_available"]), (1, 1))
        self.assertEqual((self.root / "bundle.json").read_bytes(), original)
        with self.assertRaises(ValueError):
            reassess(self.root, self.root / "review-state.json", self.root.parent / "corrected")

    def test_notes_only_do_not_claim_human_presence_or_approval(self):
        state = empty_state(self.bundle)
        state["entries"]["clip:0"] = review_entry(presence="pending")
        atomic_json(self.root / "review-state.json", state)
        totals = reassess(self.root, self.root / "review-state.json", self.root.parent / "notes")
        self.assertEqual((totals["primary"]["geometric_available"], totals["primary"]["human_visible"]), (1, 0))
        self.assertEqual(totals["primary"]["human_sufficient"], 0)

    def test_rejecting_one_candidate_does_not_claim_no_useful_boxes(self):
        state = empty_state(self.bundle)
        entry = review_entry()
        entry["detectors"]["primary"] = dict(verdict="incorrect", candidate_id=0)
        state["entries"]["clip:0"] = entry
        atomic_json(self.root / "review-state.json", state)
        totals = reassess(self.root, self.root / "review-state.json", self.root.parent / "candidate-rejected")
        self.assertEqual(totals["primary"]["geometric_available"], 1)
        self.assertEqual(totals["primary"]["human_absent_or_incorrect"], 0)
        self.assertEqual(totals["primary"]["human_rejected_candidates"], 1)
        self.assertEqual(totals["primary"]["human_pending"], 1)

    def test_explicit_absence_excludes_geometry_and_does_not_create_tracking_miss(self):
        state = empty_state(self.bundle)
        entry = review_entry(presence="absent")
        entry["reference"]["verdict"] = "rejected"
        entry["detectors"]["primary"] = dict(verdict="incorrect", candidate_id=0)
        state["entries"]["clip:0"] = entry
        atomic_json(self.root / "review-state.json", state)
        totals = reassess(self.root, self.root / "review-state.json", self.root.parent / "absent")
        self.assertEqual(totals["primary"]["geometric_visible"], 0)
        self.assertEqual(totals["primary"]["human_visible"], 0)
        self.assertEqual(totals["primary"]["needs_review"], 0)
        self.assertEqual(totals["primary"]["excluded"], 2)

    def test_http_save_conflict_and_cross_origin_protection(self):
        with make_server(self.root, 0) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.shutdown)
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/api/state") as response:
                self.assertEqual(json.load(response)["revision"], 0)
            submitted = empty_state(self.bundle)
            submitted["entries"]["clip:1"] = review_entry()
            data = json.dumps(dict(base_revision=0, state=submitted)).encode()
            request = Request(base + "/api/state", data=data, headers={"Content-Type": "application/json"})
            with urlopen(request) as response:
                self.assertEqual(json.load(response)["revision"], 1)
            with self.assertRaises(HTTPError) as conflict:
                urlopen(request)
            self.assertEqual(conflict.exception.code, 409)
            request.add_header("Origin", "http://another-site.invalid")
            with self.assertRaises(HTTPError) as cross:
                urlopen(request)
            self.assertEqual(cross.exception.code, 403)
            with self.assertRaises(HTTPError) as private:
                urlopen(base + "/review-state.json")
            self.assertEqual(private.exception.code, 404)
            server.shutdown()
            thread.join()


if __name__ == "__main__":
    unittest.main()
