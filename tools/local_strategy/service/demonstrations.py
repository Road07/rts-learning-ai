"""Exact demonstration-to-candidate matching. No nearest action or success inference."""
import math

SCHEMA='bc-demonstration-v1'


def argument(command,index):
    args=command.get('args',[])
    if index>=len(args) or args[index].get('redacted'):return None
    return args[index].get('value')


def same_point(candidate,point,x='x',y='y'):
    if not isinstance(point,dict):return False
    values=[candidate.get(x),candidate.get(y),point.get('x'),point.get('y')]
    return all(isinstance(v,(int,float)) and math.isfinite(v) for v in values) and abs(values[0]-values[2])<=.01 and abs(values[1]-values[3])<=.01


def match(snapshot,command):
    if snapshot.get('demonstration_schema')!=SCHEMA or snapshot.get('source')!='human' or snapshot.get('capture')!='pre_dispatch' or not snapshot.get('policy_available'):
        return {'matched':False,'reason':'missing_policy_snapshot'}
    if snapshot.get('candidate_policy')!='model-default-bounded-v1':return {'matched':False,'reason':'candidate_policy_mismatch'}
    obs=snapshot.get('policy_observation',{})
    native=snapshot.get('payload',{}).get('observation',{})
    if not native.get('ok') or native.get('observed_frame')!=snapshot.get('frame') or native.get('player_index')!=snapshot.get('player') or native.get('faction')!=obs.get('faction') or 'spell_points' not in native or 'map_extent' not in native:
        return {'matched':False,'reason':'incomplete_native_pre_state'}
    if obs.get('spell_points')!=native['spell_points']:return {'matched':False,'reason':'post_state_feature_mismatch'}
    if int(snapshot.get('command_id',-1))!=int(command.get('id',-2)) or snapshot.get('player')!=command.get('player') or snapshot.get('frame')!=command.get('frame') or obs.get('decision_frame')!=command.get('frame'):
        return {'matched':False,'reason':'state_action_identity_mismatch'}
    selected=command.get('selection_before',[]);name=command.get('command')
    head='spend';kind=None;filters={};point=None;units=None;movement=False
    if name in ('MSG_DOZER_CONSTRUCT','MSG_QUEUE_UNIT_CREATE','MSG_QUEUE_UPGRADE','MSG_CANCEL_UNIT_CREATE','MSG_CANCEL_UPGRADE','MSG_EVACUATE'):
        if len(selected)!=1:return {'matched':False,'reason':'actor_group_not_represented'}
        filters['producer']=int(selected[0])
        if name=='MSG_DOZER_CONSTRUCT':
            kind='build';filters['template']=command.get('requested_template');point=argument(command,1)
            angle=argument(command,2)
            if not isinstance(angle,(int,float)) or not math.isfinite(angle) or abs(angle)>1e-5:return {'matched':False,'reason':'rotation_not_represented'}
        elif name=='MSG_QUEUE_UNIT_CREATE':
            if argument(command,0) is not False or argument(command,3) is not False or argument(command,4) is not False:return {'matched':False,'reason':'batch_index_or_secondary_queue_not_represented'}
            kind='train';filters['template']=command.get('requested_template')
        elif name=='MSG_QUEUE_UPGRADE':kind='research';filters['template']=command.get('requested_upgrade')
        elif name in ('MSG_CANCEL_UPGRADE','MSG_CANCEL_UNIT_CREATE'):
            if name=='MSG_CANCEL_UNIT_CREATE' and (argument(command,0) is not False or argument(command,2) is not False):return {'matched':False,'reason':'bulk_or_index_cancel_not_represented'}
            kind='cancel';filters['template']=command.get('requested_upgrade') if name=='MSG_CANCEL_UPGRADE' else command.get('requested_template')
            filters['queue_kind']='research' if name=='MSG_CANCEL_UPGRADE' else 'unit'
        else:kind='exit'
    elif name=='MSG_WALL_HUB_CONSTRUCT_SPAN':
        kind='wall';filters['producer']=argument(command,4);point=argument(command,2)
        filters['wall_options']=argument(command,3)
    elif name=='MSG_ENTER':
        if len(selected)!=1 or argument(command,0)!=selected[0]:return {'matched':False,'reason':'actor_group_not_represented'}
        kind='enter';filters.update(producer=selected[0],target=argument(command,1))
    elif name in ('MSG_DO_MOVETO','MSG_DO_ATTACK_OBJECT'):
        if not selected:return {'matched':False,'reason':'missing_actors'}
        head='tactical';units=sorted(map(int,selected))
        if name=='MSG_DO_MOVETO':kind='move';movement=True;point=argument(command,0)
        else:kind='attack';filters['target']=argument(command,0)
    else:return {'matched':False,'reason':'command_not_represented'}
    if name in ('MSG_DOZER_CONSTRUCT','MSG_DO_MOVETO','MSG_WALL_HUB_CONSTRUCT_SPAN') and not isinstance(point,dict):return {'matched':False,'reason':'missing_or_redacted_parameters'}
    if any(v is None for v in filters.values()):return {'matched':False,'reason':'missing_or_redacted_parameters'}
    candidates=snapshot.get('spend_candidates' if head=='spend' else 'tactical_candidates',[])
    hits=[]
    for i,candidate in enumerate(candidates):
        kind_matches=candidate.get('kind') in ('scout','defend','help') if movement else candidate.get('kind')==kind
        if not kind_matches or any(candidate.get(k)!=v for k,v in filters.items()):continue
        if point is not None and not same_point(candidate,point):continue
        if name=='MSG_WALL_HUB_CONSTRUCT_SPAN' and (not candidate.get('connected_wall') or not same_point(candidate,argument(command,1),'start_x','start_y')):continue
        if units is not None and sorted(map(int,candidate.get('units',[])))!=units:continue
        hits.append(i)
    if len(hits)!=1:return {'matched':False,'reason':'ambiguous_candidates' if hits else 'outside_candidate_space','head':head,'kind':kind}
    return {'matched':True,'head':head,'selected_index':hits[0],'selected_id':candidates[hits[0]]['id'],'candidate':candidates[hits[0]]}


def queue_evidence(before,result,choice):
    """Only confirm exact native queue insertions/removals; no quality labels."""
    if result.get('dispatcher_error'):return 'dispatcher_error'
    if choice['kind'] not in ('train','research','cancel'):return 'dispatch_not_verified'
    producer=choice.get('producer');old=next((o.get('queue',[]) for o in before.get('objects',[]) if o['id']==producer),[])
    after=next((o['queue'] for o in result.get('selected_queues',[]) if o['producer']==producer),None)
    if after is None:return 'missing_queue_result'
    def ids(queue):return {(q.get('id'),q.get('upgrade') or q.get('template')) for q in queue}
    old_ids,new_ids=ids(old),ids(after);template=choice.get('template')
    if choice['kind']=='cancel':
        identity=(choice.get('variant'),template)
        return 'native_queue_removed' if identity in old_ids and identity not in new_ids else 'dispatch_not_verified'
    return 'native_queue_inserted' if any(name==template for _,name in new_ids-old_ids) else 'dispatch_not_verified'
