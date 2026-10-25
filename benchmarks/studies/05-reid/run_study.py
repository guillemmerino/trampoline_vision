"""Compara OC-SORT i BoT-SORT amb/sense ReID sobre caixes YOLO fixes i vídeo original.

Prototip de benchmark: el registre de backends de producció no s'amplia.
OSNet només extreu aparença; les articulacions són absents explícites.
Cada vídeo es descodifica amb PTS verificats i tots els actors es conserven.
"""

import argparse
from dataclasses import asdict
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
import shutil
import sys
import time
from uuid import uuid4

import av
import numpy as np
import torch

from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.results.tracking import tracking_record
from trampoline_vision.tracking.backend import BackendUpdate
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.session import TrackingSession
from trampoline_vision.contracts.tracking import BoundingBox


def import_replay_helpers(benchmarks):
    """Reutilitza l'adaptador de caixes de l'estudi 04 sense copiar ni canviar el seu comportament."""
    case = benchmarks / 'cases/JPN_AGE_1_000905_31.0/study-04'
    sys.path.insert(0, str(case))
    from replay_boxes import load_boxes, make_frame
    return load_boxes, make_frame


def sha256(path):
    """Identifica bytes d'entrada, pesos i protocol, llegint vídeos per blocs."""
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


class FixedCamera:
    """Component CMC explícit d'identitat per a la càmera fixa del protocol."""

    def apply(self, image, detections):
        """Retorna una transformació identitat; no estima moviment de càmera ni usa les anotacions."""
        return np.array([[1., 0., 0.], [0., 1., 0.]])


class BotSortPort:
    """Tradueix l'API fixada BoxMOT 16.0.9 a assignacions i vida del domini existent.

    Usa el det_ind retornat per update, mai solapament reconstruït per decidir
    quina detecció s'ha assignat. Les llistes active_tracks/lost_stracks i xyxy
    són dependències explícites d'aquest port experimental i es proven abans.
    """

    def __init__(self, weights, settings, with_reid):
        """Crea un tracker independent; la política comuna de naixement continua a TrackingSession."""
        from boxmot import BotSort
        self.tracker = BotSort(reid_weights=weights, device=torch.device('cpu'), half=False,
                               with_reid=with_reid, **settings)
        self.tracker.cmc = FixedCamera()
        self.with_reid = with_reid
        self.embeddings = None
        self.known = set()
        self.confirmed_ids = lambda: set()
        self.blank_image = None

    def update(self, frame):
        """Conserva les mesures originals i permet evidència feble només en identitats ja confirmades."""
        candidates = [c for c in frame.candidates if c.measurement is not None]
        dets = np.asarray([[c.measurement.bbox.x_min, c.measurement.bbox.y_min,
                            c.measurement.bbox.x_max, c.measurement.bbox.y_max,
                            c.measurement.score, 0] for c in candidates], dtype=np.float32).reshape(-1, 6)
        # CMC és identitat i els embeddings ja provenen del fotograma original verificat.
        # Es preserven les dimensions d'API; aquests píxels no intervenen en l'associació.
        shape=(frame.source.context.height_px,frame.source.context.width_px,3)
        if self.blank_image is None or self.blank_image.shape!=shape:
            self.blank_image=np.zeros(shape,dtype=np.uint8)
        image=self.blank_image
        output = self.tracker.update(dets, image, self.embeddings if self.with_reid else None)
        assignments = {c.candidate_id: -1 for c in candidates}
        confirmed = self.confirmed_ids()
        for row in output:
            index, tid = int(row[7]), int(row[4])
            if row[7] != index or not 0 <= index < len(candidates):
                raise ValueError('BoxMOT returned invalid detection index')
            candidate = candidates[index]
            if assignments[candidate.candidate_id] != -1:
                raise ValueError('BoxMOT assigned one candidate twice')
            if tid in confirmed or candidate.measurement.score >= .1:
                assignments[candidate.candidate_id] = tid
                self.known.add(tid)
        alive = []
        for track in self.tracker.active_tracks + self.tracker.lost_stracks:
            # La disponibilitat segueix les llistes públiques d'associació.
            # BoxMOT 16.0.9 pot conservar un element retirat un tick a lost_stracks;
            # encara pot retornar-lo al tick següent. No s'interpreten enums interns
            # ni es força una retirada anticipada que permetria reusar un ID acabat.
            # El pressupost de 15 fotogrames és nominal; l'auditoria exposa aquest tick.
            if track.id not in self.known:
                continue
            try:
                box = BoundingBox(*(float(v) for v in track.xyxy))
            except ValueError:
                box = None
            alive.append((int(track.id), box))
        if len({tid for tid, _ in alive}) != len(alive):
            raise ValueError('BoxMOT exposed duplicate active/lost IDs')
        self.known &= {tid for tid, _ in alive}
        return BackendUpdate(tuple(assignments.items()), tuple(alive))


