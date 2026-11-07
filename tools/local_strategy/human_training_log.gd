extends RefCounted

# Separate human demonstrations. Native records are captured before command
# execution on the logic thread; file IO is batched here on the main thread.
var file: FileAccess
var folder := ""
var session := ""
var part := 0
var match_index := 0
var rows := 0
var last_poll := -1000
var last_flush := 0
var outcome_written := false
var disabled := false
var active_world: Node
var policy_builder: Node

func write_raw(raw: String) -> void:
	if file == null: return
	if raw.contains('"human_policy_snapshot"'):
		var snapshot=JSON.parse_string(raw)
		if snapshot is Dictionary and snapshot.get("event","")=="human_policy_snapshot":
			var observation: Dictionary=snapshot.get("payload",{}).get("observation",{})
			if is_instance_valid(policy_builder) and policy_builder.has_method("options") and observation.get("ok",false) and observation.has("spell_points") and observation.has("map_extent") and int(observation.get("observed_frame",-1))==int(snapshot.get("frame",-2)):
				# Only immutable pre-command observation plus the map's fixed extent;
				# never rebuild dynamic state from the world at record-drain time.
				var spec: Dictionary=policy_builder.options(observation,true)
				spec.summary["decision_frame"]=snapshot.frame
				snapshot["policy_observation"]=spec.summary
				snapshot["tactical_candidates"]=spec.candidates
				snapshot["spend_candidates"]=snapshot.payload.get("spend_candidates",[])
				snapshot["feature_encoding"]="rts-mechanics-v1+bfme-public-rules-v2+native-queue-v1"
				snapshot["game_rules_sha256"]=OS.get_environment("OPENBFME_GAME_RULES_SHA256")
				snapshot["candidate_policy"]=snapshot.payload.get("candidate_policy","unknown")
				snapshot["policy_available"]=true
			else: snapshot["policy_available"]=false
			raw=JSON.stringify(snapshot)
	if file.get_position() >= 8*1024*1024:
		file.close()
		part += 1
		file = FileAccess.open(folder.path_join(session+"-%02d.jsonl" % part), FileAccess.WRITE)
		if file == null:
			disabled = true
			if is_instance_valid(active_world): active_world.human_training_records(false)
			push_error("HUMAN_LOG could not rotate recording")
			return
	file.store_line('{"schema":1,"session":%s,"match":%d,"elapsed_ms":%d,"data":%s}' % [JSON.stringify(session),match_index,Time.get_ticks_msec(),raw])
	rows += 1

func tick(game: Node, permitted: bool) -> void:
	if disabled: return
	var playing: bool = game._state == game.State.PLAYING and is_instance_valid(game._world) and permitted and not OS.get_cmdline_user_args().has("--no-human-training")
	if not playing:
		close("left_match")
		return
	var now := Time.get_ticks_msec()
	if now-last_poll < 250: return
	last_poll = now
	var world: Node = game._world
	if not world.has_method("human_training_records"): return
	if is_instance_valid(active_world) and active_world != world: close("world_changed")
	active_world = world
	var records: PackedStringArray = world.human_training_records(true)
	if file == null and not records.is_empty():
		folder = OS.get_executable_path().get_base_dir().path_join("human-logs")
		if not OS.get_environment("OPENBFME_AI_LOG_ROOT").is_empty(): folder=OS.get_environment("OPENBFME_AI_LOG_ROOT").path_join("human-logs")
		if DirAccess.make_dir_recursive_absolute(folder) != OK:
			disabled = true
			world.human_training_records(false)
			push_error("HUMAN_LOG could not create folder")
			return
		session = Time.get_datetime_string_from_system().replace(":","-")+"-"+str(OS.get_process_id())+"-human"+str(match_index)
		part = 0
		rows = 0
		outcome_written = false
		file = FileAccess.open(folder.path_join(session+"-00.jsonl"),FileAccess.WRITE)
		if file == null:
			disabled = true
			world.human_training_records(false)
			push_error("HUMAN_LOG could not open recording")
			return
		var fixture := false
		for arg in OS.get_cmdline_user_args():
			if str(arg).begins_with("--arena-stage="): fixture = true
		write_raw(JSON.stringify({"event":"human_session_start","map":game.get("_map_key"),"fixture":fixture,"scope":"fresh_local_human","capture":"pre_dispatch","fog":"own_and_living_allied_vision","schema_version":1}))
		var latest = FileAccess.open(folder.path_join("latest.txt"),FileAccess.WRITE)
		if latest != null: latest.store_string(session)
	for record in records: write_raw(record)
	if file != null:
		record_outcome(world)
		if now-last_flush >= 1000:
			file.flush()
			last_flush = now

func marker(frame: int) -> void:
	write_raw(JSON.stringify({"event":"human_review_marker","frame":frame,"label":null}))
	if file != null: file.flush()

func record_outcome(world: Node) -> void:
	if outcome_written: return
	var end: Dictionary = world.get_end_game_state()
	if end.get("ok",false) and (end.get("allied_victory",false) or end.get("allied_defeat",false) or end.get("player_defeat",false)):
		write_raw(JSON.stringify({"event":"human_match_result","frame":end.get("frame",0),"local_player":end.get("local_player",-1),"allied_victory":end.get("allied_victory",false),"allied_defeat":end.get("allied_defeat",false),"player_defeat":end.get("player_defeat",false)}))
		outcome_written = true

func close(reason: String) -> void:
	if is_instance_valid(active_world) and active_world.has_method("human_training_records"):
		if file != null: record_outcome(active_world)
		for record in active_world.human_training_records(false): write_raw(record)
	active_world = null
	if file == null: return
	write_raw(JSON.stringify({"event":"human_session_end","reason":reason,"records":rows,"outcome_recorded":outcome_written}))
	file.flush()
	file.close()
	file = null
	match_index += 1
