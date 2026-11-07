"""Shared, versioned economy task, masked observations and fixed-seed evaluation."""
import csv
import functools
import json
from pathlib import Path
import sys
import time
import numpy as np
import gymnasium as gym
from gymnasium import spaces
HERE=Path(__file__).resolve().parent;LOCAL=HERE.parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(LOCAL))
from gym_env import OpenBFMEEnv
from run_match import engine_path
from decision_net import features
from spend_policy import spend_features
from feature_cache import begin,end

TASK=HERE/'economy_task.json'
CSV_FIELDS=['kind','policy','train_steps','seed','episodes','reward','reward_std','income','buildings','army_value','terminated','truncated','simulation_seconds','wall_seconds']

def task_config(path=TASK):
    task=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if task.get('schema')!='economy-task-v1' or len(task.get('evaluation_seeds',[]))!=5 or len(set(task['evaluation_seeds']))!=5:raise ValueError('Economy task requires five distinct fixed evaluation seeds')
    return task

class EconomyObservation(gym.Wrapper):
    """Numerical codec wrapper only; never changes the existing game/network.

SB3 rejects nested Dict observations and one-hot template IDs are enormous.
Use the existing 385/383 candidate encoders, padded in their original order.
The experiment uses a separate stock SB3 MLP, not the existing GRU checkpoint.
"""
    def __init__(self,env,excluded_seeds=()):
        super().__init__(env)
        self.excluded_seeds=set(excluded_seeds)
        self._episode_return=0.;self._episode_length=0;self._episode_components={};self._episode_started=time.monotonic()
        self.tactical_width=len(features({}, {'id':'none'}));self.spend_width=len(spend_features({}, {'id':'none','kind':'wait'}))
        width=self.tactical_width+64*self.tactical_width+65*self.spend_width
        self.observation_space=spaces.Box(-np.inf,np.inf,(width,),np.float32)

    def encode(self,info):
        obs=info['policy_observation'];choices=self.env._choices
        token=begin(True)
        try:
            tactical=np.zeros((64,self.tactical_width),np.float32);spend=np.zeros((65,self.spend_width),np.float32)
            for i,c in enumerate(choices['tactical']):tactical[i]=features(obs,c)
            for i,c in enumerate(choices['spend']):spend[i]=spend_features(obs,c)
            result=np.concatenate([features(obs,{'id':'none'}),tactical.ravel(),spend.ravel()])
        finally:end(token)
        if not np.isfinite(result).all():raise ValueError('Nonfinite economy observation')
        return result

    def reset(self,**kwargs):
        if self.excluded_seeds:
            seed=kwargs.get('seed')
            if seed is None:
                seed=int(self.env.np_random.integers(0,2147483648))
                while seed in self.excluded_seeds:seed=int(self.env.np_random.integers(0,2147483648))
                kwargs['seed']=seed
            if seed in self.excluded_seeds:raise ValueError('Held-out seed cannot enter training')
        _,info=self.env.reset(**kwargs)
        self._episode_return=0.;self._episode_length=0;self._episode_components={};self._episode_started=time.monotonic()
        return self.encode(info),info

    def step(self,action):
        _,reward,terminated,truncated,info=self.env.step(action)
        # Monitor-equivalent episode statistics only; reward passed through unchanged.
        self._episode_return+=float(reward);self._episode_length+=1
        for key,value in info.get('reward_components',{}).items():
            self._episode_components[key]=self._episode_components.get(key,0.)+float(value)
        observation=self.encode(info)
        if terminated or truncated:
            result=self.env._backend.result
            row=next(r for r in result['gym_reward_state']['players'] if r['player']==info['player'])
            info['economy_metrics']={key:row[key] for key in ('total_income','building_count','army_value')}
            info['episode']={'r':self._episode_return,'l':self._episode_length,'t':time.monotonic()-self._episode_started,
                             'reward_income':self._episode_components.get('potential_income',0.),
                             'reward_buildings':self._episode_components.get('potential_buildings',0.),
                             'reward_army':self._episode_components.get('potential_army',0.),
                             'reward_result':self._episode_components.get('terminal',0.)+self._episode_components.get('truncated_result',0.)}
        return observation,reward,terminated,truncated,info

    def action_masks(self):return self.env.action_masks()

def make_env(task,workspace,engine,rank=0,smoke=False,training=False):
    options={k:task[k] for k in ('duration','map_name','factions','positions','agent_index','native_difficulty','time_scale','a','b','c','gamma')}
    if task.get('reuse_package',False):options['runtime_cache']=Path(workspace)/('worker-%02d'%rank)/'.package-cache'
    if task.get('persistent_games',False):options['persistent_games']=True
    env=OpenBFMEEnv(**options,workspace_root=Path(workspace)/('worker-%02d'%rank),engine_package=engine,
                   timeout=60 if smoke else 900,episode_timeout=180 if smoke else 3600)
    return EconomyObservation(env,task.get('training_excluded_seeds',task['evaluation_seeds']) if training else ())

def env_factory(task,workspace,engine,rank=0,smoke=False):
    return functools.partial(make_env,task,workspace,engine,rank,smoke,True)

def init_csv(path):
    with Path(path).open('x',newline='',encoding='utf-8') as f:csv.DictWriter(f,fieldnames=CSV_FIELDS).writeheader()

def evaluate(task,workspace,engine,csv_path,*,policy='random',model=None,train_steps=0):
    """Exact same five seeds/settings/CSV for random and mask-aware PPO inference."""
    rows=[];started=time.monotonic()
    for seed in task['evaluation_seeds']:
        env=make_env(task,Path(workspace)/str(seed),engine)
        total=0.;began=time.monotonic()
        try:
            observation,info=env.reset(seed=seed)
            while True:
                if model is None:action=env.unwrapped.sample_action()
                else:action,_=model.predict(observation,deterministic=True,action_masks=env.action_masks())
                observation,reward,terminated,truncated,info=env.step(action);total+=reward
                if terminated or truncated:break
            metrics=info['economy_metrics']
            rows.append(dict(kind='episode',policy=policy,train_steps=train_steps,seed=seed,episodes=1,reward=total,reward_std='',
                income=metrics['total_income'],buildings=metrics['building_count'],army_value=metrics['army_value'],
                terminated=int(terminated),truncated=int(truncated),simulation_seconds=info['elapsed_seconds'],wall_seconds=time.monotonic()-began))
        finally:env.close()
    mean={k:float(np.mean([r[k] for r in rows])) for k in ('reward','income','buildings','army_value','simulation_seconds')}
    mean.update(kind='mean',policy=policy,train_steps=train_steps,seed='',episodes=len(rows),reward_std=float(np.std([r['reward'] for r in rows])),
                terminated=sum(r['terminated'] for r in rows),truncated=sum(r['truncated'] for r in rows),wall_seconds=time.monotonic()-started)
    with Path(csv_path).open('a',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=CSV_FIELDS);writer.writerows(rows+[mean]);f.flush()
    return mean

def write_config(path,data):Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
