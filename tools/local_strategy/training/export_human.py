"""Export paired, pre-command human demonstrations; never treats them as verified good."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-fixtures", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    sessions = defaultdict(list)
    sources = []
    counts = Counter()
    for path in sorted(args.logs.glob("*.jsonl")):
        raw = path.read_bytes()
        sources.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
        for line_no, line in enumerate(raw.decode("utf-8").splitlines(), 1):
            try: record = json.loads(line)
            except json.JSONDecodeError:
                counts["invalid_lines"] += 1
                continue
            record["source"] = {"path": str(path), "line": line_no}
            sessions[(record.get("session"), record.get("match"))].append(record)
    kinds = Counter()
    with (args.output / "human_actions.jsonl").open("w", encoding="utf-8") as output:
        for (session, match), rows in sessions.items():
            header = next((r["data"] for r in rows if r["data"].get("event") == "human_session_start"), None)
            if not header:
                counts["sessions_without_header"] += 1
                continue
            if header.get("fixture") and not args.include_fixtures:
                counts["fixture_sessions_skipped"] += 1
                continue
            if any(r["data"].get("event") == "capture_gap" for r in rows):
                counts["sessions_with_capture_gap_skipped"] += 1
                continue
            states, results = {}, {}
            outcomes = [r["data"] for r in rows if r["data"].get("event") == "human_match_result"]
            for row in rows:
                data = row["data"]
                if data.get("event") == "human_state" and data.get("reason") == "before_command":
                    states[(data["player"], data["command_id"])] = row
                elif data.get("event") == "human_command_result":
                    results[(data["player"], data["id"])] = row
            for row in rows:
                action = row["data"]
                if action.get("event") != "human_command": continue
                key = (action["player"], action["id"])
                state, result = states.get(key), results.get(key)
                if not state or not result:
                    counts["selection_or_unpaired_commands_skipped"] += 1
                    continue
                if state["data"]["frame"] != action["frame"]:
                    counts["mismatched_state_skipped"] += 1
                    continue
                outcome = next((o for o in outcomes if o.get("local_player") == action["player"]), None)
                example = {"schema": 1, "session_group": session, "match": match, "fixture": bool(header.get("fixture")),
                           "source": row["source"], "state_source": state["source"], "result_source": result["source"],
                           "observation": state["data"], "action": action, "immediate_result": result["data"],
                           "match_result": outcome,
                           "quality": {"source": "human_player", "human_reviewed": False,
                                       "good_move_verified": False, "execution_success_verified": False,
                                       "dispatcher_error": bool(result["data"].get("dispatcher_error"))}}
                output.write(json.dumps(example, ensure_ascii=False) + "\n")
                kinds[action["command"]] += 1
                counts["exported"] += 1
    report = {"schema": 1, "sources": sources, "counts": dict(counts), "command_counts": dict(kinds),
              "fixtures_allowed": args.include_fixtures,
              "limits": "Attempts, cancellations and failed commands remain distinct; no automatic good/win labels. Periodic states are not automatically labelled wait."}
    (args.output / "inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"counts": dict(counts), "command_counts": dict(kinds)}))


if __name__ == "__main__": main()
