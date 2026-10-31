import json,sys,hashlib
from pathlib import Path
root=Path('/home/tics/personal/trampoline-vision');run=root/'runs/calibration/sample-expansion-preparation-v1';sel=json.loads((root/'benchmarks/calibration/annotation-expanded-v1/selection.json').read_text());ent=sel['cases'][int(sys.argv[1])];cid=ent['case_id']; props=json.loads((run/'foreground-proposals.json').read_text())[cid]
p=run/'visual-review.json';data=json.loads(p.read_text()) if p.exists() else {};assert cid not in data
fixes=json.loads(sys.argv[2]); assert all(f in props and not props[f]['legacy'] for f in fixes)
data[cid]={'reviewer_type':'model','human_reviewed':False,'reviewed_frames':ent['frames'],'reviewed_sheets':{f'proposal-sheets/{cid}-p{i}.jpg':hashlib.sha256((run/f'proposal-sheets/{cid}-p{i}.jpg').read_bytes()).hexdigest() for i in range(5)},'corrections':fixes,'notes':sys.argv[3] if len(sys.argv)>3 else 'All 80 raw-frame overlays inspected by the same model; approximate visible-body extent, not human ground truth. Corrected unrelated motion, clipped limbs and merged apparatus; null means ambiguous/occluded extent.'}
p.write_text(json.dumps(data,indent=2)+'\n');print(cid,len(fixes),'corrections/exclusions;',len(data),'cases reviewed')
