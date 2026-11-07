import copy
import json
from pathlib import Path
import tempfile
import unittest
from benchmark import create,add,summarize,read,source_manifest
from benchmark_metrics import outcome,metrics,aggregate,wilson
from test_economy_evaluation import sample

class BenchmarkTests(unittest.TestCase):
    def report(self,winner=None):
        return {'ok':True,'benchmark':{'model_players':[1,2,3],'native_players':[4,5,6],'victory':{'ok':True,'single_alliance':winner is not None,'events':[] if winner is None else [{'kind':'alliance_victory','player':winner}]}}}
    def test_outcomes_do_not_invent_wins_or_draws(self):
        self.assertEqual(outcome(self.report()),'truncated')
        self.assertEqual(outcome(self.report(1)),'win');self.assertEqual(outcome(self.report(4)),'loss')
        r=self.report(1);r['ok']=False;self.assertEqual(outcome(r),'invalid')
        r=self.report(1);r['benchmark']['victory']['events']=[];self.assertEqual(outcome(r),'unresolved_terminal')
    def test_actual_income_completion_intervals_and_missing_data(self):
        rows=[sample(0),sample(25,income=20),sample(50,income=30)]
        for r in rows:
            for a in r['own_assets']:a['template']='test'
        rows[1]['own_assets'].append({'id':9,'template':'newfarm','economy':True,'complete':False,'resource_share':.8})
        rows[2]['own_assets'].append({'id':9,'template':'newfarm','economy':True,'complete':True,'resource_share':.8})
        r=metrics(self.report(),rows);p=r['economy']['players'][0]
        self.assertEqual(p['real_income_per_minute'],300)
        event=r['build_order'][0]['events'][0];self.assertEqual(event['completion_interval_seconds'],[5,10]);self.assertEqual(event['ordinal'],1)
        self.assertEqual(event['template'],'newfarm')
        rows[2]['income_complete']=False;p=metrics(self.report(),rows)['economy']['players'][0]
        self.assertIsNone(p['real_income_per_minute']);self.assertIsNone(p['minute_income'])
    def test_aggregation_match_denominator_not_players(self):
        games=[metrics(self.report(1),[]),metrics(self.report(4),[]),metrics(self.report(),[])]
        a=aggregate(games);self.assertEqual(a['completed'],2);self.assertEqual(a['win_rate_completed'],.5);self.assertAlmostEqual(a['completion_fraction'],2/3)
        self.assertIsNone(wilson(0,0));self.assertLess(wilson(1,2)[0],.5);self.assertGreater(wilson(1,2)[1],.5)
    def test_suite_pins_schedule_snapshots_and_empty_curve(self):
        root=Path(__file__).resolve().parents[4]
        with tempfile.TemporaryDirectory(dir=root/'AI-Test-Sahasi') as d:
            suite=create(root/'AI-Yeni-Model/ai-service/runtime.json',Path(d)/'suite',games=2)
            m=read(suite/'suite.json');self.assertEqual([g['model_team'] for g in m['plan']],[1,2])
            self.assertEqual(len(m['checkpoints']),1)
            a=add(suite,root/'AI-Yeni-Model/ai-service/runtime.json','duplicate');self.assertEqual(a['id'],m['checkpoints'][0]['id'])
            r=summarize(suite);self.assertEqual(r['checkpoints'][0]['pending_games'],2);self.assertIsNone(r['checkpoints'][0]['win_rate_completed'])
            self.assertTrue((suite/'learning-curve.html').exists())

if __name__=='__main__':unittest.main()
