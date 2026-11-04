"""Small shared candidate-scoring neural policy. No language-model/pretrained weights."""
import hashlib
import math
import re
import numpy as np

VERSION = 1
FACTIONS = ["FactionMen", "FactionElves", "FactionDwarves", "FactionWild", "FactionMordor", "FactionIsengard", "FactionAngmar"]
KINDS = ["defend", "help", "attack", "scout"]


def kind(candidate):
    return str(candidate["id"]).split("_", 1)[0]


def magnitude(value, scale):
    return min(3.0, math.log1p(max(0, float(value or 0))) / math.log1p(scale))


def bag(items):
    result = [0.0] * 16
    for name, count in items.items():
        bucket = hashlib.sha256(str(name).encode()).digest()[0] % len(result)
        result[bucket] += float(count)
    return [magnitude(count, 20) for count in result]


def features(observation, candidate, include_mechanics=True, include_rules=True):
    obs = observation
    context = [float(obs.get("faction") == f) for f in FACTIONS]
    context += [float(obs.get("personality") == p) for p in ["aggressive", "balanced", "defensive"]]
    context += [float(obs.get("team_role") == p) for p in ["pressure", "economy", "defender", "flex"]]
    context += [float(obs.get("phase") == p) for p in ["develop", "pressure", "stabilize", "finish"]]
    axes = obs.get("personality_axes", {})
    context += [float(axes.get(key, 0.5)) for key in ["aggression", "economy", "precision", "risk", "tech"]]
    context += [float(bool(obs.get("home_emergency")))]
    context += [magnitude(obs.get(key), scale) for key, scale in
                [("money", 5000), ("army_groups", 20), ("home_threat_groups", 10),
                 ("visible_enemy_groups", 20), ("cp_free", 500)]]
    for field in ["own_composition", "visible_enemy_composition", "own_buildings"]:
        context += bag(obs.get(field, {}))
    description = candidate.get("description", "")
    def number(pattern, default=0):
        match = re.search(pattern, description)
        return float(match[1]) if match else default
    choice = [float(kind(candidate) == k) for k in KINDS]
    choice += [magnitude(number(r"ROI=([0-9.]+)"), 30),
               magnitude(number(r"nearby enemy groups (\d+)"), 10),
               magnitude(number(r"available own groups (\d+)"), 20),
               float("structure" in description), float("enemy army" in description),
               number(r"readiness=([0-9.]+)"), float("ROI=" in description)]
    extra=[]
    if include_mechanics:
        from mechanics_features import state_features,action_features
        extra=state_features(observation)+action_features(candidate)
        if include_rules:
            from public_game_rules import tactical_features
            extra+=tactical_features(observation,candidate)
    return np.asarray(context + choice + extra, dtype=np.float32)


class DecisionNet:
    def __init__(self, inputs, seed=42):
        rng = np.random.default_rng(seed)
        self.weights = {}
        self.factions = {}
        for i, (a, b) in enumerate([(inputs, 64), (64, 32), (32, 1)]):
            self.weights["w" + str(i)] = (rng.standard_normal((a, b)) * math.sqrt(1 / a)).astype(np.float32)
            self.weights["b" + str(i)] = np.zeros(b, dtype=np.float32)

    def forward(self, x):
        w = self.weights
        h1 = np.tanh(x @ w["w0"] + w["b0"])
        h2 = np.tanh(h1 @ w["w1"] + w["b1"])
        scores = (h2 @ w["w2"] + w["b2"]).squeeze(-1)
        return scores, (x, h1, h2)

    def gradients(self, derivative, cache):
        x, h1, h2 = cache
        g = derivative.reshape(-1, 1)
        h1, h2, x = h1.reshape(-1, 64), h2.reshape(-1, 32), x.reshape(-1, x.shape[-1])
        result = {"w2": h2.T @ g, "b2": g.sum(0)}
        g = (g @ self.weights["w2"].T) * (1 - h2 * h2)
        result.update(w1=h1.T @ g, b1=g.sum(0))
        g = (g @ self.weights["w1"].T) * (1 - h1 * h1)
        result.update(w0=x.T @ g, b0=g.sum(0))
        return result

    def predict(self, observation, candidates):
        selected = self.for_faction(observation.get("faction"))
        if selected is not self: return selected.predict(observation, candidates)
        if not candidates: raise ValueError("No legal candidate offered")
        x = np.stack([features(observation, c) for c in candidates])
        scores, _ = self.forward(x)
        return str(candidates[int(np.argmax(scores))]["id"])

    def save(self, path):
        extra = {}
        if self.factions:
            extra["faction_version"] = np.array(1)
            for faction, model in self.factions.items():
                extra.update({"faction_"+faction+"_"+key:value for key,value in model.weights.items()})
        np.savez(path, features_version=np.array(VERSION), **self.weights, **extra)

    def ensure_factions(self):
        if not self.factions:
            for faction in FACTIONS:
                bank = DecisionNet(self.weights["w0"].shape[0])
                bank.weights = {key:value.copy() for key,value in self.weights.items()}
                self.factions[faction] = bank
        return self

    def expand_inputs(self, inputs, allowed):
        old=self.weights["w0"].shape[0]
        if old==inputs: return self
        if old not in allowed or old>inputs: raise ValueError("Unknown model feature dimensions")
        for bank in [self]+list(self.factions.values()):
            bank.weights["w0"]=np.vstack([bank.weights["w0"],np.zeros((inputs-old,64),dtype=np.float32)])
        return self

    def for_faction(self, faction):
        if self.factions:
            if faction not in self.factions: raise ValueError("Unknown faction policy: " + str(faction))
            return self.factions[faction]
        return self

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as stored:
            if int(stored["features_version"]) != VERSION: raise ValueError("Feature version mismatch")
            model = cls(stored["w0"].shape[0])
            model.weights = {key: stored[key].copy() for key in model.weights}
            if any(not np.isfinite(value).all() for value in model.weights.values()): raise ValueError("Nonfinite weights")
            if "faction_version" in stored:
                if int(stored["faction_version"]) != 1: raise ValueError("Unknown faction checkpoint version")
                model.ensure_factions()
                for faction, bank in model.factions.items():
                    bank.weights = {key:stored["faction_"+faction+"_"+key].copy() for key in model.weights}
                    if any(value.shape != model.weights[key].shape or not np.isfinite(value).all() for key,value in bank.weights.items()):
                        raise ValueError("Invalid faction checkpoint: " + faction)
            return model


def load_tactical_model(path):
    inputs=len(features({}, {"id":"none"}))
    legacy=len(features({}, {"id":"none"},include_mechanics=False))
    mechanics=len(features({}, {"id":"none"},include_rules=False))
    return DecisionNet.load(path).expand_inputs(inputs,[legacy,mechanics])
