"""One six-simulation-second Gym episode. No training/activation/fixture units."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from gym_env import OpenBFMEEnv

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    env=OpenBFMEEnv(duration=6.,workspace_root=args.output)
    try:
        obs,info=env.reset(seed=271026);frames=[info['frame']];actions=[];rewards=[]
        while True:
            # Explicit policy supplied by this smoke caller: keep orders, no purchase.
            # The environment never substitutes these for an invalid agent action.
            action=[0,0];actions.append(action)
            obs,reward,terminated,truncated,info=env.step(action)
            frames.append(info['frame']);rewards.append(reward)
            if terminated or truncated:break
        result={'ok':env.observation_space.contains(obs),'frames':frames,'actions':actions,'rewards':rewards,
                'terminated':terminated,'truncated':truncated,'native_result':str(env._backend.result_path),
                'final_observation_frame':info['frame'],'training_performed':False,'activated':False}
        (args.output/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
    finally:env.close()

if __name__=='__main__':main()
