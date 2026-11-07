"""USER-RUN ONLY: fixed-seed legacy/light+cache equivalence, no training.

Starts real games. Run only AFTER the current training has stopped.
Compares masks/actions/flat observations/rewards plus every native frame hash.
This is a short regression, not proof of long-match equivalence or speedup.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from economy_common import ROOT, task_config, engine_path, env_factory, write_config
from economy_resources import close_vector


class DirectComparison:
    """No auto-reset: exercise three requested seeds in one native session."""
    def __init__(self,factory):self.env=factory();self.seed_value=None
    def seed(self,seed):self.seed_value=seed
    def reset(self):return self.env.reset(seed=self.seed_value)[0][None,...]
    def env_method(self,name):return [getattr(self.env,name)()]
    def step(self,actions):
        obs,reward,terminated,truncated,info=self.env.step(actions[0]);done=terminated or truncated
        info['TimeLimit.truncated']=truncated and not terminated
        if done:info['terminal_observation']=obs
        return obs[None,...],np.asarray([reward]),np.asarray([done]),[info]
    def close(self):self.env.close()


def digest(value):
    value=np.asarray(value)
    return hashlib.sha256(value.dtype.str.encode()+str(value.shape).encode()+value.tobytes()).hexdigest()


def run(mode,root,task,seeds,engine):
    from stable_baselines3.common.vec_env import SubprocVecEnv
    from light_economy_vec import LightEconomyVecEnv
    work=root/mode;task=dict(task,reuse_package=mode=='fast')
    factory=env_factory(task,work,engine,0)
    direct=task.get('direct_comparison',False)
    vector=DirectComparison(factory) if direct else LightEconomyVecEnv([factory]) if mode=='fast' else SubprocVecEnv([factory],start_method='spawn')
    cases=[]
    try:
        for seed in seeds:
            existing=set(work.glob('worker-00/e-*/result.json'))
            vector.seed(seed);observation=vector.reset();rng=np.random.default_rng(seed)
            trace=[{'observation':digest(observation)}]
            while True:
                masks=vector.env_method('action_masks')[0]
                action=[int(rng.choice(np.flatnonzero(masks[:64]))),int(rng.choice(np.flatnonzero(masks[64:])))]
                observation,reward,done,infos=vector.step(np.asarray([action]))
                info=infos[0];final=info['terminal_observation'][None,...] if done[0] else observation
                trace.append({'masks':digest(masks),'action':action,'observation':digest(final),
                              'reward':float(reward[0]),'components':info.get('reward_components'),
                              'done':bool(done[0]),'truncated':info.get('TimeLimit.truncated'),
                              'frame':info['frame'],'action_ids':info['action_ids']})
                if done[0]:break
            matches=[]
            for path in set(work.glob('worker-00/e-*/result.json'))-existing:
                result=json.loads(path.read_text(encoding='utf-8'))
                if result.get('ok') and int(result['seed'])==seed:matches.append((path,result))
            if len(matches)!=1:raise RuntimeError('Missing or ambiguous native episode result')
            path,result=matches[0]
            if not result.get('persistent_session') and result.get('process_exit_code')!=0:raise RuntimeError('Unclean native exit')
            cases.append({'seed':seed,'trace':trace,'native_hashes_sha256':hashlib.sha256(path.with_name('result.json.hashes.jsonl').read_bytes()).hexdigest(),
                          'state_hash':result['state_hash'],'players':result['players'],'reward_state':result['gym_reward_state'],
                          'end_reason':result['end_reason']})
    finally:
        if direct:vector.close()
        else:close_vector(vector)
    return cases


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=6);p.add_argument('--seeds',default='615000,1320713198,615000')
    p.add_argument('--persistent-games',action='store_true')
    args=p.parse_args();args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=False)
    task=task_config();task['duration']=args.seconds;engine=str(engine_path());seeds=[int(s) for s in args.seeds.split(',')]
    results={};times={}
    for mode in ('legacy','fast'):
        task['persistent_games']=args.persistent_games and mode=='fast'
        task['direct_comparison']=args.persistent_games
        start=time.monotonic();results[mode]=run(mode,args.output,task,seeds,engine);times[mode]=time.monotonic()-start
        write_config(args.output/(mode+'.json'),results[mode])
    passed=results['legacy']==results['fast']
    report={'passed':passed,'seeds':seeds,'seconds':args.seconds,'wall_seconds':times,'training_performed':False,
            'checks':['masks','actions','observations','reward components','terminal/truncation','every native frame hash','final statistics'],
            'persistent_game_process':args.persistent_games,'note':'Short regression, not a training speed benchmark.'}
    write_config(args.output/'verification.json',report);print(json.dumps(report,indent=2));return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
