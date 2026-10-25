"""Comprova la frontera BoxMOT/domain amb casos sintètics abans de reproduir vídeo real."""

from pathlib import Path
import argparse
import json
import numpy as np

from trampoline_vision.contracts.observations import FrameContext
from trampoline_vision.contracts.tracking import BoundingBox
from trampoline_vision.tracking.config import TrackerConfig
from trampoline_vision.tracking.session import TrackingSession
from run_study import BotSortPort, import_replay_helpers


def main():
    """Exigeix partició de candidats, naixement fort, recuperació feble i cap intercanvi per ordre de files."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights',type=Path,required=True)
    parser.add_argument('--benchmarks',type=Path,required=True)
    parser.add_argument('--protocol',type=Path,required=True)
    args=parser.parse_args()
    _,make_frame=import_replay_helpers(args.benchmarks)
    config=json.loads(args.protocol.read_text())['botsort']
    for reid in (False,True):
        session=TrackingSession(TrackerConfig(),30)
        port=BotSortPort(args.weights,config,reid)
        port.confirmed_ids=lambda:set(session.live)
        session.backend=port
        birth=None
        for index,score in enumerate([.05]*4+[.8]*6+[.05,.05,.8,None,None,.8]+[None]*19):
            context=FrameContext('synthetic',index,index/30,1/30,100,100)
            box=BoundingBox(10,10,30,60)
            frame=make_frame(context,[(7,box,score,2)] if score is not None else [],Path('synthetic.csv'))
            features=np.zeros((1 if score is not None else 0,512),np.float32)
            if score is not None: features[0,0]=1
            port.embeddings=features
            result=session.update(frame)
            if index<6:
                assert not result.tracks,'Weak or insufficient evidence confirmed a birth'
            if index==9:
                assert len(result.tracks)==1 and result.tracks[0].evidence=='observed'
                birth=result.tracks[0].track_id
            if index in (10,11,12,15):
                assert len(result.tracks)==1 and result.tracks[0].track_id==birth
                assert result.tracks[0].evidence=='observed','Existing identity failed a weak update'
            if index in (13,14):
                assert len(result.tracks)==1 and result.tracks[0].track_id==birth
                assert result.tracks[0].state=='lost' and result.tracks[0].candidate_id is None
            if index==34:
                assert not result.tracks and not session.live,'Expired track remained alive'
            if score is not None and result.tracks:
                assert result.tracks[0].candidate_id==f'{index}:yolo_candidate:7'
                assert result.tracks[0].bbox==box,'Smoothed boxes replaced detector measurements'
        # Dos actors canvien l'ordre dels candidats, però conserven posició i descriptor.
        reordered=TrackingSession(TrackerConfig(),30)
        other=BotSortPort(args.weights,config,reid)
        other.confirmed_ids=lambda:set(reordered.live)
        reordered.backend=other
        identity_by_position={}
        for index in range(8):
            left,right=BoundingBox(10,10,30,60),BoundingBox(65,10,85,60)
            boxes=[left,right] if index%2==0 else [right,left]
            frame=make_frame(FrameContext('reordered',index,index/30,1/30,100,100),
                             [(7,boxes[0],.8,2),(9,boxes[1],.8,3)],Path('synthetic.csv'))
            features=np.zeros((2,512),np.float32)
            for j,box in enumerate(boxes): features[j,0 if box==left else 1]=1
            other.embeddings=features
            result=reordered.update(frame)
            if index>=4:
                assert len(result.tracks)==2
                for track in result.tracks:
                    position=track.bbox.x_min
                    if position in identity_by_position: assert identity_by_position[position]==track.track_id
                    identity_by_position[position]=track.track_id
                    expected=7 if boxes[0].x_min==position else 9
                    assert track.candidate_id==f'{index}:yolo_candidate:{expected}'
    print('PASS strong_birth_weak_update_recovery_expiry_reordered_candidates_original_measurement',flush=True)


if __name__=='__main__':
    main()
