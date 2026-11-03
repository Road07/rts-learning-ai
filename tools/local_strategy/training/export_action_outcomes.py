"""Observed human state/action/future pairs; no inferred rewards or replay state."""
import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "replay"))
import rotwk_replay


def features(state):
    own = [o for o in state["objects"] if o["relation"] == "self"]
    enemy = [o for o in state["objects"] if o["relation"] == "enemy"]
    return {"faction": state["faction"], "money": state["money"],
            "cp_used": state["cp_used"], "cp_limit": state["cp_limit"],
            "own_templates": dict(Counter(o["template"] for o in own)),
            "visible_enemy_templates": dict(Counter(o["template"] for o in enemy)),
            "own_queue_entries": sum(len(o.get("queue", [])) for o in own),
            "own_incomplete_structures": sum(o["structure"] and not o["complete"] for o in own),
            "own_injured_heroes": sum(o["hero"] and o["health_ratio"] < .2 for o in own)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay", type=Path, action="append", default=[])
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a new output directory; existing datasets are immutable")
    sessions = defaultdict(list)
    sources, counts = [], Counter()
    for path in sorted(args.logs.glob("*.jsonl")):
        raw = path.read_bytes()
        sources.append({"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest()})
        for line_no, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            # A malformed capture fails the export rather than silently bridging missing state.
            row = json.loads(line)
            row["source"] = {"path": str(path.resolve()), "line": line_no}
            sessions[(row["session"], row["match"])].append(row)
    args.output.mkdir(parents=True)
    with (args.output / "observed-transitions.jsonl").open("w", encoding="utf-8") as output:
        for (session, match), rows in sessions.items():
            header = next((r["data"] for r in rows if r["data"].get("event") == "human_session_start"), {})
            if header.get("fixture") or header.get("scope") != "fresh_local_human" or header.get("fog") != "own_and_living_allied_vision":
                counts["unsafe_or_fixture_sessions_skipped"] += 1
                continue
            if any(r["data"].get("event") == "capture_gap" for r in rows):
                counts["capture_gap_sessions_skipped"] += 1
                continue
            before, results, periodic, commands = {}, {}, defaultdict(list), defaultdict(list)
            outcomes = [r for r in rows if r["data"].get("event") == "human_match_result"]
            for row in rows:
                d = row["data"]
                key = (d.get("player"), d.get("command_id", d.get("id")))
                if d.get("event") == "human_state":
                    if d.get("reason") == "before_command": before[key] = row
                    elif d.get("reason") == "periodic": periodic[d["player"]].append(row)
                elif d.get("event") == "human_command_result": results[key] = row
                elif d.get("event") == "human_command": commands[d["player"]].append(d["frame"])
            for player in periodic:
                periodic[player].sort(key=lambda r: r["data"]["frame"])
            for player in commands: commands[player].sort()
            frames = {p: [r["data"]["frame"] for r in rs] for p, rs in periodic.items()}
            for row in rows:
                d = row["data"]
                if d.get("event") != "human_command": continue
                key = (d["player"], d["id"])
                pre, result = before.get(key), results.get(key)
                if not pre or not result or pre["data"]["frame"] != d["frame"]:
                    counts["unpaired_or_selection_commands_skipped"] += 1
                    continue
                if result["data"].get("dispatcher_error"):
                    counts["dispatcher_errors_skipped"] += 1
                    continue
                observed = []
                pf = frames.get(d["player"], [])
                for horizon in (25, 50):  # Native logic is 5 frames/second.
                    at = bisect_left(pf, d["frame"] + horizon)
                    if at >= len(pf) or pf[at] > d["frame"] + horizon + 5: continue
                    future = periodic[d["player"]][at]
                    later = future["data"]
                    if later["faction"] != pre["data"]["faction"]: raise ValueError("Faction changed inside capture group")
                    cf = commands[d["player"]]
                    intervening = bisect_right(cf, later["frame"]) - bisect_right(cf, d["frame"])
                    observed.append({"horizon_frames": horizon, "actual_frame_gap": later["frame"] - d["frame"],
                                     "state_source": future["source"], "features": features(later),
                                     "money_delta": later["money"] - pre["data"]["money"],
                                     "cp_used_delta": later["cp_used"] - pre["data"]["cp_used"],
                                     "intervening_commands": intervening,
                                     "caused_by_this_action_verified": False})
                if not observed:
                    counts["no_future_observation_skipped"] += 1
                    continue
                outcome = next((r for r in outcomes if r["data"].get("local_player") == d["player"]), None)
                record = {"schema": 1, "session_group": session, "match": match, "player": d["player"],
                          "source": row["source"], "state_source": pre["source"], "features": features(pre["data"]),
                          "action": d, "immediate_result": result["data"], "result_source": result["source"],
                          "future_observations": observed, "match_result": outcome["data"] if outcome else None,
                          "match_result_source": outcome["source"] if outcome else None,
                          "quality": {"source": "human_player", "fixture": False, "fog_filtered": True,
                                      "good_move_verified": False, "execution_success_verified": False,
                                      "causal_reward_available": False, "split_group": session}}
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
                counts["exported"] += 1
                if outcome: counts["with_recorded_match_result"] += 1
    replay_audit = []
    for path in args.replay:
        info = rotwk_replay.summarize(path)
        messages = info.pop("_messages")
        replay_audit.append({"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                             "commands": len(messages), "complete": info["complete"],
                             "undecoded_bytes": info["leftover_bytes"], "state_available": False,
                             "outcome_available": False, "tactical_training_eligible": False,
                             "reason": "Command decoding does not reconstruct compatible simulation state or fog."})
    report = {"schema": 1, "counts": dict(counts), "sources": sources, "replay_audit": replay_audit,
              "weights_changed": False,
              "limits": ["Split by whole session before fitting; never randomly split adjacent commands.",
                         "Future observations and match result are targets/analysis only, never input features.",
                         "Money/CP changes include other actions and ongoing income/combat; no causal success label.",
                         "Enemy disappearance is not labelled death; fog-filtered observations only."]}
    (args.output / "inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"counts": dict(counts), "replays_audited": len(replay_audit)}))


if __name__ == "__main__": main()
