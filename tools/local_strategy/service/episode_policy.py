"""Arena-only stochastic policy. Normal games never enable this module's sampler."""
import numpy as np
from decision_net import features


def probabilities(scores, temperature=1.0):
    scores = np.asarray(scores, dtype=np.float64) / temperature
    scores -= scores.max()
    weights = np.exp(scores)
    return weights / weights.sum()


class EpisodePolicy:
    def __init__(self, seed, mode):
        if mode not in ("sample", "evaluate"):
            raise ValueError("Unknown episode mode")
        self.rng = np.random.default_rng(seed)
        self.mode = mode
        self.count = 0

    def choose(self, model, observation, candidates, encoder=features, stream="tactical"):
        model = model.for_faction(observation.get("faction"))
        x = np.stack([encoder(observation, c) for c in candidates])
        scores, _ = model.forward(x)
        p = probabilities(scores)
        index = int(self.rng.choice(len(p), p=p)) if self.mode == "sample" else int(np.argmax(scores))
        self.count += 1
        token = "episode-%s-%d" % (stream,self.count)
        return candidates[index]["id"], token, {
            "action_id": token, "head":stream, "observation": observation, "candidates": candidates,
            "selected_index": index, "probabilities": p.tolist(), "mode": self.mode,
        }
