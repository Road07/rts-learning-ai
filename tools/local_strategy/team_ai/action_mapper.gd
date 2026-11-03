extends RefCounted

const C = preload("res://scripts/team_ai/contracts.gd")
var logbook: RefCounted
var unit_locks: Dictionary = {}
var sequence = preload("res://scripts/team_ai/replay_sequence.gd").new()

func validate(intent: Dictionary, obs: Dictionary, candidates: Array) -> String:
	var error = C.validate_intent(intent, candidates)
	if not error.is_empty(): return error
	for candidate in candidates:
		if candidate.id == intent.candidate_id and candidate.kind == "attack" and not int(candidate.target) in C.visible_ids(obs): return "attack_target_not_visible"
	return ""

func claim_unit(id: int, player: int, frame: int, ttl: int) -> bool:
	var old: Dictionary = unit_locks.get(id, {})
	if not old.is_empty() and int(old.expires) > frame and int(old.player) != player: return false
	unit_locks[id] = {"player": player, "expires": frame + ttl}
	return true

func prune(frame: int) -> void:
	for id in unit_locks.keys():
		if int(unit_locks[id].expires) <= frame: unit_locks.erase(id)

func owned_group(ids: Array, player: int, obs: Dictionary) -> Array:
	if int(obs.get("player_index", -1)) != player: return []
	var owned = C.objects(obs, "self").map(func(o): return int(o.id))
	return ids.filter(func(id): return int(id) in owned)

func move(world: Node, player: int, ids: Array, point: Vector2, mode: String, obs: Dictionary, sequence_scout: bool = false) -> Dictionary:
	var group = owned_group(ids, player, obs)
	if group.size() != ids.size() or group.is_empty() or mode not in ["move", "attack"] or not is_finite(point.x) or not is_finite(point.y):
		return {"ok": false, "error": "invalid_owned_move"}
	var selected_mode=mode
	if obs.has("classic_opening") and sequence_scout and mode=="attack": selected_mode=sequence.scout_mode(player,group,point,obs,int(obs.observed_frame))
	var result: Dictionary = world.order_move(group, point.x, point.y, {"type": selected_mode, "player": player})
	if obs.has("classic_opening"):
		if result.get("ok",false) and selected_mode!=mode:
			logbook.write("replay_sequence_applied",{"player":player,"frame":obs.observed_frame,"units":group,"model":sequence.model_name,"from":mode,"to":selected_mode,"scope":"safe_scout_travel","result":result})
		sequence.record(player,selected_mode,int(obs.observed_frame),result)
	result["sequence_mode"]=selected_mode
	return result

func attack(world: Node, player: int, ids: Array, target: int, obs: Dictionary) -> Dictionary:
	var group = owned_group(ids, player, obs)
	if group.size() != ids.size() or group.is_empty() or target not in C.visible_ids(obs): return {"ok": false, "error": "unowned_or_unobserved_attack"}
	var result: Dictionary = world.order_attack(group, target)
	if obs.has("classic_opening"): sequence.record(player,"attack",int(obs.observed_frame),result)
	return result

func formation(world: Node, player: int, id: int, obs: Dictionary) -> Dictionary:
	if owned_group([id], player, obs).is_empty(): return {"ok": false, "error": "unowned_formation"}
	var state: Dictionary = world.get_object(id)
	if str(state.get("horde_next_formation", "")).is_empty(): return {"ok": false, "error": "formation_unavailable"}
	var result: Dictionary = world.order_toggle_formation(id)
	if obs.has("classic_opening"): sequence.record(player,"formation",int(obs.observed_frame),result)
	return result
