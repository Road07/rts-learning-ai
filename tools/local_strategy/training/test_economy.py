"""Codec/mask/evaluation CSV tests without native games or model training."""
import csv
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from economy_common import task_config,EconomyObservation,init_csv,evaluate,ROOT
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from gym_env import OpenBFMEEnv
from test_gym_env import BackendFixture,RulesFixture

class EconomyChecks(unittest.TestCase):
    def test_monitor_equivalent_reward_components_and_reset(self):
        base=OpenBFMEEnv(_backend_factory=BackendFixture,_rules=RulesFixture())
        env=EconomyObservation(base);env.reset(seed=3);original=base._backend.step
        def step(answer):
            packet=original(answer)
            if packet['done']:base._backend.result={'gym_reward_state':packet['snapshot']['reward_state']}
            return packet
        base._backend.step=step;total=0.;parts={}
        for index in range(4):
            _,reward,terminated,truncated,info=env.step([0,0]);total+=reward
            for key,value in info['reward_components'].items():parts[key]=parts.get(key,0.)+value
            if index<3:self.assertNotIn('episode',info)
        self.assertEqual(info['episode']['r'],total);self.assertEqual(info['episode']['l'],4)
        self.assertEqual(info['episode']['reward_income'],parts['potential_income'])
        self.assertEqual(info['episode']['reward_result'],parts['terminal']+parts['truncated_result'])
        env.reset(seed=3);self.assertEqual(env._episode_length,0);self.assertEqual(env._episode_return,0.);env.close()

    def test_versioned_task_easy_far_180(self):
        task=task_config();self.assertEqual(task['duration'],180);self.assertEqual(task['native_difficulty'],'easy')
        self.assertEqual(task['positions'],[0,5]);self.assertEqual(len(task['evaluation_seeds']),5)

    def test_flat_codec_preserves_masks_and_uses_no_privileged_metrics(self):
        base=OpenBFMEEnv(_backend_factory=BackendFixture,_rules=RulesFixture())
        env=EconomyObservation(base);obs,info=env.reset(seed=3)
        self.assertEqual(obs.shape,(49920,));self.assertEqual(obs.dtype,np.float32)
        self.assertTrue(env.observation_space.contains(obs));np.testing.assert_array_equal(env.action_masks(),base.action_masks())
        info['reward_components']={'total':9999};again=env.encode(info);np.testing.assert_array_equal(obs,again);env.close()

    def test_heldout_training_seed_rejected_before_game(self):
        env=EconomyObservation(OpenBFMEEnv(_backend_factory=BackendFixture,_rules=RulesFixture()),[17])
        with self.assertRaises(ValueError):env.reset(seed=17)
        self.assertIsNone(env.unwrapped._backend);env.close()

    def test_five_fixed_seeds_and_same_csv_for_random_and_masked_model(self):
        seeds=[]
        class Stub:
            unwrapped=None
            def __init__(self):self.unwrapped=self
            def reset(self,seed):seeds.append(seed);return np.zeros(2),{}
            def sample_action(self):return np.array([0,0])
            def action_masks(self):return np.ones(129,bool)
            def step(self,a):return np.zeros(2),.25,False,True,{'elapsed_seconds':180,'economy_metrics':{'total_income':100,'building_count':3,'army_value':0}}
            def close(self):pass
        class Policy:
            def predict(self,obs,deterministic,action_masks):
                self.checked=deterministic and len(action_masks)==129;return np.array([0,0]),None
        task=task_config()
        with tempfile.TemporaryDirectory(dir=ROOT/'AI-Test-Sahasi') as d:
            path=Path(d)/'eval.csv';init_csv(path)
            with patch('economy_common.make_env',side_effect=lambda *a,**k:Stub()):
                random=evaluate(task,d,'unused',path)
                model=Policy();trained=evaluate(task,d,'unused',path,policy='maskable_ppo',model=model,train_steps=20000)
            with path.open(encoding='utf-8') as f:rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),12);self.assertEqual(seeds,task['evaluation_seeds']*2)
            self.assertEqual(random['reward'],trained['reward']);self.assertTrue(model.checked)
            self.assertEqual(rows[-1]['kind'],'mean');self.assertEqual(rows[-1]['train_steps'],'20000')

if __name__=='__main__':unittest.main()
