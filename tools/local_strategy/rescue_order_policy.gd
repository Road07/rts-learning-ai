extends RefCounted

# Persistent per-unit assignments. A check is not a new command.
var assignments: Dictionary = {}
var combat_until: Dictionary = {}

static func combat_active(unit: Dictionary, members: Array = []) -> bool:
	if unit.get("combat_active",false): return true
	if unit.get("horde_melee", false):
		return true
	var states: Array = [unit]
	states.append_array(members)
	for state in states:
		for raw in state.get("conditions", []):
			var condition := str(raw)
			for token in ["ATTACKING", "FIRING", "PREATTACK", "RELOADING", "USING_WEAPON"]:
				if condition.contains(token):
					return true
	return false

func needs_order(id: int, at: Vector2, goal: Vector2, center: Vector2, frame: int,
		moving: bool, engaged: bool, defend: bool) -> bool:
	var previous: Dictionary = assignments.get(id, {})
	var changed := previous.is_empty() or Vector2(previous.get("goal", goal)).distance_to(goal) > 80.0
	# Hordes can look idle while their individual archers wind up, fire or reload.
	# Do not replace that cycle, even on first assignment or a changed objective.
	if engaged:
		combat_until[id] = frame + 15
	if engaged or frame < int(combat_until.get(id, -1)):
		return false
	if defend and at.distance_to(center) <= 320.0:
		assignments[id] = {"goal": goal, "issued": previous.get("issued", frame), "phase": "guard"}
		return false
	if not changed:
		if defend and previous.get("phase", "travel") == "guard":
			# Leave a broad gap between arrival and pursuit limits to avoid ping-pong.
			if at.distance_to(center) <= 700.0 or frame - int(previous.issued) < 25:
				return false
		else:
			if moving or engaged or at.distance_to(goal) <= 220.0 or frame - int(previous.issued) < 75:
				return false
	assignments[id] = {"goal": goal, "issued": frame, "phase": "travel"}
	return true

static func self_check() -> bool:
	var p = new()
	var c := Vector2.ZERO
	var far := Vector2(1500, 0)
	# A marching or fighting attacker keeps its current order, even after cooldown.
	if not p.needs_order(1, far, c, c, 10, false, false, false): return false
	if p.needs_order(1, far, c, c, 100, true, false, false): return false
	if p.needs_order(1, far, c, c, 100, false, true, false): return false
	# A truly idle distant unit can retry, at most once every 15 game seconds.
	if p.needs_order(1, far, c, c, 110, false, false, false): return false
	if not p.needs_order(1, far, c, c, 120, false, false, false): return false
	if p.needs_order(1, far, c, c, 130, false, false, false): return false
	if p.needs_order(1, Vector2(50, 0), c, c, 200, false, false, false): return false
	# Arriving defenders guard without being dragged back to a precise point.
	if not p.needs_order(2, far, c, c, 10, false, false, true): return false
	if p.needs_order(2, Vector2(200, 0), c, c, 100, false, false, true): return false
	if p.needs_order(2, Vector2(600, 0), c, c, 110, true, true, true): return false
	if not p.needs_order(2, Vector2(750, 0), c, c, 130, true, false, true): return false
	if p.needs_order(2, Vector2(740, 0), c, c, 140, true, false, true): return false
	# A genuinely changed objective can replace an old order.
	if not p.needs_order(1, far, Vector2(500, 0), Vector2(500, 0), 210, true, false, false): return false
	# An idle horde with a firing / reloading member is still in combat.
	for condition in ["FIRING_A", "PREATTACK_A", "RELOADING_A", "BETWEEN_FIRING_SHOTS_A"]:
		if not combat_active({"idle": true}, [{"conditions": [condition]}]): return false
	if combat_active({"conditions": ["MOVING"]}, [{"conditions": ["IDLE"]}]): return false
	# Do not interrupt a volley, including first assignment and short reload gaps.
	if p.needs_order(3, far, c, c, 10, false, true, false): return false
	if p.needs_order(3, far, c, c, 20, false, false, false): return false
	if not p.needs_order(3, far, c, c, 30, false, false, false): return false
	return true
