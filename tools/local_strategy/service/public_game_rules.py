"""Public base-rule retrieval and numeric model inputs; never hidden live state."""
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from feature_cache import cached

ENCODING='bfme-public-rules-v2'
STAT_SCALES={'cost':5000.,'build_time':180.,'cp':100.,'max_health':10000.,'member_health':10000.,
             'member_count':30.,'hit_damage':5000.,'attack_range':1000.,'delay_ms':5000.,'speed':200.,
             'armor_slash':1.,'armor_pierce':1.,'armor_crush':1.,'armor_specialist':1.,'armor_siege':1.,'armor_magic':1.}
STAT_SCALES.update({k:1. for k in ('armor_cavalry','armor_cavalry_ranged','armor_hero','armor_hero_ranged','armor_flame','armor_poison')})
FLAGS=('HERO','STRUCTURE','HORDE','CAVALRY','INFANTRY')
DAMAGE_TYPES=('SLASH','PIERCE','CRUSH','SPECIALIST','SIEGE','MAGIC','CAVALRY','CAVALRY_RANGED','HERO','HERO_RANGED','FLAME','POISON')


def encode_card(card):
    stats=card.get('stats',{});coverage=card.get('coverage',{})
    result=[]
    for key,scale in STAT_SCALES.items():
        value=stats.get(key)
        if value is None: result += [0.,0.];continue
        value=float(value)
        known=float(coverage.get(key,1.))
        if not math.isfinite(value) or value<0 or not math.isfinite(known) or not 0<=known<=1: raise ValueError('Invalid public rule fact')
        result += [min(3.,math.log1p(value)/math.log1p(scale)),known]
    flags=card.get('flag_fractions',{})
    result += [float(flags.get(k,float(k in card.get('flags',[])))) for k in FLAGS]
    types=card.get('damage_type_fractions',{})
    result += [float(types.get(k,float(k in card.get('damage_types',[])))) for k in DAMAGE_TYPES]
    if any(not math.isfinite(v) or v<0 or v>3 for v in result): raise ValueError('Invalid public rule encoding')
    return result


def context_features(observation):
    return cached('public_rule_context',observation,lambda:_context_features(observation))

def _context_features(observation):
    context=observation.get('public_rules',{})
    return encode_card(context.get('own',{}))+encode_card(context.get('enemy',{}))


def tactical_features(observation,candidate):
    facts=candidate.get('public_rules',{})
    return context_features(observation)+encode_card(facts.get('selected',{}))+encode_card(facts.get('target',{}))


def spend_rule_features(observation,candidate):
    return context_features(observation)+encode_card(candidate.get('public_rules',{}).get('template',{}))


class PublicGameRules:
    def __init__(self,path):
        raw=Path(path).read_bytes();self.sha256=hashlib.sha256(raw).hexdigest()
        self.data=json.loads(raw)
        if self.data.get('schema')!=2 or self.data.get('id')!=ENCODING: raise ValueError('Unsupported public rules catalogue')
        self.lookups=0

    def card(self,name): return self.data['cards'].get(name,{})

    def definitions(self,name):
        # Full conditional declarations remain accessible beyond the fixed feature vector.
        return self.data['objects'].get(name)

    @lru_cache(maxsize=512)
    def _aggregate(self,items):
        total=sum(count for _,count in items);stats={};coverage={};flags={};types={}
        if not total: return {}
        for key in STAT_SCALES:
            known=[(self.card(name)['stats'][key],count) for name,count in items if self.card(name).get('stats',{}).get(key) is not None]
            n=sum(count for _,count in known)
            stats[key]=sum(value*count for value,count in known)/n if n else None
            coverage[key]=n/total
        for flag in FLAGS: flags[flag]=sum(count for name,count in items if flag in self.card(name).get('flags',[]))/total
        for kind in DAMAGE_TYPES: types[kind]=sum(count for name,count in items if kind in self.card(name).get('damage_types',[]))/total
        return {'stats':stats,'coverage':coverage,'flag_fractions':flags,'damage_type_fractions':types}

    def aggregate(self,counts):
        items=[]
        for name,count in sorted(counts.items()):
            n=float(count)
            if not math.isfinite(n) or n<0: raise ValueError('Invalid observed template count')
            if n: items.append((name,n))
        return self._aggregate(tuple(items))

    def attach(self,observation,candidates,purchases):
        visible=observation.get('human_state_features',{})
        observation['public_rules']={'encoding':ENCODING,'sha256':self.sha256,
            'own':self.aggregate(visible.get('own_templates',{})),
            'enemy':self.aggregate(visible.get('visible_enemy_templates',{}))}
        resolved=0
        for candidate in candidates:
            refs=candidate.get('rule_refs',{})
            target=refs.get('target','')
            # Only template names supplied by the fog-filtered controller are looked up.
            candidate['public_rules']={'selected':self.aggregate(refs.get('selected',{})),
                                       'target':self.numeric_card(target)}
            resolved+=bool(self.card(target))
        for candidate in purchases:
            name=candidate.get('template','')
            candidate['public_rules']={'template':self.numeric_card(name)}
            resolved+=bool(self.card(name))
        return {'catalogue_sha256':self.sha256,'encoding':ENCODING,'resolved_choice_templates':resolved,
                'numeric_inputs_enabled':True,'neural_weights_changed':False}

    def numeric_card(self,name):
        card=self.card(name)
        if not card:
            # Purchase/technology declarations also feed the scorer. Spell-point
            # prices are already separate native inputs, never treated as money.
            nodes=self.data['tables'].get('Upgrade',{}).get(name,[])
            if len(nodes)!=1: return {}
            stats={}
            for key,field in [('cost','BuildCost'),('build_time','BuildTime')]:
                found=[f for f in nodes[0]['fields'] if f['key']==field]
                if len(found)==1 and 'numeric' in found[0]: stats[key]=found[0]['numeric']['value']
            return {'stats':stats,'flags':[]}
        return {'stats':card['stats'],'flags':card['flags'],'damage_types':card['damage_types']}
