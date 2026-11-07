"""Five bounded random-policy episodes, including one exact-seed determinism repeat."""
import argparse
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from gym_env import OpenBFMEEnv
from run_match import engine_path

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seconds',type=int,default=6);args=parser.parse_args()
    if not 1<=args.seconds<=1800:parser.error('seconds must be 1..1800')
    args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=False)
    seeds=[271026,271027,271028,271029,271026];engine=engine_path();runs=[];hashes=[]
    for i,seed in enumerate(seeds):
        env=OpenBFMEEnv(duration=args.seconds,engine_package=engine,workspace_root=args.output/('match-%02d'%i))
        actions=[];steps=[];totals={}
        try:
            obs,info=env.reset(seed=seed)
            while True:
                action=env.sample_action()
                actions.append({'frame':info['frame'],'indices':action.tolist(),
                    'ids':[info['action_ids'][h][int(a)] for h,a in zip(('tactical','spend'),action)]})
                obs,reward,terminated,truncated,info=env.step(action)
                assert env.observation_space.contains(obs)
                parts=info['reward_components'];assert reward==parts['total']
                for key,value in parts.items():totals[key]=totals.get(key,0.)+value
                steps.append({'frame':info['frame'],'components':parts})
                if terminated or truncated:break
            result=read(env._backend.result_path)
            assert result['ok'] and result['script_errors']==0 and result['logic_frames']==args.seconds*5
            rows=[json.loads(line) for line in Path(str(env._backend.result_path)+'.hashes.jsonl').read_text().splitlines()]
            hashes.append(rows)
            row={'index':i,'seed':seed,'simulation_seconds':result['duration_seconds'],'totals':totals,'steps':steps,
                 'actions':actions,'terminated':terminated,'truncated':truncated,'state_hash':result['state_hash'],
                 'result_path':str(env._backend.result_path),'reward_log':str(env._backend.directory/'reward.jsonl'),
                 'finite':all(math.isfinite(v) for v in totals.values()),'abs_total_at_most_2':abs(totals['total'])<=2}
            runs.append(row);print(json.dumps({'match':i,'seed':seed,'totals':totals}),flush=True)
        finally:env.close()
    first,last=runs[0],runs[-1]
    deterministic=hashes[0]==hashes[-1] and first['actions']==last['actions'] and first['steps']==last['steps']
    summary={'schema':'gym-dense-check-v1','runs':runs,'repeat_seed_deterministic':deterministic,
             'matching_native_frames':len(hashes[0]) if hashes[0]==hashes[-1] else 0,
             'reward_range':[min(r['totals']['total'] for r in runs),max(r['totals']['total'] for r in runs)],
             'plausibility_criterion':'Finite episode total with abs(total)<=2 in this short check; not a global reward bound',
             'all_plausible':all(r['finite'] and r['abs_total_at_most_2'] for r in runs),
             'training_performed':False,'activated':False,'engine':str(engine)}
    (args.output/'verification.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    if not deterministic or not summary['all_plausible']:raise RuntimeError('Determinism/reward plausibility failed; inspect verification.json')
    return 0

if __name__=='__main__':sys.exit(main())
