"""Versioned visible-entity tensors for the shared recurrent policy.

Raw object IDs are only references, never learned numeric features. Missing
facts have explicit masks. No hidden entities are reconstructed from rules.
"""
import math
import numpy as np
from public_game_rules import encode_card
from mechanics_features import ACTION_KEYS,ACTION_SCALES

ENCODING='rts-entities-v1'
FACTIONS=('FactionMen','FactionElves','FactionDwarves','FactionWild','FactionMordor','FactionIsengard','FactionAngmar')
KINDS=('defend','attack','help','scout','wait','build','train','hero','research','science','power','enter','exit','stance','formation','cancel','stop','wall')
RELATIONS=('self','ally','enemy','neutral')
ENTITY_FIELDS=('x','y','health_ratio','cost','queue_count','resource_share','member_count','complete','hero','structure','base','builder','mobile','armed','combat_active','contained','factory_disabled')
ACTION_FIELDS=('cost','cp_cost','x','y','start_x','start_y','farm_share','build_seconds','wall_length','wall_tiles','connected_wall','wall_seed','queue_progress','queue_paid_cost','queue_work_seconds','queue_remaining','target_distance','source_health','actor_coverage','target_present')
ENTITY_WIDTH=len(ENTITY_FIELDS)*2+len(encode_card({}))
ACTION_FIELDS=tuple(dict.fromkeys(ACTION_FIELDS+ACTION_KEYS+('variant','points_cost','needs_position','reviving','source_distance_home','source_hero','target_hero','source_contained','target_structure','queue_verified')))
ACTION_WIDTH=len(ACTION_FIELDS)*2+len(encode_card({}))
GLOBAL_WIDTH=16


def pair(value,scale=1.):
    if value is None:return [0.,0.]
    value=float(value)
    if not math.isfinite(value) or value<0:raise ValueError('Invalid entity/action observation')
    return [min(3.,value/scale),1.]


