"""Tracking complet i cache existent → propostes experimentals, sense apply ni inferència."""

from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import platform
import tempfile
import time
from types import SimpleNamespace
from uuid import uuid4

from trampoline_vision import __version__
from trampoline_vision.infrastructure.artifacts import publish_exclusive
from trampoline_vision.infrastructure.embedding_cache import ReadOnlyEmbeddingCache
from trampoline_vision.ingestion.json_io import parse_json
from trampoline_vision.ingestion.recovery import read_tracking_report,report_path,load_tracking_trace,sha256_file
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.recovery.config import RecoveryAuditConfig
from trampoline_vision.recovery.errors import RecoveryError
from trampoline_vision.recovery.pipeline import audit_recovery
from trampoline_vision.tracking.errors import TrackingError


def code_identity():
    """Identifica els bytes Python efectius, també en una wheel sense checkout Git."""
    root=Path(__file__).resolve().parents[1]
    files={str(p.relative_to(root)).replace('\\','/'):sha256_file(p) for p in sorted(root.rglob('*.py'))}
    return {'software_version':__version__,'python':platform.python_version(),
            'source_tree_sha256':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),
            'source_files_sha256':files}


def _appearance_identity(report):
    """Comprova el fingerprint registrat, sense importar models ni instal·lar-ne versions."""
    try:
        appearance=report['appearance']
        identity={key:appearance[key] for key in ('provider','weights_sha256','preprocessing','dimensions','device','threads','versions')}
        fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        if appearance['fingerprint']!=fingerprint:
            raise ValueError('Recorded appearance fingerprint differs')
        return identity,fingerprint
    except (KeyError,TypeError,ValueError) as exc:
        raise RecoveryError(f'Tracking report lacks verified appearance identity: {exc}') from exc


