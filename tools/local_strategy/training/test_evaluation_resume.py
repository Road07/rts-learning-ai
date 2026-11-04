import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import automatic_training as training
import training_supervisor as supervisor


class EvaluationResume(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.run=Path(self.temp.name)
        for name in ['baseline.npz','candidate.npz','spend-baseline.npz','spend-candidate.npz']:
            (self.run/name).write_bytes(name.encode())
        self.config=self.run/'runtime.json'
        self.environment={'sha256':training.sha(self.run/'baseline.npz'),'spend_sha256':training.sha(self.run/'spend-baseline.npz'),'reward_sha256':'reward','game_rules_sha256':'rules','arena_directory':str(self.run)}
        training.write_json(self.config,self.environment)
        training.write_json(self.run/'train-000-runtime.json',self.environment)
        self.report={'status':'running','settings':{'evaluate':True,'cycles':1},'rounds':[{'checkpoint_sha256':training.sha(self.run/'candidate.npz'),'spend_sha256':training.sha(self.run/'spend-candidate.npz')}],'baseline_sha256':training.sha(self.run/'baseline.npz')}
        training.write_json(self.run/'report.json',self.report)

    def test_committed_pair_resumes_but_changed_weights_or_policy_do_not(self):
        training.resumable_evaluation(self.run,self.config)
        self.environment['reward_sha256']='changed'
        training.write_json(self.config,self.environment)
        with self.assertRaises(ValueError): training.resumable_evaluation(self.run,self.config)
        self.environment['reward_sha256']='reward'
        training.write_json(self.config,self.environment)
        (self.run/'candidate.npz').write_bytes(b'changed')
        with self.assertRaises(ValueError): training.resumable_evaluation(self.run,self.config)

    def test_partial_rollout_is_not_resumable(self):
        self.report['rounds']=[]
        training.write_json(self.run/'report.json',self.report)
        with self.assertRaises(ValueError): training.resumable_evaluation(self.run,self.config)

    def test_completed_baseline_is_kept_when_candidate_was_interrupted(self):
        args=SimpleNamespace(seed=1759,cycles=1,seconds=6,stage='late',case='baseline',config=self.config)
        self.report['evaluation_progress']={'eval-baseline':{'name':'eval-baseline','weights_sha256':training.sha(self.run/'baseline.npz'),'spend_sha256':training.sha(self.run/'spend-baseline.npz')}}
        (self.run/'eval-candidate').mkdir()
        with patch.object(training,'episode_data',return_value=(.1,[],0,[])) as old, patch.object(training,'run_episode',return_value=(.2,[],0,[])) as new, patch.object(training,'read_json',side_effect=lambda p: self.environment if Path(p)==self.config else {}), patch.object(training,'compare_economy',return_value={}):
            training.evaluate_pair(args,self.run,self.report,*[self.run/n for n in ['baseline.npz','candidate.npz','spend-baseline.npz','spend-candidate.npz']])
        self.assertEqual(old.call_count,1)
        self.assertEqual(new.call_count,1)
        self.assertEqual(new.call_args.args[2],'eval-candidate-retry-001')
        self.assertEqual(new.call_args.kwargs['roster_seed'],1759)
        self.assertFalse(self.report['evaluation']['sufficient_to_claim_strength'])

    def test_supervisor_preserves_valid_pending_evaluation(self):
        path=self.run/'state.json'
        training.write_json(path,{'schema':1,'completed':29,'next_seed':1759,'schedule_index':29,'last_completed_run':None,'pending_run':str(self.run)})
        with patch.object(training,'resumable_evaluation',return_value=self.report):
            state=supervisor.load_progress(path)
        self.assertEqual(state['pending_run'],str(self.run))
        self.assertEqual(state['completed'],29)


if __name__=='__main__': unittest.main()
