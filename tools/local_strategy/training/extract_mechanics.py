"""Local retail mechanics catalogue. Source facts, not simulated matchup outcomes."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

TOOLS=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(TOOLS/"object_oracle"))
import object_oracle as oo

FACTIONS={"Men":"FactionMen","Elves":"FactionElves","Dwarves":"FactionDwarves","Wild":"FactionWild",
          "Mordor":"FactionMordor","Isengard":"FactionIsengard","Angmar":"FactionAngmar"}
KINDS={"Object","ChildObject","ObjectReskin","Weapon","Armor","CommandSet","CommandButton","Upgrade",
       "Science","SpecialPower","PlayerTemplate","ModifierList","ExperienceLevel","GameData"}
OBJECT_FIELDS={"Side","KindOf","BuildCost","BuildTime","CommandPoints","CommandSet","BuildVariations",
               "Prerequisites","VisionRange","ShroudClearingRange","CrushableLevel","CrusherLevel",
               "CrushWeapon","MinCrushVelocityPercent","CrushDecelerationPercent","BountyValue",
               "IsTrainable","ThreatLevel","RecruitText","MaxSimultaneousOfType","RemoveModule"}
MODULES={"Body","Behavior","WeaponSet","ArmorSet","LocomotorSet","AddModule","ReplaceModule","InheritableModule"}
MECHANICAL_CLASSES=("Body","HordeContain","TerrainResource","Production","SpecialPower","Upgrade","AttributeModifier",
                    "Experience","Level","AutoHeal","Respawn","TransportContain","Worker","Slaved","Stealth","Crush","Emotion")


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output",type=Path,required=True)
    cli.add_argument("--rotwk",type=Path,default=Path("D:/Games/RotWK"))
    cli.add_argument("--bfme2",type=Path,default=Path("D:/Games/BFME2"))
    args=cli.parse_args()
    if args.output.exists(): raise ValueError("Use a new catalogue directory")
    files=oo.mount(args.rotwk,args.bfme2)
    object_files=oo.object_files(files,oo.legend_entry(files),False)
    fixed=["default/gamedata","gamedata","playertemplate","weapon","armor","commandset","commandbutton",
           "default/upgrade","upgrade","default/science","science","default/specialpower","specialpower",
           "attributemodifier","experiencelevels"]
    roots=[oo.normalize("data/ini/"+p+".ini") for p in fixed]+object_files
    roots=list(dict.fromkeys(roots))
    expanded=[]; errors=[]; macros={}; macro_sources={}; conflicts=set(); source_paths=set()
    priors=oo.Priors()
    for key in roots:
        if key not in files: errors.append("Missing root "+key); continue
        lines=oo.expand(files,key,errors)
        for file,line,raw in lines:
            source_paths.add(file)
            match=re.match(r"\s*#define\s+(\w+)\s+(.+)",oo.strip_comment(raw))
            if match:
                name,value=match.groups(); name=name.lower(); value=value.strip()
                if name in macros and macros[name]!=value: conflicts.add(name)
                macros[name]=value; macro_sources[name]={"file":file,"line":line}
        items=oo.lex(lines); priors.learn(items); expanded.append((key,items))
    if errors: raise ValueError("; ".join(errors[:10]))

    def number(raw,seen=()):
        value=raw.strip(); key=value.lower()
        if re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?%?",value):
            return {"value":float(value.rstrip("%")),"unit":"percent" if value.endswith("%") else "source_scalar"}
        if key in macros and key not in conflicts and key not in seen:
            n=number(macros[key],seen+(key,))
            if n: return {**n,"macro":key,"macro_source":macro_sources[key]}
        return None  # Arithmetic macros/expressions are not silently approximated.

    def retain(node):
        token=node["header"].split()[0]
        if token not in MODULES: return False
        if token in {"WeaponSet","ArmorSet","LocomotorSet","AddModule","ReplaceModule","InheritableModule"}: return True
        return any(word in node["header"] for word in MECHANICAL_CLASSES)

    def filtered(node,is_object=False):
        fields=[]
        for f in node["fields"]:
            if is_object and f["key"] not in OBJECT_FIELDS: continue
            n=number(f["raw"])
            fields.append({**f,**({"numeric":n} if n else {})})
        return {"header":node["header"],"source":node["source"],"fields":fields,
                "blocks":[filtered(c) for c in node["blocks"] if not is_object or retain(c)]}

    definitions=defaultdict(list); failures=[]
    for key,items in expanded:
        try: depths,openers=oo.parse_structure(items,priors)
        except oo.OracleError as error: failures.append({"file":key,"error":str(error)}); continue
        stack=[]
        for i,it in enumerate(items):
            depth=depths[i]
            while len(stack)>depth: stack.pop()
            if it.is_end: continue
            if openers[i]:
                node={"header":" ".join(it.tokens),"source":{"file":it.file,"line":it.line},"fields":[],"blocks":[]}
                if depth==0:
                    if it.tokens[0] in KINDS and len(it.tokens)>1:
                        definitions[(it.tokens[0],it.tokens[1])].append(node)
                elif stack: stack[-1]["blocks"].append(node)
                stack.append(node)
            elif stack:
                stack[-1]["fields"].append({"key":it.tokens[0],"raw":" ".join(it.tokens[1:]),"source":{"file":it.file,"line":it.line}})
    catalogue={}; duplicates=[]
    for (kind,name),nodes in definitions.items():
        # Child inheritance and duplicate load definitions stay explicit, not flattened.
        if len(nodes)>1: duplicates.append({"kind":kind,"name":name,"definitions":len(nodes)})
        catalogue.setdefault(kind,{})[name]=[filtered(n,kind in {"Object","ChildObject","ObjectReskin"}) for n in nodes]

    def fields(node,key): return [f for f in node["fields"] if f["key"]==key]
    objects={}
    for kind in ("Object","ChildObject","ObjectReskin"):
        for name,nodes in catalogue.get(kind,{}).items():
            objects[name]={"kind":kind,"declarations":nodes,"parent":nodes[-1]["header"].split()[2] if kind!="Object" else None,
                           "effective_values_verified":False}
    cards={}
    for side,faction in FACTIONS.items():
        templates=[]
        for name,entry in objects.items():
            declared=[f["raw"] for n in entry["declarations"] for f in fields(n,"Side")]
            if side in declared: templates.append(name)
        player=catalogue.get("PlayerTemplate",{}).get(faction,[])
        cards[faction]={"side":side,"declared_templates":sorted(templates),"player_template":player,
                        "ring_and_custom_heroes_in_scope":False,"note":"Declared side membership is not proof of legal multiplayer production; use command sets and live production options."}
    facts={"schema":1,"id":"rotwk-mechanics-v1","profile":"Mounted RotWK 2.01/BFME2 1.06 archive policy; actual source hashes recorded",
           "factions":cards,"objects":objects,"tables":{k:v for k,v in catalogue.items() if k not in {"Object","ChildObject","ObjectReskin","PlayerTemplate"}},
           "semantics":{"armor_percent":"Percentage of incoming damage taken for the damage type; lower is more protection. DEFAULT applies only when no explicit type entry exists.",
                        "damage":"Nugget damage is not DPS or a duel result. Weapon conditions, scalars, target filters, cooldown, animation, splash, armor and range matter.",
                        "economy":"Terrain-resource module values are base declarations; actual yield also depends on terrain claims, saturation, upgrades, difficulty and mod income policy.",
                        "units":"Preserve milliseconds/frames/percent/scalar tokens until the corresponding native parser is known; source scalar is not an asserted runtime unit.",
                        "inheritance":"ChildObject/ObjectReskin parents and module edits are explicit; no unverified effective inherited stats are substituted."},
           "limits":["Static source declarations, not a native-engine state dump or trained neural weights.","Object block nesting uses the existing independent oracle; inferred structure requires native checks before authoritative use.",
                     "Conflicting macros and arithmetic expressions remain unresolved.","No all-pairs battle outcomes, win-rate ranking or placement advice is inferred.","No live hidden enemy information; only public template facts may be retrieved."]}
    args.output.mkdir(parents=True)
    path=args.output/"mechanics.json"
    path.write_text(json.dumps(facts,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    sources=[]
    for name in sorted(source_paths):
        archive,_,_=files[name]
        sources.append({"file":name,"archive":str(archive),"sha256":hashlib.sha256(oo.read_file(files,name)).hexdigest()})
    inventory={"schema":1,"catalogue_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"source_files":sources,
               "counts":{"objects":len(objects),**{k:len(v) for k,v in facts["tables"].items()}},"faction_counts":{k:len(v["declared_templates"]) for k,v in cards.items()},
               "structural_failures":failures,"duplicate_definitions":duplicates,"conflicting_macros":sorted(conflicts)}
    (args.output/"inventory.json").write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:inventory[k] for k in ("counts","faction_counts")}))
    print("Structural failures:",len(failures),"Conflicting macros:",len(conflicts))


if __name__=="__main__": main()
