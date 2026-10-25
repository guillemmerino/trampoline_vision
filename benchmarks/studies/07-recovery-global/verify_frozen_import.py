"""Compara la CLI integrada amb el pilot congelat; no torna a executar models."""
import argparse,json
from pathlib import Path
from trampoline_vision.ingestion.recovery import load_tracking_trace,sha256_file
from trampoline_vision.ingestion.video import probe_video
from trampoline_vision.interfaces.cli.main import main as cli
from trampoline_vision.recovery.pipeline import prepare_recovery


def minimum_changes(sets):
    dp={}
    for ids in sets:
        if ids:dp={i:min((v+(i!=j) for j,v in dp.items()),default=0) for i in ids}
    return min(dp.values()) if dp else None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-root',type=Path,required=True)
    parser.add_argument('--profiles',type=Path,required=True)
    parser.add_argument('--pilot-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    report=args.import_root/'tracking.json'
    imported=json.loads(report.read_text())
    verification=json.loads((args.import_root/'import-verification.json').read_text())
    cache=Path(verification['cache_path'])
    before={str(p):sha256_file(p) for p in (report,cache,Path(imported['artifacts']['frames_jsonl']))}
    video=probe_video(Path(imported['inputs']['video']['path']),imported['case_id'])
    loaded=load_tracking_trace(imported['artifacts']['frames_jsonl'],report,video)
    fragments=prepare_recovery(loaded.trace).fragments
    source_map={(s.context.frame_index,f.track_id):f.fragment_id for f in fragments for s in f.samples}
    pilot=json.loads((args.pilot_root/'results.json').read_text())['variants']['conf002_all']['configurations']
    names={'disabled-v1':None,'global-geometry-v1':'geometry_2s_055','global-osnet-hungarian-v1':'appearance_2s_055',
        'global-osnet-conservative-v1':'appearance_2s_045','global-osnet-permissive-v1':'appearance_2s_065',
        'global-osnet-long-gap-v1':'appearance_31s_055'}
    rows=[]
    for name,old_name in names.items():
        profile=args.profiles/(name+'.json')
        config=json.loads(profile.read_text())
        output=args.output/(name+'.json')
        command=['audit-recovery','--tracking-report',str(report),'--config',str(profile),'--output',str(output)]
        if config['strategy']=='geometry_appearance':command+=['--appearance-cache',str(cache)]
        if cli(command)!=0:raise ValueError('Integrated public CLI failed: '+name)
        result=json.loads(output.read_text())
        proposals=[json.loads(line) for line in output.with_suffix('.links.jsonl').read_text().splitlines()]
        selected={(l['source_fragment_id'],l['target_fragment_id']) for l in proposals if l['status']=='proposed'}
        if result['applied'] or result['validation']['identity_accuracy']!='not_evaluated':
            raise ValueError('Audit incorrectly applied/certified identities')
        entry={'profile':name,'totals':result['totals'],'elapsed_s':result['elapsed_s'],'code_sha256':result['code']['source_tree_sha256'],
               'profile_sha256':result['profile']['sha256'],'report_sha256':sha256_file(output)}
        if old_name:
            old=pilot[old_name]
            expected={(l['from_id'],l['to_id']) for l in old['links']}
            mapping={fid:h['hypothesis_id'] for h in result['actor_hypotheses'] for fid in h['fragment_ids']}
            sets=[{mapping[source_map[d['frame'],tid]] for tid in d['track_ids']} for d in old['details']]
            changes=minimum_changes(sets)
            entry.update({'selected_link_set_matches_numpy_pilot':selected==expected,
                'links_only_in_integrated':sorted(selected-expected),'links_only_in_pilot':sorted(expected-selected),
                'sparse_minimum_changes_integrated':changes,'sparse_minimum_changes_pilot':old['minimum_changes_actor'],
                'matched_reference_instants':sum(bool(v) for v in sets),'references_independent':False})
            if changes!=old['minimum_changes_actor'] or sum(bool(v) for v in sets)!=79:
                raise ValueError('Frozen sparse metric differs: '+name)
        rows.append(entry)
        print(json.dumps({k:v for k,v in entry.items() if k not in ('links_only_in_integrated','links_only_in_pilot')}),flush=True)
    if any(sha256_file(Path(p))!=value for p,value in before.items()):
        raise ValueError('Original imported inputs/cache changed')
    result={'status':'passed','purpose':'integration_regression_not_independent_identity_validation','frames':930,
        'appearance_inference':False,'tracking_reexecuted':False,'input_files_unchanged':True,'profiles':rows}
    with (args.output/'verification.json').open('x') as f:json.dump(result,f,indent=2)


if __name__=='__main__':main()
