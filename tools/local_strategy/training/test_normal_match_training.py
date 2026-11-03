import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from decision_net import DecisionNet, features
from normal_match_training import replay_one, imitation_update
from normal_match_capture import NormalMatchCapture
from spend_policy import spend_features, WAIT
from test_rewards import sample, TUNING


class NormalMatchChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.temp.name)
        self.service = self.root / "AI-Yeni-Model/ai-service/logs"; self.service.mkdir(parents=True)
        self.game = self.root / "AI-Yeni-Model/logs"; self.game.mkdir(parents=True)
        (self.root / "AI-Egitim/otomatik-dongu").mkdir(parents=True)
        self.model = DecisionNet(len(features({}, {"id":"none"})))
        self.spend = DecisionNet(len(spend_features({}, WAIT)))
        obs = {"match_id":"session:0","diagnostic_session":"session","decision_frame":10,"player_index":3,"money":500}
        options = [{"id":"defend_home"},{"id":"attack_enemy"}]
        purchases = [WAIT,{"id":"train:1:unit","kind":"train","role":0,"cost":100}]
        self.action = NormalMatchCapture().action(obs,options,"attack_enemy",purchases,"train:1:unit")
        self.start = {"event":"normal_match_start","schema":"normal-trajectory-v1","match_id":"session:0",
                      "diagnostic_session":"session","reward_tuning":TUNING,"fixture":False}
        self.rows = [self.start,dict(self.action,event="normal_match_action"),
                     {"event":"reward_observation","match_id":"session:0","sample":sample(0)}]
        self.final = {"event":"normal_match_closed","data":{"match_id":"session:0","fixture":False,"samples":[sample(20,won=True)]}}
        self.rows[-1]["sample"]["credit_schema"]="action-credit-v1"
        self.final["data"]["samples"][0]["credit_schema"]="action-credit-v1"
        self.credit_events=[{"event":"decision_credit_action","data":{"match_id":"session:0","player":3,"observed_frame":10,"frame":10,"head":head,"submitted":True,"operation":{"kind":"wait"}}} for head in ("tactical","spend")]
        self.ack = {"event":"model_decision","data":{"match_id":"session:0","player":3,"observed_frame":10}}
        self.write()

    def write(self, closed=True, ack=True):
        (self.service/"host.jsonl").write_text("\n".join(json.dumps(r) for r in self.rows)+"\n",encoding="utf-8")
        rows = ([self.ack] if ack else []) + self.credit_events + ([self.final] if closed else [])
        (self.game/"session-00.jsonl").write_text("\n".join(json.dumps(r) for r in rows)+"\n",encoding="utf-8")
    def tearDown(self): self.temp.cleanup()

    def test_verified_terminal_match_updates_both_heads_once(self):
        before = self.model.weights["w0"].copy()
        result = replay_one(self.model,self.spend,self.root)
        self.assertTrue(result[0]["update"]["updated"])
        self.assertTrue(result[0]["spend_update"]["updated"])
        self.assertFalse(np.array_equal(before,self.model.weights["w0"]))
        report = self.root/"AI-Egitim/otomatik-dongu/done"; report.mkdir()
        (report/"report.json").write_text(json.dumps({"status":"complete","normal_matches":result}),encoding="utf-8")
        self.assertEqual(replay_one(self.model,self.spend,self.root),[])

    def test_partial_fixture_unacknowledged_and_ongoing_matches_are_not_learned(self):
        self.write(closed=False)
        self.assertEqual(replay_one(self.model,self.spend,self.root),[])
        self.final["data"]["fixture"] = True; self.write()
        self.assertEqual(replay_one(self.model,self.spend,self.root),[])
        self.final["data"]["fixture"] = False; self.write(ack=False)
        result = replay_one(self.model,self.spend,self.root)
        self.assertEqual(result,[])
        self.final["data"]["samples"] = [sample(20)]; self.write()
        self.assertEqual(replay_one(self.model,self.spend,self.root),[])

    def test_corrupt_reward_and_features_are_excluded_without_partial_update(self):
        self.final["data"]["samples"] = [sample(20,won=True,income_complete=False)]; self.write()
        self.assertEqual(replay_one(self.model,self.spend,self.root),[])
        self.final["data"]["samples"] = [sample(20,won=True)]
        self.rows[1]["spend"]["features"] = [[1,2]]; self.write()
        before = {k:v.copy() for k,v in self.model.weights.items()}
        self.assertEqual(replay_one(self.model,self.spend,self.root),[])
        for key in before: np.testing.assert_array_equal(before[key],self.model.weights[key])

    def test_capture_is_throttled_and_winning_choice_likelihood_increases(self):
        trace = self.action["tactical"]
        x = np.asarray(trace["features"],dtype=np.float32)
        from episode_policy import probabilities
        index = trace["selected_index"]
        before = probabilities(self.model.forward(x)[0])[index]
        imitation_update(self.model,[trace],1.)
        self.assertGreater(probabilities(self.model.forward(x)[0])[index],before)
        capture = NormalMatchCapture()
        obs = {"match_id":"test","player_index":3,"decision_frame":10}
        args = ([{"id":"defend_home"}],"defend_home",[WAIT],"none")
        self.assertIsNotNone(capture.action(obs,*args))
        obs["decision_frame"] = 11
        self.assertIsNone(capture.action(obs,*args))

    def test_bad_choice_in_win_and_good_choice_in_loss_are_distinguished(self):
        from test_action_credit import asset
        from episode_policy import probabilities
        for win,expected_sign in [(True,-1),(False,1)]:
            self.model = DecisionNet(len(features({}, {"id":"none"})))
            self.spend = DecisionNet(len(spend_features({},WAIT)))
            initial=self.rows[-1]["sample"]
            initial.update(own_assets=[asset(cost=1000)],owned_present_ids=[1])
            final=sample(20,won=win,defeated=not win,team_defeated=not win)
            final.update(credit_schema="action-credit-v1",own_assets=[asset(cost=1000,health=.1 if win else 1.)],owned_present_ids=[1])
            if not win: final["visible_enemies"][0]["health"] = .1
            for row in (initial,final): row["visible_enemies"][0].update(x=0,y=0)
            self.final["data"]["samples"]=[final]
            self.credit_events=self.credit_events[:2]
            self.credit_events[0]["data"]["operation"]={"kind":"attack","units":[1],"target":99}
            for i in range(20):
                if i!=10: self.credit_events.append({"event":"decision_credit_action","data":{"match_id":"session:0","player":3,"observed_frame":i,"frame":i,"head":"tactical","submitted":True,"operation":{"kind":"wait"}}})
            self.write()
            trace=self.action["tactical"]; x=np.asarray(trace["features"],dtype=np.float32); index=trace["selected_index"]
            before=probabilities(self.model.forward(x)[0])[index]
            result=replay_one(self.model,self.spend,self.root)
            self.assertTrue(result)
            after=probabilities(self.model.forward(x)[0])[index]
            self.assertGreater((after-before)*expected_sign,0)


if __name__ == "__main__": unittest.main()
