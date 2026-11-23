"""Prototip d'associació per al banc, amb predicció i observació separades."""

from collections import deque
from dataclasses import dataclass
import math

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass(frozen=True)
class Candidate:
    """Caixa local amb score i descriptor opcional, sense etiqueta d'actor."""

    key: str
    box: tuple[float, float, float, float]
    score: float
    appearance: np.ndarray | None = None
    silhouette: float = 0.


def box_center(box):
    """Converteix una caixa en un centre i dues dimensions en píxels."""
    left, top, right, bottom = box
    return np.array([(left+right)/2, (top+bottom)/2]), np.array([right-left, bottom-top])


class Track:
    """Estat temporal d'una persona hipotètica, amb memòria de mesures fiables."""

    def __init__(self, identity, candidate, timestamp):
        """Inicialitza una hipòtesi que encara ha de confirmar-se."""
        self.identity = identity
        self.center, self.size = box_center(candidate.box)
        self.timestamp = timestamp
        self.streak = 1
        self.confirmed = False
        self.appearance = candidate.appearance
        self.history = deque([(timestamp, self.center.copy())], maxlen=5)
        self.state = np.r_[self.center, 0., 0.]
        self.cov = np.diag([25., 25., 65000., 65000.])

    def kalman(self, timestamp):
        """Extrapola centre i velocitat amb soroll d'acceleració i temps real."""
        dt = timestamp-self.timestamp
        transition = np.eye(4)
        transition[:2,2:] = np.eye(2)*dt
        forcing = np.r_[np.eye(2)*dt**2/2, np.eye(2)*dt]
        return transition@self.state, transition@self.cov@transition.T + 1300**2*forcing@forcing.T

    def predict(self, timestamp, motion):
        """Estima el centre sense extrapolar els canvis de forma de la caixa."""
        dt = timestamp-self.timestamp
        if motion == 'last':
            return self.center, 0.
        if motion == 'kalman':
            position, covariance = self.kalman(timestamp)
            return position[:2], min(42., math.sqrt(covariance[1,1]))
        if len(self.history) < 2:
            return self.center, 10.
        (then, previous), (last, recent) = self.history[-2], self.history[-1]
        elapsed = last-then
        velocity = (recent-previous)/elapsed
        if len(self.history) >= 3:
            older, anchor = self.history[0]
            average = (recent-anchor)/(last-older)
            velocity = .65*velocity + .35*average
        vx, vy = np.clip(velocity, -1600, 1600)
        # En coordenades d'imatge la gravetat empeny cap avall. La caixa només
        # n'és un proxy. Si l'actor sembla quiet, usem acceleració zero.
        airborne = abs(vy) > 135 and abs(vy) > abs(vx)*.65
        acceleration = 725. if airborne and motion == 'flight' else 0.
        spread = 13. if airborne else 8.
        if motion == 'flight' and len(self.history) >= 3:
            prior_time, prior = self.history[-3]
            prior_vy = (previous[1]-prior[1])/(then-prior_time)
            if prior_vy*vy < 0 and abs(prior_vy-vy) > 320:
                spread += 17.
        # El model de vol serveix a curt termini. La cerca creix amb el buit.
        extrapolation = min(dt,.16)
        return self.center + np.array([vx*extrapolation, vy*extrapolation+acceleration*extrapolation**2/2]), spread

    def update(self, candidate, timestamp, reliable, update_appearance, motion):
        """Actualitza la caixa observada i protegeix la història de mesures febles."""
        center, size = box_center(candidate.box)
        if motion == 'kalman':
            state, covariance = self.kalman(timestamp)
            noise = 8. if reliable else 30.
            gain = np.linalg.solve(covariance[:2,:2]+np.eye(2)*noise**2, covariance[:2,:]).T
            self.state = state + gain@(center-state[:2])
            self.cov = covariance-gain@covariance[:2,:]
        if reliable:
            self.history.append((timestamp,center))
            self.size = self.size*.75 + size*.25
        self.center = center if reliable else self.center*.55 + center*.45
        self.timestamp = timestamp
        if update_appearance and candidate.appearance is not None:
            vector = candidate.appearance
            if self.appearance is not None:
                vector = self.appearance*.8 + vector*.2
            self.appearance = vector / np.linalg.norm(vector)


