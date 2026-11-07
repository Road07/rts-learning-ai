extends Node3D

# Isolated CLI match. The normal game scene/controller is never ticked here.
enum State { LOADING, PLAYING }
var _state=State.LOADING
var _world: Node
var _campaign_flow=null
var _net_host=-1
var _net_join=""
var _lan_mode=""
var _lan_shell_game=false
var _last_game_online=false
var _replay_active=false
var _cli_campaign=""
var _load_file=""
var config: Dictionary={}
var participants: Array=[]
var income_cursors: Dictionary={}
var total_income: Dictionary={}
var driver: Node
var transport: HTTPRequest
var hashes: FileAccess
var boot_us: int=0
var play_us: int=0
var done=false
var decisions=0
var result_code=0
var chain=HashingContext.new()

func _ready() -> void:
	set_process(false)
	boot_us=Time.get_ticks_usec()
	var args=OS.get_cmdline_user_args()
	var path=""
	for i in args.size():
		if args[i]=="--simulation-config" and i+1<args.size(): path=args[i+1]
	if path.is_empty():
		get_tree().change_scene_to_file("res://scenes/game_normal.tscn")
		return
	var parsed=JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary: fail("Invalid simulation config"); return
	config=parsed
	call_deferred("run_session" if config.get("session_mode",false) else "run_match")

func run_session() -> void:
	while true:
		await run_match()
		if result_code!=0:return
		# clear_game_data already released native gameplay references. Replace
		# the entire GameWorld/controller, rather than reusing their match state.
		if is_instance_valid(transport):transport.free()
		if is_instance_valid(driver):driver.free()
		if is_instance_valid(_world):_world.free()
		transport=null;driver=null;_world=null;hashes=null
		var mailbox=str(config.session_command)
		while not FileAccess.file_exists(mailbox):
			await get_tree().create_timer(0.01).timeout
		var next=JSON.parse_string(FileAccess.get_file_as_string(mailbox))
		DirAccess.remove_absolute(mailbox)
		if not next is Dictionary:get_tree().quit(1);return
		if next.get("shutdown",false):get_tree().quit(0);return
		config=next
		participants.clear();income_cursors.clear();total_income.clear()
		decisions=0;done=false;result_code=0;chain=HashingContext.new()
		boot_us=Time.get_ticks_usec();_state=State.LOADING

func fail(message: String) -> void:
	if done: return
	var result={"schema":"rts-headless-match-v1","ok":false,"error":message,"seed":config.get("seed"),"winner":null,"players":[]}
	write_result(result,1)

func write_result(result: Dictionary, code: int) -> void:
	if done: return
	done=true
	result["exit_code"]=code
	result_code=code
	result["persistent_session"]=config.get("session_mode",false)
	if hashes!=null: hashes.close()
	if driver!=null: driver.diagnostics.close_session()
	# Match the normal game's quit path: release LiveFX while its FXPlayer
	# child still exists. SceneTree destruction frees children before the
	# native GameWorld destructor, leaving LiveFX's playback reference dangling.
	if is_instance_valid(_world):
		var cleanup: Dictionary=_world.clear_game_data(false)
		result["teardown"]=cleanup
		if code==0 and not cleanup.get("ok",false):
			code=1
			result["ok"]=false
			result["error"]="Match teardown failed: "+str(cleanup.get("error","unknown"))
	result["exit_code"]=code
	var target=str(config.get("out",""))
	result_code=code
	if target.is_empty(): printerr(JSON.stringify(result)); get_tree().quit(1); return
	var file=FileAccess.open(target+".tmp",FileAccess.WRITE)
	if file==null: printerr("Cannot write result: ",target); get_tree().quit(1); return
	file.store_string(JSON.stringify(result,"  "));file.close()
	if DirAccess.rename_absolute(target+".tmp",target)!=OK: printerr("Cannot publish result"); get_tree().quit(1); return
	print("MATCH_RESULT ",target," exit=",code)
	if not config.get("session_mode",false) or code!=0:get_tree().quit(code)

