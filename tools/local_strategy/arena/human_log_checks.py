"""Validate real human-type dispatch telemetry from the isolated human-log case."""
import json


def check(folder, report):
    session = report.get("human_log_session", "")
    paths = sorted((folder / "human-logs").glob(session + "-*.jsonl")) if session else []
    records = [json.loads(line)["data"] for path in paths for line in path.read_text(encoding="utf-8").splitlines()]
    probe = report.get("human_probe", {})
    states = [r for r in records if r.get("event") == "human_state"]
    commands = [r for r in records if r.get("event") == "human_command"]
    results = {r["id"]: r for r in records if r.get("event") == "human_command_result"}
    before = {r.get("command_id"): r for r in states if r.get("reason") == "before_command"}
    names = {r.get("command") for r in commands}
    queued = next((r for r in commands if r.get("command") == "MSG_QUEUE_UNIT_CREATE"), {})
    cancelled = next((r for r in commands if r.get("command") == "MSG_CANCEL_UNIT_CREATE"), {})
    first = states[0] if states else {}
    objects = first.get("objects", [])
    checks = {
        "human_only": bool(commands) and all(r.get("player") == probe.get("player") for r in commands),
        "periodic_states": any(r.get("reason") == "periodic" for r in states),
        "queue_cancel_move": {"MSG_QUEUE_UNIT_CREATE", "MSG_CANCEL_UNIT_CREATE", "MSG_DO_MOVETO"} <= names,
        "pre_command_state_link": all(r["id"] in before for r in commands if r.get("command") in ["MSG_QUEUE_UNIT_CREATE", "MSG_CANCEL_UNIT_CREATE", "MSG_DO_MOVETO"]),
        "pre_post_pairing": all(r["id"] in results for r in commands),
        "own_science_and_upgrades": "science" in first and "player_upgrades" in first,
        "hidden_enemy_excluded": bool(first) and probe.get("hidden") not in [o["id"] for o in objects],
        "visible_enemy_included": probe.get("visible") in [o["id"] for o in objects],
        "enemy_private_fields_absent": all(not any(k in o for k in ["queue", "powers", "upgrades", "money"]) for s in states for o in s.get("objects", []) if o.get("relation") != "self"),
        "fixture_marked": any(r.get("event") == "human_session_start" and r.get("fixture") for r in records),
        "review_marker": any(r.get("event") == "human_review_marker" for r in records),
        "clean_close": bool(records) and records[-1].get("event") == "human_session_end",
        "no_buffer_gap": not any(r.get("event") == "capture_gap" for r in records),
    }
    checks["training_spent_money"] = bool(queued) and results.get(queued.get("id"), {}).get("money", float("inf")) < queued["money"]
    checks["cancel_refunded_money"] = bool(cancelled) and results.get(cancelled.get("id"), {}).get("money", -1) > cancelled["money"]
    return {"ok": all(checks.values()), "checks": checks, "states": len(states), "commands": len(commands), "records": len(records), "files": [str(p) for p in paths]}
