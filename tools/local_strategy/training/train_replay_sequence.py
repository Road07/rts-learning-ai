"""Offline next-different-command imitation; never fabricates game state or deploys."""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "replay"))
import rotwk_replay as replay

FAMILIES = {
    "construct": ["DOZER_CONSTRUCT", "FOUNDATION_CONSTRUCT"],
    "train": ["QUEUE_UNIT_CREATE"],
    "cancel": ["CANCEL_UNIT_CREATE", "CANCEL_UPGRADE", "DOZER_CANCEL_CONSTRUCT"],
    "upgrade": ["QUEUE_UPGRADE"],
    "attack": ["DO_ATTACK_OBJECT", "DO_FORCE_ATTACK_OBJECT", "DO_FORCE_ATTACK_GROUND", "DO_ATTACKMOVETO"],
    "move": ["DO_MOVETO", "DO_FORCEMOVETO", "DO_MOVETO_FORMATION", "ADD_WAYPOINT"],
    "stance": ["CHANGE_STANCE", "CHANGE_ORDERMODE", "ENABLE_RETALIATION_MODE"],
    "ability": ["DO_SPECIAL_POWER", "DO_SPECIAL_POWER_AT_LOCATION", "DO_SPECIAL_POWER_AT_OBJECT", "DO_WEAPON_AT_LOCATION", "DO_WEAPON_AT_OBJECT", "DO_AUTO_ABILITY"],
    "spellbook": ["DO_SPELLBOOK_SPECIAL_POWER"],
    "science": ["PURCHASE_SCIENCE"],
    "garrison": ["ENTER"],
    "evacuate": ["EXIT", "EVACUATE", "EVACUATE_CONTESTERS"],
    "stop": ["DO_STOP", "DO_SCATTER"],
    "rally": ["SET_RALLY_POINT"],
    "sell": ["SELL"],
    "formation": ["HORDE_TOGGLE_FORMATION", "HORDE_SET_FORMATION"],
}
LABELS = list(FAMILIES)
LOOKUP = {"MSG_" + name: i for i, names in enumerate(FAMILIES.values()) for name in names}
HISTORY = 8


def encode(history):
    x = np.zeros((HISTORY, len(LABELS) + 1), np.float32)
    for i, command in enumerate(history):
        x[i, command["label"]] = 1
        if i:
            gap = max(0, command["frame"] - history[i-1]["frame"])
            x[i, -1] = min(1, np.log1p(gap) / np.log(10001))
    return x.ravel()


