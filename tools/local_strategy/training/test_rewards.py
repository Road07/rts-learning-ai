import copy
import json
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent / "service"))
from reward_policy import RewardLedger, calculate_episode

TUNING=json.loads((HERE.parent / "knowledge/reward_v3.json").read_text(encoding="utf-8"))


def sample(frame=0,player=3,members=None,**extra):
    row={"ok":True,"income_complete":True,"income_delta":0,"income_cursor":frame,
        "player":player,"frame":frame,"team_members":members or [3],"enemy_units":0,
        "enemy_structures":0,"own_units_lost":0,"own_structures_lost":0,"dead_heroes":[],
        "bases":[{"id":player*10,"health":1}],"heroes":[{"id":player*10+1,"health":1}],
        "visible_enemies":[{"id":99,"template":"enemy","health":1,"cost":1000}],"won":False,"defeated":False}
    row.update(extra)
    return row


class RewardChecks(unittest.TestCase):
    def test_refunds_spending_and_commands_give_no_reward(self):
        ledger=RewardLedger(TUNING); ledger.observe(sample())
        result=ledger.observe(sample(1,money=100000,earned=100000,spent=200000,commands=10000,queued=1000))
        self.assertEqual(result["total"],0)
        result=ledger.observe(sample(2,income_delta=1000))
        self.assertAlmostEqual(result["components"]["income"],.1)

    def test_combat_losses_and_health_have_expected_signs(self):
        ledger=RewardLedger(TUNING); ledger.observe(sample())
        result=ledger.observe(sample(1,enemy_units=3,enemy_structures=1,own_units_lost=1,
            bases=[{"id":30,"health":.8}],heroes=[{"id":31,"health":.5}],
            visible_enemies=[{"id":99,"template":"enemy","health":.7,"cost":1000}]))
        self.assertAlmostEqual(result["total"],.0235)
        self.assertLess(result["components"]["own_units_lost"],0)
        self.assertGreater(result["components"]["visible_damage"],0)

    def test_fog_disappearance_and_reappearance_are_not_kills_or_damage(self):
        ledger=RewardLedger(TUNING); ledger.observe(sample())
        ledger.observe(sample(1,visible_enemies=[]))
        result=ledger.observe(sample(2,visible_enemies=[{"id":99,"template":"enemy","health":.1,"cost":1000}]))
        self.assertEqual(result["total"],0)

    def test_shared_sight_and_duplicate_rows_do_not_double_reward(self):
        ledger=RewardLedger(TUNING)
        ledger.observe(sample(player=3,members=[3,4])); ledger.observe(sample(player=4,members=[3,4]))
        damaged=[{"id":99,"template":"enemy","health":.5,"cost":1000}]
        row=sample(1,player=3,members=[3,4],enemy_units=1,visible_enemies=damaged)
        ledger.observe(row); ledger.observe(row)
        result=ledger.observe(sample(1,player=4,members=[3,4],visible_enemies=damaged))
        self.assertAlmostEqual(result["total"],.077)

    def test_heal_and_reveal_loops_cannot_farm_rewards(self):
        ledger=RewardLedger(TUNING); ledger.observe(sample())
        for frame,hp in enumerate((.5,1,.5,1),1):
            enemies=[{"id":99,"template":"enemy","health":hp,"cost":1000}]
            result=ledger.observe(sample(frame,bases=[{"id":30,"health":hp}],visible_enemies=enemies))
        self.assertAlmostEqual(result["components"]["base_health"],0)
        self.assertAlmostEqual(result["components"]["visible_damage"],.075)

    def test_terminal_dominates_capped_shaping_without_fabricating_short_match_win(self):
        ledger=RewardLedger(TUNING); ledger.observe(sample())
        result=ledger.observe(sample(1,income_delta=10000000,enemy_units=10000,enemy_structures=10000))
        self.assertEqual(result["outcome"],"ongoing")
        self.assertLessEqual(result["shaping"],1)
        won=ledger.observe(sample(2,income_delta=10000000,enemy_units=10000,enemy_structures=10000,won=True))
        self.assertEqual(won["terminal"],10)
        again=ledger.observe(sample(3,enemy_units=10000,enemy_structures=10000,won=True))
        self.assertEqual(again["terminal"],10)

    def test_one_defeated_ally_is_not_team_defeat(self):
        ledger=RewardLedger(TUNING); ledger.observe(sample(player=3,members=[3,4]))
        first=ledger.observe(sample(1,player=3,members=[3,4],defeated=True))
        self.assertEqual(first["terminal"],0)
        ledger.observe(sample(player=4,members=[3,4]))
        last=ledger.observe(sample(1,player=4,members=[3,4],defeated=True))
        self.assertEqual(last["terminal"],-10)

    def test_invalid_and_truncated_counters_are_rejected(self):
        ledger=RewardLedger(TUNING)
        with self.assertRaises(ValueError): ledger.observe(sample(income_complete=False))
        ledger.observe(sample(enemy_units=1))
        with self.assertRaises(ValueError): ledger.observe(sample(1,enemy_units=0))
        with self.assertRaises(ValueError): ledger.observe(sample(1,enemy_units=1,income_delta=float("nan")))

    def test_actual_hero_death_penalty_and_no_purchase_bonus(self):
        ledger=RewardLedger(TUNING); ledger.observe(sample())
        result=ledger.observe(sample(1,heroes=[],dead_heroes=["HeroA"]))
        self.assertEqual(result["components"]["hero_deaths"],-.4)
        result=ledger.observe(sample(2,heroes=[{"id":999,"health":1}],dead_heroes=[]))
        self.assertEqual(result["components"]["hero_health"],0)

    def test_episode_replay_sorts_rows_and_requires_every_learner(self):
        rows=[sample(2,income_delta=100),sample(0),sample(1,income_delta=100)]
        result=calculate_episode(TUNING,rows,[3])
        self.assertAlmostEqual(result["total"],.02)
        with self.assertRaises(ValueError): calculate_episode(TUNING,rows,[3,4])


if __name__=="__main__": unittest.main()
