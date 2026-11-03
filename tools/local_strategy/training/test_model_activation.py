import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import model_activation as activation
from decision_net import DecisionNet, features
from spend_policy import spend_features, WAIT


class ActivationChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.temp.name).resolve()
        self.config = self.root / "runtime.json"
        self.original = {"strict_model_only":True, "spend_encoding":"spend-v2",
                         "weights":"old-tactic", "sha256":"old", "spend_weights":"old-spend", "spend_sha256":"old",
                         "other_setting":"preserved"}
        activation.atomic_json(self.config, self.original)
        self.run = self.root / "run"; self.run.mkdir()
        DecisionNet(len(features({}, {"id":"none"}))).save(self.run / "candidate.npz")
        DecisionNet(len(spend_features({}, WAIT))).save(self.run / "spend-candidate.npz")
        self.report = {"status":"complete", "candidate_sha256":self.sha("candidate.npz"),
                       "rounds":[{"spend_sha256":self.sha("spend-candidate.npz"),
                                   "reward_breakdown":{"version":"bfme-outcome-reward-v3"}}]}
        activation.atomic_json(self.run / "report.json", self.report)
        activation.atomic_json(self.run / "spend-metadata.json", {"encoding":"spend-v2"})

    def sha(self, name): return activation.hashlib.sha256((self.run / name).read_bytes()).hexdigest()
    def tearDown(self): self.temp.cleanup()

    def test_pair_switch_preserves_previous_and_is_idempotent(self):
        result = activation.activate(self.run, self.config)
        current = activation.read(self.config)
        self.assertTrue(result["changed"])
        self.assertEqual(current["other_setting"], "preserved")
        self.assertEqual(activation.read(self.root / "runtime.previous.json"), self.original)
        for field, hashfield in [("weights","sha256"),("spend_weights","spend_sha256")]:
            self.assertEqual(activation.hashlib.sha256(Path(current[field]).read_bytes()).hexdigest(), current[hashfield])
        self.assertFalse(activation.activate(self.run, self.config)["changed"])

    def test_incomplete_and_corrupt_pairs_never_replace_live_config(self):
        self.report["status"] = "failed"
        activation.atomic_json(self.run / "report.json", self.report)
        with self.assertRaises(ValueError): activation.activate(self.run, self.config)
        self.report["status"] = "complete"
        activation.atomic_json(self.run / "report.json", self.report)
        (self.run / "spend-candidate.npz").write_bytes(b"broken")
        with self.assertRaises(ValueError): activation.activate(self.run, self.config)
        self.assertEqual(activation.read(self.config), self.original)

    def test_nonfinite_and_wrong_shapes_are_rejected_even_with_matching_hash(self):
        model = DecisionNet(len(features({}, {"id":"none"})))
        model.weights["b0"][0] = np.nan
        model.save(self.run / "candidate.npz")
        self.report["candidate_sha256"] = self.sha("candidate.npz")
        activation.atomic_json(self.run / "report.json", self.report)
        with self.assertRaises(ValueError): activation.activate(self.run, self.config)
        DecisionNet(3).save(self.run / "candidate.npz")
        self.report["candidate_sha256"] = self.sha("candidate.npz")
        activation.atomic_json(self.run / "report.json", self.report)
        with self.assertRaises(ValueError): activation.activate(self.run, self.config)
        self.assertEqual(activation.read(self.config), self.original)

    def test_interruption_before_commit_preserves_old_complete_pair(self):
        original = activation.atomic_json
        def interrupt(path, value):
            if path == self.config: raise OSError("simulated interrupted commit")
            return original(path, value)
        with patch.object(activation, "atomic_json", side_effect=interrupt):
            with self.assertRaises(OSError): activation.activate(self.run, self.config)
        self.assertEqual(activation.read(self.config), self.original)
        self.assertTrue(activation.activate(self.run, self.config)["changed"])

    def test_old_run_cannot_roll_back_newer_activation(self):
        config = dict(self.original, model_activation={"generation":self.run.stat().st_ctime_ns + 1000000})
        activation.atomic_json(self.config, config)
        self.assertEqual(activation.activate(self.run, self.config)["skipped"], "older_run")
        self.assertEqual(activation.read(self.config), config)


if __name__ == "__main__": unittest.main()