class EntityCodec:
    def __init__(self,rules,max_entities=256):
        self.rules=rules;self.max_entities=int(max_entities)
        if not 1<=self.max_entities<=1024:raise ValueError('Entity cap outside supported range')
        names=set(rules.data['cards'])
        for table in rules.data.get('tables',{}).values():
            if isinstance(table,dict):names.update(table)
        self.vocabulary=['<unknown>']+sorted(names)
        self.templates={name:i for i,name in enumerate(self.vocabulary)}

    def encode(self,observation,heads,delta_seconds=0.):
        state=observation.get('entity_state',{})
        if state.get('encoding')!=ENCODING or state.get('source')!='native_fog_filtered':raise ValueError('Missing current entity observations')
        if int(state['frame'])!=int(observation['decision_frame']):raise ValueError('Entity frame mismatch')
        faction=observation['faction']
        if faction not in FACTIONS:raise ValueError('Unknown observer faction')
        extent=state['map_extent'];width=float(extent['extent_x']);height=float(extent['extent_y'])
        if not math.isfinite(width+height) or width<=0 or height<=0:raise ValueError('Invalid public map extent')
        rows=state['entities'];ids=[int(e['id']) for e in rows]
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate entity ID')
        for e in rows:
            if e['relation'] not in RELATIONS or not e.get('visible',False):raise ValueError('Non-visible or unknown-relation entity supplied')
        wanted=set()
        for choices in heads.values():
            for c in choices:wanted.update(map(int,c.get('units',[])));wanted.update(int(c.get(k,0)) for k in ('producer','target'))
        kept=sorted(rows,key=lambda e:(int(e['id']) not in wanted,not (e.get('hero') or e.get('base')),RELATIONS.index(e['relation']),int(e['id'])))[:self.max_entities]
        kept.sort(key=lambda e:int(e['id']))
        dropped=len(rows)-len(kept);lookup={int(e['id']):i for i,e in enumerate(kept)}
        n=max(1,len(kept))
        entities=np.zeros((n,ENTITY_WIDTH),np.float32);valid=np.zeros(n,bool)
        templates=np.zeros(n,np.int64);relations=np.zeros(n,np.int64);owner_factions=np.full(n,7,np.int64);roles=np.zeros(n,np.int64)
        for i,e in enumerate(kept):
            valid[i]=True;templates[i]=self.templates.get(e.get('template',''),0);relations[i]=RELATIONS.index(e['relation'])
            if e.get('faction') in FACTIONS:owner_factions[i]=FACTIONS.index(e['faction'])
            role=int(e.get('category',-1));roles[i]=role+1 if 0<=role<8 else 0
            values=[]
            for field in ENTITY_FIELDS:
                value=e.get(field)
                if field=='cost':value=e.get('own_cost',e.get('public_cost'))
                if field=='contained':value=float(int(e['contained_by'])>0) if 'contained_by' in e else None
                scale={'x':width,'y':height,'cost':5000.,'queue_count':10.,'member_count':30.}.get(field,1.)
                values+=pair(value,scale)
            entities[i]=values+encode_card(self.rules.numeric_card(e.get('template','')))
        human=observation.get('human_state_features',{})
        globals=[]
        for value,scale in [(observation.get('money'),5000.),(human.get('cp_used'),500.),(human.get('cp_limit'),500.),(observation.get('spell_points'),25.),(float(state['frame'])/5.,1800.),(delta_seconds,30.),(dropped/max(1,len(rows)),1.),(len(rows),256.)]:globals+=pair(value,scale)
        result={'entities':entities,'entity_valid':valid,'entity_templates':templates,'relations':relations,'owner_factions':owner_factions,'roles':roles,'faction':np.int64(FACTIONS.index(faction)),'globals':np.asarray(globals,np.float32),'heads':{},'dropped_entities':dropped}
        for head,choices in heads.items():
            if head not in ('tactical','spend'):raise ValueError('Unknown action head')
            if len({c['id'] for c in choices})!=len(choices):raise ValueError('Duplicate action ID')
            count=max(1,len(choices));features=np.zeros((count,ACTION_WIDTH),np.float32);kinds=np.zeros(count,np.int64);names=np.zeros(count,np.int64)
            actors=np.zeros((count,n),bool);targets=np.zeros((count,n),bool);legal=np.zeros(count,bool)
            for i,c in enumerate(choices):
                legal[i]=True;kind=c.get('kind','wait')
                if kind not in KINDS:raise ValueError('Unknown legal action kind')
                kinds[i]=KINDS.index(kind);names[i]=self.templates.get(c.get('template',''),0)
                source=set(map(int,c.get('units',[])))
                if int(c.get('producer',0))>0:source.add(int(c['producer']))
                for oid in source:
                    if oid in lookup:actors[i,lookup[oid]]=True
                target=int(c.get('target',0))
                if target in lookup:targets[i,lookup[target]]=True
                values=[]
                for field in ACTION_FIELDS:
                    value=c.get('mechanics',c).get(field,c.get(field))
                    if field=='variant' and kind not in ('stance','formation'):value=None
                    if field=='actor_coverage':value=sum(oid in lookup for oid in source)/max(1,len(source)) if source else 1.
                    if field=='target_present':value=float(target in lookup) if target else None
                    scale={'cost':5000.,'cp_cost':100.,'x':width,'y':height,'start_x':width,'start_y':height,'build_seconds':180.,'wall_length':1000.,'wall_tiles':20.,'queue_paid_cost':5000.,'queue_work_seconds':180.,'queue_remaining':20.,'target_distance':4000.,'points_cost':25.,'source_distance_home':4000.,'variant':10.}.get(field,ACTION_SCALES.get(field,1.))
                    values+=pair(value,scale)
                features[i]=values+encode_card(self.rules.numeric_card(c.get('template','')))
            result['heads'][head]={'features':features,'kinds':kinds,'templates':names,'actors':actors,'targets':targets,'legal':legal,'ids':[c['id'] for c in choices]}
        return result
