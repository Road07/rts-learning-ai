"""Imitate human recruit choice from pre-dispatch legal options, split by match."""
import os
os.environ["OPENBLAS_NUM_THREADS"]="1"
os.environ["OMP_NUM_THREADS"]="1"
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"service"))
from mechanics_knowledge import MechanicsKnowledge
from production_policy import ProductionPolicy,encode,regular_unit,INPUTS


def train(rows,knowledge):
    rng=np.random.default_rng(42)
    w={"w1":(rng.standard_normal((INPUTS,24))/np.sqrt(INPUTS)).astype(np.float32),"b1":np.zeros(24,np.float32),
       "w2":(rng.standard_normal((24,1))/np.sqrt(24)).astype(np.float32),"b2":np.zeros(1,np.float32)}
    samples=[(np.stack([encode(r["features"],o,knowledge) for o in r["options"]]),r["label"]) for r in rows]
    moments={k:[np.zeros_like(v),np.zeros_like(v)] for k,v in w.items()};step=0
    for epoch in range(60):
        for idx in rng.permutation(len(samples)):
            x,y=samples[idx];h=np.tanh(x@w["w1"]+w["b1"]);s=(h@w["w2"]+w["b2"]).ravel()
            p=np.exp(s-s.max());p/=p.sum();p[y]-=1;g=p[:,None];dh=(g@w["w2"].T)*(1-h*h)
            gradients={"w2":h.T@g+.001*w["w2"],"b2":g.sum(0),"w1":x.T@dh+.001*w["w1"],"b1":dh.sum(0)};step+=1
            for k,v in gradients.items():
                m,q=moments[k];m*=.9;m+=.1*v;q*=.999;q+=.001*v*v
                w[k]-=.002*(m/(1-.9**step))/(np.sqrt(q/(1-.999**step))+1e-8)
    return w


