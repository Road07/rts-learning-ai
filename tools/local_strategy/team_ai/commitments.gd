extends RefCounted

# Ledger transitions are code-owned. LLM text cannot directly mark promises fulfilled.
var board: RefCounted
var logbook: RefCounted

func transition(team: int, key: String, entry: Dictionary, next: String, reason: String, frame: int) -> bool:
	var previous = str(entry.get("status", "proposed"))
	var legal = {"proposed": ["active", "rejected", "cancelled"], "active": ["fulfilled", "cancelled", "timed_out"], "fulfilled": [], "cancelled": [], "rejected": [], "timed_out": []}
	if next not in legal.get(previous, []): return false
	entry.status = next
	entry.reason = reason
	entry.frame = frame
	entry.confidence = 1.0
	board.commitment(team, key, entry)
	logbook.write("commitment_transition", {"team": team, "key": key, "previous": previous, "status": next, "reason": reason, "frame": frame, "owner": entry.owner})
	return true

func expired(entry: Dictionary, frame: int) -> bool:
	return frame >= int(entry.get("expires", frame))