def load(path, folder):
    parsed = replay.summarize(path)
    messages = parsed.pop("_messages")
    streams = defaultdict(list)
    histogram = Counter()
    with (folder / (path.stem + "-commands.jsonl")).open("w", encoding="utf-8") as output:
        for msg in messages:
            name = replay.MSG_NAMES.get(msg["type"], "unknown")
            if name not in LOOKUP: continue
            histogram[name] += 1
            event = {"frame": msg["frame"], "player": msg["player"], "label": LOOKUP[name],
                     "family": LABELS[LOOKUP[name]], "message": name, "args": msg["args"],
                     "outcome_verified": False}
            output.write(json.dumps(event, ensure_ascii=False) + "\n")
            # Task is explicitly NEXT DIFFERENT command family, not all clicks or timing.
            stream = streams[msg["player"]]
            if stream and stream[-1]["label"] == event["label"]: stream[-1] = event
            else: stream.append(event)
    samples = {}
    for player, commands in streams.items():
        samples[player] = [(encode(commands[i-HISTORY:i]), commands[i]["label"], commands[i]["frame"])
                           for i in range(HISTORY, len(commands))]
    metadata = {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "version_field": parsed["header"]["version"], "map": parsed["header"]["options"].get("map"),
                "complete": parsed["complete"], "incomplete_reasons": parsed["incomplete_reasons"],
                "trailing_bytes": parsed["leftover_bytes"], "stream_records": len(messages),
                "extracted_commands": sum(histogram.values()), "command_histogram": dict(histogram),
                "transition_samples": {str(p): len(v) for p, v in samples.items()}}
    if parsed["leftover_bytes"]: raise ValueError("Undecoded replay tail: refusing training")
    return samples, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-replay", type=Path, required=True, action="append")
    parser.add_argument("--test-replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=35)
    args = parser.parse_args()
    if not 1 <= args.epochs <= 100: parser.error("epochs must be 1..100")
    if args.output.exists(): raise ValueError("Use a new output directory; never overwrite a model")
    test_hash = hashlib.sha256(args.test_replay.read_bytes()).hexdigest()
    train_hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in args.train_replay]
    if test_hash in train_hashes: raise ValueError("Train/test replay must differ")
    if len(set(train_hashes)) != len(train_hashes): raise ValueError("Duplicate training replay")
    if len({p.stem for p in args.train_replay+[args.test_replay]}) != len(args.train_replay)+1:
        raise ValueError("Replay export filenames must be distinct")
    started = time.monotonic()
    args.output.mkdir(parents=True)
    second, meta_b = load(args.test_replay, args.output)
    meta_b["split"] = "test"
    splits = {"train": [], "validation": [], "test": []}
    sources = []
    for path in args.train_replay:
        first, metadata = load(path, args.output)
        metadata["split"] = "train_and_chronological_validation"
        sources.append(metadata)
        for samples in first.values():
            cut = int(len(samples) * 0.8)
            splits["train"].extend(samples[:cut])
            # Never combine players or matches into a single history; purge boundary windows.
            splits["validation"].extend(samples[cut+HISTORY:])
    for samples in second.values(): splits["test"].extend(samples)
    if any(len(v) < 20 for v in splits.values()): raise ValueError("Insufficient split")
    arrays = {k: (np.stack([s[0] for s in rows]), np.array([s[1] for s in rows])) for k, rows in splits.items()}
    rng = np.random.default_rng(42)
    inputs = HISTORY * (len(LABELS) + 1)
    weights = {"w1": (rng.standard_normal((inputs,32))/np.sqrt(inputs)).astype(np.float32),
               "b1": np.zeros(32,np.float32), "w2": (rng.standard_normal((32,len(LABELS)))) .astype(np.float32)/np.sqrt(32),
               "b2": np.zeros(len(LABELS),np.float32)}
    def forward(x):
        hidden = np.tanh(x @ weights["w1"] + weights["b1"])
        scores = hidden @ weights["w2"] + weights["b2"]
        probabilities = np.exp(scores - scores.max(1,keepdims=True))
        probabilities /= probabilities.sum(1,keepdims=True)
        return hidden, probabilities
    def evaluate(key):
        x,y = arrays[key]
        _, probabilities = forward(x)
        predictions = probabilities.argmax(1)
        per_class = {LABELS[c]: {"samples": int((y==c).sum()), "accuracy": float((predictions[y==c]==c).mean())}
                     for c in np.unique(y)}
        return {"loss": float(-np.log(np.maximum(probabilities[np.arange(len(y)),y],1e-12)).mean()),
                "accuracy": float((predictions==y).mean()),
                "mean_class_recall": float(np.mean([v["accuracy"] for v in per_class.values()])), "by_family": per_class}
    x,y = arrays["train"]
    moments = {k: [np.zeros_like(v), np.zeros_like(v)] for k,v in weights.items()}
    step = 0
    best_loss = float("inf")
    best_epoch = 0
    best = None
    history = []
    initial = evaluate("validation")
    for epoch in range(1,args.epochs+1):
        order = rng.permutation(len(y))
        for start in range(0,len(y),128):
            ids = order[start:start+128]
            hidden, probabilities = forward(x[ids])
            probabilities[np.arange(len(ids)),y[ids]] -= 1
            derivative = probabilities / len(ids)
            hidden_derivative = (derivative @ weights["w2"].T) * (1-hidden*hidden)
            gradients = {"w2": hidden.T @ derivative, "b2": derivative.sum(0),
                         "w1": x[ids].T @ hidden_derivative, "b1": hidden_derivative.sum(0)}
            step += 1
            for key,g in gradients.items():
                m,v = moments[key]
                m *= 0.9; m += 0.1*g
                v *= 0.999; v += 0.001*g*g
                weights[key] -= 0.001*(m/(1-0.9**step))/(np.sqrt(v/(1-0.999**step))+1e-8)
        metric = evaluate("validation")
        if not np.isfinite(metric["loss"]): raise ValueError("Non-finite training loss")
        history.append({"epoch":epoch,"validation_loss":metric["loss"],"validation_accuracy":metric["accuracy"]})
        if metric["loss"] < best_loss-1e-5:
            best_loss,best_epoch = metric["loss"],epoch
            best = {k:v.copy() for k,v in weights.items()}
        if epoch-best_epoch>=7: break
    weights = best
    np.savez(args.output/"sequence-network.npz", **weights, schema=np.array(1), history=np.array(HISTORY), labels=np.array(LABELS))
    checkpoint = np.load(args.output/"sequence-network.npz",allow_pickle=False)
    assert all(np.array_equal(checkpoint[k],v) for k,v in weights.items())
    majority = int(np.bincount(y,minlength=len(LABELS)).argmax())
    transitions = np.ones((len(LABELS),len(LABELS)),np.float64)
    for feature,label,_ in splits["train"]:
        previous = int(feature.reshape(HISTORY,-1)[-1,:len(LABELS)].argmax())
        transitions[previous,label] += 1
    test_x,test_y = arrays["test"]
    previous = test_x.reshape(-1,HISTORY,len(LABELS)+1)[:,-1,:len(LABELS)].argmax(1)
    baseline = transitions.argmax(1)[previous]
    report = {"schema":1,"task":"Predict next DIFFERENT command family from own last eight command families and past frame gaps only",
              "architecture":"136 inputs -> tanh32 -> 16 softmax","parameters":sum(v.size for v in weights.values()),
              "initialization":"random seed 42; no pretrained or LocalModel data", "sources":sources+[meta_b],
              "split":"training replays each chronological 80% train/20% validation with eight-sample purge per player; separate test replay never trained on",
              "split_counts":{k:len(v) for k,v in splits.items()},"initial_validation":initial,"epochs_run":len(history),"best_epoch":best_epoch,
              "metrics":{k:evaluate(k) for k in arrays},"test_baselines":{"majority_family":LABELS[majority],"majority_accuracy":float((test_y==majority).mean()),"previous_family_markov_accuracy":float((baseline==test_y).mean())},
              "history":history,"seconds":time.monotonic()-started,"weights_sha256":hashlib.sha256((args.output/"sequence-network.npz").read_bytes()).hexdigest(),
              "deployment":"OFFLINE EXPERIMENT ONLY; existing game decision network untouched",
              "limitations":["Small replay collection; training/test match sizes and versions can differ.","Chronological validation shares players and matches with training; only test replay is separate.","If reused for comparison, test replay is a known benchmark, not a new blind evaluation.","No resources, positions, factions, fog, success or winner labels inferred.","No tactical attack/defend/help/scout or unit/building selection learned.","Repeated adjacent command families collapsed for this specific sequence task.","Incomplete replays contribute observed prefixes only; no terminal or victory target.","Results measure imitation of input order, not playing strength."]}
    (args.output/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:report[k] for k in ["split_counts","epochs_run","best_epoch","test_baselines","seconds"]}))
    print(json.dumps({"test":report["metrics"]["test"]["accuracy"],"validation":report["metrics"]["validation"]["accuracy"],"checkpoint":str(args.output/"sequence-network.npz")}))


if __name__ == "__main__": main()
