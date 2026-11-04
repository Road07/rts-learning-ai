from pathlib import Path
import tempfile
import unittest
import numpy as np
from automatic_training import update
from decision_net import DecisionNet, features, FACTIONS
from episode_policy import EpisodePolicy
from normal_match_training import faction_imitation
from spend_policy import spend_features, WAIT, load_spend_model


class FactionChecks(unittest.TestCase):
    def model(self): return DecisionNet(len(features({}, {"id":"none"}))).ensure_factions()
    def snapshots(self, model): return {f:{k:v.copy() for k,v in m.weights.items()} for f,m in model.factions.items()}
    def assert_unchanged(self, model, snapshots, except_faction):
        for faction in FACTIONS:
            if faction == except_faction: continue
            for key in snapshots[faction]: np.testing.assert_array_equal(snapshots[faction][key],model.factions[faction].weights[key])

    def test_migration_preserves_scores_and_has_no_shared_arrays(self):
        model = self.model()
        for faction in FACTIONS:
            obs = {"faction":faction}
            x = features(obs,{"id":"attack_enemy"})[None,:]
            np.testing.assert_array_equal(model.forward(x)[0],model.for_faction(faction).forward(x)[0])
        self.assertFalse(np.shares_memory(model.factions[FACTIONS[0]].weights["w0"],model.factions[FACTIONS[1]].weights["w0"]))
        with self.assertRaises(ValueError): model.for_faction("unknown")

    def test_goblin_gradient_cannot_change_other_factions_or_base(self):
        model = self.model(); before = self.snapshots(model)
        base = model.weights["w0"].copy()
        obs = {"faction":"FactionWild"}
        _,_,action = EpisodePolicy(42,"sample").choose(model,obs,[{"id":"attack_enemy"},{"id":"defend_home"}])
        result = update(model,[action],.5,0,.01)
        self.assertTrue(result["factions"]["FactionWild"]["updated"])
        self.assert_unchanged(model,before,"FactionWild")
        np.testing.assert_array_equal(base,model.weights["w0"])
        self.assertFalse(np.array_equal(before["FactionWild"]["w0"],model.factions["FactionWild"].weights["w0"]))

    def test_spend_gradient_and_normal_replay_use_own_bank(self):
        model = DecisionNet(len(spend_features({},WAIT))).ensure_factions()
        before = self.snapshots(model)
        obs = {"faction":"FactionAngmar","money":1000}
        choices = [WAIT,{"id":"train:1:Thrall","kind":"train","cost":100}]
        _,_,action = EpisodePolicy(42,"sample").choose(model,obs,choices,spend_features,"spend")
        self.assertTrue(update(model,[action],.5,0,.01,spend_features)["updated"])
        self.assert_unchanged(model,before,"FactionAngmar")
        trace = {"features":[spend_features(obs,c).tolist() for c in choices],"selected_index":1}
        before = self.snapshots(model)
        result = faction_imitation(model,[{"faction":"FactionAngmar","spend":trace}],"spend")
        self.assertTrue(result["updated"])
        self.assert_unchanged(model,before,"FactionAngmar")

    def test_round_trip_preserves_trained_bank_and_old_spend_migration(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory)/"network.npz"
            model = self.model(); model.factions["FactionMen"].weights["b0"][0] += .25
            model.save(path); restored = DecisionNet.load(path)
            self.assertEqual(set(restored.factions),set(FACTIONS))
            for f in FACTIONS:
                for k in model.weights: np.testing.assert_array_equal(restored.factions[f].weights[k],model.factions[f].weights[k])
            inputs = len(spend_features({},WAIT))
            legacy = len(spend_features({},WAIT,include_mechanics=False))-32
            old = DecisionNet(legacy).ensure_factions(); old.save(path)
            migrated = load_spend_model(path)
            for f in FACTIONS:
                self.assertEqual(migrated.factions[f].weights["w0"].shape[0],inputs)
                np.testing.assert_array_equal(migrated.factions[f].weights["w0"][:legacy],old.factions[f].weights["w0"])
            migrated.save(path); DecisionNet.load(path)


if __name__ == "__main__": unittest.main()