def audit_tracking_recovery(report_file,output,*,config_file,tracks_path=None,video_path=None,
                            appearance_cache=None,detections_path=None,links_output=None,
                            ffprobe='ffprobe',probe_timeout_s=120):
    """Publica JSON/JSONL nous després de validar inputs, model, cadenes i partició.

    El cache SQLite natiu es llegeix en mode immutable. Un cache absent/parcial
    és un error explícit: no s'executen models per completar-lo. Els NPZ antics
    necessiten un importador de benchmark verificat; no s'accepten com a SQLite.
    """
    started=time.perf_counter()
    report_file,output,config_file=Path(report_file).resolve(),Path(output).resolve(),Path(config_file).resolve()
    config_bytes=config_file.read_bytes()
    try:
        raw_config=parse_json(config_bytes.decode('utf-8-sig'),str(config_file))
        config=RecoveryAuditConfig.from_dict(raw_config)
    except (UnicodeError,TypeError,ValueError) as exc:
        raise RecoveryError(f'Invalid recovery audit profile: {exc}') from exc
    report_data=read_tracking_report(report_file)
    report,_=report_data
    try:
        tracks_path=Path(tracks_path).resolve() if tracks_path else report_path(report_file,report['artifacts']['frames_jsonl'])
        video_path=Path(video_path).resolve() if video_path else report_path(report_file,report['inputs']['video']['path'])
    except (KeyError,TypeError,ValueError) as exc:
        raise RecoveryError(f'Tracking report lacks paths: {exc}') from exc
    links_output=Path(links_output).resolve() if links_output else output.with_suffix('.links.jsonl')
    needs_appearance=config.strategy=='geometry_appearance'
    if needs_appearance and appearance_cache is None:
        raise RecoveryError('Appearance profile requires --appearance-cache (existing native SQLite)')
    if not needs_appearance and (appearance_cache is not None or detections_path is not None):
        raise RecoveryError('Appearance inputs require geometry_appearance strategy')
    cache_path=Path(appearance_cache).resolve() if appearance_cache else None
    if needs_appearance:
        try:
            detections_path=Path(detections_path).resolve() if detections_path else report_path(report_file,report['inputs']['detections']['path'])
        except (KeyError,TypeError,ValueError) as exc:
            raise RecoveryError('Appearance requires source detections path or --detections override') from exc
    destinations=[links_output,output]
    protected={report_file,tracks_path,video_path,config_file}
    for value in (cache_path,detections_path):
        if value is not None:
            protected.add(value)
    for entry in report.get('inputs',{}).values():
        if isinstance(entry,dict) and isinstance(entry.get('path'),str):
            protected.add(report_path(report_file,entry['path']))
    if len(set(destinations))!=len(destinations):
        raise RecoveryError('Choose distinct audit report and link export paths')
    for destination in destinations:
        if destination.exists() or destination in protected:
            raise RecoveryError(f'Refusing to overwrite audit input or existing output: {destination}')
    video=probe_video(video_path,report['case_id'],ffprobe=ffprobe,timeout_s=probe_timeout_s)
    loaded=load_tracking_trace(tracks_path,report_file,video,report_data=report_data)
    video_sha=sha256_file(video_path)
    declared=report.get('inputs',{}).get('video',{}).get('sha256')
    if declared is not None and declared!=video_sha:
        raise RecoveryError('Source video content hash differs from tracking report')
    inputs={'tracking_report':{'path':str(report_file),'sha256':loaded.report_sha256},
            'tracks':{'path':str(tracks_path),'sha256':loaded.frames_sha256},
            'video':{'path':str(video_path),'sha256':video_sha}}
    cache=None
    try:
        appearances=None
        if needs_appearance:
            identity,fingerprint=_appearance_identity(report)
            detection_sha=sha256_file(detections_path)
            recorded=report.get('inputs',{}).get('detections',{}).get('sha256')
            if recorded is not None and recorded!=detection_sha:
                raise RecoveryError('Source detections content hash differs from tracking report')
            cache_sha=sha256_file(cache_path)
            timeline_sha=hashlib.sha256(json.dumps([video.timestamps_s,video.frame_durations_s]).encode()).hexdigest()
            cache=ReadOnlyEmbeddingCache(cache_path,{'video_id':video.video_id,'video_sha256':video_sha,
                'detections_sha256':detection_sha,'timeline_sha256':timeline_sha,'source_format':'person_boxes_csv'},fingerprint)
            def cached_frames():
                """Adapta contractes de traça a signatures natives, sense inventar deteccions/poses."""
                for frame in loaded.trace.frames:
                    prepared_frame=SimpleNamespace(source=SimpleNamespace(context=frame.context,source_status=frame.source_status),
                        candidates=tuple(c.candidate for c in frame.candidates))
                    value=cache.get(prepared_frame)
                    if value is None:
                        raise RecoveryError(f'Existing appearance cache missing frame {frame.context.frame_index}')
                    if any(len(e.values)!=identity['dimensions'] for e in value.embeddings):
                        raise RecoveryError('Cache dimensions differ from recorded model')
                    yield value
            appearances=cached_frames()
            inputs['detections']={'path':str(detections_path),'sha256':detection_sha}
            inputs['appearance_cache']={'path':str(cache_path),'sha256':cache_sha,'model_fingerprint':fingerprint,'model_identity':identity}
        prepared,proposals,chains,details=audit_recovery(loaded.trace,config,appearances)
    except TrackingError as exc:
        raise RecoveryError(str(exc)) from exc
    finally:
        if cache is not None:
            cache.close()
    if cache_path and sha256_file(cache_path)!=inputs['appearance_cache']['sha256']:
        raise RecoveryError('Appearance cache changed during audit')
    run_id=str(uuid4())
    by_id={f.fragment_id:f for f in prepared.fragments}
    selected=[p for p in proposals if p.status=='proposed']
    hypotheses=[{'hypothesis_id':f'hypothesis:{run_id}:{i+1}','status':'provisional_identity_unverified',
        'fragment_ids':chain,'observed_samples':sum(len(by_id[fid].samples) for fid in chain)} for i,chain in enumerate(chains)]
    summary={'schema_version':'1.0','task':'audit_tracking_recovery','status':'experimental',
        'run_id':run_id,'created_at':datetime.now(timezone.utc).isoformat(),'software_version':__version__,
        'tracking_run_id':loaded.trace.run_id,'video_id':video.video_id,'mode':'audit','applied':False,
        'profile':{'path':str(config_file),'sha256':hashlib.sha256(config_bytes).hexdigest(),'snapshot':raw_config},
        'effective_config':asdict(config),'code':code_identity(),'inputs':inputs,
        'coverage':{'first_frame_index':0,'last_frame_index':video.frame_count-1,'frames':video.frame_count,'duration_s':video.duration_s},
        'totals':{'fragments':len(prepared.fragments),'gaps':len(prepared.gaps),'link_candidates':len(proposals),
            'selected_link_proposals':len(selected),'cross_track_proposals':sum(by_id[p.source_fragment_id].track_id!=by_id[p.target_fragment_id].track_id for p in selected),
            'actor_hypotheses':len(hypotheses),'observed_samples':sum(len(f.samples) for f in prepared.fragments)},
        'validation':{'complete_video_coverage':True,'lifecycle_and_partition':True,
            'exclusive_forward_chains':config.strategy!='disabled','identity_accuracy':'not_evaluated'},
        'actor_hypotheses':hypotheses,'diagnostics':details,
        'warnings':['experimental_costs_not_calibrated','chain_temporality_does_not_verify_identity',
            'same_track_may_contain_actor_transfers','duplicates_and_contamination_not_automatically_resolved'],
        'capabilities_not_executed':['detector_inference','tracking','appearance_inference','apply','subject_selection','scoring'],
        'elapsed_s':time.perf_counter()-started}
    if declared is None:
        summary['warnings'].append('legacy_tracking_report_has_no_original_video_content_binding')
    for destination in destinations:
        destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='trampoline-recovery-audit-') as temporary:
        root=Path(temporary)
        staged_links,staged_report=root/'links.jsonl',root/'report.json'
        with staged_links.open('w',encoding='utf-8',newline='\n') as stream:
            for proposal in proposals:
                stream.write(json.dumps({'schema_version':'1.0','audit_run_id':run_id,'tracking_run_id':loaded.trace.run_id,
                    **asdict(proposal)},ensure_ascii=False,allow_nan=False)+'\n')
        summary['artifacts']={'links_jsonl':str(links_output),'links_sha256':sha256_file(staged_links)}
        staged_report.write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        published=[]
        try:
            for source,destination in ((staged_links,links_output),(staged_report,output)):
                publish_exclusive(source,destination)
                published.append(destination)
        except Exception:
            for destination in published:
                destination.unlink(missing_ok=True)
            raise
    return summary
