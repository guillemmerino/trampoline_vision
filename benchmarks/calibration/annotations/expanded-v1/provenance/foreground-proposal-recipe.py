import json
from pathlib import Path
import numpy as np
import cv2
from PIL import Image
root=Path('/workspace'); run=root/'runs/calibration/sample-expansion-preparation-v1';sel=json.loads((root/'benchmarks/calibration/annotation-expanded-v1/selection.json').read_text()); oldroot=root/'benchmarks/calibration/annotation-pilot/references';out={}
for ent in sel['cases']:
 cid=ent['case_id'];x0,y0,x1,y1=ent['review_crop_xyxy'];imgs={f:np.asarray(Image.open(run/'raw'/cid/f'frame-{f:06d}.png')) for f in ent['frames']};bg=np.median(np.stack([imgs[f][y0:950,x0:x1] for f in ent['uniform_frames']]),axis=0).astype('uint8');rows={}
 old={s['frame_index']:s for s in json.loads((oldroot/(cid+'.json')).read_text())['samples']} if (oldroot/(cid+'.json')).exists() else {}
 for f,img in imgs.items():
  delta=np.max(np.abs(img[y0:950,x0:x1].astype('int16')-bg.astype('int16')),axis=2); mask=(delta>45).astype('uint8')*255;mask=cv2.medianBlur(mask,3);closed=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((7,7),dtype='uint8'));grown=cv2.dilate(closed,np.ones((13,13),dtype='uint8'))
  num,lab,stats,cent=cv2.connectedComponentsWithStats(grown)
  choices=[]
  for j in range(1,num):
   xx,yy,w,h,area=stats[j]; cx,cy=cent[j]; cy+=y0
   if area<200 or w<15 or h<18 or cy>895:continue
   # Suppress small spectator movement high in the background. Only a proposal, not an annotation.
   score=area if cy>330 else area*.1
   choices.append((score,j))
  if choices:
   j=max(choices)[1]; yy,xx=np.nonzero((lab==j)&(mask>0)); b=[int(xx.min()+x0),int(yy.min()+y0),int(xx.max()+x0+1),int(yy.max()+y0+1)] if len(xx) else None
  else:b=None
  rows[str(f)]={'bbox_xyxy':old[f]['bbox_xyxy'] if f in old else b,'state':old[f]['state'] if f in old else 'pending_visual_review','legacy':f in old,'proposed_bbox_xyxy':b}
 out[cid]=rows
 print(cid,flush=True)
(run/'foreground-proposals.json').write_text(json.dumps(out,indent=2)+'\n')
