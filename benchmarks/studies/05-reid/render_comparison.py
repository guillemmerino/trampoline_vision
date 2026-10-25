"""Publica comparacions temporals OC-SORT/ReID i trajectòries de tots els IDs.

El ressaltat d'un ID és diagnòstic manual, sense unir fragments. Les caixes
observades són les del detector i les prediccions es dibuixen discontínues.
"""

import argparse
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import sys

from PIL import Image,ImageDraw,ImageFont
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.results.overlay import RenderStyle,HEADER_HEIGHT
from trampoline_vision.results.video import encode_visualization
from trampoline_vision.application.visualization import validate_rendered_video
from run_study import import_replay_helpers
from evaluate_study import read_records


@dataclass(frozen=True)
class ComparisonFrame:
    """Comparteix el context del vídeo entre dues execucions sobre les mateixes deteccions."""

    source: object  # Observacions canòniques amb punts absents explícits.
    baseline: dict  # Registre OC-SORT original.
    reid: dict  # Registre BoT-SORT amb ReID original.

    @property
    def context(self):
        """Exposa PTS i geometria que el codificador verifica contra el vídeo."""
        return self.source.context

    @property
    def source_status(self):
        """Propaga l'estat del registre de deteccions original."""
        return self.source.source_status

    @property
    def detections(self):
        """Conserva el recompte real de propostes per a l'informe del codificador."""
        return self.source.detections


class ComparisonRenderer:
    """Dibuixa tots els tracks i ressalta un ID fix per execució, sense canviar-ne les assignacions."""

    def __init__(self,highlighted,review,renderer_class,overlay_class):
        """Inicialitza dos renderitzadors independents i les referències només per mostrar avisos."""
        self.highlighted=highlighted
        self.review=review
        self.renderers={name:renderer_class(None,[]) for name in ('ocsort','botsort_reid')}
        self.overlay_class=overlay_class

    def __call__(self,image,frame,style):
        """Retorna dues vistes a escala original i recomptes separats; no retalla el vídeo font."""
        panels=[]; counts={}; font=ImageFont.load_default(size=13)
        index=frame.context.frame_index
        reference=self.review.get(index)
        for name,record in [('ocsort',frame.baseline),('botsort_reid',frame.reid)]:
            annotated=self.overlay_class(frame.source,record)
            panel,stats=self.renderers[name](image,annotated,RenderStyle(view='all'))
            draw=ImageDraw.Draw(panel)
            tid=self.highlighted[name]
            track=next((t for t in record['tracks'] if t['track_id']==tid and t['state']!='finished'),None)
            status='instant sense anotacio'
            color='white'
            if reference:
                expected={f'{index}:yolo_candidate:{det}' for det in reference['acceptable_det_ids']}
                if reference['quality']=='ambiguous_overlap': status='caixa ambigua: fora de metrica principal';color='yellow'
                elif not expected: status='cap caixa del gimnasta al CSV';color='orange'
                elif track and track['evidence']=='observed' and track['candidate_id'] in expected:
                    status='ID destacat correspon al gimnasta revisat';color='#55ffaa'
                else: status='ID destacat no te match observat del gimnasta';color='#ff7777'
            if track and track['bbox']:
                b=track['bbox']; coords=[b['x_min'],b['y_min']+HEADER_HEIGHT,b['x_max'],b['y_max']+HEADER_HEIGHT]
                if track['evidence']=='observed': draw.rectangle(coords,outline=color,width=5)
            draw.rectangle((0,0,image.width,HEADER_HEIGHT-1),fill='#101820')
            draw.text((8,4),f'{name} | frame {index} | t={frame.context.timestamp_s:.3f}s',font=font,fill='white')
            draw.text((8,24),f'ID ressaltat {tid}: seleccio manual fixa, sense unir IDs',font=font,fill='white')
            draw.text((8,44),status,font=font,fill=color)
            panels.append(panel);counts[name]=stats['tracking']
        canvas=Image.new('RGB',(panels[0].width*2,panels[0].height),'black')
        for j,panel in enumerate(panels): canvas.paste(panel,(j*panel.width,0))
        return canvas,counts


