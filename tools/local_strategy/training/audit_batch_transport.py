"""Isolated real-host protocol audit with a mocked game process, not gameplay.

Reuses two captured fixture observations at an explicitly synthetic common frame.
Never starts a game, trains, activates, or exports demonstrations.
"""
import argparse
import copy
import http.client
import json
from pathlib import Path
import sys
from unittest.mock import patch
from automatic_training import ROOT,read_json,write_json
import decision_host

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=ROOT/'AI-Yeni-Model/ai-service/runtime.json')
    args=parser.parse_args();requests=[]
    for path in sorted(args.capture.glob('*.jsonl')):
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            row=json.loads(line)
            if row.get('event')=='model_request':
                r=row['data'];requests.append({k:copy.deepcopy(r[k]) for k in ('observation','candidates','production_options')})
                if len(requests)==2:break
        if len(requests)==2:break
    if len(requests)!=2:raise ValueError('Two fixture requests required')
    for request in requests:
        request['observation'].update(match_id='protocol-fixture',decision_frame=100,fixture=True)
    args.output.mkdir(parents=True,exist_ok=False)
    config=read_json(args.config);config.update(persistent_http=True,compact_wire=True,feature_cache=True)
    outputs=[]
    for batched in (False,True):
        workspace=args.output/('batch' if batched else 'single');workspace.mkdir()
        config_path=workspace/'runtime.json';write_json(config_path,config)
        replies=[]
        class GameStub:
            pid=0
            def __init__(self,*unused,env,**kwargs):self.endpoint=env['OPENBFME_AI_URL']
            def wait(self):
                connection=http.client.HTTPConnection('127.0.0.1',int(self.endpoint.rsplit(':',1)[1]),timeout=10)
                try:
                    envelopes=[{'model':config['model'],'requests':requests}] if batched else [{'model':config['model'],'request':r} for r in requests]
                    for envelope in envelopes:
                        connection.request('POST','/api/chat',json.dumps(envelope),{'Content-Type':'application/json'})
                        response=connection.getresponse();payload=json.loads(response.read())
                        if response.status!=200:raise ValueError(payload)
                        if batched:
                            if any(r['status']!=200 for r in payload['results']):raise ValueError(payload)
                            replies.extend(r['response'] for r in payload['results'])
                        else:replies.append(payload)
                finally:connection.close()
                return 0
        argv=['decision_host','--config',str(config_path),'--arena','middle','--episode-dir',str(workspace/'fixture'),'--episode-mode','evaluate','--episode-seed','271026']
        with patch.object(sys,'argv',argv),patch.object(decision_host.subprocess,'Popen',GameStub):
            if decision_host.main()!=0:raise RuntimeError('Isolated host failed')
        outputs.append(replies)
    if outputs[0]!=outputs[1]:raise ValueError('Single and multi-request replies differ')
    result={'fixture':True,'mocked_game_process':True,'real_host_http':True,'requests':2,'single_and_batch_replies_exact':True,'native_multi_bot_gameplay_tested':False,'training_performed':False,'activated':False}
    write_json(args.output/'result.json',result);print(json.dumps(result));return 0

if __name__=='__main__':sys.exit(main())
