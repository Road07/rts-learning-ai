"""Inference for the configured replay sequence checkpoint; no tactical mapping."""
import numpy as np

LABELS = ["construct", "train", "cancel", "upgrade", "attack", "move", "stance", "ability",
          "spellbook", "science", "garrison", "evacuate", "stop", "rally", "sell", "formation"]
HISTORY = 8


class SequencePolicy:
    def __init__(self, path, model_name):
        if not isinstance(model_name,str) or not model_name.startswith("replay-sequence-v"):
            raise ValueError("Invalid replay sequence model name")
        self.model_name=model_name
        with np.load(path, allow_pickle=False) as data:
            if int(data["schema"]) != 1 or int(data["history"]) != HISTORY or data["labels"].tolist() != LABELS:
                raise ValueError("Replay sequence checkpoint schema mismatch")
            self.w = {name: data[name].copy() for name in ["w1", "b1", "w2", "b2"]}
        expected = {"w1": (136, 32), "b1": (32,), "w2": (32, 16), "b2": (16,)}
        if any(value.shape != expected[name] or not np.isfinite(value).all() for name, value in self.w.items()):
            raise ValueError("Invalid sequence weights")

    @staticmethod
    def encode(events):
        if len(events) != HISTORY: raise ValueError("Eight observed command groups required")
        x = np.zeros((HISTORY, len(LABELS)+1), np.float32)
        for i, event in enumerate(events):
            family, frame = event["family"], event["frame"]
            if family not in LABELS or not isinstance(frame, int) or frame < 0:
                raise ValueError("Invalid observed command history")
            if i and (frame < events[i-1]["frame"] or family == events[i-1]["family"]):
                raise ValueError("History must be chronological different-family groups")
            x[i, LABELS.index(family)] = 1
            if i:
                x[i, -1] = min(1, np.log1p(frame-events[i-1]["frame"]) / np.log(10001))
        return x.ravel()

    def hint(self, context):
        events = context.get("events", [])
        if len(events) < HISTORY: return {"ready": False, "reason": "history_warmup"}
        x = self.encode(events)
        scores = np.tanh(x @ self.w["w1"] + self.w["b1"]) @ self.w["w2"] + self.w["b2"]
        probabilities = np.exp(scores-scores.max())
        probabilities /= probabilities.sum()
        return {"ready": True, "model": self.model_name, "revision": int(context["revision"]),
                "history_frame": events[-1]["frame"], "probabilities": dict(zip(LABELS, probabilities.tolist())),
                "scope": "mapped_controller_orders_only; safe scout travel advisory"}
