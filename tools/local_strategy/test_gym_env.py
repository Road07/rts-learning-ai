"""Gym API/lifecycle tests with a synthetic transport; not gameplay/training data."""
import copy
import unittest
import numpy as np
from gymnasium.utils.env_checker import check_env
from gymnasium.error import InvalidAction,ResetNeeded
from gym_env import OpenBFMEEnv
from run_match import arguments

class RulesFixture:
    data={'cards':{},'tables':{}}
    def numeric_card(self,name):return {}
    def attach(self,*unused):return {}

class BackendFixture:
    def __init__(self,**unused):self.frame=0;self.calls=[];self.closed=False;self.result=None
    def reset(self,seed):
        self.frame=0;self.seed=seed;self.closed=False
        return self.packet()
    def packet(self,done=False,won=False,lost=False):
        obs={'model_only':True,'faction':'FactionDwarves','player_index':3,'decision_frame':self.frame,'money':1000,
             'entity_state':{'encoding':'rts-entities-v1','source':'native_fog_filtered','frame':self.frame,'map_extent':{'extent_x':1000,'extent_y':1000},'entities':[]}}
        reward_state={'ok':True,'schema':'gym-reward-state-v1','frame':self.frame,'players':[
            {'player':p,'team':team,'total_income':self.frame,'building_count':1,'army_value':100,'army_complete':True} for p,team in ((3,1),(4,2))]}
        return {'snapshot':{'observation':obs,'reward_state':reward_state,'candidates':[{'id':'defend_'+str(i),'kind':'defend'} for i in range(64)],
                'production_options':[{'id':'train:1:Test:%d:0'%i,'kind':'train','cost':0} for i in range(64)],'won':won,'defeated':lost},
                'done':done,'reason':'victory' if won else 'agent_defeated' if lost else 'duration'}
    def step(self,answer):
        self.calls.append(answer);self.frame+=25
        return self.packet(done=self.frame>=100)
    def close(self):self.closed=True

class GymChecks(unittest.TestCase):
    def env(self,**kwargs):return OpenBFMEEnv(_backend_factory=BackendFixture,_rules=RulesFixture(),**kwargs)
    def test_gymnasium_checker_synthetic_transport(self):
        env=self.env();check_env(env,skip_render_check=True);env.close()
    def test_terminal_and_truncation_keep_final_observation(self):
        for won,lost,terminated,truncated,reward in [(False,False,False,True,0.),(True,False,True,False,1.),(False,True,True,False,-1.)]:
            env=self.env();env.reset(seed=7)
            def final(answer):
                env._backend.frame=30;return env._backend.packet(True,won,lost)
            env._backend.step=final
            obs,r,t,tr,info=env.step([0,0])
            self.assertEqual((r,t,tr),(reward,terminated,truncated));self.assertEqual(info['frame'],30)
            self.assertTrue(env.observation_space.contains(obs))
            with self.assertRaises(ResetNeeded):env.step([0,0])
            env.close();env.close()
    def test_masked_invalid_action_never_sends_command(self):
        env=self.env();env.reset(seed=1);env._choices['tactical']=env._choices['tactical'][:1]
        with self.assertRaises(InvalidAction):env.step([1,0])
        self.assertEqual(env._backend.calls,[]);self.assertEqual(env._frame,0)
        self.assertEqual(env.action_masks().sum(),66);env.close()
    def test_reset_closes_previous_match_and_is_seeded(self):
        env=self.env();first,_=env.reset(seed=3);old=env._backend
        second,_=env.reset(seed=3);self.assertTrue(old.closed)
        np.testing.assert_array_equal(first['entities'],second['entities'])
        self.assertEqual(env.sample_action().shape,(2,));env.close()
    def test_native_failure_is_not_a_fake_terminal_transition(self):
        env=self.env();env.reset(seed=4);old=env._backend
        def broken(answer):raise RuntimeError('native failed')
        env._backend.step=broken
        with self.assertRaisesRegex(RuntimeError,'native failed'):env.step([0,0])
        self.assertTrue(old.closed)
        with self.assertRaises(ResetNeeded):env.step([0,0])
    def test_external_endpoint_only_explicit_local_single_agent(self):
        args=arguments(['--out','x.json','--controllers','model,native','--controller-endpoint','http://127.0.0.1:12345/api/chat'])
        self.assertIsNone(args.model_config)

if __name__=='__main__':unittest.main()
