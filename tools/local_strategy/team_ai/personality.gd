extends RefCounted

const AXES = ["aggression", "economy", "precision", "risk", "tech"]
var values: Dictionary = {}
var last_adapt: Dictionary = {}
var rngs: Dictionary = {}
var config: Dictionary

func seed_player(player: int, seed_value: int) -> void:
	if values.has(player): return
	var rng = RandomNumberGenerator.new()
	rng.seed = seed_value * 7919 + player * 104729
	rngs[player] = rng
	values[player] = {}
	for axis in AXES: values[player][axis] = rng.randf_range(0.25, 0.75)

func adapt(player: int, situation: Dictionary, frame: int) -> bool:
	if frame - int(last_adapt.get(player, 0)) < int(config.adapt_frames): return false
	last_adapt[player] = frame
	var before: Dictionary = values[player].duplicate()
	var targets = {"aggression": 0.7 if situation.get("advantage", false) else 0.3, "economy": 0.65 if not situation.get("critical", false) else 0.3, "precision": 0.7 if situation.get("critical", false) else 0.5, "risk": 0.3 if situation.get("critical", false) else 0.55, "tech": 0.65 if situation.get("money", 0) > 1500 else 0.4}
	for axis in AXES:
		values[player][axis] = clampf(move_toward(float(before[axis]), float(targets[axis]), float(config.max_step)), float(config.minimum), float(config.maximum))
	return true

func style(player: int) -> int:
	var v: Dictionary = values[player]
	if float(v.aggression) > 0.6 and float(v.risk) > 0.45: return 0
	if float(v.aggression) < 0.4 or float(v.risk) < 0.35: return 1
	return 2

func reaction(player: int, minimum: int, maximum: int) -> int:
	return rngs[player].randi_range(minimum, maximum)

func imperfect(player: int, probability: float) -> bool:
	# Isolated controller RNG; never consumes simulation RNG. It may skip optional micro only.
	return rngs[player].randf() < probability