def export_trajectories(records,path):
    """Exporta totes les identitats i distingeix mesures, estimacions i finalitzacions."""
    fields=['frame_index','timestamp_s','track_id','state','evidence','candidate_id','x_min','y_min','x_max','y_max','center_x_px','center_y_px']
    with path.open('x',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for record in records:
            for track in record['tracks']:
                row={k:track[k] for k in ['track_id','state','evidence','candidate_id']}
                row.update(frame_index=record['context']['frame_index'],timestamp_s=record['context']['timestamp_s'])
                if track['bbox']:
                    box=track['bbox'];row.update(box)
                    row.update(center_x_px=(box['x_min']+box['x_max'])/2,center_y_px=(box['y_min']+box['y_max'])/2)
                writer.writerow(row)


def main():
    """Genera vídeos complets amb PTS verificats, CSV i informes nous per als tres casos."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs',type=Path,required=True)
    parser.add_argument('--benchmarks',type=Path,required=True)
    parser.add_argument('--tfm',type=Path,required=True)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--analysis',type=Path,required=True)
    parser.add_argument('--cases',nargs='+')
    parser.add_argument('--output-name',default='review-output',help='Carpeta nova, per preservar revisions anteriors')
    args=parser.parse_args()
    load_boxes,make_frame=import_replay_helpers(args.benchmarks)
    from render_boxes import RecordedOverlay,ReplayRenderer
    analysis=json.loads(args.analysis.read_text())
    reference=json.loads(args.reference.read_text())['samples']
    for cid,result in analysis['cases'].items():
        if args.cases and cid not in args.cases: continue
        if Path(args.output_name).name!=args.output_name: raise ValueError('Output name must be one directory')
        folder=args.runs/cid/args.output_name
        if folder.exists(): raise ValueError('Review output already exists')
        video=probe_video(args.tfm/'jumping_score/output_clips'/f'{cid}.mp4',cid)
        csv_path=args.tfm/'Tracking_system/output_videos'/f'{cid}_bboxes.csv'
        rows=load_boxes(csv_path,video)
        records={name:read_records(args.runs/cid/f'{name}.frames.jsonl') for name in ('ocsort','botsort_motion','botsort_reid')}
        if any(len(r)!=video.frame_count for r in records.values()): raise ValueError('Incomplete tracking output')
        for name,items in records.items():
            for i,record in enumerate(items):
                if record['context']!=vars(video.frame(i)): raise ValueError('Tracking timeline differs from video')
        folder.mkdir()
        selected={name:result['variants'][name]['dominant_id'] for name in ('ocsort','botsort_reid')}
        reviewed={s['frame_index']:s for s in reference if s['case_id']==cid}
        annotations=(ComparisonFrame(make_frame(video.frame(i),rows[i],csv_path).source,records['ocsort'][i],records['botsort_reid'][i]) for i in range(video.frame_count))
        target=folder/'comparison.mp4'
        style=RenderStyle(view='compare')
        details=encode_visualization(video,annotations,target,style,0,video.frame_count,
                                     renderer=ComparisonRenderer(selected,reviewed,ReplayRenderer,RecordedOverlay))
        rendered=probe_video(target,cid)
        validation=validate_rendered_video(video,rendered,0,video.frame_count,style)
        for name,items in records.items(): export_trajectories(items,folder/f'{name}.trajectories.csv')
        from run_study import sha256
        report={'case_id':cid,'reference_sha256':sha256(args.reference),'analysis_sha256':sha256(args.analysis),
                'frames':rendered.frame_count,'duration_s':rendered.duration_s,
                'dimensions':[rendered.width_px,rendered.height_px],'validation':validation,'highlighted_ids':selected,
                'highlighting_policy':'manual_diagnostic_dominant_id_at_reviewed_samples_not_automatic_subject_selection',
                'totals':details['totals_by_view'],'limitations':['box_center_not_center_of_mass','no_identity_stitching','no_pose_association','sparse_reference']}
        (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print('RENDERED',cid,json.dumps(report),flush=True)


if __name__=='__main__':
    main()
