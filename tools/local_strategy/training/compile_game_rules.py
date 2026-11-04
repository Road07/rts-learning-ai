"""Compile source-labelled public rules and conservative base-stat cards."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import math
from collections import Counter


ARMOR_TYPES=('SLASH','PIERCE','CRUSH','SPECIALIST','SIEGE','MAGIC','CAVALRY','CAVALRY_RANGED','HERO','HERO_RANGED','FLAME','POISON')
STATS=('cost','build_time','cp','max_health','member_health','member_count','hit_damage','attack_range',
       'delay_ms','speed')+tuple('armor_'+k.lower() for k in ARMOR_TYPES)


def values(fields,key): return [f for f in fields if f['key'].lower()==key.lower()]
def text(fields,key):
    found=values(fields,key)
    return found[0].get('expanded_raw',found[0]['raw']) if len(found)==1 else None
def scalar(fields,key):
    found=values(fields,key)
    if len(found)!=1: return None
    return found[0].get('numeric',{}).get('value')


class Compiler:
    def __init__(self,data):
        self.data=data; self.merged={}; self.cards={}; self.active=set()

    def merge(self,name,trail=()):
        if name in self.merged: return self.merged[name]
        if name in trail: raise ValueError('inheritance cycle')
        entry=self.data['objects'].get(name)
        if not entry or len(entry['declarations'])!=1: raise ValueError('missing or duplicate declaration: '+name)
        node=entry['declarations'][0]
        fields=[]; modules={}
        if entry['parent']:
            fields,modules=copy.deepcopy(self.merge(entry['parent'],trail+(name,)))
        inherited_kind=(text(fields,'KindOf') or '').split()
        local={}
        for f in node['fields']: local.setdefault(f['key'].lower(),[]).append(f)
        fields=[f for f in fields if f['key'].lower() not in local]+list(node['fields'])
        kind_edits=values(node['fields'],'KindOf')
        if len(kind_edits)==1:
            words=kind_edits[0]['raw'].split()
            if words and all(w.startswith(('+','-')) for w in words):
                flags=set(inherited_kind)
                for word in words:
                    if word.startswith('+'): flags.add(word[1:])
                    else: flags.discard(word[1:])
                replacement=copy.deepcopy(kind_edits[0]);replacement['raw']=' '.join(sorted(flags));replacement['expanded_raw']=replacement['raw']
                fields=[replacement if f is kind_edits[0] else f for f in fields]
        for f in values(node['fields'],'RemoveModule'):
            for key in list(modules):
                if modules[key]['header'].split()[-1].lower()==f['raw'].lower(): modules.pop(key)
        def add(part):
            words=part['header'].split(); token=words[0]
            if token in ('AddModule','ReplaceModule','InheritableModule'):
                if token=='ReplaceModule' and len(words)>1:
                    for k in list(modules):
                        if modules[k]['header'].split()[-1].lower()==words[1].lower(): modules.pop(k)
                for child in part['blocks']: add(child)
                return
            if token in ('WeaponSet','ArmorSet','LocomotorSet'):
                condition=text(part['fields'],'Condition' if token=='LocomotorSet' else 'Conditions') or 'None'
                key=(token,condition.lower())
            else: key=(token,words[-1].lower())
            modules[key]=part
        for part in node['blocks']: add(part)
        self.merged[name]=(fields,modules)
        return fields,modules

    def table(self,kind,name):
        nodes=self.data['tables'].get(kind,{}).get(name,[])
        return nodes[0] if len(nodes)==1 else None

    def weapon(self,name,trail=()):
        if name in trail: return None
        node=self.table('Weapon',name)
        if not node: return None
        nuggets=[p for p in node['blocks'] if p['header'].split()[0]=='DamageNugget']
        damage=[]; types=[];unknown=False
        for part in nuggets:
            required=text(part['fields'],'RequiredUpgradeNames')
            if required and required.lower()!='none': continue  # Base card explicitly has no upgrades.
            value=scalar(part['fields'],'Damage')
            if value is None: unknown=True;continue
            # A conditional nugget cannot be asserted as unconditional base damage.
            if any(f['key'] in ('SpecialObjectFilter','ForbiddenObjectFilter') for f in part['fields']): unknown=True;continue
            damage.append(value); types.append(text(part['fields'],'DamageType'))
        if not nuggets:
            for p in node['blocks']:
                warhead=text(p['fields'],'WarheadTemplateName')
                if warhead:
                    nested=self.weapon(warhead,trail+(name,))
                    if nested and nested['hit_damage'] is not None: damage.append(nested['hit_damage']); types+=nested['damage_types']
                    else: unknown=True
        return {'hit_damage':None if unknown or (not nuggets and not damage) else sum(damage),'attack_range':scalar(node['fields'],'AttackRange'),
                'delay_ms':scalar(node['fields'],'DelayBetweenShots'),'damage_types':sorted(set(x for x in types if x))}

    def card(self,name):
        if name in self.cards: return self.cards[name]
        if name in self.active: return None
        self.active.add(name)
        entry=self.data['objects'][name]
        card={'stats':{key:None for key in STATS},'flags':[],'members':[],'weapon_refs':[],
              'armor_refs':[],'power_refs':[],'damage_types':[],'issues':[],'base_values_not_live':True,
              'source':entry['declarations'][0]['source']}
        try:
            fields,modules=self.merge(name)
            card['flags']=(text(fields,'KindOf') or '').split()
            for key,source in [('cost','BuildCost'),('build_time','BuildTime'),('cp','CommandPoints')]: card['stats'][key]=scalar(fields,source)
            body=[p for p in modules.values() if p['header'].split()[0]=='Body']
            if len(body)==1: card['stats']['max_health']=scalar(body[0]['fields'],'MaxHealth')
            for part in modules.values():
                token=part['header'].split()[0]
                if token=='LocomotorSet' and (text(part['fields'],'Condition') or '').upper()=='SET_NORMAL': card['stats']['speed']=scalar(part['fields'],'Speed')
                if token=='WeaponSet':
                    for f in values(part['fields'],'Weapon'):
                        words=f['raw'].split()
                        if len(words)>1: card['weapon_refs'].append({'slot':words[0],'weapon':words[1],'conditions':text(part['fields'],'Conditions') or 'None'})
                if token=='ArmorSet':
                    armor=text(part['fields'],'Armor')
                    if armor: card['armor_refs'].append({'armor':armor,'conditions':text(part['fields'],'Conditions') or 'None'})
                for f in values(part['fields'],'SpecialPowerTemplate'): card['power_refs'].append(f['raw'])
                if token=='Behavior' and 'HordeContain' in part['header'].split():
                    for payload in values(part['fields'],'InitialPayload'):
                        words=payload.get('expanded_raw',payload['raw']).split()
                        if len(words)==2 and re.fullmatch(r'\d+(?:\.0+)?',words[1]):
                            card['members'].append({'template':words[0],'count':int(float(words[1]))})
                        else: card['issues'].append('unresolved payload: '+payload['raw'])
            normal=[w for w in card['weapon_refs'] if w['conditions'].lower()=='none' and w['slot']=='PRIMARY']
            if len(normal)==1:
                weapon=self.weapon(normal[0]['weapon'])
                if weapon:
                    card['stats'].update({key:weapon[key] for key in ('hit_damage','attack_range','delay_ms')})
                    card['damage_types']=weapon['damage_types']
            normal_armor=[a for a in card['armor_refs'] if a['conditions'].lower()=='none']
            if len(normal_armor)==1:
                armor=self.table('Armor',normal_armor[0]['armor'])
                fractions={}
                if armor:
                    for f in values(armor['fields'],'Armor'):
                        raw=f.get('expanded_raw',f['raw'])
                        match=re.fullmatch(r'(\w+)\s+([-+0-9.]+)%',raw)
                        if match: fractions[match[1].upper()]=float(match[2])/100.
                for kind in ARMOR_TYPES:
                    card['stats']['armor_'+kind.lower()]=fractions.get(kind,fractions.get('DEFAULT'))
            if 'HORDE' in card['flags']:
                card['controller_max_health']=card['stats']['max_health']
                # Never teach the horde controller's ImmortalBody MaxHealth=1 as soldier HP.
                for key in ('max_health','member_health','hit_damage','attack_range','delay_ms'):
                    card['stats'][key]=None
                card['damage_types']=[]
                members=[(self.card(p['template']) if p['template'] in self.data['objects'] else None,p['count']) for p in card['members']]
                count=sum(n for _,n in members)
                if count and not any('unresolved payload' in s for s in card['issues']):
                    card['stats']['member_count']=count
                    for key in ('max_health','hit_damage','attack_range','delay_ms')+tuple('armor_'+k.lower() for k in ARMOR_TYPES):
                        if all(c and c['stats'].get(key) is not None for c,_ in members):
                            total=sum(c['stats'][key]*n for c,n in members)
                            card['stats'][key]=total if key in ('max_health','hit_damage') else total/count
                    card['stats']['member_health']=card['stats']['max_health']/count if card['stats']['max_health'] is not None else None
                    card['damage_types']=sorted(set(t for c,_ in members if c for t in c['damage_types']))
                else: card['issues'].append('unknown horde member totals')
            else:
                card['stats']['member_count']=1
                card['stats']['member_health']=card['stats']['max_health']
        except ValueError as error: card['issues'].append(str(error))
        for key,value in card['stats'].items():
            if value is not None and (not math.isfinite(value) or value<0):
                card['stats'][key]=None;card['issues'].append('non-positive-domain scalar: '+key)
        self.active.remove(name); self.cards[name]=card
        return card


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--catalogue',type=Path,required=True)
    args=parser.parse_args();raw=args.catalogue/'mechanics.json'
    data=json.loads(raw.read_text(encoding='utf-8')); compiler=Compiler(data)
    for name in data['objects']: compiler.card(name)
    # All gameplay declarations stay queryable, including conditional abilities/upgrades.
    definitions=copy.deepcopy(data['objects'])
    def trim(node):
        node['blocks']=[b for b in node['blocks'] if b['header'].split()[0]!='Draw']
        for b in node['blocks']: trim(b)
    for entry in definitions.values():
        for node in entry['declarations']: trim(node)
    runtime={'schema':2,'id':'bfme-public-rules-v2','cards':compiler.cards,'objects':definitions,
             'tables':data['tables'],'factions':data['factions'],'semantics':data['semantics'],
             'source_catalogue_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),
             'limits':['Conservative declared base values; not effective live combat stats or matchup results.',
                       'Missing/ambiguous fields stay unknown; unflattened source rules remain available.',
                       'Horde damage is a nominal sum of member hit values, not simultaneous damage or DPS.',
                       'Inherited module interpretation is source-derived; actual engine commands/costs remain authoritative.']}
    files=[];file_ids={}
    def compact(node):
        if isinstance(node,list):
            for item in node: compact(item)
        elif isinstance(node,dict):
            if node.get('expanded_raw')==node.get('raw'): node.pop('expanded_raw',None)
            for key,value in list(node.items()):
                if key in ('source','macro_source') and isinstance(value,dict) and 'file' in value and 'line' in value:
                    name=value['file']
                    if name not in file_ids: file_ids[name]=len(files);files.append(name)
                    node[key]=[file_ids[name],value['line']]
                else: compact(value)
    compact(runtime);runtime['files']=files
    path=args.catalogue/'game-rules.json';path.write_text(json.dumps(runtime,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    report={'objects':len(compiler.cards),'tables':{k:len(v) for k,v in data['tables'].items()},
            'known_stats':{k:sum(c['stats'][k] is not None for c in compiler.cards.values()) for k in STATS},
            'cards_with_issues':sum(bool(c['issues']) for c in compiler.cards.values()),
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
    (args.catalogue/'game-rules-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))


if __name__=='__main__': main()
