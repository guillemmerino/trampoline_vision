"""Propostes globals experimentals amb opció de no unir; mai s'apliquen al tracking."""

from collections import Counter
from trampoline_vision.contracts.recovery import FragmentLink
from trampoline_vision.recovery.appearance import appearance_cost
from trampoline_vision.recovery.hungarian import linear_assignment
from trampoline_vision.recovery.motion import motion_cost


def associate(features,config):
    """Optimitza totes les parelles admissibles alhora, exportant alternatives locals."""
    n=len(features)
    p=config.parameters
    forbidden=float(n+1)
    matrix=[[forbidden]*n+[p.no_link_cost]*n for _ in range(n)]
    edges={}
    rejected=Counter()
    for i,a in enumerate(features):
        for j,b in enumerate(features):
            costs,reason=motion_cost(a,b,p)
            if reason:
                rejected[reason]+=1
                continue
            costs['appearance']=0.
            if config.strategy=='geometry_appearance':
                costs['appearance'],costs['cosine_distance']=appearance_cost(a,b,p.appearance_distance_scale)
            total=sum(getattr(p,k+'_weight')*costs[k] for k in ('appearance','geometry','scale','time'))
            costs['total']=total
            edges[i,j]=costs
            if total<p.no_link_cost:
                matrix[i][j]=total
    columns=linear_assignment(matrix)
    selected={(i,j) for i,j in enumerate(columns) if j<n}
    proposals=[]
    alternatives=[]
    for i,a in enumerate(features):
        ranked=sorted(((cost['total'],j) for (row,j),cost in edges.items() if row==i),key=lambda x:(x[0],x[1]))
        choices=[{'target_fragment_id':features[j].fragment_id,'cost':value} for value,j in ranked[:3]]
        ambiguous=len(ranked)>1 and ranked[1][0]-ranked[0][0]<=p.ambiguity_margin
        alternatives.append({'source_fragment_id':a.fragment_id,'alternatives':choices,'no_link_cost':p.no_link_cost,
            'locally_ambiguous':ambiguous,'meaning':'local_costs_not_global_confidence'})
    for (i,j),cost in sorted(edges.items()):
        chosen=(i,j) in selected
        reason='selected_by_optimizer_identity_unverified' if chosen else ('not_better_than_abstention' if cost['total']>=p.no_link_cost else 'not_selected_by_global_assignment')
        proposals.append(FragmentLink(features[i].fragment_id,features[j].fragment_id,
            'proposed' if chosen else 'rejected',tuple(sorted(cost.items())),(reason,)))
    return tuple(proposals),tuple((features[i].fragment_id,features[j].fragment_id) for i,j in sorted(selected)),{
        'objective':sum(matrix[i][j] for i,j in enumerate(columns)),
        'gated_pairs':dict(rejected),'alternatives':alternatives,'solver':'rectangular_primal_dual_hungarian_v1',
        'scope':'single_full_video_matrix','no_link_cost':p.no_link_cost}
