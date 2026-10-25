"""Prepara anotació visual d'identitat a partir del vídeo i CSV, sense mostrar cap tracker.

Les anotacions referencien candidats per fotograma i admeten alternatives
duplicades. Són revisió pilot assistida, no una veritat terreny independent.
"""

import argparse
import csv
import json
from pathlib import Path
import cv2
from PIL import Image,ImageDraw,ImageFont


def review_font():
    """Tria una lletra llegible a Windows o Linux, amb alternativa inclosa a Pillow."""
    for path in ('C:/Windows/Fonts/arial.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        if Path(path).is_file(): return ImageFont.truetype(path,22)
    return ImageFont.load_default(size=22)


def review_indices(case_id, count):
    """Fixa mostreig abans de llegir resultats, amb finestres denses de fallada ja coneguda."""
    indices=set(range(0,count,15 if '000905' in case_id or 'AGE_3' in case_id else 30))
    if '000905' in case_id:
        indices.update(range(300,311))
        indices.update(range(435,452))
        indices.update(range(475,496))
    return sorted(indices)


def main():
    """Genera fulls numerats, taula de candidats i plantilla buida; no consumeix assignacions calculades."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--tfm',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--full-width',action='store_true',default=True,help='Mostra tot el vídeo; comportament per defecte')
    parser.add_argument('--left-panel-only',dest='full_width',action='store_false',help='Només revisió del cas conegut amb esport a l’esquerra')
    parser.add_argument('--cases',nargs='+',help='Limita només les làmines generades, sense canviar el protocol de tracking')
    args=parser.parse_args()
    if args.output.exists(): raise ValueError('Review folder already exists')
    args.output.mkdir()
    protocol=json.loads(args.protocol.read_text())
    font=review_font()
    references=[]
    for case in protocol['cases']:
        cid=case['case_id']; indices=review_indices(cid,case['frames']); wanted=set(indices)
        if args.cases and cid not in args.cases: continue
        panel_width=480 if args.full_width else 330
        by_frame={i:[] for i in indices}
        with (args.tfm/'Tracking_system/output_videos'/f'{cid}_bboxes.csv').open() as stream:
            for row in csv.DictReader(stream):
                index=int(row['frame'])
                if index in wanted: by_frame[index].append(row)
        cap=cv2.VideoCapture(str(args.tfm/'jumping_score/output_clips'/f'{cid}.mp4'))
        images={}; index=0
        while True:
            ok,frame=cap.read()
            if not ok: break
            if index in wanted:
                image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB));draw=ImageDraw.Draw(image)
                for row in reversed(by_frame[index]):
                    det=int(row['det_id']);box=[int(row[k]) for k in ('x1','y1','x2','y2')]
                    shades=['yellow','cyan','magenta','orange','lime','white']
                    shade=shades[det] if det<6 else '#999999'
                    draw.rectangle(box,outline=shade,width=2 if det<6 else 1)
                    if det<6:
                        draw.text((box[0],max(0,box[1]-25)),str(det),fill=shade,font=font,stroke_width=2,stroke_fill='black')
                images[index]=(image if args.full_width else image.crop((0,0,660,1080))).resize((panel_width,540))
                references.append({'case_id':cid,'frame_index':index,'acceptable_det_ids':None,'quality':'pending'})
            index+=1
        cap.release()
        if index!=case['frames'] or len(images)!=len(indices): raise ValueError('Unexpected review frame coverage')
        for page,start in enumerate(range(0,len(indices),12)):
            selected=indices[start:start+12]
            sheet=Image.new('RGB',(panel_width*4,1680),'#101820');draw=ImageDraw.Draw(sheet)
            for cell,frame_index in enumerate(selected):
                x,y=(cell%4)*panel_width,(cell//4)*560
                sheet.paste(images[frame_index],(x,y+20))
                draw.text((x+3,y+3),f'{frame_index} | {frame_index/30:.2f}s',fill='white')
            sheet.save(args.output/f'{cid}-page-{page:02}.png')
        (args.output/f'{cid}-candidates.json').write_text(json.dumps(by_frame,indent=2))
        print(cid,'review_frames',len(indices),'pages',(len(indices)+11)//12,flush=True)
    (args.output/'reference-template.json').write_text(json.dumps({'samples':references},indent=2))


if __name__=='__main__':
    main()
