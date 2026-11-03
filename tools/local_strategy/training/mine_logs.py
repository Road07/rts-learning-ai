"""Audit existing bot logs and export weak, task-specific examples without training."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def wall(operation):
    return "wall" in str(operation.get("template", "")).lower()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    groups = defaultdict(list)
    event_counts, source_counts, exported = Counter(), Counter(), Counter()
    manifest = []
    for folder in ["AI-Genel", "AI-Test-Sahasi", "AI-3v3-Test"]:
        for path in sorted((args.root / folder / "logs").glob("*.jsonl")):
            raw = path.read_bytes()
            manifest.append({"file": str(path.relative_to(args.root)), "sha256": hashlib.sha256(raw).hexdigest()})
            for line_no, line in enumerate(raw.decode("utf-8").splitlines(), 1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    source_counts[folder + ":invalid_lines"] += 1
                    continue
                source_counts[folder + ":events"] += 1
                if folder != "AI-Genel": continue  # archive inventory, never silently mix fixtures into training
                event_counts[row.get("event", "unknown")] += 1
                session = str(row.get("session", path.stem.rsplit("-", 1)[0]))
                row["_source"] = {"file": str(path.relative_to(args.root)), "line": line_no}
                groups[session].append(row)
    names = ["strategy", "strategy_filtered", "forced_strategy", "production", "micro_partial", "counter_partial", "evidence_events", "review_queue", "quarantined"]
    files = {name: (args.output / (name + ".jsonl")).open("w", encoding="utf-8") for name in names}
    signatures = defaultdict(set)
    actions, forced_actions, production_kinds, production_templates, reviews = Counter(), Counter(), Counter(), Counter(), Counter()
    session_reports = []

    def write(name, row, signature=None):
        # Deduplicate complete observable inputs + labels, excluding provenance and IDs.
        if signature is not None:
            digest = hashlib.sha256(json.dumps(signature, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if digest in signatures[name]: return False
            signatures[name].add(digest)
        files[name].write(json.dumps(row, ensure_ascii=False) + "\n")
        exported[name] += 1
        return True

    try:
        for session, rows in groups.items():
            fixture = any(str(row.get("event", "")).endswith("_fixture") or str(row.get("event", "")).startswith("arena_") for row in rows)
            requests = {}
            game_index = 0
            hero_templates, bot_factions = {}, {}
            session_counts = Counter()
            for row in rows:
                event, data = row.get("event"), row.get("data", {})
                if event == "general_bots":
                    game_index += 1
                    hero_templates.clear()
                    bot_factions = {int(b["index"]): b["faction"] for b in data.get("bots", [])}
                group = session + ":" + str(game_index)
                base = {"schema": 1, "session_group": session, "game_group": group, "source": row["_source"],
                        "player": data.get("player"), "observed_frame": data.get("frame"),
                        "quality": {"human_reviewed": False, "match_outcome": None, "fixture_marker": fixture}}
                key = (data.get("request"), data.get("player"))
                if event == "model_request":
                    requests[key] = (data, row["_source"], group)
                    continue
                request, request_source, request_group = requests.get(key, ({}, {}, None))
                matched = bool(request) and request_group == group
                if event == "model_decision":
                    session_counts["model_decisions"] += 1
                    if not matched:
                        session_counts["unmatched_decision"] += 1
                        continue
                    chosen = data.get("plan", {}).get("id")
                    candidates = request.get("candidates", [])
                    if chosen not in [c.get("id") for c in candidates]:
                        session_counts["unoffered_decision"] += 1
                        continue
                    age = int(data.get("frame", 0)) - int(request.get("frame", 0))
                    example = dict(base, request=key[0], observation=request.get("observation", {}),
                                   observed_frame=request.get("frame"), request_source=request_source,
                                   candidates=candidates, labels={"candidate_id": chosen, "production_id": None},
                                   snapshot_age_frames=age)
                    example["quality"].update(source="existing_model_decision", forced=len(candidates) == 1)
                    if fixture or age < 0 or age > 40:
                        write("quarantined", dict(example, reason="fixture_session" if fixture else "old_snapshot"))
                        continue
                    kind = data.get("plan", {}).get("kind", "unknown")
                    observation = example["observation"]
                    review_reason = None
                    if kind == "scout" and int(observation.get("home_threat_groups", 0)) > 0:
                        review_reason = "scout_while_home_threat_logged"
                    if kind == "defend" and not observation.get("home_emergency") and int(observation.get("home_threat_groups", 0)) == 0 and int(observation.get("army_groups", 0)) > 0:
                        review_reason = "defend_without_logged_home_threat"
                    example["quality"]["review_reason"] = review_reason
                    destination = "forced_strategy" if len(candidates) == 1 else "strategy"
                    if write(destination, example):
                        (forced_actions if destination == "forced_strategy" else actions)[kind] += 1
                    if destination == "strategy" and review_reason is None:
                        write("strategy_filtered", example)
                    if review_reason:
                        reviews[review_reason] += 1
                        write("review_queue", dict(example, review_reason=review_reason, verdict=None))
                elif event == "model_production":
                    operation = data.get("operation", {})
                    accepted = bool(data.get("result", {}).get("ok"))
                    if wall(operation):
                        reviews["standalone_wall_known_bad"] += 1
                        write("review_queue", dict(base, review_reason="standalone_wall_known_bad", verdict="exclude_action",
                                                   request=key[0], accepted_by_engine=accepted, bad_action=operation,
                                                   observation=request.get("observation") if matched else None))
                        continue
                    if not accepted or not matched:
                        session_counts["production_not_usable"] += 1
                        continue
                    offers = [p for p in request.get("production_options", []) if not wall(p)]
                    if operation.get("id") not in [p.get("id") for p in offers]:
                        session_counts["production_not_offered"] += 1
                        continue
                    example = dict(base, request=key[0], request_source=request_source, observation=request.get("observation", {}),
                                   observed_frame=request.get("frame"), production_options=offers,
                                   labels={"production_id": operation["id"]}, operation=operation,
                                   snapshot_age_frames=int(data.get("frame", 0)) - int(request.get("frame", 0)))
                    example["quality"].update(source="existing_model_purchase", submitted=True, purchase_completed=None)
                    if fixture:
                        write("quarantined", dict(example, reason="fixture_session"))
                    else:
                        write("production", example)
                        production_kinds[operation.get("kind", "unknown")] += 1
                        production_templates[operation.get("template", "unknown")] += 1
                elif event in ["hero_retreat", "hero_recovered", "cavalry_avoidance"]:
                    unit_key = (data.get("player"), data.get("unit"))
                    if event == "hero_retreat": hero_templates[unit_key] = data.get("template")
                    if event in ["hero_retreat", "hero_recovered"]:
                        if "health_ratio" not in data: continue
                        inputs = {"unit_type": "hero", "template": data.get("template", hero_templates.get(unit_key)),
                                  "health_ratio": data["health_ratio"]}
                        action = "retreat" if event == "hero_retreat" else "recovery_complete"
                    else:
                        if "visible_pikes" not in data: continue
                        inputs = {"unit_type": "cavalry", "visible_pikes": data["visible_pikes"]}
                        action = "avoid_pikes"
                    example = dict(base, task=event, inputs=inputs, label=action)
                    example["quality"].update(source="code_owned_micro", context_complete=False, action_success=None)
                    if fixture: continue
                    write("micro_partial", example, {"inputs": inputs, "label": action})
                elif event == "counter_production":
                    if fixture or not data.get("desired"): continue
                    inputs = {"faction": bot_factions.get(data.get("player")), "seen_enemy": data.get("seen_enemy", {})}
                    labels = data["desired"]
                    example = dict(base, task="composition_preference", inputs=inputs, labels=labels)
                    example["quality"].update(source="existing_production_policy", context_complete=False, actual_units_trained=None)
                    write("counter_partial", example, {"inputs": inputs, "labels": labels})
                elif event in ["tactic_result", "battle_losses", "tunnel_enter", "tunnel_exit", "production_capacity", "user_marker"]:
                    if fixture: continue
                    example = dict(base, event=event, evidence=data)
                    example["quality"].update(plan_attribution_verified=False)
                    write("evidence_events", example)
            session_reports.append({"session": session, "fixture_marker": fixture,
                                    "duration_seconds": max((r.get("elapsed_ms", 0) for r in rows), default=0) / 1000,
                                    "counts": dict(session_counts)})
    finally:
        for file in files.values(): file.close()
    report = {"schema": 1, "source_files": manifest, "source_counts": dict(source_counts),
              "main_event_counts": dict(event_counts), "sessions": session_reports, "exports": dict(exported),
              "strategy_classes": dict(actions), "forced_classes": dict(forced_actions),
              "production_kinds": dict(production_kinds), "production_templates": dict(production_templates),
              "review_reasons": dict(reviews),
              "rules": ["AI-Test-Sahasi and AI-3v3-Test inventoried separately; not used as normal-match training data.",
                        "Entire sessions with explicit fixture markers quarantined. Unmarked sessions are not certified human matches.",
                        "Future results and global economy/unit telemetry never added to model observations.",
                        "Accepted command means submitted, not successful gameplay or completed purchase.",
                        "Forced single-choice decisions are mask examples, not new strategic discrimination examples.",
                        "Micro/counter examples have partial context and are not input-compatible with the v0 strategy net.",
                        "Tactic feedback lacks reliable plan IDs; retained as evidence, never auto-converted to win/reward labels."]}
    (args.output / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ["exports", "strategy_classes", "forced_classes", "production_kinds", "review_reasons"]}))


if __name__ == "__main__":
    main()