def extract_embeddings(video, rows, model, destination):
    """Calcula una sola vegada descriptors de totes les caixes i comprova índexs, PTS i geometria."""
    features, sizes = [], []
    started = time.perf_counter()
    with av.open(str(video.path)) as source:
        count = 0
        for index, decoded in enumerate(source.decode(video=0)):
            if index >= video.frame_count or decoded.pts is None or not decoded.time_base or decoded.is_corrupt:
                raise ValueError('Invalid decoded video frame')
            context = video.frame(index)
            if abs(float(decoded.pts*decoded.time_base)-video.source_start_s-context.timestamp_s) > .0001:
                raise ValueError('Decoded video timestamp differs from ffprobe')
            if (decoded.width, decoded.height) != (video.width_px, video.height_px):
                raise ValueError('Decoded video geometry differs from ffprobe')
            boxes = np.array([[b.x_min,b.y_min,b.x_max,b.y_max] for _,b,_,_ in sorted(rows[index])], dtype=np.float32)
            embedding = model.get_features(boxes, decoded.to_ndarray(format='bgr24'))
            if embedding.shape != (len(boxes),512) or not np.isfinite(embedding).all():
                raise ValueError('Invalid OSNet descriptors')
            if not np.allclose(np.linalg.norm(embedding,axis=1),1,atol=1e-4):
                raise ValueError('OSNet descriptors are not normalized')
            features.append(embedding.astype(np.float32)); sizes.append(len(boxes)); count += 1
            if index % 200 == 0:
                print(f'EMBEDDINGS {video.video_id} {index}/{video.frame_count-1}',flush=True)
    if count != video.frame_count:
        raise ValueError('Decoded frame count differs from ffprobe')
    offsets = np.r_[0,np.cumsum(sizes)]
    np.savez_compressed(destination, features=np.concatenate(features), offsets=offsets)
    return features, {'elapsed_s':time.perf_counter()-started,'boxes':sum(sizes),'dimensions':512,
                     'cache_sha256':sha256(destination),'decoded_pts_verified':True}


def reuse_embeddings(origin,video,csv_path,rows,destination,weights_hash):
    """Reutilitza un cache verificat per refinar associació sense repetir inferència ReID.

    Rebutja canvis de vídeo, CSV, pesos, runtime de preprocessament, índexs
    o descriptors; canviar paràmetres d'associació sí que és compatible.
    """
    started=time.perf_counter()
    previous=json.loads((origin/'summary.json').read_text())
    if previous['weights_sha256']!=weights_hash: raise ValueError('Cached ReID weights differ')
    for package in ('boxmot','torch','torchvision','numpy','opencv-python','av'):
        if previous['versions'][package]!=version(package): raise ValueError('Cached descriptor runtime differs')
    case=previous['cases'][video.video_id]
    if case['video_sha256']!=sha256(video.path) or case['csv_sha256']!=sha256(csv_path):
        raise ValueError('Cached video or detections differ')
    path=origin/video.video_id/'embeddings.npz'
    if sha256(path)!=case['embeddings']['cache_sha256']: raise ValueError('Cached descriptors changed')
    with np.load(path,allow_pickle=False) as stored:
        features,offsets=stored['features'],stored['offsets']
    sizes=[len(rows[i]) for i in range(video.frame_count)]
    if not np.array_equal(offsets,np.r_[0,np.cumsum(sizes)]): raise ValueError('Cached candidate alignment differs')
    if features.shape!=(sum(sizes),512) or not np.isfinite(features).all(): raise ValueError('Invalid descriptor cache')
    if not np.allclose(np.linalg.norm(features,axis=1),1,atol=1e-4): raise ValueError('Invalid cached normalization')
    shutil.copyfile(path,destination)
    return [features[offsets[i]:offsets[i+1]] for i in range(video.frame_count)], {
        **case['embeddings'],'elapsed_s':time.perf_counter()-started,'reused_from':str(path),
        'source_extraction_elapsed_s':case['embeddings']['elapsed_s'],'new_reid_inference':False}


