"""Publish a validated, immutable checkpoint pair through one atomic config switch."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import msvcrt
from pathlib import Path
import sys
import uuid
import numpy as np
from decision_net import DecisionNet, features, load_tactical_model

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent / "service"))
from spend_policy import spend_features, WAIT, ENCODING, load_spend_model


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def atomic_json(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def publication_lock(folder):
    with (folder / "model-publication.lock").open("a+b") as lock:
        lock.seek(0)
        if not lock.read(1): lock.write(b"0"); lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        try: yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def validate_network(path, inputs):
    model = load_tactical_model(path) if inputs==len(features({}, {"id":"none"})) else load_spend_model(path)
    expected = DecisionNet(inputs).weights
    if set(model.weights) != set(expected): raise ValueError("Model katmanları uyumsuz")
    for key, value in model.weights.items():
        if value.shape != expected[key].shape or not np.isfinite(value).all():
            raise ValueError("Geçersiz model katmanı: " + key)
    if not np.isfinite(model.forward(np.zeros((1, inputs), dtype=np.float32))[0]).all():
        raise ValueError("Model sonlu bir skor üretmiyor")


def activate(folder, config_path):
    folder, config_path = Path(folder).resolve(), Path(config_path).resolve()
    report = read(folder / "report.json")
    if report.get("status") != "complete" or not report.get("rounds"):
        raise ValueError("Yalnız tamamlanmış eğitim aktarılabilir")
    last = report["rounds"][-1]
    if (last.get("reward_breakdown") or {}).get("version") != "bfme-outcome-reward-v3":
        raise ValueError("Ödül sürümü uyumsuz")
    if read(folder / "spend-metadata.json").get("encoding") != ENCODING:
        raise ValueError("Komut özellikleri uyumsuz")
    pair = [("candidate.npz", report["candidate_sha256"], len(features({}, {"id":"none"}))),
            ("spend-candidate.npz", last["spend_sha256"], len(spend_features({}, WAIT)))]
    contents = []
    for name, expected, inputs in pair:
        path = folder / name
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected: raise ValueError("Checkpoint değişmiş: " + name)
        validate_network(path, inputs)
        contents.append(data)
    generation = folder.stat().st_ctime_ns
    service = config_path.parent
    # Keep paths readable by the .NET Framework launcher on Windows (MAX_PATH).
    pair_key = hashlib.sha256((pair[0][1] + pair[1][1]).encode("ascii")).hexdigest()[:20]
    target = service / "trained-models" / pair_key
    with publication_lock(service):
        config = read(config_path)
        if not config.get("strict_model_only") or config.get("spend_encoding") != ENCODING:
            raise ValueError("Oyun paketi uyumsuz")
        previous = config.get("model_activation", {})
        if previous.get("source_run") == str(folder) and config["sha256"] == pair[0][1] and config["spend_sha256"] == pair[1][1] and config.get("weights") == str(target / pair[0][0]) and config.get("spend_weights") == str(target / pair[1][0]):
            return dict(previous, changed=False)
        if int(previous.get("generation", 0)) > generation:
            return dict(previous, changed=False, skipped="older_run")
        # Both files are immutable and exist before any reader can see their config.
        target.mkdir(parents=True, exist_ok=True)
        for (name, expected, _), data in zip(pair, contents):
            dest = target / name
            if dest.exists():
                if hashlib.sha256(dest.read_bytes()).hexdigest() != expected: raise ValueError("Arşiv modeli bozulmuş")
            else:
                temporary = dest.with_suffix(".tmp")
                temporary.write_bytes(data)
                temporary.replace(dest)
        activation = {"source_run":str(folder), "generation":generation,
                      "activated_utc":datetime.now(timezone.utc).isoformat(),
                      "tactic_sha256":pair[0][1], "spend_sha256":pair[1][1],
                      "strength_verified":False}
        updated = dict(config, weights=str(target / pair[0][0]), sha256=pair[0][1],
                       spend_weights=str(target / pair[1][0]), spend_sha256=pair[1][1],
                       model_activation=activation)
        atomic_json(service / "runtime.previous.json", config)
        atomic_json(config_path, updated)
        return dict(activation, changed=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "AI-Yeni-Model/ai-service/runtime.json")
    args = parser.parse_args()
    print(json.dumps(activate(args.run, args.config), ensure_ascii=False))
