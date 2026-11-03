"""Reviewed match feedback, explicit tuning rather than invented training labels."""
import json
import re
from pathlib import Path


class MatchFeedback:
    def __init__(self, path):
        self.data = json.loads(Path(path).read_text(encoding="utf-8"))
        if self.data.get("schema") != 1: raise ValueError("Invalid match feedback")

    def adjustments(self, obs, candidates):
        if obs.get("home_emergency") or not self.data["enabled"]: return {}
        eligible = []
        for candidate in candidates:
            facts = candidate.get("facts", {})
            if not candidate["id"].startswith("attack_") or not facts.get("economy") or not facts.get("structure"):
                continue
            description = candidate.get("description", "")
            roi = re.search(r"ROI=([0-9.]+)", description)
            readiness = re.search(r"readiness=([0-9.]+)", description)
            if not roi or not readiness: continue
            if (0 < float(facts.get("health_ratio", 1)) <= self.data["target_health_max"]
                and int(facts.get("own_near", 0)) >= 1
                and float(roi[1]) >= self.data["minimum_roi"]
                and float(readiness[1]) >= self.data["minimum_readiness"]):
                eligible.append(candidate["id"])
        if not eligible: return {}
        result = {key: self.data["finish_bonus"] for key in eligible}
        for candidate in candidates:
            if candidate["id"] == "scout": result[candidate["id"]] = -self.data["scout_penalty"]
        return result
