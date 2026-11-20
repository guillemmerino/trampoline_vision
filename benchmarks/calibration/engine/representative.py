"""Experimental preparation for the full-clip calibration replay.

Port of the frozen tiered_safe_regional and guard12 prototypes. Shared with
the benchmark only. The dataclass adapter never changes the source detections.
"""

from dataclasses import asdict

import cv2
import numpy as np

from trampoline_vision.contracts.geometry import BoundingBox
from trampoline_vision.contracts.tracking import BoxMeasurement, TrackingCandidate, TrackingFrame
from trampoline_vision.preparation.boxes import prepare_boxes

REGIONAL = {
    'high_cap': 1.5, 'medium_cap': 3., 'regional_cap': 6., 'keep_outer': True,
    'outer_coverage': .95, 'ambiguous_to_regional': True, 'regional': True,
}
def geometry(boxes):
    """Vectorized intersection, areas and IoU for original-pixel xyxy boxes."""
    b=np.asarray(boxes,dtype=float).reshape(-1,4)
    area=np.prod(b[:,2:]-b[:,:2],axis=1)
    intersection=np.prod(np.maximum(0,np.minimum(b[:,None,2:],b[None,:,2:])-np.maximum(b[:,None,:2],b[None,:,:2])),axis=2)
    return b,area,intersection,intersection/(area[:,None]+area[None,:]-intersection)

def xyxy(box):
    """Read unchanged original-pixel serialized geometry."""
    return [box[k] for k in ('x_min','y_min','x_max','y_max')]

def prepare_arrays(frame):
    """Cache geometry once, without annotations; density uses one vote per base candidate."""
    raw=frame['source']['detections'];cs=frame['candidates'];index={d['detection_id']:i for i,d in enumerate(raw)}
    b,area,inter,iou=geometry([xyxy(d['bbox']) for d in raw]);scores=np.array([d['score'] for d in raw])
    members=[np.array([index[r] for r in c['source_detection_ids']],dtype=int) for c in cs]
    rep=np.array([m[0] for m in members],dtype=int)
    seed=np.array([min(m,key=lambda i:(-scores[i],raw[i]['detection_id'])) for m in members],dtype=int)
    cover=np.zeros((len(cs),len(cs)),dtype=bool)
    for j,m in enumerate(members):cover[:,j]=np.all(inter[rep[:,None],m]/area[m]>=.95,axis=1)
    sa=area[seed];ios=inter[seed[:,None],seed[None,:]]/np.minimum(sa[:,None],sa[None,:])
    ratio=sa[None,:]/sa[:,None]
    support=(ios>=COMMON['neighbour_ios']) & (ratio>=.1) & (ratio<=10.)
    np.fill_diagonal(support,False)
    density=support.sum(axis=1)
    weights=np.sqrt(scores[seed])
    frame_area=frame['source']['context']['width_px']*frame['source']['context']['height_px']
    return dict(raw=raw,candidates=cs,b=b,area=area,inter=inter,iou=iou,scores=scores,members=members,rep=rep,seed=seed,
                support=support,density=density,weights=weights,cover=cover,frame_area=frame_area)

COMMON={'strong_score':.1,'high_score':.5,'neighbour_ios':.5,'neighbour_area_ratio':[.1,10.],
        'image_area_fraction':.1,'weak_region_min_members':4,'expansion_penalty':.1,'ambiguous_fit_gap':.1,
        'keep_outer_min_coverage':.5,'note':'All thresholds are exploratory; no independent validation.'}

def box_area(b):
    """Area of a continuous observed or derived xyxy rectangle."""
    return float(np.prod(b[2:]-b[:2]))

def intersections(box,b):
    """Shared areas against an array of observed boxes."""
    return np.prod(np.maximum(0,np.minimum(box[2:],b[:,2:])-np.maximum(box[:2],b[:,:2])),axis=1)

def union_box(boxes):
    """Derived support extent, explicitly distinct from an observed detection or prediction."""
    return np.r_[np.min(boxes[:,:2],axis=0),np.max(boxes[:,2:],axis=0)]

