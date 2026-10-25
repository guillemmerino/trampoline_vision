"""Fragmentació determinista de tracking complet, sense associar IDs diferents.

consecutive_observations_v1 tanca un fragment a la primera mostra sense
mesura. Si el mateix track es recupera, comença un fragment nou. Els buits
es mantenen separats, amb prediccions/finished i referències als fragments.
No es divideix un track per canvis geomètrics ni s'interpola cap buit.
"""

from collections import defaultdict

from trampoline_vision.contracts.recovery import TrajectorySample, TrajectoryFragment, TrajectoryGap, FragmentationResult


def build_fragments(trace, config):
    """Particiona totes les mostres públiques sense canviar-les ni crear actor_id.

Disabled retorna zero fragments/buits i la mateixa traça. Un fragment que
arriba al final és censurat: no es declara finished artificialment.
"""
    if not config.enabled:
        return FragmentationResult(trace, config.policy, (), ())
    by_track = defaultdict(list)
    for frame in trace.frames:
        candidates = {c.candidate.candidate_id: c for c in frame.candidates}
        for sample in frame.tracks:
            by_track[sample.track_id].append(TrajectorySample(frame.context, sample, candidates.get(sample.candidate_id)))
    fragments, gaps = [], []
    for tid in sorted(by_track):
        samples = by_track[tid]
        observed, predicted = [], []
        ordinal, previous_fragment = 0, None
        start_reason = 'confirmed'
        for sample in samples:
            if sample.track.evidence == 'observed':
                if not observed:
                    ordinal += 1
                    next_id = f'fragment:{tid}:{ordinal}'
                    if predicted:
                        gaps.append(TrajectoryGap(f'gap:{tid}:{ordinal-1}', tid, previous_fragment, next_id, tuple(predicted), 'recovered'))
                        predicted = []
                        start_reason = 'recovered'
                observed.append(sample)
            else:
                if observed:
                    previous_fragment = f'fragment:{tid}:{ordinal}'
                    fragments.append(TrajectoryFragment(previous_fragment, tid, tuple(observed), start_reason, sample.track.state))
                    observed = []
                predicted.append(sample)
        if observed:
            fragments.append(TrajectoryFragment(f'fragment:{tid}:{ordinal}', tid, tuple(observed), start_reason, 'video_end'))
        if predicted:
            reason = 'finished' if predicted[-1].track.state == 'finished' else 'video_end'
            gaps.append(TrajectoryGap(f'gap:{tid}:{ordinal}', tid, previous_fragment, None, tuple(predicted), reason))
    return FragmentationResult(trace, config.policy, tuple(fragments), tuple(gaps))
