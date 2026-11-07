"""Bounded model-controlled speed measurement through the REAL arena service.

Evaluation only: no gradient update, normal-match import, activation or benchmark registration.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import hashlib
from itertools import zip_longest
import json
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace
from automatic_training import run_episode,read_json,write_json,ROOT,HERE,sha
from benchmark import lock
sys.path.insert(0,str(HERE.parent))
from engine_update import active

def distribution(values):
    if not values:return {'n':0,'sum':0.,'mean':None,'p50':None,'p95':None,'max':None}
    values=sorted(values);n=len(values)
    return {'n':n,'sum':sum(values),'mean':statistics.mean(values),'p50':statistics.median(values),'p95':statistics.quantiles(values,n=100,method='inclusive')[94] if n>1 else values[0],'max':values[-1]}

def analyze(folder,stage,total_seconds):
    report=read_json(folder/'arena'/(stage+'.json'))
    service=[json.loads(l) for l in (folder/'service.jsonl').read_text(encoding='utf-8-sig').splitlines() if l.strip()]
    records=[json.loads(l) for f in (folder/'telemetry').glob('*.jsonl') for l in f.read_text(encoding='utf-8-sig').splitlines() if l.strip()]
    waits=[r['data'] for r in records if r.get('event')=='model_inference_timing']
    server=[r for r in service if r.get('event')=='inference_profile']
    controlled=report.get('model_only_validation',{}).get('players',[])
    if len(controlled)!=6 or not all(p.get('model_only') for p in controlled):raise ValueError('All six players must be model controlled')
    if not report.get('ok') or report.get('script_errors') or any(r['http']!=200 or r['result']!=0 for r in waits):raise ValueError('Measurement has a failed model request')
    if len(waits)!=len(server) or len(waits)!=report['model_decisions']:raise ValueError('Incomplete per-decision profiling')
    profile=report['inference_profile'];wall=profile['simulation_wall_seconds'];sim=report['headless_training']['simulation_seconds']
    result={'speed':report['headless_training']['time_scale'],'simulation_seconds':sim,'simulation_wall_seconds':wall,'episode_wall_seconds':total_seconds,'effective_simulation_speed':sim/wall,'decisions':len(waits),'requests_by_player':dict(Counter(str(r['player']) for r in waits)),'game_prepare_ms':distribution([r['prepare_ms'] for r in waits]),'game_prepare_parts':{k:distribution([r['parts'][k] for r in waits]) for k in ('snapshot_ms','tactical_options_ms','reward_sensor_ms','production_options_ms','serialization_log_ms')},'rpc_wait_ms':distribution([r['rpc_wait_ms'] for r in waits]),'callback_ms':distribution([r['data']['callback_ms'] for r in records if r.get('event')=='model_response_timing']),'server':{k:distribution([r[k] for r in server]) for k in ('read_parse_ms','rules_ms','reward_and_observation_log_ms','policy_and_trace_ms','shadow_and_reply_ms','server_total_ms')},'hash_seconds':profile.get('hash_seconds'),'hash_samples':profile.get('hash_samples'),'hash_stride':profile.get('hash_stride'),'native_advance_seconds':profile['native_advance_seconds'],'state_hash':profile['state_hash'],'hash_chain_sha256':profile['hash_chain_sha256'],'hashes':profile['hashes'],'report':str(folder/'arena'/(stage+'.json')),'fixture':True,'training_performed':False}
    result['rpc_wait_fraction']=result['rpc_wait_ms']['sum']/1000/wall
    result['serialization_ms']=distribution([r['serialization_ms'] for r in waits if 'serialization_ms' in r])
    result['request_bytes']=distribution([r['request_bytes'] for r in waits if 'request_bytes' in r])
    result['response_bytes']=distribution([r.get('response_bytes',0) for r in server])
    result['connections']=len(set(r.get('peer_port') for r in server))
    choices=[r for r in service if r.get('event')=='network_choice']
    if len(choices)!=len(server):raise ValueError('Missing decision trace')
    result['choices']=[(p['player'],p['frame'],r['candidate_id'],r['production_id']) for p,r in zip(server,choices)]
    result['decision_sha256']=hashlib.sha256(json.dumps(result['choices'],separators=(',',':')).encode()).hexdigest()
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--config',type=Path,default=ROOT/'AI-Yeni-Model/ai-service/runtime.json');p.add_argument('--seconds',type=int,default=180);p.add_argument('--speeds',default='1,10');p.add_argument('--fast-poll',action='store_true');p.add_argument('--hash-stride',type=int,default=1);p.add_argument('--decision-stride',type=int,choices=[5,10,15,20],default=5);p.add_argument('--stage',choices=['opening','middle','late'],default='middle');p.add_argument('--case',default='pressure');p.add_argument('--seed',type=int,default=271026)
    for key in ('persistent-http','compact-wire','feature-cache','batch-wire'):p.add_argument('--'+key,action='store_true')
    p.add_argument('--parallel',type=int,choices=[1,4,8],default=1)
    a=p.parse_args();speeds=[float(x) for x in a.speeds.split(',')]
    if not 1<=a.seconds<=1800 or any(not .25<=s<=100 for s in speeds):p.error('Invalid bounded measurement settings')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    c=read_json(a.config);engine=active()
    if engine is None:raise ValueError('Validated engine package is required')
    result={'schema':'model-inference-speed-v1','seed':a.seed,'stage':a.stage,'case':a.case,'seconds':a.seconds,'model':'active NumPy faction-bank model','mode':'evaluate','decision_stride_frames':a.decision_stride,'fast_poll':a.fast_poll,'hash_stride':a.hash_stride,'tactic_sha256':c['sha256'],'spend_sha256':c['spend_sha256'],'engine':engine['directory'],'runs':[],'training_performed':False,'activated':False}
    result.update(parallel=a.parallel,transport={k:getattr(a,k) for k in ('persistent_http','compact_wire','feature_cache','batch_wire')})
    with lock(ROOT/'AI-Test-Sahasi/training.lock'):
        for i,speed in enumerate(speeds):
            print('MEASURE speed='+str(speed)+' simulation_seconds='+str(a.seconds),flush=True)
            if sha(c['weights'])!=c['sha256'] or sha(c['spend_weights'])!=c['spend_sha256']:raise ValueError('Pinned checkpoint changed')
            args=SimpleNamespace(config=a.config.resolve(),headless_training=True,inference_profile=True,hash_stride=a.hash_stride,headless_fast_poll=a.fast_poll,decision_stride=a.decision_stride,time_scale=speed,rotate_factions=False,seconds=a.seconds,stage=a.stage,case=a.case,seed=a.seed,engine_package=engine['directory'],**result['transport'])
            if a.parallel>1:
                def worker(j):
                    workspace=out/('worker-%02d'%j);workspace.mkdir()
                    started=time.perf_counter()
                    try:
                        run_episode(args,workspace,'measure',Path(c['weights']),Path(c['weights']),a.seed,'evaluate',Path(c['spend_weights']),Path(c['spend_weights']))
                        return analyze(workspace/'measure',a.stage,time.perf_counter()-started)
                    except Exception as error:
                        return {'failed':True,'error':str(error),'worker':j,'episode_wall_seconds':time.perf_counter()-started}
                started=time.perf_counter()
                with ThreadPoolExecutor(max_workers=a.parallel) as pool:rows=list(pool.map(worker,range(a.parallel)))
                elapsed=time.perf_counter()-started
                result['runs']+=rows
                completed=sum(not r.get('failed',False) for r in rows)
                result['throughput']={'finished_duration_limited_episodes':completed,'failed':len(rows)-completed,'batch_wall_seconds':elapsed,'episodes_per_hour_extrapolated':3600*completed/elapsed,'actual_one_hour_run':False}
                write_json(out/'summary.json',result)
                return 0 if completed==len(rows) else 1
            name='measure-%02d'%i;started=time.perf_counter()
            run_episode(args,out,name,Path(c['weights']),Path(c['weights']),a.seed,'evaluate',Path(c['spend_weights']),Path(c['spend_weights']))
            row=analyze(out/name,a.stage,time.perf_counter()-started);result['runs'].append(row);write_json(out/'summary.json',result)
            print(json.dumps(row,ensure_ascii=False),flush=True)
    if len(result['runs'])>=2:
        first=result['runs'][0];comparisons=[]
        for other in result['runs'][1:]:
            mismatch=None;count=0
            with Path(first['hashes']).open(encoding='utf-8-sig') as f,Path(other['hashes']).open(encoding='utf-8-sig') as g:
                for x,y in zip_longest(f,g):
                    if x is None or y is None or json.loads(x)!=json.loads(y):mismatch={'left':json.loads(x) if x else None,'right':json.loads(y) if y else None};break
                    count+=1
            comparisons.append({'speeds':[first['speed'],other['speed']],'matching_hash_frames':count,'first_divergence':mismatch,'equal':mismatch is None and first['hash_chain_sha256']==other['hash_chain_sha256'],'wall_speedup':first['simulation_wall_seconds']/other['simulation_wall_seconds']})
        result['comparisons']=comparisons
    write_json(out/'summary.json',result)
    return 0
if __name__=='__main__':sys.exit(main())
