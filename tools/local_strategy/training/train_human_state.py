"""Fixed-recipe leave-one-session-out evaluation and final shadow checkpoint."""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"service"))
from human_state_policy import encode, HumanStatePolicy, INPUTS, LABELS
from train_replay_sequence import LOOKUP


def fit(x, y, balanced=False):
    counts=np.bincount(y,minlength=len(LABELS))
    class_weights=np.ones(len(LABELS),np.float32)
    if balanced:
        present=counts>0
        class_weights[present]=np.minimum(4.0,np.sqrt(len(y)/(present.sum()*counts[present])))
        class_weights/=class_weights[y].mean()
    rng = np.random.default_rng(42)
    w = {"w1":(rng.standard_normal((INPUTS,24))/np.sqrt(INPUTS)).astype(np.float32),
         "b1":np.zeros(24,np.float32), "w2":(rng.standard_normal((24,16))/np.sqrt(24)).astype(np.float32),
         "b2":np.zeros(16,np.float32)}
    moments = {k:[np.zeros_like(v),np.zeros_like(v)] for k,v in w.items()}
    step = 0
    for epoch in range(60):  # Fixed before evaluation; no tuning against held-out sessions.
        for ids in np.array_split(rng.permutation(len(y)), max(1,int(np.ceil(len(y)/32)))):
            h = np.tanh(x[ids] @ w["w1"]+w["b1"])
            scores = h @ w["w2"]+w["b2"]
            p = np.exp(scores-scores.max(1,keepdims=True)); p /= p.sum(1,keepdims=True)
            p[np.arange(len(ids)),y[ids]] -= 1; p *= class_weights[y[ids],None]; p /= len(ids)
            dh = (p @ w["w2"].T)*(1-h*h)
            gradients = {"w2":h.T@p+0.001*w["w2"], "b2":p.sum(0),
                         "w1":x[ids].T@dh+0.001*w["w1"], "b1":dh.sum(0)}
            step += 1
            for k,g in gradients.items():
                m,v = moments[k]; m *= .9; m += .1*g; v *= .999; v += .001*g*g
                w[k] -= .002*(m/(1-.9**step))/(np.sqrt(v/(1-.999**step))+1e-8)
    return w


def probabilities(x,w):
    s = np.tanh(x@w["w1"]+w["b1"])@w["w2"]+w["b2"]
    p = np.exp(s-s.max(1,keepdims=True)); return p/p.sum(1,keepdims=True)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--dataset",type=Path,required=True)
    cli.add_argument("--output",type=Path,required=True)
    cli.add_argument("--balanced",action="store_true")
    cli.add_argument("--model-name",default="human-state-v1")
    args = cli.parse_args()
    if args.output.exists(): raise ValueError("Use a new model directory")
    rows, removed = [], Counter()
    for line in args.dataset.open(encoding="utf-8"):
        r = json.loads(line); q = r["quality"]; a=r["action"]; result=r["immediate_result"]
        if q.get("fixture") or q.get("source")!="human_player" or not q.get("fog_filtered") or result.get("dispatcher_error"):
            removed["unsafe_or_error"]+=1; continue
        if a["command"] not in LOOKUP: removed["unknown_command"]+=1; continue
        label = LOOKUP[a["command"]]
        # Purchases without a recorded spend are ambiguous, not successful examples.
        if LABELS[label] in ("construct","train","upgrade") and result["money"]>=a["money"]:
            removed["purchase_without_spend_evidence"]+=1; continue
        rows.append(r)
    groups = sorted(set((r["session_group"],r["match"]) for r in rows))
    if len(groups)<3: raise ValueError("At least three independent match groups required")
    x=np.stack([encode(r["features"]) for r in rows]); y=np.array([LOOKUP[r["action"]["command"]] for r in rows])
    folds=[]; correct=baseline_correct=0; oof=np.zeros_like(y)
    for group in groups:
        test=np.array([(r["session_group"],r["match"])==group for r in rows]); train=~test
        w=fit(x[train],y[train],args.balanced); pred=probabilities(x[test],w).argmax(1); oof[test]=pred
        majority=Counter(y[train].tolist()).most_common(1)[0][0]
        hits=int((pred==y[test]).sum()); base=int((y[test]==majority).sum())
        correct+=hits; baseline_correct+=base
        folds.append({"held_out":list(group),"train_samples":int(train.sum()),"test_samples":int(test.sum()),
                      "accuracy":hits/int(test.sum()),"train_majority_accuracy":base/int(test.sum()),
                      "train_factions":sorted(set(r["features"]["faction"] for r,t in zip(rows,train) if t)),
                      "test_factions":sorted(set(r["features"]["faction"] for r,t in zip(rows,test) if t))})
    args.output.mkdir(parents=True)
    final=fit(x,y,args.balanced); factions=sorted(set(r["features"]["faction"] for r in rows))
    checkpoint=args.output/"human-state-network.npz"
    np.savez(checkpoint,schema=np.array(1),labels=np.array(LABELS),trained_factions=np.array(factions),model_name=np.array(args.model_name),**final)
    loaded=HumanStatePolicy(checkpoint)
    np.testing.assert_allclose(np.stack([loaded.predict(r["features"]) for r in rows]),probabilities(x,final),rtol=1e-5,atol=1e-6)
    per_class={LABELS[c]:{"samples":int((y==c).sum()),"recall":float((oof[y==c]==c).mean()),"precision":float((y[oof==c]==c).mean()) if (oof==c).any() else 0.0} for c in np.unique(y)}
    report={"schema":1,"model":args.model_name,"mode":"shadow","controls_game":False,
            "dataset_sha256":hashlib.sha256(args.dataset.read_bytes()).hexdigest(),"checkpoint_sha256":hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
            "samples":len(rows),"excluded":dict(removed),"command_counts":dict(Counter(LABELS[i] for i in y)),
            "parameters":sum(v.size for v in final.values()),"recipe":{"epochs":60,"seed":42,"hidden":24,"input":INPUTS,"balanced":args.balanced,"class_weighting":"train-fold-only capped inverse square root" if args.balanced else "none"},
            "folds":folds,"oof_accuracy":correct/len(rows),"oof_train_majority_accuracy":baseline_correct/len(rows),
            "oof_mean_class_recall":float(np.mean([v["recall"] for v in per_class.values()])),"by_family":per_class,
            "final_fit":"All retained samples after fixed-recipe cross-validation; no independent test of final checkpoint.",
            "limits":["Imitates attempted command family, not tactical goal, selected unit, target or successful execution.",
                      "Few independent matches and factions; adjacent rows remain correlated.",
                      "No future observations, results, post-command resources or IDs enter encoder.",
                      "No live order mapping or comparison between command family and tactical candidate intent."]}
    (args.output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    with (args.output/"oof-predictions.jsonl").open("w",encoding="utf-8") as f:
        for r,label,pred in zip(rows,y,oof):
            f.write(json.dumps({"session":r["session_group"],"match":r["match"],"source":r["source"],"expected":LABELS[label],"predicted":LABELS[pred]},ensure_ascii=False)+"\n")
    print(json.dumps({k:report[k] for k in ("samples","excluded","oof_accuracy","oof_train_majority_accuracy","oof_mean_class_recall","parameters")}))


if __name__=="__main__": main()
