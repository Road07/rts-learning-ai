"""Numerical PPO checks; all generated rollouts are fixture-only, never saved."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
import torch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'service'))
from recurrent_ppo import PPOConfig,gae,clipped_surrogate,RolloutCollector,RecurrentPPO,policy_digest
from entity_policy import SharedEntityPolicy,tensor_frame
from entity_codec import EntityCodec,FACTIONS
from public_game_rules import PublicGameRules
ROOT=Path(__file__).resolve().parents[4]

class PPOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.manual_seed(17);torch.set_num_threads(2)
        c=json.loads((ROOT/'AI-Yeni-Model/ai-service/runtime.json').read_text(encoding='utf-8-sig'));rules=PublicGameRules(c['game_rules']);cls.codec=EntityCodec(rules)
        cls.base=SharedEntityPolicy(len(cls.codec.vocabulary),width=32,hidden=32).eval()
        obs={'faction':FACTIONS[0],'money':200,'decision_frame':1,'entity_state':{'encoding':'rts-entities-v1','source':'native_fog_filtered','frame':1,'map_extent':{'extent_x':1000,'extent_y':1000},'entities':[]}}
        heads={'tactical':[{'id':'a','kind':'scout','x':100,'y':200},{'id':'b','kind':'defend','x':200,'y':100}],'spend':[{'id':'none','kind':'wait'},{'id':'buy','kind':'science','template':'unknown','points_cost':1}]}
        cls.encoded=cls.codec.encode(obs,heads)
    def collect(self,model,terminal=True,key=('test',1)):
        collector=RolloutCollector(model,key,fixture=True)
        for i in range(4):
            collector.sample(self.encoded);collector.commit([.1,-.2,.3,.2][i],5,terminated=terminal and i==3)
        if not terminal:collector.close(self.encoded)
        return collector.rollout()
    def test_gae_known_returns_and_trace(self):
        c=replace(PPOConfig(),gamma=1.,gae_lambda=1.)
        a,r=gae([1,2],[.5,.25],[.25,0],[False,True],[False,False],[5,5],c)
        torch.testing.assert_close(a,torch.tensor([2.5,1.75]));torch.testing.assert_close(r,torch.tensor([3.,2.]))
        a,_=gae([0,0],[1,2],[2,4],[False,False],[False,True],[5,5],replace(c,gamma=.9,gae_lambda=.5))
        torch.testing.assert_close(a,torch.tensor([1.52,1.6]))
    def test_terminal_vs_time_limit_and_duration(self):
        c=replace(PPOConfig(),gamma=.9,gae_lambda=0.)
        a,_=gae([1],[2],[0],[True],[False],[5],c);self.assertAlmostEqual(a.item(),-1)
        a,_=gae([1],[2],[10],[False],[True],[5],c);self.assertAlmostEqual(a.item(),8)
        a,_=gae([1],[2],[10],[False],[False],[10],c);self.assertAlmostEqual(a.item(),7.1,places=5)
        with self.assertRaises(ValueError):gae([1],[2],[1],[True],[False],[5],c)
        with self.assertRaises(ValueError):gae([1,1],[2,3],[3,0],[True,False],[False,False],[5,5],c)
    def test_probability_ratio_clips_both_signs(self):
        lr=torch.tensor([.5,-.5],requires_grad=True);adv=torch.tensor([1.,-1.],requires_grad=True)
        loss,_=clipped_surrogate(lr,adv,.2)
        torch.testing.assert_close(loss,torch.tensor([-1.2,.8]));loss.sum().backward()
        torch.testing.assert_close(lr.grad,torch.zeros(2));self.assertIsNone(adv.grad)
    def test_critic_and_actor_both_learn_joint_transition_once(self):
        model=copy.deepcopy(self.base);rollout=self.collect(model);before=copy.deepcopy(model.state_dict())
        algorithm=RecurrentPPO(model,replace(PPOConfig(),epochs=2,sequence_length=2,minibatch_sequences=1))
        report=algorithm.update([rollout],allow_fixtures=True)
        self.assertEqual(report['transitions'],4);self.assertGreater(report['optimizer_steps'],0)
        self.assertFalse(torch.equal(before['value.weight'],model.value.weight))
        self.assertFalse(torch.equal(before['scorer.2.weight'],model.scorer[2].weight))
        self.assertTrue(all(r['exact_joint_kl']<=.02 for r in report['history'] if r['accepted']))
        self.assertTrue(all(torch.isfinite(p).all() for p in model.parameters()))
    def test_fixture_stale_masks_and_old_logp_rejected(self):
        model=copy.deepcopy(self.base);rollout=self.collect(model);trainer=RecurrentPPO(model)
        with self.assertRaises(ValueError):trainer.update([rollout])
        stale=copy.deepcopy(rollout);stale['policy_sha256']='bad'
        with self.assertRaises(ValueError):trainer.update([stale],True)
        bad=copy.deepcopy(rollout);bad['steps'][0]['old_logp']+=1
        with self.assertRaises(ValueError):trainer.update([bad],True)
        bad=copy.deepcopy(rollout);bad['steps'][0]['encoded']['heads']['tactical']['legal'][0]=False
        with self.assertRaises(ValueError):trainer.update([bad],True)
        with self.assertRaises(ValueError):trainer.update([rollout,rollout],True)
    def test_gru_prefix_recomputed_and_time_limit_bootstraps(self):
        model=copy.deepcopy(self.base);rollout=self.collect(model,False);trainer=RecurrentPPO(model)
        full=trainer._unroll(rollout['steps'],grad=False);part=trainer._unroll(rollout['steps'],start=2,end=4,grad=False)
        for a,b in zip(full[2:],part):
            torch.testing.assert_close(a[0],b[0]);torch.testing.assert_close(a[2],b[2])
        self.assertNotEqual(rollout['steps'][-1]['next_value'],0.)
        collector=RolloutCollector(model,('truncated',1),True);collector.sample(self.encoded)
        with self.assertRaises(ValueError):collector.commit(1,5,truncated=True)
        collector.commit(1,5,truncated=True,final_encoded=self.encoded);self.assertTrue(collector.rollout()['steps'][-1]['truncated'])
    def test_kl_rolls_back_weights_and_adam(self):
        model=copy.deepcopy(self.base);rollout=self.collect(model);before=policy_digest(model)
        trainer=RecurrentPPO(model,replace(PPOConfig(),learning_rate=.01,target_kl=1e-12,epochs=2))
        report=trainer.update([rollout],True)
        self.assertTrue(report['early_stopped_kl']);self.assertEqual(report['optimizer_steps'],0)
        self.assertEqual(policy_digest(model),before);self.assertFalse(trainer.optimizer.state)
    def test_numerical_proposal_restores_weights_and_optimizer(self):
        model=copy.deepcopy(self.base);rollout=self.collect(model);trainer=RecurrentPPO(model,replace(PPOConfig(),epochs=1))
        before=policy_digest(model);original_step=trainer.optimizer.step
        def corrupt():
            original_step()
            with torch.no_grad():model.scorer[2].weight.fill_(float('nan'))
        trainer.optimizer.step=corrupt
        with self.assertRaises(ValueError):trainer.update([rollout],True)
        self.assertEqual(policy_digest(model),before);self.assertFalse(trainer.optimizer.state)

    def test_gpu_actor_critic_update(self):
        if not torch.cuda.is_available():self.skipTest('CUDA unavailable')
        model=copy.deepcopy(self.base).cuda();rollout=self.collect(model)
        report=RecurrentPPO(model,replace(PPOConfig(),epochs=1)).update([rollout],True)
        self.assertGreater(report['optimizer_steps'],0);self.assertEqual(next(model.parameters()).device.type,'cuda')

if __name__=='__main__':unittest.main()