def assignment(cost, limit):
    """Dona a cada track una alternativa pròpia de quedar sense assignació."""
    if not cost.shape[0] or not cost.shape[1]:
        return []
    extended = np.full((cost.shape[0],cost.shape[0]+cost.shape[1]),1e5)
    extended[:,:cost.shape[1]] = cost
    np.fill_diagonal(extended[:,cost.shape[1]:],limit)
    rows, cols = linear_sum_assignment(extended)
    return [(int(row),int(col)) for row,col in zip(rows,cols) if col<cost.shape[1] and cost[row,col]<limit]


def covered_by(box, other):
    """Retorna la fracció de la candidata ja coberta per una observació forta."""
    left,top,right,bottom = box
    x0,y0,x1,y1 = other
    shared = max(0,min(right,x1)-max(left,x0))*max(0,min(bottom,y1)-max(top,y0))
    return shared/((right-left)*(bottom-top))


class Prototype:
    """Fa dues passades d'associació i exporta només IDs confirmats."""

    def __init__(self, plan, variant):
        """Fixa paràmetres i inicia cada clip amb estat buit."""
        self.variant = variant
        self.plan = plan
        self.tracks = []
        self.next_id = 0

    def costs(self, tracks, candidates, timestamp, secondary):
        """Combina distància, cobertura, mida i aparença per als parells plausibles."""
        if not tracks or not candidates:
            shape = (len(tracks),len(candidates))
            return np.empty(shape), np.zeros(len(candidates),dtype=bool)
        parts = [box_center(c.box) for c in candidates]
        centers, sizes = map(np.array,zip(*parts))
        lower, upper = centers-sizes/2, centers+sizes/2
        area = sizes.prod(axis=1)
        output = []
        confirmed_centers = []
        for track in tracks:
            prediction, uncertainty = track.predict(timestamp,self.variant['motion'])
            if track.confirmed:
                confirmed_centers.append(prediction)
            dt = timestamp-track.timestamp
            margin = np.clip(track.size/2,18,100) + uncertainty + (90 if secondary else 45)*dt
            if secondary:
                margin *= 1.45
            distance = np.linalg.norm((centers-prediction)/margin,axis=1)
            size_ratio = np.sqrt(area/track.size.prod())
            overlap = np.maximum(0,np.minimum(upper,prediction+track.size/2)-np.maximum(lower,prediction-track.size/2)).prod(axis=1)
            iou = overlap/(area+track.size.prod()-overlap)
            cost = .51*distance + .33*(1-iou) + .12*np.minimum(2,np.abs(np.log(size_ratio)))
            cost += .055*dt/.5
            cost[(distance>1.35) | (size_ratio>3.1) | (size_ratio<.20)] = 1e5
            output.append(cost)
        mixed = np.zeros(len(candidates),dtype=bool)
        if len(confirmed_centers)>1:
            locations = np.array(confirmed_centers)
            contains = ((locations[None,:,:]>=lower[:,None,:]) & (locations[None,:,:]<=upper[:,None,:])).all(axis=2)
            mixed = contains.sum(axis=1)>=2
        matrix = np.array(output)
        if self.variant.get('appearance'):
            for row,track in enumerate(tracks):
                if track.appearance is None:
                    continue
                usable = [col for col,c in enumerate(candidates)
                          if not mixed[col] and c.appearance is not None and matrix[row,col]<1]
                if len(usable)<2:
                    continue
                similarity = np.array([float(track.appearance@candidates[col].appearance) for col in usable])
                if np.ptp(similarity) >= .08:
                    matrix[row,usable] += .20*(1-similarity)
        return matrix,mixed

    def future_cost(self, track, candidate, timestamp, future):
        """Avalua una hipòtesi curta amb mesures futures, sense publicar ni reescriure IDs."""
        center, size = box_center(candidate.box)
        displacement = center-track.center
        velocity = np.clip(displacement/(timestamp-track.timestamp),-1100,1100)
        error = 0.
        for future_time,others in future:
            expected = center+velocity*(future_time-timestamp)
            distances = [np.linalg.norm((box_center(other.box)[0]-expected)/np.maximum(size,28))
                         for other in others if other.score>=self.plan['high_score']]
            error += min(min(distances,default=1.),1.)
        return error/len(future)

    def adjust_maintenance(self, cost, mixed, tracks, candidates, timestamp, strong_boxes, limit):
        """Permet provar una política de manteniment sobre la mateixa matriu de costos."""
        return {}

    def step(self, timestamp, candidates, future=()):
        """Publica assignacions i prediccions vives, amb comptadors de decisions ambigües."""
        high = self.plan['high_score']
        self.tracks = [t for t in self.tracks if timestamp-t.timestamp<=self.plan['max_lost_s']
                       and (t.confirmed or t.streak>0)]
        remaining = set(range(len(candidates)))
        unmatched = set(range(len(self.tracks)))
        observed, blocked, strong_boxes = {}, set(), []
        decisions = {'ambiguous_rejected':0,'mixed_rejected':0,'lookahead_resolved':0,
                     'very_weak_observed':0,'very_weak_rejected':0}
        for secondary in (False,True):
            track_indices = [i for i in sorted(unmatched) if not secondary or self.tracks[i].confirmed]
            floor = self.variant.get('weak_score',.02) if secondary else high
            candidate_indices = [i for i in sorted(remaining-blocked) if candidates[i].score>=floor]
            tracks = [self.tracks[i] for i in track_indices]
            boxes = [candidates[i] for i in candidate_indices]
            cost,mixed = self.costs(tracks,boxes,timestamp,secondary)
            original_cost = cost.copy()
            limit = .86 if secondary else .76
            if secondary:
                decisions.update(self.adjust_maintenance(cost,mixed,tracks,boxes,timestamp,strong_boxes,limit))
            if secondary and self.variant.get('weak_guard'):
                # Les caixes molt febles només poden sostenir una hipòtesi recent i
                # distingible. El filtre deixa intacta la passada de .02 o més.
                for col,candidate in enumerate(boxes):
                    if candidate.score>=.02:
                        continue
                    eligible = sorted((cost[row,col],row) for row,track in enumerate(tracks)
                                      if timestamp-track.timestamp<=.16 and cost[row,col]<.67)
                    duplicate = any(covered_by(candidate.box,other)>.72 for other in strong_boxes)
                    winner = eligible[0][1] if eligible else None
                    contender_close = len(eligible)>1 and eligible[1][0]-eligible[0][0]<.115
                    for row in range(len(tracks)):
                        if row!=winner or duplicate or mixed[col] or contender_close:
                            cost[row,col] = 1e5
                    decisions['very_weak_rejected'] += int(bool(eligible) and np.all(cost[:,col]>=limit))
            guard = self.variant.get('guard',False)
            if guard and mixed.any():
                decisions['mixed_rejected'] += int(mixed.sum())
                blocked.update(candidate_indices[i] for i in np.flatnonzero(mixed))
                cost[:,mixed] = 1e5
            margins = .14 if secondary else .075
            if future and cost.size:
                # Només desempatem opcions pròximes. La cerca futura no crea caixes.
                for row,track in enumerate(tracks):
                    possible = np.flatnonzero(cost[row]<limit)
                    ordered = sorted(possible,key=lambda col:cost[row,col])
                    if track.confirmed and len(ordered)>1 and cost[row,ordered[1]]-cost[row,ordered[0]]<margins:
                        for col in ordered[:2]:
                            cost[row,col] += .32*self.future_cost(track,boxes[col],timestamp,future)
            accepted = []
            for row,col in assignment(cost,limit):
                track, candidate = tracks[row], boxes[col]
                if guard:
                    alternatives = np.delete(cost[row],col)
                    competitors = [cost[i,col] for i,other in enumerate(tracks) if i!=row and other.confirmed]
                    margin = min(min(alternatives,default=1e5),min(competitors,default=1e5))-cost[row,col]
                    if (track.confirmed or secondary) and margin<margins:
                        decisions['ambiguous_rejected'] += 1
                        blocked.add(candidate_indices[col])
                        continue
                if future and cost[row,col]!=original_cost[row,col]:
                    decisions['lookahead_resolved'] += 1
                accepted.append((row,col))
            for row,col in accepted:
                track, candidate = tracks[row], boxes[col]
                reliable = candidate.score>=high and not mixed[col]
                track.streak = track.streak+1 if reliable else 0
                track.confirmed |= track.streak>=self.plan['confirmation_frames']
                track.update(candidate,timestamp,reliable,reliable,self.variant['motion'])
                if reliable:
                    strong_boxes.append(candidate.box)
                if track.confirmed:
                    observed[candidate.key] = track.identity
                    decisions['very_weak_observed'] += int(candidate.score<.02)
                unmatched.remove(track_indices[row])
                remaining.remove(candidate_indices[col])
        predicted = [self.tracks[i].identity for i in sorted(unmatched) if self.tracks[i].confirmed]
        for i in unmatched:
            self.tracks[i].streak = 0
        for index in sorted(remaining-blocked):
            candidate = candidates[index]
            if candidate.score>=high:
                self.tracks.append(Track(self.next_id,candidate,timestamp))
                self.next_id += 1
        return observed,predicted,decisions
