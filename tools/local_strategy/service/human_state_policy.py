"""Human command-family imitation. Shadow only: never maps predictions to orders."""
import hashlib
import numpy as np

LABELS = ["construct", "train", "cancel", "upgrade", "attack", "move", "stance", "ability",
          "spellbook", "science", "garrison", "evacuate", "stop", "rally", "sell", "formation"]
FACTIONS = ["FactionMen", "FactionElves", "FactionDwarves", "FactionIsengard", "FactionMordor", "FactionWild", "FactionAngmar"]
INPUTS = 138


def encode(features):
    x = np.zeros(INPUTS, np.float32)
    faction = features["faction"]
    if faction not in FACTIONS: raise ValueError("Unknown faction")
    x[FACTIONS.index(faction)] = 1
    values = [features[k] for k in ("money", "cp_used", "cp_limit")]
    if any(not isinstance(v, (float, int)) or not np.isfinite(v) or v < 0 for v in values):
        raise ValueError("Invalid resource features")
    x[7:10] = [np.log1p(values[0])/np.log(100001), values[1]/2000, values[2]/2000]
    x[7:10] = np.clip(x[7:10], 0, 1)
    for offset, key in [(10, "own_templates"), (74, "visible_enemy_templates")]:
        for name, count in features[key].items():
            if not isinstance(name, str) or not isinstance(count, (float, int)) or not np.isfinite(count) or count < 0:
                raise ValueError("Invalid template count")
            bucket = int.from_bytes(hashlib.sha256(name.encode()).digest()[:4], "little") % 64
            x[offset+bucket] += count
        x[offset:offset+64] = np.log1p(x[offset:offset+64])/np.log(65)
        x[offset:offset+64] = np.clip(x[offset:offset+64], 0, 1)
    return x


class HumanStatePolicy:
    def __init__(self, path):
        with np.load(path, allow_pickle=False) as data:
            if int(data["schema"]) != 1 or data["labels"].tolist() != LABELS:
                raise ValueError("Human state checkpoint schema mismatch")
            self.factions = data["trained_factions"].tolist()
            self.model_name=str(data["model_name"].item()) if "model_name" in data else "human-state-v1"
            self.w = {k: data[k].copy() for k in ("w1", "b1", "w2", "b2")}
        expected = {"w1": (INPUTS,24), "b1": (24,), "w2": (24,16), "b2": (16,)}
        if any(v.shape != expected[k] or not np.isfinite(v).all() for k,v in self.w.items()):
            raise ValueError("Invalid human state weights")

    def predict(self, features):
        x = encode(features)
        scores = np.tanh(x @ self.w["w1"]+self.w["b1"]) @ self.w["w2"]+self.w["b2"]
        p = np.exp(scores-scores.max()); p /= p.sum()
        return p

    def shadow(self, features):
        if not isinstance(features, dict): return {"ready": False, "reason": "missing_state_features", "mode": "shadow"}
        if features.get("faction") not in self.factions:
            return {"ready": False, "reason": "untrained_faction", "mode": "shadow"}
        p = self.predict(features)
        return {"ready": True, "mode": "shadow", "model": self.model_name,
                "command_family": LABELS[int(p.argmax())], "probabilities": dict(zip(LABELS,p.tolist())),
                "controls_game": False, "scope": "human_attempt_family; no target or success prediction"}