func run_match() -> void:
	Engine.time_scale=1.0 # native logic step is authoritative; never scale it twice.
	Engine.max_fps=0
	if DisplayServer.get_name()!="headless": DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	var fs=ClassDB.instantiate("RetailFileSystem")
	var mounted: Dictionary=fs.mount_retail_paths(str(config.rotwk),str(config.bfme2))
	if not mounted.get("ok",false): fail("Retail mount failed: "+str(mounted)); return
	var regex=RegEx.new()
	regex.compile("(?m)^PlayerTemplate\\s+(\\w+)")
	var names: Array=[]
	for found in regex.search_all(fs.read_file("data/ini/playertemplate.ini").get_string_from_utf8()): names.append(found.get_string(1))
	config["templates"]={}
	for faction in config.factions+["FactionMen"]:
		if not names.has(faction): fail("Unknown installed faction: "+str(faction));return
		config.templates[faction]=names.find(faction)
	_world=ClassDB.instantiate("GameWorld")
	if not _world.setup(fs).get("ok",false): fail("World setup failed"); return
	_world.set_auto_advance(false)
	var slots: Array=[]
	for i in 8:
		var active: bool=i<config.factions.size()
		slots.append({"state":int(config.get("native_slot_state",5)) if active else 1,"name":"Sim%d"%i,"color":i if active else -1,"start_pos":config.positions[i] if active else -1,"player_template":int(config.templates[config.factions[i]]) if active else int(config.templates.FactionMen),"team":config.teams[i] if active else -1})
	var spec={"mode":"skirmish","map":config.map,"map_crc":0,"map_size":0,"seed":int(config.seed),"starting_cash":1000,"slots":slots,"rules":[0,0,0,100,1000,0,-1,-1,-1,-1]}
	var prepared: Dictionary=_world.prepare_new_game(spec)
	if not prepared.get("ok",false): fail("Prepare failed: "+str(prepared)); return
	var started: Dictionary=_world.start_new_game({"test_hooks":false,"logic_thread":false})
	if not started.get("ok",false): fail("Start failed: "+str(started)); return
	add_child(_world)
	_world.set_auto_advance(false)
	_world.set_logic_thread(false)
	for p in _world.get_economy().get("players",[]):
		if not p.get("playable",false): continue
		var n: int=participants.size()
		if n>=config.factions.size(): fail("Unexpected player count"); return
		participants.append({"player":int(p.index),"name":str(p.name),"faction":str(p.faction),"team":config.teams[n],"controller":config.controllers[n]})
		income_cursors[int(p.index)]=int(_world.strategy_reward_observation(int(p.index),-1).get("income_cursor",0))
		total_income[int(p.index)]=0
	if participants.size()!=config.factions.size(): fail("Missing playable players"); return
	if not bool(config.headless): make_camera()
	if "model" in config.controllers:
		var script=load("res://scripts/general_strategy.gd")
		if script==null or not script.can_instantiate(): fail("Model controller unavailable"); return
		driver=script.new();add_child(driver)
		driver.game=self
		driver.diagnostics.open_session()
		driver.team_ai.mapper.logbook=driver.diagnostics
		driver.team_ai.mapper.sequence.logbook=driver.diagnostics
		transport=HTTPRequest.new();transport.use_threads=true;transport.timeout=float(config.get("controller_timeout",300)) if config.get("gymnasium",false) else 30;transport.max_redirects=0;add_child(transport)
		for p in participants:
			if p.controller=="model" and not _world.strategy_model_control(p.player,true).get("ok",false): fail("Model authority refused"); return
	_state=State.PLAYING
	hashes=FileAccess.open(str(config.out)+".hashes.jsonl",FileAccess.WRITE)
	if hashes==null: fail("Cannot open state hashes"); return
	chain.start(HashingContext.HASH_SHA256)
	var initial_frame: int=int(_world.get_frame())
	var frame_budget: int=int(config.frames)
	play_us=Time.get_ticks_usec()
	for step in frame_budget:
		var agent_end_reason: String=""
		var before: int=int(_world.get_frame())
		if step%25==0:
			for p in participants:
				if p.controller=="model":
					var ok: bool=await decide(p,before)
					if not ok: return
		_world.advance(0.2)
		var frame: int=int(_world.get_frame())
		if frame!=before+1: fail("Native logic did not advance exactly one frame: "+str([before,frame])); return
		for p in participants:
			var payment: Dictionary=_world.strategy_reward_observation(p.player,int(income_cursors[p.player]))
			if not payment.get("ok",false) or not payment.get("income_complete",false): fail("Incomplete native income history"); return
			total_income[p.player]+=int(payment.income_delta)
			income_cursors[p.player]=int(payment.income_cursor)
			if config.get("gymnasium",false) and p.controller=="model":
				if payment.get("won",false):agent_end_reason="agent_victory"
				elif payment.get("defeated",false):agent_end_reason="agent_defeated"
		var row={"frame":frame,"hash":str(_world.get_state_hash())}
		var line=JSON.stringify(row)
		hashes.store_line(line);chain.update((line+"\n").to_utf8_buffer())
		var victory: Dictionary=_world.get_victory_report()
		if victory.get("single_alliance",false) and not victory.get("events",[]).filter(func(e): return e.kind=="alliance_victory").is_empty():
			finish_match(initial_frame,"victory");return
		if not agent_end_reason.is_empty():finish_match(initial_frame,agent_end_reason);return
		# Only pacing varies. Every speed executes the SAME 0.2 s native steps.
		var due: int=play_us+int(float(step+1)*200000.0/float(config.time_scale))
		while Time.get_ticks_usec()<due:
			OS.delay_usec(mini(10000,maxi(1,due-Time.get_ticks_usec())))
			await get_tree().process_frame
		await get_tree().process_frame
	finish_match(initial_frame,"duration")

