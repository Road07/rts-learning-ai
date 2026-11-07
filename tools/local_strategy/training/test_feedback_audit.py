import copy
import unittest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'service'))
from feedback_audit import build


def trace(frame=10,mode='sample'):
    return {'observation':{'player_index':3,'decision_frame':frame,'faction':'FactionDwarves'},
            'candidates':[{'kind':'cancel'},{'kind':'wait'}],'selected_index':0,'mode':mode}


class FeedbackAudit(unittest.TestCase):
    def test_opponent_effects_do_not_become_learner_feedback(self):
        credit={(7,10,'spend'):{'components':{'research_restart_delay':-.1},'reward':-.1,'matured':True}}
        result=build([3],{'spend':[trace()]},credit,[])
        self.assertEqual(result['trace_groups'][0]['nonzero_components'],{})
        self.assertFalse(result['all_player_credit'][0]['learner'])
        self.assertEqual(result['all_player_credit'][0]['nonzero_components']['research_restart_delay'],1)

    def test_dispatch_maturity_and_unobserved_effects_are_distinct(self):
        traces=[trace(frame) for frame in [10,20,30,40]]
        events=[{'player':3,'observed_frame':frame,'head':'spend','submitted':True} for frame in [20,30,40]]
        credit={(3,30,'spend'):{'components':{},'reward':0,'matured':False},(3,40,'spend'):{'components':{},'reward':0,'matured':True}}
        group=build([3],{'spend':traces},credit,events)['trace_groups'][0]
        self.assertEqual(group['zero_credit_reasons'],{'no_dispatch':1,'no_credit_match':1,'unmatured':1,'matured_without_measured_local_effect':1})
        self.assertEqual(group['counts']['submitted'],3)

    def test_terminal_and_local_effects_are_separate_and_inputs_unchanged(self):
        traces=[trace(10),trace(20,'evaluate')]
        credit={(3,10,'spend'):{'components':{},'reward':1,'terminal_share':1,'matured':True},(3,20,'spend'):{'components':{'research_restart_delay':-.1},'reward':-.1,'matured':True}}
        before=copy.deepcopy((traces,credit))
        group=build([3],{'spend':traces},credit,[])['trace_groups'][0]
        self.assertEqual(group['counts']['terminal_only'],1)
        self.assertEqual(group['counts']['local_feedback'],1)
        self.assertEqual(group['counts']['sample_multichoice'],1)
        self.assertEqual((traces,credit),before)


if __name__=='__main__':unittest.main()
