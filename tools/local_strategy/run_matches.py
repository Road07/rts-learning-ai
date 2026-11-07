"""Run isolated matches in separate processes; aggregate only real result files."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import copy
from itertools import zip_longest
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time
from run_match import arguments,read,write,HERE

def compare_results(left,right):
    left,right=Path(left),Path(right);a,b=read(left),read(right)
    conditions=('seed','map','factions','initial_frame','logic_frames','model_identity')
    def inputs(row):
        config=Path(row.get('runtime_directory',''))/'match-config.json'
        data=read(config) if config.is_file() else row
        return {k:data.get(k) for k in ('positions','controllers')}

    compatible=inputs(a)==inputs(b) and all(a.get(k)==b.get(k) for k in conditions) and all(a.get('identity',{}).get(k)==b.get('identity',{}).get(k) for k in ('native_sha256','harness_sha256','base_pck_sha256','runtime_pck_sha256'))
    first=None;hashes_checked=0
    if compatible:
        with Path(str(left)+'.hashes.jsonl').open(encoding='utf-8-sig') as f,Path(str(right)+'.hashes.jsonl').open(encoding='utf-8-sig') as g:
            for x,y in zip_longest(f,g):
                if x is None or y is None or json.loads(x)!=json.loads(y):first={'left':json.loads(x) if x else None,'right':json.loads(y) if y else None};break
                hashes_checked+=1
    equal=compatible and first is None and a.get('ok') and b.get('ok') and all(a.get(k)==b.get(k) for k in ('winner','end_reason','duration_seconds','players','state_hash_chain_sha256'))
    return {'compatible':compatible,'deterministic_equal':bool(equal),'hash_frames_checked':hashes_checked,'first_divergence':first,'left':str(left),'right':str(right),'scope':'Measured fixed-step trajectory on this installed engine/platform only; not a universal determinism proof.'}

def summary(results,wall):
    ok=[r for r in results if r.get('ok')];completed=[r for r in ok if r.get('winner') is not None];wins={str(team):sum(r['winner']==team for r in completed) for team in (1,2)}
    mean=lambda key:statistics.mean(r[key] for r in ok) if ok else None
    return {'schema':'rts-match-batch-v1','attempts':len(results),'successful':len(ok),'failed':len(results)-len(ok),'completed':len(completed),'duration_limited':sum(r.get('end_reason')=='duration' for r in ok),'wins':wins,'win_rate_completed':{k:v/len(completed) if completed else None for k,v in wins.items()},'average_duration_seconds':mean('duration_seconds'),'average_match_wall_seconds':mean('worker_wall_seconds'),'average_simulation_wall_seconds':mean('simulation_wall_seconds'),'batch_wall_seconds':wall,'results':results,'interpretation':'Duration-limited matches are unresolved, not draws/wins; per-match wall includes loading and scheduling contention.'}

def main(argv=None):
    argv=sys.argv[1:] if argv is None else argv
    extra=argparse.ArgumentParser(add_help=False);extra.add_argument('--matches',type=int,default=1);extra.add_argument('--parallel',type=int,default=1);extra.add_argument('--same-seed',action='store_true')
    control,rest=extra.parse_known_args(argv)
    if not 1<=control.matches<=10000 or not 1<=control.parallel<=64:extra.error('matches 1..10000, parallel 1..64')
    if '--help' in rest or '-h' in rest:print('Batch options: --matches N --parallel P [--same-seed]. --out is a batch directory.')
    a=arguments(rest);root=a.out.resolve()
    if (root/'summary.json').exists():raise ValueError('Batch already has a summary; choose a new --out directory')
    root.mkdir(parents=True,exist_ok=True)
    if not control.same_seed and a.seed+control.matches-1>2147483647:extra.error('Seed range exceeds supported bounds')
    batch_lock=root/'batch.lock'
    with batch_lock.open('x',encoding='utf-8') as f:f.write(str(os.getpid()))
    start=time.perf_counter();active={};guard=threading.Lock();cancel=threading.Event()
    def stop(process,log=None):
        if process.poll() is not None:return
        if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=log or subprocess.DEVNULL,stderr=subprocess.STDOUT)
        else:process.kill()
        process.wait(timeout=10)
    def worker(index):
        folder=root/('match-%04d'%index);folder.mkdir(exist_ok=True);out=folder/'result.json';seed=a.seed if control.same_seed else a.seed+index
        # Build argv from parsed settings: paths containing spaces remain single args.
        cmd=[sys.executable,str(HERE/'run_match.py'),'--out',str(out),'--duration',str(a.duration),'--time-scale',str(a.time_scale),'--map',a.map,'--seed',str(seed),'--bfme2',str(a.bfme2),'--rotwk',str(a.rotwk),'--positions',','.join(map(str,a.position_list)),'--controllers',','.join(a.controller_list)]
        if a.factions:cmd+=['--factions',a.factions]
        else:cmd+=['--faction1',a.faction1,'--faction2',a.faction2]
        if a.headless:cmd+=['--headless']
        if a.engine_package:cmd+=['--engine-package',str(a.engine_package)]
        if a.model_config:cmd+=['--model-config',str(a.model_config)]
        if a.timeout:cmd+=['--timeout',str(a.timeout)]
        began=time.perf_counter()
        with (folder/'worker.log').open('w',encoding='utf-8') as log:
            with guard:
                if cancel.is_set():raise RuntimeError('Batch cancelled')
                proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' and a.headless else 0);active[index]=proc
            try:
                code=proc.wait(timeout=(a.timeout or max(120.,60+3*a.duration/a.time_scale))+45)
            except BaseException:stop(proc,log);raise
            finally:
                with guard:active.pop(index,None)
        r=read(out) if out.exists() else {'ok':False,'error':'Worker produced no result','seed':seed}
        if code:r['ok']=False
        r.update(result_file=str(out),worker_wall_seconds=time.perf_counter()-began,worker_exit_code=code)
        return r
    results=[];futures={};pool=ThreadPoolExecutor(max_workers=control.parallel)
    try:
        for i in range(control.matches):futures[pool.submit(worker,i)]=i
        for future in as_completed(futures):
            index=futures[future]
            try:r=future.result()
            except Exception as error:r={'ok':False,'error':str(error),'match_index':index}
            r['match_index']=index;results.append(r);write(root/'summary.json',summary(sorted(results,key=lambda r:r['match_index']),time.perf_counter()-start))
    except BaseException:
        cancel.set()
        with guard:
            for proc in active.values():stop(proc)
        for future in futures:future.cancel()
        raise
    finally:
        pool.shutdown(wait=True,cancel_futures=True)
        batch_lock.unlink(missing_ok=True)
    result=summary(sorted(results,key=lambda r:r['match_index']),time.perf_counter()-start);write(root/'summary.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='results'},ensure_ascii=False))
    return 0 if not result['failed'] else 1
if __name__=='__main__':sys.exit(main())
