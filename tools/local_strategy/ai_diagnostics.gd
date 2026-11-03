extends RefCounted

# Local JSONL telemetry: urgent markers flush immediately; routine records batch
# for at most one second / 128 records to avoid synchronous IO on every AI event.
# Split large sessions into 8 MiB segments. No game state is modified here.
var file: FileAccess
var folder := ""
var session := ""
var part := 0
var phase := -1
var last_sample := -1
var tracked: Dictionary = {}
var records := 0
var pending_records = 0
var last_flush_ms = 0

func open_session() -> void:
	folder = OS.get_executable_path().get_base_dir().path_join("logs")
	if DirAccess.make_dir_recursive_absolute(folder) != OK:
		push_error("AI_DIAG could not create local logs folder")
		return
	session = Time.get_datetime_string_from_system().replace(":", "-") + "-" + str(OS.get_process_id())
	open_part()
	write("session_start", {"mod": "rescue-v4", "build": "v0.4.12-nightly.261024200", "mode": "scripted_local_test", "model_controls_game": false})
	print("AI_DIAG local session ", session)

func open_part() -> void:
	file = FileAccess.open(folder.path_join(session + "-%02d.jsonl" % part), FileAccess.WRITE)
	if file == null:
		push_error("AI_DIAG could not open local log file")
	pending_records=0
	last_flush_ms=Time.get_ticks_msec()

func write(event: String, data: Dictionary = {}) -> void:
	if file == null:
		return
	if file.get_position() >= 8 * 1024 * 1024:
		file.close()
		part += 1
		open_part()
		if file == null: return
	var row := {"schema": 1, "session": session, "event": event, "elapsed_ms": Time.get_ticks_msec(), "data": json_safe(data)}
	file.store_line(JSON.stringify(row))
	pending_records+=1
	var now=Time.get_ticks_msec()
	if event in ["user_marker","session_start","session_end","order_refused","hero_retreat"] or pending_records>=128 or now-last_flush_ms>=1000:
		file.flush()
		pending_records=0
		last_flush_ms=now
	records += 1

static func json_safe(value: Variant) -> Variant:
	if value is Vector2: return {"x": value.x, "y": value.y}
	if value is Vector3: return {"x": value.x, "y": value.y, "z": value.z}
	if value is float and not is_finite(value): return null
	if value is Array: return value.map(func(item): return json_safe(item))
	if value is Dictionary:
		var result: Dictionary = {}
		for key in value: result[str(key)] = json_safe(value[key])
		return result
	return value

func phase_changed(value: int, frame: int) -> void:
	if value != phase:
		write("phase_changed", {"from": phase, "to": value, "frame": frame})
		phase = value
		tracked.clear()
		last_sample = -1

func sample(world: Node, players: Array, frame: int, force := false) -> void:
	if not force and last_sample >= 0 and frame - last_sample < 150 and frame >= last_sample:
		return
	last_sample = frame
	var live: Dictionary = {}
	var economies: Array = []
	for p in world.get_economy().get("players", []):
		if p.get("playable", false):
			economies.append({"player": p.index, "faction": p.faction, "money": p.money, "cp_used": p.cp_used, "cp_limit": p.cp_limit})
	write("economy_sample", {"frame": frame, "players": economies})
	for name in players:
		for summary in world.get_player_objects(name):
			if summary.structure or summary.dozer: continue
			var o: Dictionary = world.get_object(int(summary.id))
			if not o.get("selectable", false) or not o.get("has_ai", false) or int(o.get("contained_by", 0)) != 0: continue
			var id := int(summary.id)
			live[id] = true
			var at := Vector2(float(o.get("x", 0)), float(o.get("y", 0)))
			var members: Array = []
			for member in o.get("members", []):
				var state: Dictionary = world.get_object(int(member))
				members.append({"id": member, "conditions": state.get("conditions", []), "health": state.get("health", 0)})
			var engaged: bool = preload("res://scripts/rescue_order_policy.gd").combat_active(o, members)
			var before: Dictionary = tracked.get(id, {"position": at, "since": frame, "warned": -300})
			if engaged or at.distance_to(Vector2(before.position)) > 25.0:
				before.position = at
				before.since = frame
			if o.get("moving", false) and not engaged and frame - int(before.since) >= 150 and frame - int(before.warned) >= 300:
				write("possible_stuck", {"frame": frame, "unit": id, "template": o.template, "x": at.x, "y": at.y, "stationary_frames": frame - int(before.since)})
				before.warned = frame
			tracked[id] = before
			write("unit_sample", {"frame": frame, "unit": id, "template": o.template, "x": at.x, "y": at.y, "moving": o.get("moving", false), "idle": o.get("idle", false), "combat": engaged, "conditions": o.get("conditions", []), "member_count": members.size(), "member_sample": members.slice(0, 3)})
	for id in tracked.keys():
		if not live.has(id): tracked.erase(id)

func close_session() -> void:
	write("session_end", {"records": records})
	if file != null:
		file.close()
		file = null
