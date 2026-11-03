"""Bounded from-scratch imitation experiment; never deploys its checkpoint to the game."""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from decision_net import DecisionNet, VERSION, features, kind


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not 1 <= args.epochs <= 200: parser.error("epochs must be 1..200")
    start = time.monotonic()
    rows = [json.loads(line) for line in args.data.read_text(encoding="utf-8").splitlines()]
    unique, conflicts, removed = {}, set(), Counter()
    for row in rows:
        pairs = [(tuple(np.round(features(row["observation"], c), 4)), c) for c in row["candidates"]]
        pairs.sort(key=lambda pair: pair[0])
        label = next(i for i, pair in enumerate(pairs) if pair[1]["id"] == row["labels"]["candidate_id"])
        if sum(pair[0] == pairs[label][0] for pair in pairs) > 1:
            removed["indistinguishable_target"] += 1
            continue
        signature = hashlib.sha256(np.asarray([pair[0] for pair in pairs], np.float32).tobytes()).hexdigest()
        if signature in unique:
            removed["duplicate_state"] += 1
            if unique[signature]["label"] != label: conflicts.add(signature)
            continue
        unique[signature] = {"x": np.asarray([pair[0] for pair in pairs], np.float32), "label": label,
                             "kinds": [kind(pair[1]) for pair in pairs], "group": row["session_group"],
                             "observation": row["observation"], "candidates": [pair[1] for pair in pairs]}
    samples = [sample for key, sample in unique.items() if key not in conflicts]
    removed["conflicting_states"] = len(conflicts)
    rng = np.random.default_rng(args.seed)
    groups = sorted({s["group"] for s in samples})
    if len(groups) < 5: raise ValueError("Need at least five distinct session groups")
    rng.shuffle(groups)
    held = max(1, len(groups) // 5)
    split_groups = {"test": groups[:held], "validation": groups[held:2 * held], "train": groups[2 * held:]}
    splits = {key: [s for s in samples if s["group"] in group] for key, group in split_groups.items()}
    if any(not split for split in splits.values()): raise ValueError("Empty split")
    inputs, choices = samples[0]["x"].shape[1], max(len(s["x"]) for s in samples)
    def arrays(items):
        x = np.zeros((len(items), choices, inputs), np.float32)
        mask = np.zeros((len(items), choices), bool)
        y = np.asarray([s["label"] for s in items])
        for i, sample in enumerate(items):
            x[i, :len(sample["x"])] = sample["x"]
            mask[i, :len(sample["x"])] = True
        return x, mask, y
    data = {key: arrays(items) for key, items in splits.items()}
    model = DecisionNet(inputs, args.seed)
    moments = {key: [np.zeros_like(w), np.zeros_like(w)] for key, w in model.weights.items()}
    def evaluate(items):
        x, mask, y = items
        scores, _ = model.forward(x)
        scores = np.where(mask, scores, -1e9)
        probabilities = np.exp(scores - scores.max(1, keepdims=True))
        probabilities /= probabilities.sum(1, keepdims=True)
        loss = float(-np.log(np.maximum(probabilities[np.arange(len(y)), y], 1e-12)).mean())
        return {"loss": loss, "teacher_choice_accuracy": float(np.mean(np.argmax(scores, 1) == y))}
    step, best_loss, best, best_epoch = 0, float("inf"), None, 0
    history = []
    initial = evaluate(data["validation"])
    for epoch in range(1, args.epochs + 1):
        x, mask, y = data["train"]
        order = rng.permutation(len(y))
        for start_index in range(0, len(y), 32):
            ids = order[start_index:start_index + 32]
            scores, cache = model.forward(x[ids])
            scores = np.where(mask[ids], scores, -1e9)
            probabilities = np.exp(scores - scores.max(1, keepdims=True))
            probabilities /= probabilities.sum(1, keepdims=True)
            probabilities[np.arange(len(ids)), y[ids]] -= 1
            grads = model.gradients(probabilities / len(ids), cache)
            step += 1
            norm = np.sqrt(sum(float((g * g).sum()) for g in grads.values()))
            for key, gradient in grads.items():
                gradient *= min(1.0, 5 / max(norm, 1e-8))
                m, v = moments[key]
                m *= 0.9; m += 0.1 * gradient
                v *= 0.999; v += 0.001 * gradient * gradient
                model.weights[key] -= 0.001 * (m / (1 - 0.9 ** step)) / (np.sqrt(v / (1 - 0.999 ** step)) + 1e-8)
        validation = evaluate(data["validation"])
        if not np.isfinite(validation["loss"]): raise ValueError("Training diverged")
        history.append({"epoch": epoch, "validation": validation})
        if validation["loss"] < best_loss - 1e-5:
            best_loss, best_epoch = validation["loss"], epoch
            best = {key: value.copy() for key, value in model.weights.items()}
        if epoch - best_epoch >= 12: break
    model.weights = best
    args.output.mkdir(parents=True, exist_ok=True)
    model.save(args.output / "network.npz")
    reloaded = DecisionNet.load(args.output / "network.npz")
    by_action = {}
    for sample in splits["test"]:
        predicted = model.predict(sample["observation"], sample["candidates"])
        assert predicted == reloaded.predict(sample["observation"], sample["candidates"])
        true_kind = sample["kinds"][sample["label"]]
        bucket = by_action.setdefault(true_kind, {"samples": 0, "correct_candidate": 0})
        bucket["samples"] += 1
        bucket["correct_candidate"] += predicted == sample["candidates"][sample["label"]]["id"]
    majority = Counter(s["kinds"][s["label"]] for s in splits["train"]).most_common(1)[0][0]
    baseline = np.mean([next((i for i, k in enumerate(s["kinds"]) if k == majority), 0) == s["label"] for s in splits["test"]])
    report = {"schema": 1, "architecture": "shared candidate scorer: tanh 64 -> tanh 32 -> scalar",
              "initialization": "random; no pretrained weights", "features_version": VERSION,
              "parameters": sum(w.size for w in model.weights.values()), "device": "CPU (NumPy)",
              "seed": args.seed, "data_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(),
              "removed": dict(removed), "split_counts": {key: len(value) for key, value in splits.items()},
              "split_groups": split_groups, "best_epoch": best_epoch, "epochs_run": len(history),
              "initial_validation": initial, "metrics": {key: evaluate(value) for key, value in data.items()},
              "test_baseline": {"preferred_action": majority, "teacher_choice_accuracy": float(baseline)},
              "test_by_action": by_action,
              "history": history, "seconds": time.monotonic() - start,
              "deployment": "not deployed; existing Qwen controller unchanged",
              "scope": "Weak-label strategy imitation only; no production policy, chat, RL or win-rate evaluation."}
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ["parameters", "split_counts", "best_epoch", "epochs_run", "metrics", "test_baseline", "seconds"]}))


if __name__ == "__main__":
    main()
