"""Compact public rules plus source-labelled learning exercises; no gameplay labels."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import argparse
import re


def walk(node):
    yield node
    for child in node["blocks"]: yield from walk(child)


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--catalogue",type=Path,required=True)
    args=cli.parse_args(); source=args.catalogue/"mechanics.json"
    d=json.loads(source.read_text(encoding="utf-8")); files=[]
    def ref(s):
        if s["file"] not in files: files.append(s["file"])
        return [files.index(s["file"]),s["line"]]
    def field(f):
        return {"value":f.get("numeric",{}).get("value",f["raw"]),"source":ref(f["source"]),
                "resolved_numeric":"numeric" in f}
    objects={}; exercises=[]
    for name,entry in d["objects"].items():
        if len(entry["declarations"])!=1: continue
        node=entry["declarations"][0]; fields={}; armor_sets=[]; weapon_sets=[]; body=[]; movement=[]; rules=[]
        for f in node["fields"]: fields.setdefault(f["key"],[]).append(field(f))
        for part in walk(node):
            token=part["header"].split()[0]
            if token in {"ArmorSet","WeaponSet","LocomotorSet","Body"}:
                info={"header":part["header"],"fields":{},"source":ref(part["source"])}
                for f in part["fields"]: info["fields"].setdefault(f["key"],[]).append(field(f))
                {"ArmorSet":armor_sets,"WeaponSet":weapon_sets,"LocomotorSet":movement,"Body":body}[token].append(info)
            elif token=="Behavior" and any(x in part["header"] for x in ["TerrainResource","HordeContain","Production","Upgrade","SpecialPower","AttributeModifier","AutoHeal"]):
                rules.append({"header":part["header"],"source":ref(part["source"]),"fields":[{"key":f["key"],**field(f)} for f in part["fields"]]})
        objects[name]={"kind":entry["kind"],"parent":entry["parent"],"fields":fields,"armor_sets":armor_sets,
                       "weapon_sets":weapon_sets,"body":body,"movement":movement,"rules":rules}
        if entry["kind"]=="Object":
            for key in ["BuildCost","BuildTime"]:
                fs=fields.get(key,[])
                if len(fs)==1 and fs[0]["resolved_numeric"]:
                    exercises.append({"task":"public_declared_scalar","template":name,"field":key,"answer":fs[0]["value"],
                                      "source":fs[0]["source"],"label_origin":"retail_rule","gameplay_success_label":False})
    armor={}
    for name,nodes in d["tables"]["Armor"].items():
        if len(nodes)!=1: continue
        row={}
        for f in nodes[0]["fields"]:
            m=re.fullmatch(r"(\w+)\s+([-+0-9.]+)%",f["raw"]) if f["key"]=="Armor" else None
            if m: row[m[1]]={"percent":float(m[2]),"source":ref(f["source"])}
        armor[name]=row
        for damage,entry in row.items():
            exercises.append({"task":"armor_damage_fraction","armor":name,"damage_type":damage,
                              "answer":entry["percent"]/100,"source":entry["source"],"label_origin":"retail_rule","gameplay_success_label":False})
    # Preserve conditions, damage nuggets and prerequisite graph separately from effective stats.
    tables={}
    for kind in ["Weapon","CommandSet","CommandButton","Upgrade","Science","SpecialPower","ModifierList","ExperienceLevel"]:
        tables[kind]={}
        for name,nodes in d["tables"][kind].items():
            if len(nodes)!=1: continue
            tables[kind][name]=[{"scope":part["header"],"fields":[{"key":f["key"],**field(f)} for f in part["fields"]]} for part in walk(nodes[0])]
    compact={"schema":1,"id":"rotwk-mechanics-v1","files":files,"objects":objects,"armor":armor,"tables":tables,
             "factions":{name:{"side":card["side"],"declared_templates":card["declared_templates"]} for name,card in d["factions"].items()},
             "semantics":d["semantics"],"limits":d["limits"],"source_catalogue_sha256":hashlib.sha256(source.read_bytes()).hexdigest()}
    path=args.catalogue/"mechanics-index.json"
    path.write_text(json.dumps(compact,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    selected=set(n for card in compact["factions"].values() for n in card["declared_templates"])
    while True:
        parents={objects[n]["parent"] for n in selected if n in objects and objects[n]["parent"]}
        expanded=selected|parents
        if expanded==selected: break
        selected=expanded
    runtime={**compact,"objects":{n:objects[n] for n in sorted(selected) if n in objects},"tables":{}}
    (args.catalogue/"mechanics-runtime.json").write_text(json.dumps(runtime,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    with (args.catalogue/"rule-exercises.jsonl").open("w",encoding="utf-8") as f:
        for e in exercises: f.write(json.dumps(e,ensure_ascii=False)+"\n")
    report={"schema":1,"objects":len(objects),"armor":len(armor),"exercises":dict(Counter(e["task"] for e in exercises)),
            "index_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"index_bytes":path.stat().st_size,
            "learning_status":"Source-backed retrieval and rule exercises; not a neural training run or matchup test."}
    (args.catalogue/"compile-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report))


if __name__=="__main__": main()
