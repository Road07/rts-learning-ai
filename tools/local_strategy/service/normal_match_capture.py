"""Bounded, deterministic normal-play traces for offline reward-weighted imitation."""
import numpy as np
from decision_net import features
from spend_policy import spend_features


def trace(observation, candidates, selected, encoder):
    chosen = next(i for i, candidate in enumerate(candidates) if candidate["id"] == selected)
    # Keep the chosen action and a bounded set of alternatives; never alter play.
    indices = sorted(set([chosen] + np.linspace(0, len(candidates)-1, min(16, len(candidates)), dtype=int).tolist()))
    return {"features":[encoder(observation, candidates[i]).tolist() for i in indices],
            "selected_index":indices.index(chosen)}


class NormalMatchCapture:
    def __init__(self):
        self.last = {}

    def action(self, observation, candidates, selected, purchases, spend_id):
        player, frame = int(observation["player_index"]), int(observation["decision_frame"])
        key = (str(observation["match_id"]), player)
        if frame - self.last.get(key, -1000000) < 150: return None
        self.last[key] = frame
        return {"schema":"normal-trajectory-v1", "feature_encoding":"rts-mechanics-v1+bfme-public-rules-v2+native-queue-v1", "game_rules_sha256":observation.get("public_rules",{}).get("sha256"), "match_id":key[0], "player":player, "frame":frame, "faction":observation.get("faction"),
                "selection":"greedy", "tactical":trace(observation,candidates,selected,features),
                "spend":trace(observation,purchases,spend_id,spend_features)}
