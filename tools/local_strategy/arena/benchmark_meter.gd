extends RefCounted

# Offline measurement only. Never expose opponent/private telemetry to the policy.
var path: String=""
var file: FileAccess
var last_frame: int=-100
var sensor=preload("res://scripts/team_ai/reward_sensor.gd").new()

func start(arena: Node, output: String) -> void:
	path=output
	file=FileAccess.open(path,FileAccess.WRITE)
	arena.require(file!=null,"benchmark telemetry cannot open")
	poll(arena,true)

func poll(arena: Node, force: bool=false) -> void:
	var frame: int=int(arena._world.get_frame())
	if file==null or frame==last_frame or (not force and frame-last_frame<5): return
	last_frame=frame
	for p in arena.participants:
		var obs: Dictionary=arena._world.strategy_observation(int(p.index))
		if not obs.get("ok",false): continue
		var row: Dictionary=sensor.capture(arena._world,obs)
		file.store_line(JSON.stringify(row))
	file.flush()
