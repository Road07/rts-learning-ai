"""Bounded real-episode throughput/memory probe, never performs PPO updates."""
import argparse
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import json
from pathlib import Path
import time
import numpy as np
from economy_common import task_config,engine_path,env_factory,write_config
from economy_resources import close_vector
from economy_memory import Sampler,system_memory


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=['legacy','light','cache','session'],required=True)
    p.add_argument('--parallel',type=int,default=3);p.add_argument('--rounds',type=int,default=1)
    p.add_argument('--seconds',type=float,default=180);p.add_argument('--speed',type=float,default=10)
    p.add_argument('--memory-proof',type=Path)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if not 1<=args.parallel<=5 or not 1<=args.rounds<=2:p.error('Probe limited to 1..5 environments and 1..2 rounds')
    if args.mode=='session' and args.parallel>3:p.error('Persistent session probe capped at 3: retained allocator memory is higher')
    memory=system_memory()
    # Five-game probes only after the three-game measurement has been inspected.
    reserve=3*1024**3;budget=(1.5 if args.mode!='legacy' else 3)*1024**3
    proven=False
    if args.memory_proof and args.mode!='legacy':
        proof=json.loads(args.memory_proof.read_text(encoding='utf-8'));sample=proof['memory'];extra=max(0,args.parallel-proof['parallel'])
        proven=(sample['minimum_free']['free_physical']-extra*sample['peak_environment_ws']>=reserve+512*1024**2
                and sample['minimum_free']['free_commit']-extra*sample['peak_environment_private']>=2*1024**3
                and memory['free_physical']>=reserve+args.parallel*1024**3)
    if not proven and min(memory['free_physical'],memory['free_commit'])<reserve+budget*args.parallel:
        p.error('Insufficient memory for requested bounded probe with 3 GiB reserve')
    args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=False)
    task=task_config();task.update(duration=args.seconds,time_scale=args.speed,reuse_package=args.mode in ('cache','session'),persistent_games=args.mode=='session')
    from stable_baselines3.common.vec_env import SubprocVecEnv
    import torch
    torch.set_num_threads(1)
    from light_economy_vec import LightEconomyVecEnv
    started=time.monotonic();sampler=Sampler();sampler.start();vector=None;rounds=[]
    try:
        factories=[env_factory(task,args.output/'episodes',str(engine_path()),rank) for rank in range(args.parallel)]
        vector=SubprocVecEnv(factories,start_method='spawn') if args.mode=='legacy' else LightEconomyVecEnv(factories)
        sampler.worker_roots=[process.pid for process in vector.processes]
        vector.seed(task['training_seed']);vector.reset();initial=time.monotonic()-started
        random=[np.random.default_rng(91000+i) for i in range(args.parallel)]
        for index in range(args.rounds):
            began=time.monotonic();count=0;steps=0
            while count<args.parallel:
                masks=vector.env_method('action_masks');actions=[]
                for i,mask in enumerate(masks):
                    actions.append([int(random[i].choice(np.flatnonzero(mask[:64]))),int(random[i].choice(np.flatnonzero(mask[64:])))])
                _,_,dones,_=vector.step(np.asarray(actions));count+=int(sum(dones));steps+=args.parallel
                if time.monotonic()-started>210:raise TimeoutError('Probe exceeded 210-second wall budget')
                if sampler.minimum.get('free_physical',reserve)<reserve:raise RuntimeError('Physical free RAM dropped below 3 GiB; probe stopped')
            elapsed=time.monotonic()-began
            rounds.append({'completed':count,'transitions':steps,'wall_seconds':elapsed,'includes_autoreset':True})
        wall=time.monotonic()-started
    finally:
        close_vector(vector);sample=sampler.finish()
    completed=sum(row['completed'] for row in rounds);steps=sum(row['transitions'] for row in rounds)
    results=[]
    for path in (args.output/'episodes').glob('worker-*/e-*/result.json'):
        result=json.loads(path.read_text(encoding='utf-8'))
        if result.get('ok'):
            results.append({'seed':result['seed'],'state_hash':result['state_hash'],'chain':result['state_hash_chain_sha256'],
                            'simulation':result['simulation_wall_seconds'],'engine':result['engine_wall_seconds'],'runner':result['wall_seconds']})
    report={'mode':args.mode,'parallel':args.parallel,'seconds':args.seconds,'speed':args.speed,'rounds':rounds,
            'initial_seconds':initial,'wall_seconds':wall,'completed':completed,'matches_per_hour_estimate':completed*3600/wall,
            'transitions_per_second':steps/wall,'memory':sample,'results':results,'training_performed':False,
            'note':'Masked random action probe, includes startup and auto-reset; excludes PPO updates and evaluation.'}
    write_config(args.output/'profile.json',report);print(json.dumps(report,indent=2))


if __name__=='__main__':main()
