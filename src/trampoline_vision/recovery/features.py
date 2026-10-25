"""Resums de fragments observats; ni selecció del gimnasta ni nova inferència."""

from dataclasses import dataclass
import math
from statistics import median

from trampoline_vision.recovery.errors import RecoveryError


@dataclass(frozen=True)
class FragmentFeatures:
    """Geometria i descriptor mitjà experimental d'un fragment immutable."""

    fragment_id: str
    start_s: float
    end_s: float
    first: tuple[float,float]
    last: tuple[float,float]
    first_velocity: tuple[float,float]
    last_velocity: tuple[float,float]
    scale: float
    appearance: tuple[float,...] | None


def center(box):
    """Centre de caixa; no és centre de masses."""
    return ((box.x_min+box.x_max)/2,(box.y_min+box.y_max)/2)


def describe_fragments(prepared, appearances=None):
    """Relaciona descriptors per candidat/context, mai només per dimensió o fila."""
    fragments=prepared.fragments
    means={}
    if appearances is not None:
        sample_index={(s.context.frame_index,s.track.candidate_id):f.fragment_id for f in fragments for s in f.samples}
        stream=iter(appearances)
        fingerprint=None
        dimension=None
        for frame in prepared.trace.frames:
            appearance=next(stream,None)
            if appearance is None or appearance.context != frame.context:
                raise RecoveryError('Missing or mismatched appearance frame')
            if fingerprint is None:
                fingerprint=appearance.model_fingerprint
            if appearance.model_fingerprint != fingerprint:
                raise RecoveryError('Mixed appearance fingerprints')
            expected=[c.candidate.candidate_id for c in frame.candidates if c.candidate.measurement is not None]
            if [e.candidate_id for e in appearance.embeddings] != expected:
                raise RecoveryError('Appearance must cover exact measured candidates in original order')
            for e in appearance.embeddings:
                if dimension is None:
                    dimension=len(e.values)
                if len(e.values)!=dimension:
                    raise RecoveryError('Mixed appearance dimensions')
                fid=sample_index.get((frame.context.frame_index,e.candidate_id))
                if fid is not None:
                    values=means.setdefault(fid,[0.]*len(e.values))
                    for i,value in enumerate(e.values):
                        values[i]+=value
        if next(stream,None) is not None:
            raise RecoveryError('Extra appearance frames')
        for fid,values in means.items():
            norm=math.sqrt(sum(v*v for v in values))
            if norm<=1e-12:
                raise RecoveryError('Degenerate fragment appearance summary')
            means[fid]=tuple(v/norm for v in values)
        if set(means) != {f.fragment_id for f in fragments}:
            raise RecoveryError('Missing fragment appearance')
    result=[]
    for f in fragments:
        samples=f.samples
        centers=[center(s.track.bbox) for s in samples]
        def velocity(end):
            subset=samples[-5:] if end else samples[:5]
            first,last=subset[0],subset[-1]
            dt=last.context.timestamp_s-first.context.timestamp_s
            a,b=center(first.track.bbox),center(last.track.bbox)
            return tuple((y-x)/dt if dt else 0. for x,y in zip(a,b))
        scales=[math.sqrt((s.track.bbox.x_max-s.track.bbox.x_min)*(s.track.bbox.y_max-s.track.bbox.y_min)) for s in samples]
        result.append(FragmentFeatures(f.fragment_id,samples[0].context.timestamp_s,samples[-1].context.timestamp_s,
            centers[0],centers[-1],velocity(False),velocity(True),median(scales),means.get(f.fragment_id)))
    return tuple(result)