def predict(w,row,knowledge):
    x=np.stack([encode(row["features"],o,knowledge) for o in row["options"]])
    return int(((np.tanh(x@w["w1"]+w["b1"])@w["w2"])+w["b2"]).argmax())


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--dataset",type=Path,required=True);cli.add_argument("--mechanics",type=Path,required=True);cli.add_argument("--output",type=Path,required=True)
    cli.add_argument("--model-name",default="production-choice-roles-v2")
    args=cli.parse_args()
    if args.output.exists(): raise ValueError("New output required")
    knowledge=MechanicsKnowledge(args.mechanics)
    raw=[json.loads(s) for s in args.dataset.open(encoding="utf-8")]
    commands=[r for r in raw if r["action"]["command"]=="MSG_QUEUE_UNIT_CREATE"]
    refs=defaultdict(set)
    for r in commands: refs[r["state_source"]["path"]].add(r["state_source"]["line"])
    states={};source_hashes={}
    for path,lines in refs.items():
        p=Path(path);source_hashes[path]=hashlib.sha256(p.read_bytes()).hexdigest()
        for i,s in enumerate(p.open(encoding="utf-8"),1):
            if i in lines: states[(path,i)]=json.loads(s)
    rows=[];counts=Counter()
    for r in commands:
        a=r["action"];result=r["immediate_result"];q=r["quality"]
        if q.get("fixture") or q.get("source")!="human_player" or not q.get("fog_filtered") or result.get("dispatcher_error"):
            counts["unsafe_or_error"]+=1;continue
        capture=states[(r["state_source"]["path"],r["state_source"]["line"])];state=capture["data"]
        if (capture["session"],capture["match"],state["frame"],state["player"],state["command_id"])!=(r["session_group"],r["match"],a["frame"],a["player"],a["id"]): raise ValueError("Pre-state provenance mismatch")
        selection=a["selection_before"]
        if len(selection)!=1: counts["multiple_or_missing_producer"]+=1;continue
        producers=[o for o in state["objects"] if o["id"]==selection[0] and o["relation"]=="self" and o["structure"] and o["complete"]]
        if len(producers)!=1 or producers[0].get("queue"):
            counts["busy_or_nonfactory"]+=1;continue
        requested=a.get("requested_template")
        queued=any(x["producer"]==selection[0] and any(e.get("template")==requested for e in x["queue"]) for x in result["selected_queues"])
        if result["money"]>=a["money"] or not queued:
            counts["no_spend_or_enqueue_evidence"]+=1;continue
        options=[];seen=set()
        for o in state["selected_build_options"]:
            if o["producer"]!=selection[0] or o["can_make"]!=0 or o["cost"]>state["money"] or not regular_unit(knowledge,o["template"]): continue
            if o["template"] in seen: continue
            seen.add(o["template"])
            options.append({**o,"kind":"train","id":"train:%s:%s"%(o["producer"],o["template"]),"producer_template":producers[0]["template"],"queue_count":0})
        if requested not in [o["template"] for o in options]: counts["chosen_not_legal_regular_recruit"]+=1;continue
        if len(options)<2: counts["single_choice_not_training"]+=1;continue
        rows.append({"session":r["session_group"],"match":r["match"],"features":r["features"],"options":options,
                     "label":[o["template"] for o in options].index(requested),"source":r["source"],"state_source":r["state_source"],
                     "quality":{"enqueue_evidence":True,"completion_verified":False,"good_move_verified":False}})
    groups=sorted(set((r["session"],r["match"]) for r in rows))
    if len(groups)<3: raise ValueError("Insufficient independent production-choice matches")
    folds=[];predictions=[]
    for group in groups:
        train_rows=[r for r in rows if (r["session"],r["match"])!=group];test=[r for r in rows if (r["session"],r["match"])==group]
        w=train(train_rows,knowledge);frequency=Counter(r["options"][r["label"]]["template"] for r in train_rows)
        scored=[]
        for r in test:
            pred=predict(w,r,knowledge);cheap=min(range(len(r["options"])),key=lambda i:r["options"][i]["cost"])
            frequent=max(range(len(r["options"])),key=lambda i:frequency[r["options"][i]["template"]])
            scored.append({"session":r["session"],"match":r["match"],"source":r["source"],"correct":pred==r["label"],"cheapest_correct":cheap==r["label"],"frequency_correct":frequent==r["label"],"expected":r["options"][r["label"]]["template"],"predicted":r["options"][pred]["template"],"options":len(r["options"])})
        predictions+=scored;folds.append({"held_out":group,"train":len(train_rows),"test":len(test),"accuracy":sum(r["correct"] for r in scored)/len(scored)})
    args.output.mkdir(parents=True);final=train(rows,knowledge);path=args.output/"production-network.npz"
    np.savez(path,schema=np.array(1),feature_encoding=np.array("roles-v2"),model_name=np.array(args.model_name),trained_factions=np.array(sorted(set(r["features"]["faction"] for r in rows))),**final)
    loaded=ProductionPolicy(path,knowledge)
    for r in rows: assert int(loaded.scores(r["features"],r["options"]).argmax())==predict(final,r,knowledge)
    report={"schema":1,"model":args.model_name,"feature_encoding":"roles-v2; no faction or template identity; source KindOf classes plus costs/time","mode":"shadow","controls_game":False,"inspected_train_commands":len(commands),"retained_choice_examples":len(rows),"excluded":dict(counts),"folds":folds,
            "oof_accuracy":sum(r["correct"] for r in predictions)/len(predictions),"cheapest_baseline":sum(r["cheapest_correct"] for r in predictions)/len(predictions),"train_frequency_baseline":sum(r["frequency_correct"] for r in predictions)/len(predictions),
            "parameters":sum(v.size for v in final.values()),"recipe":{"epochs":60,"seed":42,"hidden":24,"input":INPUTS},"template_counts":dict(Counter(r["options"][r["label"]]["template"] for r in rows)),
            "dataset_sha256":hashlib.sha256(args.dataset.read_bytes()).hexdigest(),"mechanics_sha256":hashlib.sha256(args.mechanics.read_bytes()).hexdigest(),"checkpoint_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"source_hashes":source_hashes,
            "limits":["Choice among legal recruits in one selected idle factory; not producer selection or timing.","Only pre-command state/options enter features. Post-state spend/queue are acceptance filters only.","No successful completion, good tactic, counter or victory labels.","Few matches, mostly Dwarves; final all-data checkpoint has no independent blind test.","Game production options may omit duplicates or be capped; no ordering invariance claim for exact score ties."]}
    (args.output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    for name,values in [("examples.jsonl",rows),("oof-predictions.jsonl",predictions)]:
        with (args.output/name).open("w",encoding="utf-8") as f:
            for r in values:f.write(json.dumps(r,ensure_ascii=False)+"\n")
    print(json.dumps({k:report[k] for k in ["inspected_train_commands","retained_choice_examples","excluded","oof_accuracy","cheapest_baseline","train_frequency_baseline"]}))


if __name__=="__main__":main()
