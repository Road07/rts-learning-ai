"""Failure-path checks; no native games or training."""
import unittest
from unittest.mock import patch
from economy_resources import worker_budget,close_vector
from economy_common import ROOT
from gym_bridge import NativeMatchBackend


class RecoveryChecks(unittest.TestCase):
    def test_measured_light_budget_preserves_reserves_and_caps_at_five(self):
        from economy_resources import light_worker_budget
        gib=1024**3
        self.assertEqual(light_worker_budget(8,{'free_physical':12*gib,'free_commit':16*gib}),5)
        self.assertEqual(light_worker_budget(8,{'free_physical':6*gib,'free_commit':16*gib}),1)
        with self.assertRaises(RuntimeError):light_worker_budget(8,{'free_physical':4*gib,'free_commit':16*gib})

    def test_teardown_503_is_separate_from_training_failure(self):
        import json,tempfile
        from pathlib import Path
        from economy_recovery_smoke import summarize
        with tempfile.TemporaryDirectory(dir=ROOT/'AI-Test-Sahasi') as folder:
            root=Path(folder);episode=root/'training-episodes/worker-00/e-fixture';episode.mkdir(parents=True)
            (root/'run.json').write_text(json.dumps({'status':'complete','transitions':1,'parallel':1}))
            (episode/'result.json').write_text(json.dumps({'ok':False,'error':'Inference failed: [0, 503]'}))
            (episode/'reward.jsonl').write_text(json.dumps({'event':'step','terminated':False,'truncated':False})+'\n')
            report=summarize(root,0,1)
            self.assertEqual(report['cancelled_at_training_budget'],1)
            self.assertEqual(report['failed_episodes'],0)
            self.assertFalse(report['passed']) # Too short; never fake a passing smoke.
            self.assertEqual(summarize(root,1,1)['failed_episodes'],1)

    def test_memory_budget(self):
        self.assertEqual(worker_budget(8,13*1024**3),3)
        self.assertEqual(worker_budget(8,40*1024**3),8)
        with self.assertRaises(RuntimeError):worker_budget(8,5*1024**3)

    def test_startup_retries_exact_same_seed(self):
        backend=object.__new__(NativeMatchBackend)
        with patch.object(backend,'_reset_once',side_effect=[TimeoutError('fixture'),{'done':False}]) as reset,patch.object(backend,'close') as close:
            self.assertEqual(backend.reset(42),{'done':False})
            self.assertEqual([c.args for c in reset.call_args_list],[(42,),(42,)])
            close.assert_called_once()

    def test_persistent_failure_is_not_hidden(self):
        backend=object.__new__(NativeMatchBackend)
        with patch.object(backend,'_reset_once',side_effect=RuntimeError('fixture')) as reset,patch.object(backend,'close'):
            with self.assertRaisesRegex(RuntimeError,'fixture'):backend.reset(42)
            self.assertEqual(reset.call_count,2)

    def test_broken_pipe_cleanup_is_bounded(self):
        from unittest.mock import Mock
        remote=Mock();remote.poll.return_value=True;remote.recv.side_effect=EOFError;remote.send.side_effect=BrokenPipeError
        process=Mock();process.is_alive.return_value=False
        vector=Mock(closed=False,waiting=True,remotes=[remote],processes=[process])
        close_vector(vector);self.assertTrue(vector.closed);process.join.assert_called_once_with(timeout=3)


if __name__=='__main__':unittest.main()
