"""Potential algebra, terminal masks, privilege isolation and malformed telemetry."""
import copy
import tempfile
from pathlib import Path
import json
import unittest
from gymnasium.utils.env_checker import data_equivalence
from gym_env import OpenBFMEEnv
from gym_reward import PotentialConfig,PotentialReward
from test_gym_env import BackendFixture,RulesFixture

def state(frame=0,income=0,buildings=1,army=100):
    return {'ok':True,'schema':'gym-reward-state-v1','frame':frame,'players':[
        {'player':3,'team':1,'total_income':income,'building_count':buildings,'army_value':army,'army_complete':True},
        {'player':4,'team':2,'total_income':0,'building_count':1,'army_value':100,'army_complete':True}]}

class RewardChecks(unittest.TestCase):
    def test_exact_components_and_truncated_score(self):
        reward=PotentialReward(PotentialConfig(.001,.01,.0001,.9));reward.reset(state(),3,0)
        parts,_=reward.step(state(25,100,2,200),3,25,0.,False,True)
        self.assertAlmostEqual(parts['potential_income'],.09);self.assertAlmostEqual(parts['potential_buildings'],.009)
        self.assertAlmostEqual(parts['potential_army'],.009);self.assertAlmostEqual(parts['truncated_result'],.12)
        self.assertAlmostEqual(parts['total'],.228)

    def test_true_terminal_absorbs_potential_but_keeps_win_loss(self):
        reward=PotentialReward(PotentialConfig(.001,0,0,.99));reward.reset(state(income=200),3,0)
        parts,details=reward.step(state(30,income=900),3,30,1.,True,False)
        self.assertEqual(parts['terminal'],1.);self.assertEqual(parts['truncated_result'],0.)
        self.assertAlmostEqual(parts['shaping'],-.2);self.assertAlmostEqual(parts['total'],.8)
        self.assertEqual(sum(details['effective_potential_new'].values()),0.)

    def test_clipping_and_zero_weight_compatibility(self):
        for income,expected in ((100000,1.),(0,-1.)):
            s=state(30,income=income);s['players'][1]['total_income']=50000
            reward=PotentialReward(PotentialConfig());reward.reset(state(),3,0)
            parts,_=reward.step(s,3,30,0.,False,True);self.assertEqual(parts['truncated_result'],expected)
        for terminal in (-1.,0.,1.):
            reward=PotentialReward(PotentialConfig(0,0,0));reward.reset(state(),3,0)
            parts,_=reward.step(state(30,10000,20,99999),3,30,terminal,terminal!=0,terminal==0)
            self.assertEqual(parts['total'],terminal)

    def test_no_opponents_bias_from_team_size_and_no_allied_credit(self):
        s=state();s['players'] += [dict(s['players'][1],player=5),dict(s['players'][1],player=6),dict(s['players'][0],player=7,total_income=999999)]
        reward=PotentialReward(PotentialConfig());self.assertEqual(sum(reward.reset(s,3,0).values()),0.)

    def test_discounted_shaping_telescopes(self):
        gamma=.9;reward=PotentialReward(PotentialConfig(.001,0,0,gamma));reward.reset(state(income=200),3,0)
        rewards=[]
        for i,income in enumerate((300,100,500),1):
            parts,_=reward.step(state(i*25,income=income),3,i*25,0.,i==3,False);rewards.append(parts['shaping'])
        self.assertAlmostEqual(sum(gamma**i*r for i,r in enumerate(rewards)),-.2)

    def test_missing_data_and_changed_roster_are_errors(self):
        for mutate in (lambda s:s.update(frame=99),lambda s:s['players'][0].update(army_complete=False),lambda s:s['players'][0].update(army_value=float('nan'))):
            reward=PotentialReward(PotentialConfig());reward.reset(state(),3,0);bad=state(25);mutate(bad)
            with self.assertRaises(ValueError):reward.step(bad,3,25,0.,False,False)
        for gamma in (float('nan'),-1,1.1):
            with self.assertRaises(ValueError):PotentialConfig(gamma=gamma)

    def test_hidden_reward_truth_changes_reward_not_observation(self):
        env=OpenBFMEEnv(_backend_factory=BackendFixture,_rules=RulesFixture());env.reset(seed=7)
        packet=env._backend.packet();packet['snapshot']['observation']['decision_frame']=25
        packet['snapshot']['observation']['entity_state']['frame']=25;packet['snapshot']['reward_state']=state(25)
        first,_=env._encode(packet)
        packet['snapshot']['reward_state']['players'][1]['army_value']=99999
        env._frame=0;second,info=env._encode(packet)
        self.assertTrue(data_equivalence(first,second));self.assertNotIn('reward_state',info)
        self.assertNotIn('reward_state',info['policy_observation']);env.close()

    def test_components_are_logged_without_private_state_in_info(self):
        root=Path(__file__).resolve().parents[3]/'AI-Test-Sahasi'
        with tempfile.TemporaryDirectory(dir=root) as folder:
            class LoggingBackend(BackendFixture):
                def __init__(self,**kwargs):super().__init__(**kwargs);self.directory=Path(folder)
            env=OpenBFMEEnv(_backend_factory=LoggingBackend,_rules=RulesFixture());env.reset(seed=1)
            _,reward,_,_,info=env.step([0,0]);env.close()
            rows=[json.loads(line) for line in (Path(folder)/'reward.jsonl').read_text().splitlines()]
            self.assertEqual(rows[1]['components'],info['reward_components']);self.assertEqual(reward,info['reward_components']['total'])
            self.assertIn('privileged_reward_state',rows[1]);self.assertNotIn('privileged_reward_state',info)

if __name__=='__main__':unittest.main()