func decide(player: Dictionary, frame: int) -> bool:
	var obs: Dictionary=_world.strategy_observation(player.player)
	var spec: Dictionary=driver.options(obs,true)
	var purchases: Array=_world.strategy_model_options(player.player)
	var request={"observation":spec.summary,"candidates":spec.candidates,"production_options":purchases}
	if config.get("gymnasium",false):request["reward_state"]=gym_reward_state()
	var error: int=transport.request(str(config.endpoint),["Content-Type: application/json"],HTTPClient.METHOD_POST,JSON.stringify(request))
	if error!=OK: fail("Inference request could not start");return false
	var response: Array=await transport.request_completed
	if int(response[0])!=HTTPRequest.RESULT_SUCCESS or int(response[1])!=200: fail("Inference failed: "+str(response.slice(0,2)));return false
	var outer=JSON.parse_string(response[3].get_string_from_utf8())
	if not outer is Dictionary or not outer.get("done",false): fail("Malformed inference reply");return false
	var answer=JSON.parse_string(str(outer.get("message",{}).get("content","")))
	if not answer is Dictionary or not spec.candidates.any(func(c): return c.id==answer.get("candidate_id","")) or not (["none"]+purchases.map(func(c): return c.id)).has(answer.get("production_id","none")):
		fail("Inference selected an illegal candidate");return false
	driver.pending={"epoch":driver.epoch,"sequence":decisions+1,"player":player.player,"observed_frame":frame,"options":spec.candidates,"production_options":purchases}
	driver.response(HTTPRequest.RESULT_SUCCESS,200,PackedStringArray(),response[3])
	decisions+=1
	return true

func gym_reward_state() -> Dictionary:
	# Privileged scalar truth is a sibling of the policy packet, never an input
	# to options(), EntityCodec, the observation vector, or the action candidates.
	var truth: Dictionary=_world.gym_reward_state()
	if not truth.get("ok",false):return truth
	var rows: Array=[]
	for p in participants:
		var found: Array=truth.players.filter(func(row):return int(row.player)==int(p.player))
		if found.size()!=1:return {"ok":false,"error":"missing reward player"}
		var row: Dictionary=found[0].duplicate(true)
		row["team"]=p.team
		row["total_income"]=int(total_income[p.player])
		rows.append(row)
	return {"ok":true,"schema":"gym-reward-state-v1","frame":int(_world.get_frame()),"players":rows}

func finish_match(initial_frame: int, reason: String) -> void:
	var players: Array=[]
	var winner=null
	var economy: Array=_world.get_economy().get("players",[])
	for p in participants:
		var score: Dictionary=_world.strategy_reward_observation(p.player,-1)
		var current: Array=economy.filter(func(e): return int(e.index)==int(p.player))
		var obs: Dictionary=_world.strategy_observation(p.player)
		var own: Array=preload("res://scripts/team_ai/contracts.gd").objects(obs,"self")
		if not score.get("ok",false) or current.is_empty(): fail("Final statistics unavailable");return
		if score.get("won",false): winner=p.team
		players.append({"player":p.player,"faction":p.faction,"team":p.team,"controller":p.controller,"total_income":int(total_income[p.player]),"building_count":own.filter(func(o): return o.get("structure",false)).size(),"unit_count":own.filter(func(o): return o.get("mobile",false) and not o.get("structure",false)).size(),"units_lost":int(score.own_units_lost),"units_killed":int(score.enemy_units),"buildings_lost":int(score.own_structures_lost),"buildings_killed":int(score.enemy_structures)})
	var result={"schema":"rts-headless-match-v1","ok":true,"winner":winner,"end_reason":reason,"duration_seconds":float(int(_world.get_frame())-initial_frame)/5.0,"requested_duration_seconds":float(config.frames)/5.0,"seed":config.seed,"map":config.map,"factions":config.factions,"time_scale":config.time_scale,"headless":DisplayServer.get_name()=="headless","logic_frames":int(_world.get_frame())-initial_frame,"initial_frame":initial_frame,"final_frame":int(_world.get_frame()),"state_hash":str(_world.get_state_hash()),"state_hash_chain_sha256":chain.finish().hex_encode(),"simulation_wall_seconds":float(Time.get_ticks_usec()-play_us)/1000000.0,"engine_wall_seconds":float(Time.get_ticks_usec()-boot_us)/1000000.0,"players":players,"model_decisions":decisions,"godot_version":Engine.get_version_info().string,"input_enabled":false,"audio_enabled":false,"ui_enabled":false,"test_hooks":false}
	if config.get("gymnasium",false):
		var reward_truth: Dictionary=gym_reward_state()
		result["gym_reward_state"]=reward_truth
		for p in participants:
			if p.controller!="model":continue
			var native: Dictionary=_world.strategy_observation(p.player)
			var spec: Dictionary=driver.options(native,true)
			var status: Dictionary=_world.strategy_reward_observation(p.player,-1)
			result["gym_final"]={"observation":spec.summary,"candidates":spec.candidates,"production_options":_world.strategy_model_options(p.player),"won":status.get("won",false),"defeated":status.get("defeated",false)}
			result.gym_final["reward_state"]=reward_truth
	write_result(result,0)

func make_camera() -> void:
	var census: Dictionary=_world.get_census()
	var camera=Camera3D.new();camera.far=60000;camera.position=Vector3(float(census.extent_x)*0.5,2500,-float(census.extent_y)*0.5+800);add_child(camera);camera.look_at(Vector3(float(census.extent_x)*0.5,0,-float(census.extent_y)*0.5),Vector3.UP);camera.current=true