def group_record(a,anchor,members,bbox,mode,region=None):
    """Keep score provenance: a derived weak region has no invented detector confidence."""
    seed_raw=a['seed'][anchor]
    return {'anchor':int(anchor),'anchor_source_id':a['raw'][seed_raw]['detection_id'],
            'anchor_score':float(a['scores'][seed_raw]),'members':[int(i) for i in members],
            'bbox':np.asarray(bbox).tolist(),'mode':mode,'region':None if region is None else int(region),
            'region_origin':'support_extent' if region is None else 'observed_box',
            'region_score':None if region is None else float(a['scores'][a['rep'][region]])}

def group_tiered(a,cfg):
    """Build strong proposals first, then bounded stars from weak unanchored evidence.

    Strong roots are never consumed by another root. Weak attachment uses
    geometric fit rather than the largest score; ambiguous attachments remain
    pooled evidence, accessible without emitting extra independent candidates.
    """
    n=len(a['candidates']);seed_score=a['scores'][a['seed']];strong=np.flatnonzero(seed_score>=COMMON['strong_score']).tolist()
    weak=np.flatnonzero(seed_score<COMMON['strong_score']).tolist();groups=[];pool=[];attached={i:[] for i in strong};free=set(weak)
    for j in weak:
        possible=[i for i in strong if a['support'][i,j]]
        if not possible:continue
        fits=[]
        for i in possible:
            seed=a['seed'][i];rep=a['rep'][j];inter=a['inter'][seed,rep]
            fit=a['iou'][seed,rep]+.5*inter/a['area'][rep]+.1*inter/a['area'][seed]
            fits.append((float(fit),i))
        fits.sort(key=lambda pair:(-pair[0],-seed_score[pair[1]],pair[1]))
        if len(fits)>1 and fits[0][0]-fits[1][0]<COMMON['ambiguous_fit_gap']:
            if not cfg.get('ambiguous_to_regional'):
                pool.append({'member':j,'reason':'ambiguous_strong_neighbour','possible_anchors':[i for _,i in fits]});free.remove(j)
        else:attached[fits[0][1]].append(j);free.remove(j)
    for anchor in strong:
        initial=a['b'][a['rep'][anchor]];anchor_box=a['b'][a['seed'][anchor]];anchor_area=box_area(anchor_box)
        cap=cfg['high_cap'] if seed_score[anchor]>=COMMON['high_score'] else cfg['medium_cap']
        max_area=max(box_area(initial),cap*anchor_area);region=anchor;best=0.;members=[anchor,*attached[anchor]]
        other_strong=[i for i in strong if i!=anchor]
        initial_cover=(intersections(initial,a['b'][a['seed'][other_strong]])/a['area'][a['seed'][other_strong]]) if other_strong else np.array([])
        for proposal in attached[anchor]:
            box=a['b'][a['rep'][proposal]];new_area=box_area(box)
            if not box_area(initial)<=new_area<=max_area or new_area>COMMON['image_area_fraction']*a['frame_area']:continue
            if not a['cover'][proposal,anchor]:continue
            # Expansion cannot newly engulf another protected strong root.
            if other_strong:
                new_cover=intersections(box,a['b'][a['seed'][other_strong]])/a['area'][a['seed'][other_strong]]
                if bool(np.any((new_cover>=.5)&(initial_cover<.5))):continue
            extra=[j for j in attached[anchor] if j!=proposal and a['cover'][proposal,j] and not a['cover'][anchor,j]]
            gain=float(a['weights'][extra].sum())-COMMON['expansion_penalty']*np.log(new_area/box_area(initial))
            if gain>best+1e-12:best=gain;region=proposal
        bbox=a['b'][a['rep'][region]]
        if cfg['keep_outer']:
            # Preserve unexplained outer extent as a residual hypothesis rather
            # than assuming every margin is false. This may cost candidates.
            retained=[]
            for j in attached[anchor]:
                coverage=float(np.min(a['inter'][a['rep'][region],a['members'][j]]/a['area'][a['members'][j]]))
                if coverage<cfg.get('outer_coverage',COMMON['keep_outer_min_coverage']):free.add(j)
                else:retained.append(j)
            members=[anchor,*retained]
        g=group_record(a,anchor,members,bbox,'strong_anchor',region)
        g['growth_cap']=max_area/anchor_area;g['growth_from_anchor']=box_area(bbox)/anchor_area
        g['density']=int(a['density'][anchor]);g['expansion_gain']=best
        groups.append(g)
    if cfg['regional']:
        blocked=set()
        while True:
            choices=[]
            for seed in free-blocked:
                neighbours=[j for j in free if j!=seed and a['support'][seed,j]]
                if len(neighbours)>=COMMON['weak_region_min_members']-1:
                    choices.append((len(neighbours),float(seed_score[seed]),seed,neighbours))
            if not choices:break
            _,_,seed,neighbours=max(choices,key=lambda p:(p[0],p[1],-p[2]))
            bbox=a['b'][a['rep'][seed]].copy();members=[seed];max_area=cfg['regional_cap']*box_area(bbox)
            for j in sorted(neighbours,key=lambda j:(-a['iou'][a['rep'][seed],a['rep'][j]],-seed_score[j],j)):
                proposed=union_box(np.array([bbox,a['b'][a['rep'][j]]]))
                if box_area(proposed)<=max_area and box_area(proposed)<=COMMON['image_area_fraction']*a['frame_area']:
                    bbox=proposed;members.append(j)
            if len(members)<COMMON['weak_region_min_members']:blocked.add(seed);continue
            free.difference_update(members)
            g=group_record(a,seed,members,bbox,'weak_dense_region')
            g['growth_from_seed']=box_area(bbox)/box_area(a['b'][a['rep'][seed]])
            g['regional_cap']=cfg['regional_cap'];g['density']=len(neighbours)
            groups.append(g)
    for j in sorted(free):groups.append(group_record(a,j,[j],a['b'][a['rep'][j]],'weak_singleton',j))
    return groups,pool

