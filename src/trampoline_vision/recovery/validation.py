"""Invariants de preparació; la validació de cadenes d'actors arribarà al pas 5."""

from trampoline_vision.recovery.errors import RecoveryError


def validate_fragmentation(result, *, enabled=True):
    """Exigeix partició exacta d'observacions/prediccions i referències de buits consistents."""
    if not enabled:
        if result.fragments or result.gaps:
            raise RecoveryError('Disabled preparation cannot produce fragments')
        return
    fragments = {f.fragment_id: f for f in result.fragments}
    if len(fragments) != len(result.fragments) or len({g.gap_id for g in result.gaps}) != len(result.gaps):
        raise RecoveryError('Duplicate fragment/gap identifiers')
    expected = {(f.context.frame_index, s.track_id): s for f in result.trace.frames for s in f.tracks}
    seen = {}
    for block in (*result.fragments, *result.gaps):
        for sample in block.samples:
            key = (sample.context.frame_index, sample.track.track_id)
            if key in seen or expected.get(key) != sample.track or sample.context != result.trace.frames[key[0]].context:
                raise RecoveryError('Fragment/gap lost, duplicated or changed source evidence')
            if sample.candidate is not None:
                original = next(c for c in result.trace.frames[key[0]].candidates if c.candidate.candidate_id == sample.track.candidate_id)
                if sample.candidate != original:
                    raise RecoveryError('Fragment changed candidate provenance')
            seen[key] = sample
    if set(seen) != set(expected):
        raise RecoveryError('Fragmentation did not preserve every public track sample')
    for gap in result.gaps:
        before, after = fragments.get(gap.previous_fragment_id), fragments.get(gap.next_fragment_id)
        if before is None or before.track_id != gap.track_id or before.samples[-1].context.frame_index + 1 != gap.samples[0].context.frame_index:
            raise RecoveryError('Gap does not follow its source fragment')
        if after is not None and (after.track_id != gap.track_id or gap.samples[-1].context.frame_index + 1 != after.samples[0].context.frame_index):
            raise RecoveryError('Gap does not precede its recovered fragment')
        if gap.next_fragment_id is not None and after is None:
            raise RecoveryError('Gap points to an unknown fragment')
    by_track = {}
    for fragment in result.fragments:
        by_track.setdefault(fragment.track_id, []).append(fragment)
    for tid, items in by_track.items():
        items.sort(key=lambda f: f.samples[0].context.frame_index)
        for index, fragment in enumerate(items):
            first, last = fragment.samples[0], fragment.samples[-1]
            if (fragment.start_reason == 'confirmed') != (index == 0):
                raise RecoveryError('Fragment start reason differs from track lifecycle')
            if index and items[index-1].samples[-1].context.frame_index + 1 >= first.context.frame_index:
                raise RecoveryError('Consecutive observations were split without an actual gap')
            if fragment.end_reason == 'video_end':
                if last.context.frame_index != len(result.trace.frames)-1:
                    raise RecoveryError('Fragment censored before source video end')
            else:
                next_key = (last.context.frame_index+1, tid)
                if next_key not in expected or expected[next_key].state != fragment.end_reason:
                    raise RecoveryError('Fragment end reason differs from tracker evidence')


def validate_lifecycle(trace):
    """Contrasta cada transició pública, últim temps observat i retirada definitiva d'IDs."""
    previous, finished = {}, set()
    for frame in trace.frames:
        current = {s.track_id: s for s in frame.tracks}
        if set(previous) - set(current):
            raise ValueError('Public track disappeared without a finished sample')
        expected_events = set()
        for tid, sample in current.items():
            before = previous.get(tid)
            if tid in finished:
                raise ValueError('Finished track ID reappeared')
            if before is None:
                if sample.evidence != 'observed':
                    raise ValueError('New public track must start observed')
                expected_events.add((tid, 'confirmed'))
            elif sample.evidence == 'predicted':
                if sample.last_observed_timestamp_s != before.last_observed_timestamp_s:
                    raise ValueError('Prediction changed last observation timestamp')
                if sample.state == 'finished':
                    expected_events.add((tid, 'finished'))
                elif before.state != 'lost':
                    expected_events.add((tid, 'lost'))
            elif before.state == 'lost':
                expected_events.add((tid, 'recovered'))
        if {(e.track_id, e.kind) for e in frame.events} != expected_events:
            raise ValueError(f'Tracking events disagree with lifecycle at frame {frame.context.frame_index}')
        finished.update(s.track_id for s in frame.tracks if s.state == 'finished')
        previous = {tid: s for tid, s in current.items() if s.state != 'finished'}
    return previous


def build_validated_chains(fragments, links):
    """Exigeix un DAG de camins exclusius; valida temporalitat, no identitat física."""
    by_id={f.fragment_id:f for f in fragments}
    successor, predecessor={},{}
    for a,b in links:
        if a not in by_id or b not in by_id or a in successor or b in predecessor:
            raise RecoveryError('Unknown fragment or multiple predecessors/successors')
        if by_id[a].samples[-1].context.timestamp_s >= by_id[b].samples[0].context.timestamp_s:
            raise RecoveryError('Overlapping or backward fragment link')
        successor[a],predecessor[b]=b,a
    seen=set()
    chains=[]
    for f in fragments:
        if f.fragment_id in predecessor:
            continue
        chain=[]
        current=f.fragment_id
        while current is not None:
            if current in seen:
                raise RecoveryError('Cyclic or repeated fragment')
            seen.add(current)
            chain.append(current)
            current=successor.get(current)
        chains.append(tuple(chain))
    if seen!=set(by_id):
        raise RecoveryError('Fragments missing from acyclic chain partition')
    return tuple(chains)
