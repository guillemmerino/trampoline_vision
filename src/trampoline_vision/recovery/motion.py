"""Compatibilitat experimental de puntes; no modela la biomecànica dels salts."""

import math


def motion_cost(a,b,parameters):
    """Filtra arestes, conservant el significat global de la matriu de tot el vídeo."""
    p=parameters
    dt=b.start_s-a.end_s
    if dt<=0:
        return None,'not_forward'
    if dt>p.max_gap_s:
        return None,'gap_too_long'
    ratio=max(a.scale/b.scale,b.scale/a.scale)
    if ratio>p.max_scale_ratio:
        return None,'scale_gate'
    scale=max(a.scale,b.scale)
    distance=math.dist(a.last,b.first)/scale
    if distance>p.distance_base+p.distance_growth_per_s*dt:
        return None,'distance_gate'
    forward=tuple(x+v*dt for x,v in zip(a.last,a.last_velocity))
    backward=tuple(x-v*dt for x,v in zip(b.first,b.first_velocity))
    residual=min(distance,math.dist(forward,b.first)/scale,math.dist(backward,a.last)/scale)
    return {'gap_s':dt,'geometry':min(1.,residual/(1+p.geometry_growth_per_s*dt)),
            'scale':min(1.,abs(math.log(a.scale/b.scale))/math.log(p.max_scale_ratio)),
            'time':min(1.,dt/2)},None
