"""Audita buits del mateix ID i tres contraexemples d'actor visualment coneguts.

Les recuperacions són del registre del tracker. La seva correcció esportiva
només és coneguda als instants anotats; no s'assumeix identitat correcta
durant tots els buits ni s'uneixen IDs diferents.
"""

import argparse
import json
from pathlib import Path
from evaluate_study import read_records


def gaps_for_id(records,track_id):
    """Agrupa estats lost fins a recuperació, finalització o final de vídeo, sense interpolar mostres."""
    gaps=[]; pending=None
    for record in records:
        index=record['context']['frame_index']
        track=next((t for t in record['tracks'] if t['track_id']==track_id),None)
        if track and track['state']=='lost':
            if pending is None: pending={'first_lost_frame':index,'last_lost_frame':index,'missed_frames':0}
            pending['last_lost_frame']=index;pending['missed_frames']+=1
        elif pending is not None:
            recovered=bool(track and track['state']=='active' and track['evidence']=='observed')
            gaps.append({**pending,'end_frame':index,'outcome':'recovered_same_id' if recovered else 'finished_or_absent',
                         'missing_presentation_duration_s':sum(records[i]['context']['duration_s'] for i in range(pending['first_lost_frame'],pending['last_lost_frame']+1))})
            pending=None
    if pending is not None: gaps.append({**pending,'outcome':'unresolved_at_video_end'})
    return gaps


def overlap(a,b):
    """Contrasta només una caixa amb l'àncora visual del jutge, sense decidir associacions del tracker."""
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection/union if union>0 else 0


def main():
    """Escriu un informe nou de recuperacions i evidencia la correcció parcial del cas del jutge."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs',type=Path,required=True)
    parser.add_argument('--analysis',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise ValueError('Recovery audit already exists')
    analysis=json.loads(args.analysis.read_text())
    output={'cases':{},'limitations':['selected_dominant_ids_not_an_automatic_athlete_selector',
                                     'gaps_do_not_prove_actor_identity','judge_examples_are_three_sampled_frames_not_three_switch_events']}
    for cid,result in analysis['cases'].items():
        cases={}
        for name,metrics in result['variants'].items():
            records=read_records(args.runs/cid/f'{name}.frames.jsonl')
            tid=metrics['dominant_id']
            item={'selected_track_id':tid,'gaps':gaps_for_id(records,tid)}
            if '000905' in cid:
                details={d['frame_index']:d for d in metrics['details']}
                examples=[]
                for index in (300,360,390):
                    track=next((t for t in records[index]['tracks'] if t['track_id']==tid),None)
                    judge=False
                    if track and track['bbox']:
                        b=track['bbox']; judge=overlap([b[k] for k in ('x_min','y_min','x_max','y_max')],[270,640,320,695])>=.5
                    examples.append({'frame_index':index,'gymnast_match':tid in details[index]['track_ids'],
                                     'central_judge_box_overlap':judge,'candidate_id':track['candidate_id'] if track else None})
                item['known_actor_examples']=examples
            cases[name]=item
        output['cases'][cid]=cases
    args.output.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({cid:{name:{'same_id_recoveries':sum(g['outcome']=='recovered_same_id' for g in r['gaps']),
                                'known_actor_examples':r.get('known_actor_examples')} for name,r in cases.items()} for cid,cases in output['cases'].items()}))


if __name__=='__main__':
    main()
