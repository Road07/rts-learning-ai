import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import numpy as np
from automatic_training import episode_environment
from test_action_credit import asset,row,event
from action_credit import calculate,key
from decision_net import DecisionNet,FACTIONS
from spend_policy import spend_features,load_spend_model,WAIT

TUNING=json.loads((Path(__file__).resolve().parent.parent/'knowledge/reward_action_credit_v2.json').read_text(encoding='utf-8'))


class LearningPriorities(unittest.TestCase):
    def test_heldout_seed_changes_without_moving_factions(self):
        args=SimpleNamespace(rotate_factions=True,seed=1749,seconds=6)
        training=episode_environment(args,{},1749,'sample')
        baseline=episode_environment(args,{},101749,'evaluate')
        candidate=episode_environment(args,{},101749,'evaluate')
        self.assertEqual(training['arena_factions'],['FactionAngmar','FactionMen','FactionElves','FactionDwarves','FactionWild','FactionMordor'])
        self.assertEqual(training['arena_factions'],baseline['arena_factions'])
        self.assertEqual(baseline,candidate)
        self.assertEqual(baseline['arena_sim_frames'],120)
        self.assertNotIn('arena_sim_frames',training)
        last=episode_environment(args,{},101749,'evaluate',roster_seed=1750)
        self.assertEqual(last['arena_factions'],episode_environment(args,{},1750,'sample',roster_seed=1750)['arena_factions'])

    def economic_credit(self,income,end=910,paid=True):
        farm=asset(2,template='farm',structure=True,economy=True,combat=False,cost=300)
        if paid:farm['paid_cost']=300
        rows=[row(0),row(5,own_assets=[asset(),farm]),row(10,own_assets=[asset(),farm],income_payments=[{'serial':1,'object':2,'frame':10,'amount':income}]),row(end,own_assets=[asset(),farm])]
        build=event('build','spend',template='farm',before_ids=[1],cost=300)
        values,_=calculate(TUNING,rows,[build])
        return values[key(3,0,'spend')]

    def test_completed_investment_payback_not_gross_income(self):
        low=self.economic_credit(50);high=self.economic_credit(600);higher=self.economic_credit(1200)
        self.assertLess(low['reward'],0)
        self.assertGreater(high['reward'],0)
        self.assertGreater(higher['reward'],high['reward'])
        self.assertLess(higher['reward'],.15)
        self.assertAlmostEqual(high['realized_roi'],2.)
        self.assertEqual(high['version'],'action-credit-v2')

    def test_unmatured_or_unknown_paid_investment_is_not_guessed(self):
        self.assertEqual(self.economic_credit(600,end=30)['reward'],0)
        self.assertEqual(self.economic_credit(600,paid=False)['reward'],0)

    def cancellation(self,threat=False,changed=False,automatic=False,complete=True,progress=50,research=False,identity_only=False):
        factory=asset(10,template='factory',structure=True,combat=False,x=0 if threat else 2000)
        rows=[row(0,own_assets=[factory]),row(10,own_assets=[factory]),row(25,own_assets=[factory]),row(90,own_assets=[factory])]
        queued={'producer':10,'serial':1,'production_id':11,'frame':5,'kind':'queued','template':'archer','cost':300,'progress':0,'work_frames':0,'produced':0,'automatic':False}
        cancel=dict(queued,serial=2,frame=21,kind='cancelled',progress=progress,work_frames=50,automatic=automatic)
        restart=dict(queued,serial=3,frame=30,production_id=12)
        if research:
            for receipt,token in [(queued,1),(cancel,1),(restart,3)]:
                receipt.update(queue_kind='research',queue_receipt_id=token,production_id=0)
        rows[-1].update(production_receipts=[queued,cancel,restart,copy.deepcopy(cancel)],production_receipts_complete=complete)
        if changed:rows[2]['visible_enemies'][0]['template']='new enemy'
        if identity_only:rows[2]['visible_enemies'][0]['id']=999
        action=event('cancel','spend',frame=20,producer=10,variant=0 if research else 11,template='archer')
        values,metrics=calculate(TUNING,rows,[action])
        return values[key(3,20,'spend')],metrics

    def test_enemy_change_diagnostics_do_not_relax_reward_filters(self):
        for kwargs,reason in [(dict(changed=True),'template_counts'),(dict(identity_only=True),'identity_only')]:
            value,metrics=self.cancellation(**kwargs)
            self.assertEqual(value['reward'],0)
            self.assertEqual(metrics['cancel_excluded_enemy_change_'+reason],1)
            self.assertEqual(metrics['cancel_excluded_enemy_change_'+reason+'_player_3'],1)
            self.assertEqual(metrics['cancel_excluded_enemy_change_no_nearby_enemy'],1)
            self.assertEqual(metrics['cancel_excluded_enemy_change_local_unchanged'],1)

    def test_research_receipts_are_observed_without_extending_v2_rewards(self):
        value,metrics=self.cancellation(research=True)
        self.assertEqual(value['reward'],0)
        self.assertEqual(metrics['observed_research_cancellations'],1)
        self.assertEqual(metrics['observed_research_cancellations_player_3'],1)
        self.assertNotIn('verified_cancel_restart_cycles',metrics)

    def test_only_verified_worked_cancel_restart_cycle_is_penalized_once(self):
        value,metrics=self.cancellation()
        self.assertLess(value['components']['production_restart_delay'],0)
        self.assertEqual(metrics['verified_cancel_restart_cycles'],1)
        self.assertEqual(metrics['discarded_production_seconds'],10)
        # A blocked hero can accumulate >100% in the engine; cap only the
        # nominal one-order loss, without rejecting the whole match.
        stalled,_=self.cancellation(progress=150)
        self.assertLess(stalled['reward'],0)
        self.assertGreater(stalled['reward'],-.85)
        for kwargs in [dict(threat=True),dict(changed=True),dict(automatic=True),dict(complete=False)]:
            value,_=self.cancellation(**kwargs)
            self.assertEqual(value['reward'],0)

    def test_economy_does_not_steal_combat_budget_or_terminal_goal(self):
        end=row(60,won=True);end['visible_enemies'][0]['health']=0
        values,_=calculate(TUNING,[row(0),end],[event()])
        self.assertAlmostEqual(sum(v['terminal_share'] for v in values.values()),10)
        self.assertLess(sum(abs(x) for v in values.values() for x in v['components'].values()),.85)

    def test_queue_progress_is_an_input_without_resetting_old_banks(self):
        choice={'kind':'cancel','id':'cancel:1:a:0:2','queue_verified':True,'queue_progress':.5,'queue_paid_cost':300,'queue_work_seconds':10,'queue_remaining':1}
        old=spend_features({},choice,include_queue=False)[None,:];new=spend_features({},choice)[None,:]
        self.assertEqual(new.shape[1],old.shape[1]+5)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            model=DecisionNet(old.shape[1]).ensure_factions();path=Path(directory)/'old.npz';model.save(path)
            restored=load_spend_model(path)
            for faction in FACTIONS:
                np.testing.assert_allclose(model.for_faction(faction).forward(old)[0],restored.for_faction(faction).forward(new)[0],atol=1e-7)


if __name__=='__main__':unittest.main()
