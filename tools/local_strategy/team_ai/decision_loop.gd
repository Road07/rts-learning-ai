extends RefCounted

var states: Dictionary = {}
var pending: Dictionary = {}
var config: Dictionary
var logbook: RefCounted

func consider(player: int, observation: Dictionary, critical: bool, revision: int, frame: int, delay: int) -> bool:
	var signature = "%d:%d:%d:%d" % [observation.get("army_groups", 0) / 3, observation.get("home_threat_groups", 0), observation.get("visible_enemy_groups", 0) / 3, revision]
	var state: Dictionary = states.get(player, {"phase": "Think", "last": -1000, "signature": "", "due": frame + delay, "lock_until": 0, "expires": 0, "critical": false})
	var changed = signature != str(state.signature)
	var emergency = critical and not bool(state.critical)
	if changed and state.signature != "": state.due = mini(int(state.due), frame + delay)
	if emergency: state.due = frame
	var ready = not pending.has(player) and (emergency or (frame >= int(state.lock_until) and frame >= int(state.due) and frame - int(state.last) >= int(config.min_frames)))
	state.signature = signature
	state.critical = critical
	states[player] = state
	return ready

func sent(player: int, frame: int) -> void:
	pending[player] = frame
	states[player].phase = "Plan"
	states[player].last = frame
	states[player].due = frame + int(config.max_frames)

func accepted(player: int, frame: int, plan: Dictionary) -> void:
	pending.erase(player)
	if not states.has(player): return
	states[player].phase = "Execute"
	states[player].lock_until = frame + int(config.commit_frames)
	states[player].expires = frame + int(config.max_frames)
	logbook.write("intent_accepted", {"player": player, "frame": frame, "intent": plan, "lock_until": states[player].lock_until})

func finished_request(player: int) -> void:
	pending.erase(player)
	if states.has(player): states[player].phase = "Reevaluate"

func trigger(player: int, frame: int) -> void:
	if states.has(player): states[player].due = frame

func clear() -> void:
	states.clear()
	pending.clear()
