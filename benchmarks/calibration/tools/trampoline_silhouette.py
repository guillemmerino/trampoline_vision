"""Prova del suport de primer pla com a evidència separada per mantenir IDs."""

from collections import Counter
from contextlib import closing
from dataclasses import replace
import math

import numpy as np

from benchmarks.calibration.engine.common import verify_file
from benchmarks.calibration.tools.trampoline_tracker_prototype import Candidate, Prototype, covered_by
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.ingestion.video_frames import VideoFrameReader
from trampoline_vision.preparation.foreground import component_evidence, foreground, median_background, sample_indices


class SilhouettePrototype(Prototype):
    """Aplica una penalització suau de YOLO i permet usar la silueta en manteniment."""

    def adjust_maintenance(self, cost, mixed, tracks, candidates, timestamp, strong_boxes, limit):
        """Conserva una assignació feble si és recent i es distingeix de les alternatives."""
        decisions = Counter(maintenance_considered=0, maintenance_ambiguous=0,
                            maintenance_duplicate=0, maintenance_mixed=0, maintenance_stale=0)
        if not tracks or not candidates:
            return decisions
        policy = self.plan['silhouette_experiment']
        use_guard = self.variant.get('maintenance_guard',False)
        silhouette_weight = self.variant.get('silhouette_weight',0.)
        use_yolo = self.variant.get('soft_yolo',False)
        if not (use_guard or silhouette_weight or use_yolo):
            return {}
        strong_score = self.plan['high_score']
        weak = [index for index,box in enumerate(candidates) if box.score<strong_score]
        decisions['maintenance_considered'] = len(weak)
        for col in weak:
            candidate = candidates[col]
            penalty = policy['soft_confidence_weight']*(1-math.sqrt(candidate.score/strong_score)) if use_yolo else 0.
            cost[:,col] += penalty-silhouette_weight*candidate.silhouette
        if not use_guard:
            return decisions
        scored = cost.copy()
        for col in weak:
            compatible = sorted((value,row) for row,value in enumerate(scored[:,col]) if value<limit)
            if not compatible:
                continue
            best_cost,winner = compatible[0]
            candidate = candidates[col]
            next_actor_close = len(compatible)>1 and compatible[1][0]-best_cost<policy['actor_margin']
            alternatives = [value for other,value in enumerate(scored[winner])
                            if other!=col and value<limit and max(
                                covered_by(candidate.box,candidates[other].box),
                                covered_by(candidates[other].box,candidate.box)
                            )<policy['same_actor_candidate_coverage']]
            next_box_close = alternatives and min(alternatives)-best_cost<policy['candidate_margin']
            reason = None
            if mixed[col]:
                reason = 'maintenance_mixed'
            elif any(covered_by(candidate.box,box)>policy['maximum_overlap_with_assigned_strong']
                     for box in strong_boxes):
                reason = 'maintenance_duplicate'
            elif timestamp-tracks[winner].timestamp>policy['max_maintenance_gap_s']:
                reason = 'maintenance_stale'
            elif next_actor_close or next_box_close:
                reason = 'maintenance_ambiguous'
            if reason:
                cost[:,col] = 1e5
                decisions[reason] += 1
            else:
                cost[:winner,col] = 1e5
                cost[winner+1:,col] = 1e5
        return decisions


def add_real_silhouettes(frames, path, case, video_sha, background_indices, emit):
    """Mesura només les caixes congelades sobre píxels, temps i fons del run original."""
    verify_file(path,video_sha)
    video = probe_video(path,case)
    if len(frames)!=video.frame_count or tuple(background_indices)!=sample_indices(video.frame_count):
        raise ValueError('El vídeo o el fons no coincideixen amb la preparació congelada')
    with closing(VideoFrameReader(video)) as reader:
        background,_ = median_background(reader.get(i).to_ndarray(format='bgr24') for i in background_indices)
    enriched = []
    with closing(VideoFrameReader(video)) as reader:
        for index,(timestamp,candidates) in enumerate(frames):
            if abs(video.frame(index).timestamp_s-timestamp)>.0001:
                raise ValueError('La traça i el vídeo tenen temps diferents')
            image = reader.get(index).to_ndarray(format='bgr24')
            labels,sizes = foreground(image,background)
            boxes, evidence = [], []
            for candidate in candidates:
                component,fill,coverage,_ = component_evidence(np.asarray(candidate.box),labels,sizes)
                silhouette = math.sqrt(fill*coverage)
                boxes.append(replace(candidate,silhouette=silhouette))
                evidence.append({'id':candidate.key,'component':component,'fill':fill,'coverage':coverage,
                                 'silhouette':silhouette,'yolo_score':candidate.score})
            emit({'case_id':case,'frame_index':index,'candidates':evidence})
            enriched.append((timestamp,boxes))
    return enriched


def add_simulated_silhouettes(frames, labels, scenario, seed):
    """Simula suport sorollós i primers plans rivals sense donar etiquetes al tracker."""
    rng = np.random.default_rng(18000+seed)
    enriched = []
    for index,((timestamp,candidates),truth) in enumerate(zip(frames,labels,strict=True)):
        boxes = []
        for candidate in candidates:
            role = truth[candidate.key]
            centers = {'gymnast':(.34,.70),'assistant':(.27,.58),'other':(.21,.44),'mixed':(.36,.62)}
            fill,coverage = centers[role]
            if scenario=='foreground_clutter' and role=='gymnast' and candidate.score<.10:
                fill,coverage = .18,.40
            if scenario in ('camera_shift','foreground_clutter') and role in ('other','assistant','mixed'):
                fill += .13
                coverage += .13
            noisy = np.clip(rng.normal([fill,coverage],[.12,.20]),0,1)
            boxes.append(replace(candidate,silhouette=math.sqrt(math.prod(noisy))))
        if scenario=='foreground_clutter' and index%3==0:
            gymnast = next((c for c in candidates if truth[c.key]=='gymnast'),None)
            if gymnast:
                left,top,right,bottom = gymnast.box
                dx,dy = rng.choice([-1,1])*rng.uniform(25,70),rng.uniform(-12,38)
                key = f'{index}:foreground'
                truth[key] = 'other'
                boxes.append(Candidate(key,(left+dx,top+dy,right+dx,bottom+dy),
                                       float(rng.uniform(.0012,.02)),silhouette=float(rng.uniform(.48,.85))))
        enriched.append((timestamp,boxes))
    return enriched
