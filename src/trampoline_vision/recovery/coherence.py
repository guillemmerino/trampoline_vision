"""Senyals de revisió: no deduplica, divideix ni certifica identitats."""

import math
from itertools import combinations
from trampoline_vision.recovery.features import center


def diagnostics(prepared,duplicate_iou):
    """Registra solapaments entre tracks i salts interns com a hipòtesis, no errors provats."""
    duplicates=[]
    for frame in prepared.trace.frames:
        observed=[t for t in frame.tracks if t.evidence=='observed']
        for a,b in combinations(observed,2):
            x,y=a.bbox,b.bbox
            inter=max(0,min(x.x_max,y.x_max)-max(x.x_min,y.x_min))*max(0,min(x.y_max,y.y_max)-max(x.y_min,y.y_min))
            union=(x.x_max-x.x_min)*(x.y_max-x.y_min)+(y.x_max-y.x_min)*(y.y_max-y.y_min)-inter
            overlap=inter/union if union>0 else 0.
            if overlap>=duplicate_iou:
                duplicates.append({'frame_index':frame.context.frame_index,'track_ids':[a.track_id,b.track_id],'iou':overlap})
    jumps=[]
    for f in prepared.fragments:
        for a,b in zip(f.samples,f.samples[1:]):
            x,y=a.track.bbox,b.track.bbox
            sx=math.sqrt((x.x_max-x.x_min)*(x.y_max-x.y_min))
            sy=math.sqrt((y.x_max-y.x_min)*(y.y_max-y.y_min))
            if math.dist(center(x),center(y))/max(sx,sy)>3 or max(sx/sy,sy/sx)>4:
                jumps.append({'fragment_id':f.fragment_id,'frame_index':b.context.frame_index})
    return {'possible_duplicate_observations':duplicates,'possible_internal_discontinuities':jumps,
            'interpretation':'review_signals_not_identity_ground_truth','automatic_deduplication':False,'automatic_fragment_splitting':False}