ZONE = (.06, .25, .94, .93)

def area(box):
    return np.prod(box[..., 2:] - box[..., :2], axis=-1)

def intersection(a, b):
    return np.prod(np.maximum(0, np.minimum(a[..., 2:], b[..., 2:])
                              - np.maximum(a[..., :2], b[..., :2])), axis=-1)

def in_zone(groups, zone):
    if not groups:
        return []
    b = np.asarray([group['bbox'] for group in groups])
    center = (b[:, :2] + b[:, 2:])*.5
    # Include boundary-crossing body boxes without clipping the source ROI.
    selected = (np.all((center >= zone[:2]) & (center <= zone[2:]), axis=1)
                | (intersection(b,zone)/area(b) >= .55))
    return [g for g, keep in zip(groups,selected) if keep]

def foreground(image, background):
    difference = cv2.absdiff(image, background).max(axis=2)
    mask = (difference>=27).astype('uint8')
    mask = cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),dtype='uint8'))
    mask = cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((5,5),dtype='uint8'))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask,connectivity=8)
    good = stats[:,cv2.CC_STAT_AREA]>=30
    good[0] = False
    labels[~good[labels]] = 0
    return labels, stats[:,cv2.CC_STAT_AREA]

def evidence(box, labels, component_sizes):
    h,w = labels.shape
    x0,y0 = np.maximum(0,np.floor(box[:2]*.5).astype(int))
    x1,y1 = np.minimum([w,h],np.ceil(box[2:]*.5).astype(int))
    roi = labels[y0:y1,x0:x1]
    if not roi.size:
        return 0,0.,0.,0.
    counts = np.bincount(roi.ravel())
    counts[0] = 0
    if not counts.any():
        return 0,0.,0.,0.
    component = int(np.argmax(counts))
    fill = counts[component]/roi.size
    cover = counts[component]/component_sizes[component]
    all_fill = counts.sum()/roi.size
    return component,float(fill),float(cover),float(all_fill)

def annotated(group, labels, sizes, zone):
    b = np.asarray(group['bbox'])
    component,fill,cover,all_fill = evidence(b,labels,sizes)
    confidence = group['region_score'] if group['region_score'] is not None else group['anchor_score']
    # Fill and component coverage are both needed: a small box of a torso
    # can have exceptional fill but low coverage of the moving silhouette.
    priority = (.62*np.sqrt(fill*cover) + .18*all_fill
                + .16*np.sqrt(confidence) + .04*np.sqrt(intersection(b,zone)/area(b)))
    return dict(group, component=component,fill=fill,component_cover=cover,
                motion_fill=all_fill,priority=float(priority))