def main():
    """Executa el protocol congelat i publica resultats nous amb procedència i configuració efectiva."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--benchmarks',type=Path,required=True)
    parser.add_argument('--tfm',type=Path,required=True)
    parser.add_argument('--weights',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--threads',type=int,default=4)
    parser.add_argument('--reuse-embeddings-from',type=Path,help='Execució anterior verificada, per refinar només l’associació')
    args=parser.parse_args()
    if args.output.exists(): raise ValueError('Output already exists')
    if version('boxmot')!='16.0.9': raise ValueError('Unsupported BoxMOT runtime')
    if version('trampoline-vision')!='0.4.0' or version('trackers')!='2.6.1':
        raise ValueError('This study requires the frozen 0.4.0 domain and trackers 2.6.1')
    protocol=json.loads(args.protocol.read_text(encoding='utf-8'))
    if sha256(args.weights)!=protocol['reid_sha256']: raise ValueError('ReID weights differ from protocol')
    torch.set_num_threads(args.threads); torch.set_num_interop_threads(1)
    torch.manual_seed(0); np.random.seed(0); torch.use_deterministic_algorithms(True)
    load_boxes,make_frame=import_replay_helpers(args.benchmarks)
    from boxmot.reid.core.auto_backend import ReidAutoBackend
    model=ReidAutoBackend(args.weights,torch.device('cpu'),False).model
    # La biblioteca tolera capes descartades: aquí exigim explícitament tots els pesos del backbone.
    checkpoint=torch.load(args.weights,map_location='cpu',weights_only=True)
    state=checkpoint.get('state_dict',checkpoint)
    normalized={k.removeprefix('module.'):v for k,v in state.items()}
    backbone={k:v for k,v in model.model.state_dict().items() if not k.startswith('classifier.')}
    if any(k not in normalized or not torch.equal(v,normalized[k]) for k,v in backbone.items()):
        raise ValueError('The full pretrained backbone was not loaded')
    args.output.mkdir(parents=True)
    (args.output/'protocol.json').write_bytes(args.protocol.read_bytes())
    summary={'protocol_sha256':sha256(args.protocol),'weights_sha256':sha256(args.weights),'pretrained_backbone_tensors_verified':len(backbone),
             'versions':{m:version(m) for m in ['trampoline-vision','boxmot','trackers','torch','torchvision','numpy','opencv-python','av']},
             'threads':args.threads,'device':'cpu','cases':{}}
    (args.output/'environment.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True))
    for case in protocol['cases']:
        cid=case['case_id']; folder=args.output/cid; folder.mkdir()
        path=args.tfm/'jumping_score/output_clips'/f'{cid}.mp4'
        csv_path=args.tfm/'Tracking_system/output_videos'/f'{cid}_bboxes.csv'
        video=probe_video(path,cid)
        if video.frame_count!=case['frames'] or video.fps!=30: raise ValueError('Case differs from frozen protocol')
        rows=load_boxes(csv_path,video)
        if args.reuse_embeddings_from:
            embeddings,emb_info=reuse_embeddings(args.reuse_embeddings_from,video,csv_path,rows,
                                                 folder/'embeddings.npz',protocol['reid_sha256'])
        else:
            embeddings,emb_info=extract_embeddings(video,rows,model,folder/'embeddings.npz')
        case_info={'video_sha256':sha256(path),'csv_sha256':sha256(csv_path),'frames':video.frame_count,
                   'duration_s':video.duration_s,'embeddings':emb_info,'variants':{}}
        for name in protocol['variants']:
            session=TrackingSession(TrackerConfig(),video.fps)
            if name!='ocsort':
                port=BotSortPort(args.weights,protocol['botsort'],name=='botsort_reid')
                port.confirmed_ids=lambda current=session:set(current.live)
                session.backend=port
            run_id=str(uuid4()); started=time.perf_counter(); observed=predicted=0
            with (folder/f'{name}.frames.jsonl').open('x',encoding='utf-8') as stream:
                for index in range(video.frame_count):
                    frame=make_frame(video.frame(index),rows[index],csv_path)
                    if name!='ocsort': session.backend.embeddings=embeddings[index]
                    result=session.update(frame)
                    record=tracking_record(result,session.events,session.config)
                    record.update(run_id=run_id,experiment=name,pose_status='not_loaded',reid=name=='botsort_reid')
                    if name!='ocsort':
                        for item in record['tracks']+record['events']:
                            item['track_id']=item['track_id'].replace('ocsort:',name+':',1)
                    stream.write(json.dumps(record,allow_nan=False)+'\n')
                    observed+=sum(t.evidence=='observed' for t in result.tracks)
                    predicted+=sum(t.state=='lost' for t in result.tracks)
            case_info['variants'][name]={'elapsed_s':time.perf_counter()-started,'observed_all_actors':observed,'predicted_all_actors':predicted,
                                         'domain_config':asdict(session.config)}
            print(f'TRACKED {cid} {name}',flush=True)
        summary['cases'][cid]=case_info
        (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('COMPLETED',flush=True)


if __name__=='__main__':
    main()
