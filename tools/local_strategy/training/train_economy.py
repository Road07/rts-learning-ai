"""Separate stock MaskablePPO economy experiment. Never deploys to the game model.

Full default: 200000 transitions, eight native workers, 180-s episodes.
--smoke alone authorizes only 256 transitions with a two-minute wall budget.
"""
import os
os.environ.setdefault('OMP_NUM_THREADS','1');os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import argparse
import math
from pathlib import Path
import time
STARTED=time.monotonic()
from economy_common import ROOT,TASK,task_config,engine_path,env_factory,init_csv,evaluate,write_config
from economy_resources import available_commit,worker_budget,light_worker_budget,close_vector
from economy_memory import system_memory

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--task',type=Path,default=TASK)
    p.add_argument('--output',type=Path,default=ROOT/'AI-Egitim/economy-maskable-ppo')
    p.add_argument('--timesteps',type=int,default=200000);p.add_argument('--parallel',type=int,default=8)
    p.add_argument('--eval-every',type=int,default=20000);p.add_argument('--device',default='cpu')
    p.add_argument('--light-workers',action='store_true',help='Opt-in environment workers without importing PyTorch')
    p.add_argument('--reuse-package',action='store_true',help='Opt-in package cache; game process is still restarted')
    p.add_argument('--persistent-games',action='store_true',help='Reuse native process; replace GameWorld/controller every episode')
    p.add_argument('--time-scale',type=float,help='Native pacing target only; logic step and decision frequency remain fixed')
    p.add_argument('--smoke',action='store_true');args=p.parse_args()
    if not 1<=args.parallel<=32 or args.timesteps<1 or args.eval_every<1:p.error('Invalid training/evaluation budget')
    if args.time_scale is not None and (not math.isfinite(args.time_scale) or not .01<=args.time_scale<=1000):p.error('Invalid time scale')
    if args.smoke:args.timesteps=256
    requested_parallel=args.parallel
    free_commit=available_commit()
    selection_memory=system_memory() if args.light_workers else None
    args.parallel=light_worker_budget(args.parallel,selection_memory) if args.light_workers else worker_budget(args.parallel,free_commit)
    if args.persistent_games:args.parallel=min(args.parallel,3) # persistent native allocator retained more memory in the probe
    print('Worker budget: requested=%d effective=%d available_commit_bytes=%s' % (requested_parallel,args.parallel,free_commit),flush=True)
    args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=False)
    task=task_config(args.task);engine=str(engine_path())
    task['reuse_package']=args.reuse_package
    task['persistent_games']=args.persistent_games
    if args.time_scale is not None:task['time_scale']=args.time_scale
    import json
    runtime=json.loads((ROOT/'AI-Yeni-Model/ai-service/runtime.json').read_text(encoding='utf-8'))
    reserved=set(task['evaluation_seeds'])
    if runtime.get('benchmark_suite'):
        reserved.update(int(row['seed']) for row in json.loads((Path(runtime['benchmark_suite'])/'suite.json').read_text(encoding='utf-8'))['plan'])
    task['training_excluded_seeds']=sorted(reserved)
    if reserved & set(range(task['training_seed'],task['training_seed']+args.parallel)):
        p.error('Training and evaluation seeds overlap')
    init_csv(args.output/'evaluation.csv')
    status={'status':'starting','task':task,'engine':engine,'smoke':args.smoke,'requested_transitions':args.timesteps,
            'parallel':args.parallel,'requested_parallel':requested_parallel,'available_commit_bytes':free_commit,'eval_every':args.eval_every,'algorithm':'sb3-contrib MaskablePPO',
            'policy':'separate stock MlpPolicy, existing 385/383 observation codecs',
            'existing_gru_architecture_changed':False,'automatic_activation':False,'evaluation_horizon_seconds':task['duration']}
    status.update(light_workers=args.light_workers,reuse_package=args.reuse_package,persistent_games=args.persistent_games)
    status['memory_at_selection']=selection_memory
    write_config(args.output/'run.json',status)
    import torch
    from sb3_contrib import MaskablePPO
    from stable_baselines3.common.vec_env import SubprocVecEnv
    from stable_baselines3.common.callbacks import BaseCallback
    torch.set_num_threads(1)

    class PeriodicEvaluation(BaseCallback):
        def __init__(self):super().__init__();self.next_eval=args.eval_every;self.evaluations=0;self.stopped_by_budget=False
        def _on_step(self):
            if args.light_workers and system_memory()['free_physical']<3.25*1024**3:
                raise MemoryError('Training stopped to preserve at least 3 GiB physical RAM')
            for info in self.locals.get('infos',[]):
                episode=info.get('episode')
                if episode:
                    for name in ('income','buildings','army','result'):
                        self.logger.record_mean('reward/ep_'+name,episode['reward_'+name])
            # Reserve cleanup/save time. No fixed rollout is allowed to turn this
            # smoke request into a normal 200k training run.
            if args.smoke and time.monotonic()-STARTED>100:
                self.stopped_by_budget=True;return False
            return True
        def _evaluate_if_due(self):
            if args.smoke or self.num_timesteps<self.next_eval:return
            mean=evaluate(task,args.output/'evaluation-episodes'/str(self.num_timesteps),engine,args.output/'evaluation.csv',
                          policy='maskable_ppo',model=self.model,train_steps=self.num_timesteps)
            self.model.save(args.output/('checkpoint-%09d'%self.num_timesteps))
            for key in ('reward','income','buildings','army_value'):self.logger.record('eval/mean_'+key,mean[key])
            self.logger.record('eval/reward_std',mean['reward_std']);self.logger.dump(self.num_timesteps)
            self.evaluations+=1
            while self.next_eval<=self.num_timesteps:self.next_eval+=args.eval_every
        def _on_rollout_start(self):self._evaluate_if_due()
        def _on_training_end(self):self._evaluate_if_due()

    vector=None;callback=PeriodicEvaluation()
    try:
        factories=[env_factory(task,args.output/'training-episodes',engine,i,args.smoke) for i in range(args.parallel)]
        if args.light_workers:
            from light_economy_vec import LightEconomyVecEnv
            vector=LightEconomyVecEnv(factories)
        else:vector=SubprocVecEnv(factories,start_method='spawn')
        vector.seed(task['training_seed'])
        n_steps=32 if args.smoke else 100
        batch=math.gcd(64 if args.smoke else 200,n_steps*args.parallel)
        model=MaskablePPO('MlpPolicy',vector,n_steps=n_steps,batch_size=batch,n_epochs=1 if args.smoke else 4,
            gamma=task['gamma'],learning_rate=3e-4,seed=task['training_seed'],device=args.device,verbose=1,
            tensorboard_log=str(args.output/'tensorboard'))
        model.learn(total_timesteps=args.timesteps,callback=callback,tb_log_name='smoke' if args.smoke else 'economy')
        model.save(args.output/'final_model')
        elapsed=time.monotonic()-STARTED
        status.update(status='smoke_budget_reached' if callback.stopped_by_budget else 'complete',transitions=model.num_timesteps,
            optimizer_updates=int(model._n_updates),evaluations=callback.evaluations,wall_seconds=elapsed,
            transitions_per_second=model.num_timesteps/elapsed,full_training_run=not args.smoke and args.timesteps>=200000,
            note='Smoke does not run the 5x180s evaluation; first full evaluation is at 20000 transitions.')
        write_config(args.output/'run.json',status)
        print(status,flush=True)
    except BaseException as error:
        status.update(status='failed',error=repr(error),wall_seconds=time.monotonic()-STARTED)
        write_config(args.output/'run.json',status);raise
    finally:
        close_vector(vector)
        status['wall_seconds_including_close']=time.monotonic()-STARTED
        write_config(args.output/'run.json',status)

if __name__=='__main__':main()
