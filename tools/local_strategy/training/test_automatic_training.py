"""Fast checks for reward boundaries and the actual policy-gradient direction."""
import unittest
import tempfile
from pathlib import Path
import numpy as np
from automatic_training import DecisionNet, features, probabilities, survival_reward, update
from episode_policy import EpisodePolicy
from spend_policy import spend_features, legal_spend_options, load_spend_model, EXTRA_KINDS


class TrainingChecks(unittest.TestCase):
    def test_all_command_families_are_explicit_choices(self):
        choices=[{"id":k+":1:test:0:0","kind":k,"cost":0,"template":"test"} for k in EXTRA_KINDS]
        result=legal_spend_options(choices,0)
        self.assertEqual(len(result),len(EXTRA_KINDS)+1)
        encodings=[spend_features({},c) for c in result]
        self.assertEqual(len({tuple(x) for x in encodings}),len(result))
        with self.assertRaises(ValueError): legal_spend_options([{"id":"cheat:1","kind":"cheat","cost":0}],0)

    def test_v1_migration_preserves_existing_scores(self):
        obs={"money":1000}
        choices=legal_spend_options([{"id":"train:2:Soldier","kind":"train","cost":100}],1000)
        x=np.stack([spend_features(obs,c) for c in choices])
        legacy=len(spend_features(obs,choices[0],include_mechanics=False))-32
        old=DecisionNet(legacy)
        before=old.forward(x[:,:legacy])[0]
        test_root=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(dir=test_root) as directory:
            self.assertEqual(Path(directory).resolve().parent,test_root)
            path=Path(directory)/"old.npz"
            old.save(path)
            migrated=load_spend_model(path)
        np.testing.assert_allclose(migrated.forward(x)[0],before,rtol=1e-6,atol=1e-7)

    def test_stances_and_tunnel_targets_have_distinct_features(self):
        stance={"id":"stance:1:x:0:1","kind":"stance","variant":1}
        other={**stance,"variant":3}
        self.assertFalse(np.array_equal(spend_features({},stance),spend_features({},other)))
        tunnel={"id":"enter:1:x:2:0","kind":"enter","target_relation":"self","target_distance":100}
        far={**tunnel,"target_relation":"ally","target_distance":1500}
        self.assertFalse(np.array_equal(spend_features({},tunnel),spend_features({},far)))

    def test_spend_masks_and_wait(self):
        options=[{"id":"build:1:Farm","kind":"build","cost":300,"economy":True,"farm_share":.69},
            {"id":"train:2:Soldier","kind":"train","cost":100},
            {"id":"build:1:Barracks","kind":"build","cost":500}]
        legal=legal_spend_options(options,300)
        self.assertEqual([o["id"] for o in legal],["none","build:1:Farm","train:2:Soldier"])
        self.assertEqual(legal_spend_options([],0)[0]["kind"],"wait")

    def test_spend_gradient_and_distinct_build_train_features(self):
        obs={"money":1000}
        options=legal_spend_options([{"id":"build:1:Farm","kind":"build","cost":300,"economy":True,"farm_share":.75},
            {"id":"train:2:Soldier","kind":"train","cost":300,"role":0}],1000)
        self.assertFalse(np.array_equal(spend_features(obs,options[1]),spend_features(obs,options[2])))
        model=DecisionNet(len(spend_features(obs,options[0])))
        _,_,action=EpisodePolicy(42,"sample").choose(model,obs,options,spend_features,"spend")
        chosen=action["selected_index"]
        before=action["probabilities"][chosen]
        self.assertTrue(update(model,[action],.5,0,.01,spend_features)["updated"])
        after=probabilities(model.forward(np.stack([spend_features(obs,c) for c in options]))[0])[chosen]
        self.assertGreater(after,before)

    def test_income_and_completed_army_reward_without_order_bonus(self):
        report={"training":{"reward_version":"survival-income-army-v2","truncated":True,
            "initial":[{"player":3,"id":1,"cost":100,"health":1}],
            "final":[{"player":3,"id":1,"cost":100,"health":1}],
            "initial_finance":{"earned":0,"military_value":100},
            "final_finance":{"earned":0,"military_value":100}}}
        self.assertEqual(survival_reward(report),0)
        report["training"]["final_finance"].update(earned=20,military_value=200)
        self.assertAlmostEqual(survival_reward(report),.3)

    def test_reward_counts_only_original_own_assets(self):
        data = {"training":{"reward_version":"initial-own-assets-v1","truncated":True,
            "initial":[{"player":3,"id":1,"cost":100,"health":1}, {"player":4,"id":2,"cost":100,"health":1}],
            "final":[{"player":3,"id":1,"health":.5}, {"player":3,"id":99,"health":1,"cost":99999}]}}
        self.assertEqual(survival_reward(data), -.75)
        data["training"]["final"][0]["health"] = float("nan")
        with self.assertRaises(ValueError): survival_reward(data)

    def test_positive_return_increases_sampled_probability(self):
        observation = {"faction":"FactionDwarves"}
        candidates = [{"id":"defend_1"}, {"id":"attack_2"}]
        model = DecisionNet(len(features(observation,candidates[0])))
        policy = EpisodePolicy(42,"sample")
        _, _, action = policy.choose(model,observation,candidates)
        chosen = action["selected_index"]
        before = action["probabilities"][chosen]
        result = update(model,[action],.5,0,.01)
        self.assertTrue(result["updated"])
        scores,_ = model.forward(np.stack([features(observation,c) for c in candidates]))
        self.assertGreater(probabilities(scores)[chosen], before)
        with self.assertRaises(ValueError): update(model,[action],.5,0,.01)

    def test_single_choice_does_not_learn(self):
        obs = {}
        candidate = {"id":"defend_1"}
        model = DecisionNet(len(features(obs,candidate)))
        _,_,action = EpisodePolicy(1,"sample").choose(model,obs,[candidate])
        self.assertFalse(update(model,[action],-1,0,.01)["updated"])

    def test_evaluation_is_greedy_and_reproducible(self):
        obs = {}
        candidates = [{"id":"defend_1"},{"id":"attack_2"}]
        model = DecisionNet(len(features(obs,candidates[0])))
        expected = model.predict(obs,candidates)
        for seed in (1,2,3):
            selected,_,action = EpisodePolicy(seed,"evaluate").choose(model,obs,candidates)
            self.assertEqual(selected,expected)
            self.assertEqual(action["mode"],"evaluate")


if __name__ == "__main__": unittest.main()
