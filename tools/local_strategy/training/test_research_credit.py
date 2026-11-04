import copy
import json
from pathlib import Path
import unittest
from test_action_credit import asset,row,event
from action_credit import calculate,key

TUNING=json.loads((Path(__file__).resolve().parent.parent/'knowledge/reward_action_credit_v3.json').read_text(encoding='utf-8'))


class ResearchCredit(unittest.TestCase):
    def scenario(self):
        factory=asset(10,template='factory',structure=True,combat=False,x=2000)
        rows=[row(n,own_assets=[copy.deepcopy(factory)],production_receipts_complete=True) for n in [0,10,25,40,90]]
        queued=dict(producer=10,serial=1,production_id=0,frame=5,kind='queued',template='Upgrade_Test',cost=500,progress=0,work_frames=0,produced=0,automatic=False,queue_kind='research',queue_receipt_id=1)
        cancel=dict(queued,serial=2,frame=21,kind='cancelled',progress=20,work_frames=4)
        restart=dict(queued,serial=3,frame=30,queue_receipt_id=3)
        rows[1]['production_receipts']=[queued]
        rows[2]['production_receipts']=[cancel]
        rows[3]['production_receipts']=[restart,copy.deepcopy(cancel)]
        action=event('cancel','spend',frame=20,producer=10,variant=0,template='Upgrade_Test',queue_kind='research',queue_receipt_id=1)
        return rows,action

    def reward(self,rows,action,tuning=None):
        values,metrics=calculate(tuning or TUNING,rows,[action])
        return values[key(3,20,'spend')],metrics

    def test_observed_research_work_reaches_specific_cancel_once(self):
        rows,action=self.scenario();credit,metrics=self.reward(rows,action)
        self.assertLess(credit['components']['research_restart_delay'],0)
        self.assertGreater(credit['reward'],-.85)
        self.assertEqual(metrics['verified_research_restart_cycles'],1)
        self.assertEqual(metrics['discarded_research_seconds'],.8)
        self.assertNotIn('production_restart_delay',credit['components'])

    def test_v2_and_legacy_receipts_are_not_relabelled(self):
        rows,action=self.scenario();tuning=copy.deepcopy(TUNING);tuning['decision_credit']['version']='action-credit-v2'
        self.assertEqual(self.reward(rows,action,tuning)[0]['reward'],0)
        for r in rows:
            for receipt in r.get('production_receipts',[]):receipt.pop('queue_receipt_id',None)
        self.assertEqual(self.reward(rows,action)[0]['reward'],0)

    def test_zero_gameplay_id_cannot_match_another_research_order(self):
        for field,value in [('queue_receipt_id',2),('template','Upgrade_Other'),('queue_kind','unit')]:
            rows,action=self.scenario();action['operation'][field]=value
            self.assertEqual(self.reward(rows,action)[0]['reward'],0)

    def test_automatic_or_missing_or_incomplete_history_has_no_label(self):
        for change in ['automatic','missing_start','missing_cancel','gap','no_new_identity','no_work','different_restart','free','unmatured']:
            rows,action=self.scenario()
            if change=='automatic': rows[2]['production_receipts'][0]['automatic']=True;rows[3]['production_receipts']=rows[3]['production_receipts'][:1]
            if change=='missing_start': rows[1]['production_receipts']=[]
            if change=='missing_cancel': rows[2]['production_receipts']=[];rows[3]['production_receipts']=rows[3]['production_receipts'][:1]
            if change=='gap': rows[2]['production_receipts_complete']=False
            if change=='no_new_identity': rows[3]['production_receipts'][0]['queue_receipt_id']=1
            if change=='no_work': rows[2]['production_receipts'][0]['work_frames']=0;rows[3]['production_receipts']=rows[3]['production_receipts'][:1]
            if change=='different_restart': rows[3]['production_receipts'][0]['template']='Upgrade_Other'
            if change=='free':
                for r in rows:
                    for receipt in r.get('production_receipts',[]):receipt['cost']=0
            if change=='unmatured':rows=rows[:-1]
            with self.subTest(change=change): self.assertEqual(self.reward(rows,action)[0]['reward'],0)

    def test_threat_information_or_damage_changes_preserve_exclusions(self):
        for change in ['enemy','damage','nearby']:
            rows,action=self.scenario()
            if change=='enemy':rows[2]['visible_enemies'][0]['template']='changed'
            if change=='damage':rows[2]['own_assets'][0]['health']=.5
            if change=='nearby':
                for r in rows:r['own_assets'][0]['x']=0
            with self.subTest(change=change):self.assertEqual(self.reward(rows,action)[0]['reward'],0)


if __name__=='__main__':unittest.main()
