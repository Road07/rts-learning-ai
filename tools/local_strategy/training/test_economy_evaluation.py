import copy
import unittest
from automatic_training import evaluate_economy,compare_economy
from economy_evaluation import EconomyEvaluation,VERSION


def sample(frame, share=.9, busy=0, money=300, income=0):
    return {"ok":True,"player":1,"faction":"FactionWild","frame":frame,"money":money,
        "income_complete":True,"income_cursor":frame,"income_payments":([{"serial":frame,"frame":frame,"amount":income}] if income else []),
        "economy_evaluation":{"schema":VERSION,"cp_used":100,"cp_limit":300},
        "own_assets":[{"id":1,"economy":True,"complete":True,"resource_share":share},
            {"id":2,"factory":True,"complete":True,"queue_count":busy},
            {"id":3,"mobile":True,"cost":200,"health":1},
            {"id":4,"mobile":True,"builder":True,"cost":500,"health":1}]}


class EconomyChecks(unittest.TestCase):
    def test_actual_income_not_cash_refunds_or_duplicate_samples(self):
        rows=[sample(0),sample(25,money=3000,income=20)]
        rows[1]["income_payments"]*=2
        rows+=[copy.deepcopy(rows[1])]
        r=evaluate_economy(rows)["players"][0]
        self.assertEqual(r["real_income"],20)
        self.assertEqual(r["real_income_per_second"],4)
        self.assertEqual(r["army_value_start"],200)  # Builder excluded.
        self.assertFalse(r["sufficient_window"])

    def test_time_weighted_factory_and_farm_measurements(self):
        r=evaluate_economy([sample(0,share=.4,busy=1),sample(10,share=1,busy=0),sample(50)])["players"][0]
        self.assertAlmostEqual(r["farm_share_time_mean"],.88)
        self.assertAlmostEqual(r["factory_busy_fraction"],.2)
        self.assertEqual(r["factory_idle_seconds"],8)
        self.assertEqual(r["net_army_value_change"],0)

    def test_missing_income_and_sampling_gaps_are_not_success(self):
        rows=[sample(0),sample(600)]
        rows[1]["income_complete"]=False
        r=evaluate_economy(rows)["players"][0]
        self.assertIsNone(r["real_income"])
        self.assertEqual(r["coverage_fraction"],0)
        self.assertFalse(r["sufficient_window"])
        self.assertEqual(evaluate_economy([{"player":1,"frame":0}])["status"],"missing_telemetry")

    def test_no_factory_or_farm_is_missing_ratio_not_perfect_play(self):
        rows=[sample(0),sample(25)]
        for r in rows: r["own_assets"]=[]
        r=evaluate_economy(rows)["players"][0]
        self.assertIsNone(r["farm_share_time_mean"])
        self.assertIsNone(r["factory_busy_fraction"])

    def test_comparison_rejects_different_roster_or_windows(self):
        a=evaluate_economy([sample(0,.4),sample(25,.4)])
        b=evaluate_economy([sample(0,.9),sample(25,.9)])
        comparison=compare_economy(a,b)
        self.assertTrue(comparison["matched_roster_and_window"])
        self.assertAlmostEqual(comparison["players"][0]["candidate_minus_baseline"]["farm_share_time_mean"],.5)
        self.assertFalse(comparison["sufficient_to_claim_strength"])
        self.assertIsNone(comparison["automatic_winner"])
        b["players"][0]["faction"]="FactionMen"
        self.assertFalse(compare_economy(a,b)["matched_roster_and_window"])
        b["players"][0]["faction"]="FactionWild"
        b["players"][0]["end_frame"]+=20
        self.assertFalse(compare_economy(a,b)["matched_roster_and_window"])

    def test_accepted_orders_are_distinct_from_completed_production(self):
        event={"player":1,"frame":10,"observed_frame":9,"head":"spend","submitted":True,
               "operation":{"kind":"train","cost":200}}
        r=evaluate_economy([sample(0),sample(25)],[event,event])["players"][0]
        self.assertEqual(r["dispatch"]["accepted_train_orders"],1)
        self.assertEqual(r["dispatch"]["accepted_train_nominal_cost"],200)
        self.assertEqual(r["net_army_value_change"],0)


if __name__=="__main__": unittest.main()
