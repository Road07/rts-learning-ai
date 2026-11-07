"""Export pre-dispatch demonstrations in the current scorer's input space.

This collects data; it does not train, activate checkpoints or label strategy quality.
"""
import argparse
from collections import Counter,defaultdict
import copy
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'service'))
from demonstrations import match,queue_evidence,SCHEMA
from public_game_rules import PublicGameRules
from decision_net import features
from spend_policy import spend_features


def export(logs,output,config_path,include_fixtures=False):
    config=json.loads(Path(config_path).read_text(encoding='utf-8-sig'))
    path=Path(config['game_rules']);digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=config['game_rules_sha256']:raise ValueError('Game rule catalogue hash mismatch')
    rules=PublicGameRules(path)
    groups=defaultdict(list);sources=[]
    wanted={'human_session_start','human_session_end','human_policy_snapshot','human_state','human_command','human_command_result','capture_gap','demonstration_capture_error'}
    for file in sorted(Path(logs).glob('*.jsonl')):
        sources.append({'file':str(file.resolve()),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
        with file.open(encoding='utf-8') as stream:
            for line_number,line in enumerate(stream,1):
                if not any('"'+name+'"' in line for name in wanted):continue
                record=json.loads(line);data=record.get('data',{})
                if data.get('event') not in wanted:continue
                if data['event']=='human_state' and data.get('reason')!='before_command':continue
                record['_source']={'file':str(file.resolve()),'line':line_number}
                groups[record['session'],record['match']].append(record)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    counts=Counter();splits=Counter();factions=Counter();session_splits=defaultdict(set)
    with (output/'demonstrations.jsonl').open('w',encoding='utf-8') as target:
        for identity,records in sorted(groups.items()):
            header=next((r['data'] for r in records if r['data']['event']=='human_session_start'),{})
            fixture=header.get('fixture',True)
            if header.get('scope')!='fresh_local_human' or header.get('capture')!='pre_dispatch' or header.get('fog')!='own_and_living_allied_vision':counts['unsafe_session']+=1;continue
            if fixture and not include_fixtures:counts['fixture_session_excluded']+=1;continue
            if any(r['data']['event'] in ('capture_gap','demonstration_capture_error') for r in records):counts['incomplete_capture_session']+=1;continue
            indexed=defaultdict(dict);duplicate=False
            for r in records:
                d=r['data'];event=d['event']
                if event not in ('human_command','human_command_result','human_policy_snapshot','human_state'):continue
                key=(d.get('player'),d.get('command_id',d.get('id')))
                if key in indexed[event]:duplicate=True
                indexed[event][key]=r
            if duplicate:counts['duplicate_identity_session']+=1;continue
            for key,record in indexed['human_command'].items():
                command=record['data'];snapshot_record=indexed['human_policy_snapshot'].get(key)
                if snapshot_record is None:counts['missing_pre_dispatch_policy_snapshot']+=1;continue
                snapshot=copy.deepcopy(snapshot_record['data'])
                if snapshot.get('game_rules_sha256')!=digest:counts['game_rules_version_mismatch']+=1;continue
                result_record=indexed['human_command_result'].get(key)
                before=indexed['human_state'].get(key)
                if result_record is None or before is None:counts['missing_before_or_result']+=1;continue
                result=result_record['data']
                if result.get('frame')!=command['frame'] or before['data'].get('frame')!=command['frame']:counts['result_or_before_frame_mismatch']+=1;continue
                if result.get('dispatcher_error'):counts['dispatcher_error']+=1;continue
                matched=match(snapshot,command)
                if not matched['matched']:counts[matched['reason']]+=1;continue
                observation=snapshot['policy_observation'];candidates=snapshot['tactical_candidates' if matched['head']=='tactical' else 'spend_candidates']
                if len({c['id'] for c in candidates})!=len(candidates):counts['duplicate_candidate_id']+=1;continue
                rules.attach(observation,candidates if matched['head']=='tactical' else [],candidates if matched['head']=='spend' else [])
                encoder=features if matched['head']=='tactical' else spend_features
                dimensions={len(encoder(observation,c)) for c in candidates}
                if dimensions!={385 if matched['head']=='tactical' else 383}:raise ValueError('Demonstration feature encoding mismatch')
                evidence=queue_evidence(before['data'],result,matched['candidate'])
                eligible=not fixture and evidence in ('native_queue_inserted','native_queue_removed') and len(candidates)>1
                bucket=int(hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:8],16)%10
                split='fixture_validation' if fixture else ('test' if bucket==0 else 'validation' if bucket in (1,2) else 'train')
                session_splits[split].add(identity)
                row={'schema':SCHEMA,'source_kind':'human','fixture':fixture,'session':identity[0],'match':identity[1],
                     'player':key[0],'command_id':key[1],'frame':command['frame'],'head':matched['head'],
                     'observation':observation,'candidates':candidates,'selected_index':matched['selected_index'],
                     'selected_id':matched['selected_id'],'raw_command':command,'execution_evidence':evidence,
                     'training_eligible':eligible,'label_kind':'demonstrated_choice_not_strategy_quality',
                     'game_rules_sha256':digest,'split':split,'provenance':snapshot_record['_source']}
                target.write(json.dumps(row,ensure_ascii=False)+'\n');counts['matched']+=1
                counts['training_eligible']+=int(eligible);counts['evidence_'+evidence]+=1;splits[split]+=1;factions[observation['faction']]+=1
    report={'schema':SCHEMA,'counts':dict(counts),'splits':dict(splits),'split_sessions':{k:len(v) for k,v in session_splits.items()},'heldout_sessions_present':all(session_splits.get(k) for k in ['train','validation','test']),'factions':dict(factions),'source_sessions':len(groups),
            'source_files':sources,'game_rules_sha256':digest,'training_performed':False,
            'scope':'Exact candidate coverage and native queue evidence only. No nearest-position labels, strategic success labels, RL rewards or checkpoint changes.'}
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--logs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--include-fixtures',action='store_true');a=p.parse_args()
    print(json.dumps(export(a.logs,a.output,a.config,a.include_fixtures),ensure_ascii=False))
