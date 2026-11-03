"""Export observed state -> offered/accepted decisions; these are weak labels, not wins."""
import argparse
from collections import Counter
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    totals = Counter()
    classes = Counter()
    sessions = []
    with (args.output / "decisions.jsonl").open("w", encoding="utf-8") as output:
        for path in sorted(args.logs.glob("*.jsonl")):
            requests, decisions, productions = {}, {}, {}
            count = 0
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    totals["invalid_lines"] += 1
                    continue
                event, data = record.get("event"), record.get("data", {})
                if event not in ("model_request", "model_decision", "model_production"):
                    continue
                totals[event] += 1
                key = (data.get("request"), data.get("player"))
                if event == "model_request": requests[key] = data
                elif event == "model_decision": decisions[key] = data
                else: productions[key] = data
            for key, decision in decisions.items():
                request = requests.get(key)
                if not request:
                    totals["missing_request"] += 1
                    continue
                candidates = request.get("candidates", [])
                chosen = decision.get("plan", {}).get("id")
                if chosen not in [candidate.get("id") for candidate in candidates]:
                    totals["choice_not_in_original_offer"] += 1
                    continue
                if len(candidates) < 2:
                    totals["single_option_excluded"] += 1
                    continue
                # The snapshot is already each bot's fog-filtered model input.
                # Do not enrich it from later logs, test fixtures or hidden world state.
                observation = request.get("observation", {})
                production = productions.get(key, {})
                operation = production.get("operation", {})
                production_label = None
                if production.get("result", {}).get("ok"):
                    if "wall" in operation.get("template", "").lower():
                        totals["wall_labels_excluded"] += 1
                    elif operation.get("id") in [p.get("id") for p in request.get("production_options", [])]:
                        production_label = operation["id"]
                        totals["accepted_purchase_labels"] += 1
                # Never interpret a missing/failed purchase as a decision to save.
                row = {"schema": 1, "session_group": path.stem,
                       "request": key[0], "player": key[1], "observed_frame": request.get("frame"),
                       "observation": observation, "candidates": candidates,
                       "production_options": [p for p in request.get("production_options", [])
                                              if "wall" not in p.get("template", "").lower()],
                       "labels": {"candidate_id": chosen, "production_id": production_label},
                       "quality": {"source": "existing_model_decision", "human_reviewed": False,
                                   "match_outcome": None, "purchase_completed": None}}
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
                classes[decision.get("plan", {}).get("kind", "unknown")] += 1
                count += 1
            sessions.append({"file": path.name, "eligible_decisions": count})
    report = {"schema": 1, "sessions": sessions, "counts": dict(totals),
              "eligible_decisions": sum(classes.values()), "action_counts": dict(classes),
              "limitations": ["Weak imitation labels; no verified good moves or win labels.",
                              "Keep sessions separate across training and evaluation; deduplicate equivalent states.",
                              "Sparse purchase labels cannot establish a competent production policy.",
                              "This prepares data only; no weights trained and no deployed model changed."]}
    (args.output / "inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("eligible_decisions", "action_counts", "counts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
