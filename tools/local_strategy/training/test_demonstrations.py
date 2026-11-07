import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from export_demonstrations import export
from demonstrations import match,queue_evidence,SCHEMA


def pair(kind='train'):
    option={'id':'choice','kind':kind,'producer':10,'template':'unit','x':100.,'y':200.}
    snapshot={'demonstration_schema':SCHEMA,'candidate_policy':'model-default-bounded-v1','source':'human','capture':'pre_dispatch','policy_available':True,'command_id':1,'frame':5,'player':3,
              'payload':{'observation':{'ok':True,'observed_frame':5,'player_index':3,'faction':'FactionDwarves','spell_points':5,'map_extent':{'extent_x':1000,'extent_y':1000}}},
              'policy_observation':{'decision_frame':5,'player_index':3,'faction':'FactionDwarves','spell_points':5},'spend_candidates':[option,{'id':'wait','kind':'wait'}],'tactical_candidates':[]}
    command={'id':1,'frame':5,'player':3,'command':'MSG_QUEUE_UNIT_CREATE','selection_before':[10],'requested_template':'unit',
             'args':[{'value':False},{'value':42},{'value':0},{'value':False},{'value':False}]}
    return snapshot,command


class Demonstrations(unittest.TestCase):
    def test_exact_train_identity_only(self):
        snapshot,command=pair();self.assertTrue(match(snapshot,command)['matched'])
        for field,value in [('frame',6),('player',4),('id',2)]:
            changed=dict(command,**{field:value});self.assertFalse(match(snapshot,changed)['matched'])
        snapshot['source']='model';self.assertFalse(match(snapshot,command)['matched'])

    def test_later_spell_points_cannot_enter_demonstration(self):
        snapshot,command=pair();snapshot['policy_observation']['spell_points']=10
        self.assertEqual(match(snapshot,command)['reason'],'post_state_feature_mismatch')

    def test_no_nearest_position_rotation_or_actor_relabelling(self):
        snapshot,command=pair('build');command.update(command='MSG_DOZER_CONSTRUCT',args=[{'value':42},{'value':{'x':100.,'y':200.}},{'value':0.}])
        self.assertTrue(match(snapshot,command)['matched'])
        command['args'][1]['value']['x']=101.;self.assertEqual(match(snapshot,command)['reason'],'outside_candidate_space')
        command['args'][1]['value']=None;self.assertEqual(match(snapshot,command)['reason'],'missing_or_redacted_parameters')
        command['args'][1]['value']={'x':100,'y':200};command['args'][2]['value']=1.;self.assertEqual(match(snapshot,command)['reason'],'rotation_not_represented')
        command['selection_before']=[10,11];self.assertEqual(match(snapshot,command)['reason'],'actor_group_not_represented')

    def test_wall_requires_same_hub_start_end_and_options(self):
        snapshot,command=pair('wall');option=snapshot['spend_candidates'][0];option.update(start_x=0.,start_y=0.,wall_options=2,connected_wall=True)
        command.update(command='MSG_WALL_HUB_CONSTRUCT_SPAN',selection_before=[],args=[{'value':42},{'value':{'x':0,'y':0}},{'value':{'x':100,'y':200}},{'value':2},{'value':10}])
        self.assertTrue(match(snapshot,command)['matched'])
        command['args'][4]['value']=11;self.assertFalse(match(snapshot,command)['matched'])
        command['args'][4]['value']=10;command['args'][1]['value']['x']=1;self.assertFalse(match(snapshot,command)['matched'])

    def test_redacted_target_and_ambiguous_choice_not_accepted(self):
        snapshot,command=pair('enter');command.update(command='MSG_ENTER',args=[{'value':10},{'value':20}]);snapshot['spend_candidates'][0]['target']=20
        self.assertTrue(match(snapshot,command)['matched'])
        command['args'][1]['redacted']=True;self.assertEqual(match(snapshot,command)['reason'],'missing_or_redacted_parameters')
        snapshot,command=pair();snapshot['spend_candidates'].append(dict(snapshot['spend_candidates'][0],id='another'))
        self.assertEqual(match(snapshot,command)['reason'],'ambiguous_candidates')

    def test_queue_evidence_is_not_dispatch_success(self):
        before={'objects':[{'id':10,'queue':[]}]};result={'dispatcher_error':False,'selected_queues':[{'producer':10,'queue':[{'id':1,'template':'unit','upgrade':''}]}]}
        choice={'kind':'train','producer':10,'template':'unit'}
        self.assertEqual(queue_evidence(before,result,choice),'native_queue_inserted')
        before['objects'][0]['queue']=copy.deepcopy(result['selected_queues'][0]['queue'])
        self.assertEqual(queue_evidence(before,result,choice),'dispatch_not_verified')
        self.assertEqual(queue_evidence(before,result,dict(choice,kind='build')),'dispatch_not_verified')

    def test_move_does_not_invent_strategic_intent(self):
        snapshot,command=pair();command.update(command='MSG_DO_MOVETO',selection_before=[20],args=[{'value':{'x':100,'y':200}}])
        snapshot['tactical_candidates']=[{'id':'defend','kind':'defend','units':[20],'x':100,'y':200}]
        self.assertTrue(match(snapshot,command)['matched'])
        snapshot['tactical_candidates'].append({'id':'scout','kind':'scout','units':[20],'x':100,'y':200})
        self.assertEqual(match(snapshot,command)['reason'],'ambiguous_candidates')

    def test_export_eligibility_fixture_and_catalogue_filters(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root=Path(folder);logs=root/'logs';logs.mkdir();rules=root/'rules.json';rules.write_text('{}')
            sha=hashlib.sha256(rules.read_bytes()).hexdigest();config=root/'runtime.json';config.write_text(json.dumps({'game_rules':str(rules),'game_rules_sha256':sha}))
            snapshot,command=pair();snapshot['game_rules_sha256']=sha
            header={'event':'human_session_start','fixture':False,'scope':'fresh_local_human','capture':'pre_dispatch','fog':'own_and_living_allied_vision'}
            states={'event':'human_state','reason':'before_command','player':3,'command_id':1,'frame':5,'objects':[{'id':10,'queue':[]}]}
            result={'event':'human_command_result','player':3,'id':1,'frame':5,'dispatcher_error':False,'selected_queues':[{'producer':10,'queue':[{'id':1,'template':'unit','upgrade':''}]}]}
            command['event']='human_command';snapshot['event']='human_policy_snapshot'
            def write():
                (logs/'session.jsonl').write_text(''.join(json.dumps({'session':'human','match':0,'data':r})+'\n' for r in [header,states,snapshot,command,result]),encoding='utf-8')
            class Rules:
                def attach(self,*args):pass
            with patch('export_demonstrations.PublicGameRules',return_value=Rules()):
                write();report=export(logs,root/'real',config);self.assertEqual(report['counts']['training_eligible'],1)
                header['fixture']=True;write();self.assertEqual(export(logs,root/'excluded',config)['counts']['fixture_session_excluded'],1)
                report=export(logs,root/'fixture',config,True);self.assertEqual(report['counts']['training_eligible'],0)
                row=json.loads((root/'fixture/demonstrations.jsonl').read_text());self.assertEqual(row['split'],'fixture_validation')
                header['fixture']=False;snapshot['game_rules_sha256']='old';write();self.assertEqual(export(logs,root/'old',config)['counts']['game_rules_version_mismatch'],1)


if __name__=='__main__':unittest.main()
