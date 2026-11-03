"""Source-attributed soft advice over offered actions; not neural training."""
import json
from pathlib import Path
import numpy as np
from decision_net import features, kind


class FandomPolicy:
    def __init__(self, path):
        self.data = json.loads(Path(path).read_text(encoding="utf-8"))
        if self.data.get("schema") != 1 or len(self.data.get("factions", {})) != 7:
            raise ValueError("Invalid faction knowledge catalogue")

    def choose(self, model, observation, candidates, feedback=None):
        scores, _ = model.forward(np.stack([features(observation, c) for c in candidates]))
        adjusted = scores.copy()
        context = observation.get("knowledge_context", {})
        profile = self.data["factions"].get(observation.get("faction"), {})
        roles = context.get("roles", [0, 0, 0, 0])
        faction = observation.get("faction")
        trace = []
        feedback_deltas = feedback.adjustments(observation,candidates) if feedback else {}
        for i, candidate in enumerate(candidates):
            facts = candidate.get("facts", {})
            action = kind(candidate)
            advice = []
            def add(rule, amount, source):
                advice.append({"rule": rule, "delta": amount, "source": self.data["sources"][source]})
            # Missing context never authorizes invented state; home emergencies remain authoritative.
            if self.data["scoring"].get("enabled", False) and context and not observation.get("home_emergency"):
                if action == "scout" and observation.get("visible_enemy_groups", 0) == 0:
                    add("seek_visible_information", 0.12, "goblins")
                if action == "attack" and facts:
                    if facts.get("economy") and roles[0] > 0 and "raid_bonus" in profile:
                        add("sword_resource_pressure", profile["raid_bonus"], profile["source"])
                    local = facts.get("enemy_roles", [0, 0, 0, 0])
                    if local[3] > 0 and roles[2] == 0 and roles[1] > 0:
                        add("missing_pike_screen", -0.35, "angmar")
                    if local[2] > 0 and roles[3] > 0:
                        add("mounted_force_faces_pikes", -0.20, "men")
                    if faction == "FactionDwarves":
                        if facts.get("own_near", 0) >= 3:
                            add("concentrated_dwarf_force", profile["cohesion_bonus"], "dwarves")
                        elif facts.get("distance_home", 0) > 1800:
                            add("avoid_isolated_slow_march", -0.25, "dwarves")
                    if faction == "FactionElves" and roles[1] > 0 and roles[2] > 0:
                        add("protected_elven_ranged_core", 0.15, "elves")
                    if "combined_bonus" in profile and sum(v > 0 for v in roles) >= 2:
                        add("combined_arms", profile["combined_bonus"], profile["source"])
                    if faction == "FactionIsengard" and facts.get("hero") and facts.get("health_ratio", 1) < 0.5 and "IsengardLurtz" in context.get("heroes", []):
                        add("lurtz_hero_hunt_opportunity", 0.30, "lurtz")
                    if faction == "FactionAngmar" and context.get("hwaldar_supported_groups", 0) >= 2:
                        add("hwaldar_with_rhudaur", 0.20, "hwaldar")
            maximum = float(self.data["scoring"]["maximum_adjustment"])
            delta = float(np.clip(sum(row["delta"] for row in advice), -maximum, maximum))
            match_delta = float(np.clip(feedback_deltas.get(candidate["id"],0),-0.60,0.60))
            adjusted[i] += delta+match_delta
            trace.append({"id": candidate["id"], "base_score": round(float(scores[i]), 5),
                          "adjustment": round(delta, 5), "feedback_adjustment":match_delta,"rules": advice})
        before = str(candidates[int(np.argmax(scores))]["id"])
        selected = str(candidates[int(np.argmax(adjusted))]["id"])
        return selected, {"knowledge": self.data["id"], "base_choice": before, "selected": selected,
                          "feedback":feedback.data["id"] if feedback else None,
                          "changed": before != selected, "scores": trace}