def reweight(g,zone):
    b=np.asarray(g['bbox'])
    # Current measured overlap with one changed component in the half-size frame.
    # Avoid ranking tiny, highly filled spectator boxes above body-sized support.
    pixels = float(area(b))*.25*g['fill']
    size_evidence=np.sqrt(min(pixels/480.,1.))
    x=(b[0]+b[2])*.5
    centering=1.-min(abs(x-(zone[0]+zone[2])*.5)/((zone[2]-zone[0])*.5),1.)
    # Body silhouette is a stronger clue than center; preserve lateral cases.
    return .66*g['priority']+.29*size_evidence+.05*centering

def guarded(groups):
    kept=[]
    for g in groups:
        b=np.array(g['bbox'])
        for i,k in enumerate(kept):
            p=np.array(k['bbox'])
            shared=intersection(p,b)
            if shared/area(b)<.95:
                continue
            near=shared/(area(b)+area(p)-shared)>=.67
            fragment=(g['component'] and g['component']==k['component']
                      and area(b)<=.80*area(p)
                      and (g['anchor_score']<.1 or g['component_cover']+.18<k['component_cover']))
            if near or fragment:
                kept[i]=dict(k,members=[*k['members'],*g['members']])
                break
        else:
            kept.append(g)
    return kept

def replay_zone(video, panel):
    """Convert the manually identified broadcast panel to original video pixels."""
    width, height = video.width_px, video.height_px
    left, right = (0, .69 * width) if panel == 'left' else (.30 * width, width)
    return np.array([left + ZONE[0] * (right - left), ZONE[1] * height,
                     left + ZONE[2] * (right - left), ZONE[3] * height])


def downsample(image):
    return cv2.resize(image, None, fx=.5, fy=.5, interpolation=cv2.INTER_AREA)


def regional_groups(source, baseline):
    """Run S0 once, then the frozen regional policy on its candidate partition."""
    prepared = prepare_boxes(source, baseline)
    canonical = {
        'source': {'detections': [dict(detection_id=d.detection_id, bbox=asdict(d.bbox), score=d.score)
                                  for d in source.detections], 'context': asdict(source.context)},
        'candidates': [dict(candidate_id=c.candidate_id, source_detection_ids=c.source_detection_ids)
                       for c in prepared.candidates],
    }
    arrays = prepare_arrays(canonical)
    groups, pool = group_tiered(arrays, REGIONAL)
    assert not pool
    return prepared, groups


def shortlist(groups, image, background, zone):
    """Freeze the hard-zone controls and add a soft-zone comparator."""
    labels, sizes = foreground(downsample(image), background)
    hard_indices = {g['anchor'] for g in in_zone(groups, zone)}
    ranked = [annotated(g, labels, sizes, zone) for g in groups]
    ranked.sort(key=lambda g: (-reweight(g, zone), g['anchor']))
    hard = [g for g in ranked if g['anchor'] in hard_indices]
    hard_dedup = guarded(hard)
    # Identical geometry and ranking formula. The modest zone terms in the
    # score remain, but detections from outside can reach the twelve slots.
    soft_dedup = guarded(ranked)
    return {'hard8': hard_dedup[:8], 'hard12': hard_dedup[:12], 'soft12': soft_dedup[:12]}, {
        'zone_hard': hard, 'guard_hard': hard_dedup, 'guard_soft': soft_dedup,
    }


def tracker_frame(prepared, groups):
    """Adapt shortlist geometry and scores without using the ranking score as confidence."""
    source = prepared.source
    detections = {d.detection_id: d for d in source.detections}
    candidates = []
    for group in groups:
        original_ids = tuple(ref for i in group['members']
                             for ref in prepared.candidates[i].source_detection_ids)
        derived = group['region_origin'] == 'support_extent'
        representative = (group['anchor_source_id'] if derived else
                          prepared.candidates[group['region']].source_detection_ids[0])
        refs = (representative, *[ref for ref in original_ids if ref != representative])
        # The generic contract calls detector-sourced boxes "detector".
        # A derived extent is explicitly flagged in the method and audit.
        score_method = 'calibration_support_extent_seed_score' if derived else 'detector_confidence'
        candidate = TrackingCandidate(
            candidate_id=prepared.candidates[group['anchor']].candidate_id,
            source_detection_ids=refs,
            measurement=BoxMeasurement(BoundingBox(*group['bbox']), 'detector',
                                       detections[representative].score, score_method),
            issues=('calibration_support_extent',) if derived else (),
        )
        candidates.append(candidate)
    return TrackingFrame(source, tuple(candidates))
