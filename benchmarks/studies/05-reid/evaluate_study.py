"""Avalua identitat amb referències visuals fixades sense veure els trackers.

Les mètriques descriuen instants revisats. No es confonen els canvis mínims
entre matches dispersos amb els canvis reals de tot el vídeo.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import numpy as np


def read_records(path):
    """Exigeix una exportació completa i ordenada, amb un sol registre per fotograma."""
    result=[]
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            record=json.loads(line)
            if record['context']['frame_index']!=len(result): raise ValueError('Non-consecutive replay')
            result.append(record)
    return result


def evaluate(records,samples):
    """Compta matches exactes de candidat; admet duplicats de la mateixa persona i separa ambigüitat."""
    details=[]; identities=Counter(); minimum_changes={}; matched=missing=ambiguous=no_candidate=duplicates=0
    for sample in samples:
        index=sample['frame_index']; record=records[index]
        candidate_ids={f'{index}:yolo_candidate:{det}' for det in sample['acceptable_det_ids']}
        if not candidate_ids<=set(c['candidate_id'] for c in record['candidates']): raise ValueError('Unknown annotated detection')
        matches=sorted(t['track_id'] for t in record['tracks'] if t['evidence']=='observed' and t['candidate_id'] in candidate_ids)
        eligible=sample['quality']!='ambiguous_overlap'
        if not eligible: ambiguous+=1
        else:
            no_candidate+=not candidate_ids
            if matches:
                matched+=1; identities.update(set(matches)); duplicates+=len(matches)>1
                if minimum_changes:
                    minimum_changes={tid:min(cost+(tid!=old) for old,cost in minimum_changes.items()) for tid in matches}
                else: minimum_changes={tid:0 for tid in matches}
            else: missing+=1
        details.append({**sample,'track_ids':matches,'eligible':eligible})
    dominant=identities.most_common(1)
    return {'reviewed_samples':len(samples),'ambiguous_excluded':ambiguous,'eligible_samples':len(samples)-ambiguous,
            'samples_without_detector_candidate':no_candidate,'observed_matches':matched,'missing_observed_samples':missing,
            'distinct_ids':len(identities),'track_ids':sorted(identities),'duplicate_observed_ids_samples':duplicates,
            'minimum_id_changes_between_reviewed_matches':min(minimum_changes.values()) if minimum_changes else None,
            'dominant_id':dominant[0][0] if dominant else None,'dominant_id_matching_samples':dominant[0][1] if dominant else 0,
            'details':details}


def descriptor_diagnostic(cache,records,samples):
    """Mesura recuperació visual top-1 entre candidats de dos instants revisats, sense usar cap track."""
    with np.load(cache) as stored:
        features,offsets=stored['features'],stored['offsets']
    previous=None; pairs=[]
    for sample in samples:
        if sample['quality']!='clear_identity' or not sample['acceptable_det_ids']: continue
        index=sample['frame_index']; candidates=records[index]['candidates']
        # L'ordre del cache segueix det_id creixent, igual que el CSV validat i el replay.
        positions={int(c['candidate_id'].rsplit(':',1)[1]):j for j,c in enumerate(candidates)}
        accepted=[positions[d] for d in sample['acceptable_det_ids']]
        now=features[offsets[index]:offsets[index+1]]
        if previous is not None:
            distances=1-now@previous['feature']
            nearest=int(np.argmin(distances))
            pairs.append({'previous_frame':previous['frame'],'frame_index':index,'top1_correct':nearest in accepted,
                          'top1_det_id':int(candidates[nearest]['candidate_id'].rsplit(':',1)[1]),
                          'best_true_cosine_distance':float(min(distances[j] for j in accepted)),
                          'nearest_cosine_distance':float(distances[nearest])})
        best=max(accepted,key=lambda j:candidates[j]['measurement']['score'])
        previous={'frame':index,'feature':now[best]}
    return {'pairs':len(pairs),'top1_correct':sum(p['top1_correct'] for p in pairs),'details':pairs,
            'interpretation':'descriptor_only_retrieval_diagnostic_not_tracking_accuracy'}


def main():
    """Guarda comparació dels tres casos i comprova que OC-SORT reprodueix exactament l'estudi 04."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs',type=Path,required=True)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--previous',type=Path,help='Baseline anterior opcional per comprovar igualtat exacta')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise ValueError('Analysis already exists')
    reference=json.loads(args.reference.read_text(encoding='utf-8'))
    summary=json.loads((args.runs/'summary.json').read_text())
    bindings_path=args.reference.parent/'reference-inputs.json'
    bindings=json.loads(bindings_path.read_text(encoding='utf-8'))
    for cid,expected in bindings['cases'].items():
        if cid not in summary['cases']: raise ValueError('Annotated case missing from replay')
        for key in ('video_sha256','csv_sha256'):
            if summary['cases'][cid][key]!=expected[key]: raise ValueError('Annotated inputs differ from replay')
    output={'reference_sha256':hashlib.sha256(args.reference.read_bytes()).hexdigest(),'cases':{},
            'reference_inputs_sha256':hashlib.sha256(bindings_path.read_bytes()).hexdigest(),
            'limitations':reference['limitations']+['minimum_id_changes_is_a_sparse_lower_bound','duplicate_tracks_are_not_temporal_switches']}
    for cid in summary['cases']:
        samples=[s for s in reference['samples'] if s['case_id']==cid]
        variants={}
        for name in ['ocsort','botsort_motion','botsort_reid']:
            records=read_records(args.runs/cid/f'{name}.frames.jsonl')
            if len(records)!=summary['cases'][cid]['frames']: raise ValueError('Incomplete replay')
            variants[name]=evaluate(records,samples)
            if name=='ocsort':
                descriptors=descriptor_diagnostic(args.runs/cid/'embeddings.npz',records,samples)
                if '000905' in cid and args.previous:
                    old=read_records(args.previous)
                    strip=lambda r:{k:v for k,v in r.items() if k not in ('run_id','experiment','reid')}
                    if [strip(r) for r in old]!=[strip(r) for r in records]: raise ValueError('OC-SORT differs from study 04')
                    output['previous_ocsort_replay_exact']=True
        output['cases'][cid]={'variants':variants,'descriptor_diagnostic':descriptors}
        print(cid,json.dumps({n:{k:v for k,v in r.items() if k not in ('details','track_ids')} for n,r in variants.items()}),flush=True)
    args.output.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    main()
