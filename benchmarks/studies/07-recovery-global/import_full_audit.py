"""Import explícit del pilot extern: JSONL/NPZ verificats → traça/cache natius.

No és un nou detector ni tracker. No modifica cap decisió original. El cache
NPZ és específic del pilot 20261025 i no s'accepta a la CLI de producció.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from trampoline_vision.contracts.appearance import CandidateEmbedding,FrameAppearance
from trampoline_vision.infrastructure.embedding_cache import EmbeddingCache
from trampoline_vision.ingestion.recovery import _frame,sha256_file,load_tracking_trace
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.recovery.pipeline import prepare_recovery


def write(path,value):
    """Publica fitxers nous de l'import sense sobreescriure dades anteriors."""
    with path.open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-root',type=Path,required=True,help='Original detector-confidence-full-20261025 folder.')
    parser.add_argument('--video',type=Path,required=True)
    parser.add_argument('--variant',choices=['conf002_all','conf005_all','conf005_cap20'],default='conf002_all')
    parser.add_argument('--output',type=Path,required=True,help='New import directory.')
    parser.add_argument('--ffprobe',default='ffprobe')
    args=parser.parse_args()
    source=args.audit_root.resolve()
    output=args.output.resolve()
    if output.is_relative_to(source) or output.exists():
        raise ValueError('Choose a new import directory outside original audit')
    manifest=json.loads((source/'artifact-sha256.json').read_text())
    names=['full-video-results.json','detections.jsonl','embeddings.npz',args.variant+'.frames.jsonl','track_full.py']
    for name in names:
        if sha256_file(source/name)!=manifest[name]:
            raise ValueError(f'Frozen pilot content differs: {name}')
    original=json.loads((source/'full-video-results.json').read_text())
    video=probe_video(args.video,original['case_id'],ffprobe=args.ffprobe)
    if sha256_file(args.video)!=original['video_sha256'] or video.frame_count!=930:
        raise ValueError('Video differs from frozen full audit')
    appearance=original['appearance']
    model_identity={k:appearance[k] for k in ('provider','weights_sha256','preprocessing','dimensions','device','threads','versions')}
    fingerprint=hashlib.sha256(json.dumps(model_identity,sort_keys=True).encode()).hexdigest()
    if fingerprint!=appearance['fingerprint']:
        raise ValueError('Pilot model fingerprint differs')
    raw=[json.loads(line) for line in (source/'detections.jsonl').open()]
    records=[json.loads(line) for line in (source/(args.variant+'.frames.jsonl')).open()]
    with np.load(source/'embeddings.npz',allow_pickle=False) as archive:
        features,offsets=archive['features'],archive['offsets']
    if len(raw)!=930 or len(records)!=930 or features.shape!=(59580,512) or len(offsets)!=931:
        raise ValueError('Pilot coverage or descriptor shape differs')
    if offsets[0]!=0 or not np.array_equal(np.diff(offsets),[len(row['boxes']) for row in raw]):
        raise ValueError('Pilot offsets differ from detection order')
    if not np.isfinite(features).all() or not np.allclose(np.linalg.norm(features,axis=1),1,atol=2e-5):
        raise ValueError('Invalid pilot descriptors')
    run_id=records[0]['run_id']
    frames=[]
    for ix,record in enumerate(records):
        if record.pop('source_frame_index')!=ix or raw[ix]['source_frame_index']!=ix:
            raise ValueError('Pilot source frame index differs')
        frame=_frame(record,video,run_id,ix)
        expected=[rank for rank,b in enumerate(raw[ix]['boxes']) if b['score']>=(.02 if args.variant=='conf002_all' else .05)]
        if args.variant=='conf005_cap20':expected=expected[:20]
        if [int(c.candidate.candidate_id.rsplit(':',1)[1]) for c in frame.candidates]!=expected:
            raise ValueError('Pilot candidate filtering differs')
        for c in frame.candidates:
            rank=int(c.candidate.candidate_id.rsplit(':',1)[1])
            row=raw[ix]['boxes'][rank]
            b=c.candidate.measurement.bbox
            if c.candidate.candidate_id!=f'{ix}:yolo_candidate:{rank}' or [b.x_min,b.y_min,b.x_max,b.y_max]!=row['bbox'] or c.candidate.measurement.score!=row['score']:
                raise ValueError('Pilot candidate/descriptor mapping differs')
        frames.append(frame)
    # Inputs have been verified before creating the exclusive import directory.
    output.mkdir(parents=True,exist_ok=False)
    detections=output/'imported-boxes.csv'
    with detections.open('x',encoding='utf-8',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['frame','det_id','x1','y1','x2','y2','conf','class_id'])
        for frame in frames:
            for c in frame.candidates:
                ix=frame.context.frame_index
                rank=int(c.candidate.candidate_id.rsplit(':',1)[1])
                row=raw[ix]['boxes'][rank]
                writer.writerow([ix,rank,*row['bbox'],row['score'],0])
    tracks=output/'tracking.frames.jsonl'
    with tracks.open('x',encoding='utf-8') as f:
        for row in records:f.write(json.dumps(row,allow_nan=False)+'\n')
    identity={'video_id':video.video_id,'video_sha256':original['video_sha256'],
        'detections_sha256':sha256_file(detections),'source_format':'person_boxes_csv','frame_coverage':'complete_video',
        'frame_index_base':0,'preparation':None,'model_fingerprint':fingerprint,
        'timeline_sha256':hashlib.sha256(json.dumps([video.timestamps_s,video.frame_durations_s]).encode()).hexdigest()}
    cache=EmbeddingCache(output/'cache',identity,fingerprint)
    try:
        for frame in frames:
            ix=frame.context.frame_index
            prepared=SimpleNamespace(source=SimpleNamespace(context=frame.context,source_status=frame.source_status),
                candidates=tuple(c.candidate for c in frame.candidates))
            embeddings=tuple(CandidateEmbedding(c.candidate_id,tuple(float(x) for x in features[int(offsets[ix])+int(c.candidate_id.rsplit(':',1)[1])]))
                for c in prepared.candidates)
            cache.put(prepared,FrameAppearance(frame.context,fingerprint,embeddings))
        cache_path=cache.path
    finally:
        cache.close()
    report={'schema_version':'1.0','task':'track_recorded_detections','producer':'verified_import_of_frozen_experimental_tracking',
        'software_version':'0.6.0-external-pilot','run_id':run_id,'case_id':video.video_id,
        'inputs':{'video':{'path':str(args.video.resolve()),'sha256':original['video_sha256']},
                  'detections':{'path':str(detections),'sha256':sha256_file(detections)}},
        'range':{'first_frame_index':0,'last_frame_index':929,'warmup_frames':0,'tracker_started_at_frame':0,
                 'source_start_s':0.,'source_end_s':video.duration_s},'totals':{'frames':930},
        'right_censored_track_ids':sorted(t.track_id for t in frames[-1].tracks if t.state!='finished'),
        'appearance':appearance,'effective_config':next(v for v in original['variants'] if v['variant']==args.variant),
        'artifacts':{'frames_jsonl':str(tracks),'frames_sha256':sha256_file(tracks)},
        'import_provenance':{'original_root':str(source),'variant':args.variant,'source_files_sha256':{name:manifest[name] for name in names},
            'transformation':'Only redundant source_frame_index removed after checking; track samples/events/candidates/contexts unchanged. Selected source boxes exported to CSV for native cache identity.',
            'appearance_cache':str(cache_path),'appearance_inference':False,'tracking_reexecuted':False}}
    report_path=output/'tracking.json'
    write(report_path,report)
    loaded=load_tracking_trace(tracks,report_path,video)
    fragments=prepare_recovery(loaded.trace)
    expected=next(v for v in original['variants'] if v['variant']==args.variant)
    if len(fragments.fragments)!=expected['fragments']:
        raise ValueError('Imported fragment partition differs')
    write(output/'import-verification.json',{'status':'passed','tracking_frames':930,'fragments':len(fragments.fragments),
        'source_decisions_changed':False,'descriptor_mapping_verified':True,'cache_path':str(cache_path),
        'cache_sha256':sha256_file(cache_path),'tracking_sha256':sha256_file(tracks),
        'appearance_inference':False,'importer_sha256':sha256_file(Path(__file__))})
    print(json.dumps({'tracking_report':str(report_path),'appearance_cache':str(cache_path),'frames':930,'fragments':len(fragments.fragments)}))


if __name__=='__main__':main()
