import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import training_supervisor as supervisor


def complete(folder):
    folder.mkdir()
    (folder/"candidate.npz").write_bytes(b"test tactic checkpoint")
    (folder/"spend-candidate.npz").write_bytes(b"test command checkpoint")
    (folder/"spend-metadata.json").write_text(json.dumps({"encoding":"spend-v2"}),encoding="utf-8")
    report={"status":"complete","candidate_sha256":supervisor.digest(folder/"candidate.npz"),
        "settings":{"seed":1729},"rounds":[{"reward":.25,"spend_sha256":supervisor.digest(folder/"spend-candidate.npz"),
        "reward_breakdown":{"version":"bfme-outcome-reward-v3"}}]}
    (folder/"report.json").write_text(json.dumps(report),encoding="utf-8")


class SupervisorChecks(unittest.TestCase):
    def setUp(self):
        self.root=Path(__file__).resolve().parent
        self.temp=tempfile.TemporaryDirectory(dir=self.root)
        self.folder=Path(self.temp.name).resolve()
        self.assertEqual(self.folder.parent,self.root)
    def tearDown(self): self.temp.cleanup()

    def test_changed_checkpoint_and_partial_run_are_rejected(self):
        checkpoint=self.folder/"done"; complete(checkpoint)
        supervisor.checked_run(checkpoint)
        (checkpoint/"candidate.npz").write_bytes(b"interrupted data")
        with self.assertRaises(ValueError): supervisor.checked_run(checkpoint)

    def state(self,pending):
        previous=self.folder/"previous"; complete(previous)
        path=self.folder/"state.json"
        supervisor.atomic_write(path,{"schema":1,"completed":3,"next_seed":1733,"schedule_index":3,
            "last_completed_run":str(previous),"pending_run":str(pending)})
        return path

    def test_finished_pending_run_is_recovered(self):
        pending=self.folder/"pending"; complete(pending)
        path=self.state(pending)
        state=supervisor.load_progress(path)
        self.assertEqual((state["completed"],state["next_seed"],state["schedule_index"]),(4,1734,4))
        self.assertEqual(state["last_completed_run"],str(pending))
        self.assertNotIn("pending_run",state)

    def test_interrupted_pending_run_preserves_previous_checkpoint(self):
        pending=self.folder/"pending"; pending.mkdir()
        path=self.state(pending)
        state=supervisor.load_progress(path)
        self.assertEqual(state["completed"],3)
        self.assertEqual(state["next_seed"],1733)
        self.assertTrue(state["last_completed_run"].endswith("previous"))

    def test_legacy_reports_are_skipped_without_discarding_valid_pair(self):
        complete(self.folder/"good")
        bad=self.folder/"old"; bad.mkdir()
        (bad/"report.json").write_text(json.dumps({"status":"complete","rounds":[{"reward_breakdown":None}]}),encoding="utf-8")
        with patch.object(supervisor,"RUNS",self.folder):
            self.assertEqual(supervisor.latest_completed(),self.folder/"good")


if __name__=="__main__": unittest.main()
