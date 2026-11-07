extends Node3D

# A real local 3v3 start with the production/controller code from the current source.
# Fixture creation is outside the AI observation path. Only normal filtered snapshots
# reach the controller. The spectator's camera does not grant sight to the bots.
enum State { LOADING, PLAYING }
var _state = State.LOADING
var _world: Node
var _local_name = "ReplayObserver"
var _campaign_flow = null
var _net_host = -1
var _net_join = ""
var _lan_mode = ""
var _lan_shell_game = false
var _last_game_online = false
var _replay_active = false
var _cli_campaign = ""
var _load_file = ""
var config: Dictionary
var stage = "opening"
var case_name = "baseline"
var model = "off"
var seconds = 6.0
var sim_frames = 0
var sim_start = -1
var speed = 4.0
var view = false
var report_path = ""
var driver: Node
var participants: Array = []
var fixtures: Array = []
var fixture_cp_adjustments: Array = []
var errors: Array = []
var started = 0
var finished = false
var initial: Array = []
var camera: Camera3D
var title: Label
var focus = Vector2.ZERO
var camera_height = 1800.0
var paused = false
var screenshot_path = ""
var capturing = false
var preview_messages: Dictionary = {}
var human_probe: Dictionary = {}
var support_dispatch_validation: Dictionary = {}
var sequence_validation: Dictionary = {}
var training_initial: Array = []
var training_initial_finance: Dictionary = {}
var training_lease_frame = -100
var training_purchase_receipts: Array = []
var model_access_validation: Dictionary = {}
var mechanics_validation: Dictionary = {}
var cp_validation: Dictionary = {}
var feedback_validation: Dictionary = {}
var headless_training: bool=false
var training_pace_us: int=0
var headless_fast_poll: bool=false
var profile_enabled: bool=false
var profile_advance_us: int=0
var profile_hash_us: int=0
var profile_hash_count: int=0
var profile_hash_stride: int=1
var profile_hashes: FileAccess
var profile_chain=HashingContext.new()

func model_decision_stride() -> int:
	return int(config.get("decision_stride",5)) if headless_training else 5

func is_training_headless() -> bool:
	return headless_training

var benchmark: bool = false
var benchmark_team: int = 1
var benchmark_meter = preload("res://scripts/benchmark_meter.gd").new()

func model_should_control(player: int) -> bool:
	return not benchmark or (training_slot(player)<3 if benchmark_team==1 else training_slot(player)>=3)


func model_fixture_reserved_ids() -> Array:
	if case_name=="learning-feedback": return [int(feedback_validation.get("producer",0)),int(feedback_validation.get("research_producer",0))]
	if case_name!="access" or model_access_validation.is_empty(): return []
	return [int(model_access_validation.get("rider",0)),int(model_access_validation.get("pike",0)),int(model_access_validation.get("thrall",0)),int(model_access_validation.get("ability_source",0))]

func training_verify_purchases() -> void:
	if OS.get_environment("OPENBFME_AI_TRAINING")!="1" or driver==null: return
	var frame: int = int(_world.get_frame())
	for pending in driver.training_pending_purchases.duplicate():
		var operation: Dictionary = pending.operation
		var observation: Dictionary = _world.strategy_observation(int(pending.player))
		var own: Array = preload("res://scripts/team_ai/contracts.gd").objects(observation,"self")
		var new_objects: Array = own.filter(func(o): return str(o.template)==str(operation.template) and int(o.id) not in pending.before_ids)
		if operation.kind=="build": new_objects=new_objects.filter(func(o): return Vector2(o.x,o.y).distance_to(Vector2(operation.x,operation.y))<5)
		var queue: Dictionary = _world.get_production(int(pending.player),int(operation.producer)) if operation.kind=="train" else {}
		var matching: Array = queue.get("queue",[]).filter(func(e): return str(e.get("template",""))==str(operation.template))
		var verified: bool = not new_objects.is_empty() or not matching.is_empty()
		if not verified and frame-int(pending.frame)<25: continue
		var receipt: Dictionary = {"action_id":pending.action_id,"player":pending.player,"kind":operation.kind,"template":operation.template,"frame":frame,"verified":verified,"evidence":"new_owned_object" if not new_objects.is_empty() else "production_queue" if not matching.is_empty() else "not_observed","object_ids":new_objects.map(func(o): return int(o.id)),"completion_proven":not new_objects.is_empty() and bool(new_objects[0].get("complete",true))}
		training_purchase_receipts.append(receipt)
		driver.diagnostics.write("training_purchase_receipt",receipt)
		driver.training_pending_purchases.erase(pending)

func training_control() -> void:
	if OS.get_environment("OPENBFME_AI_TRAINING")!="1": return
	var frame: int = int(_world.get_frame())
	if frame-training_lease_frame<25: return
	training_lease_frame=frame
	for p in participants.slice(0,3).filter(func(player): return not player.get("human",false)):
		require(_world.strategy_training_control(int(p.index),150).get("ok",false),"training purchase lease refused")

func training_finance() -> Dictionary:
	var earned = 0.0
	var military = 0.0
	var money = 0.0
	var economy: Array = _world.get_economy().get("players",[])
	for p in participants.slice(0,3).filter(func(player): return not player.get("human",false)):
		for row in economy:
			if int(row.index)==int(p.index):
				earned+=float(row.earned)
				money+=float(row.money)
		var obs: Dictionary = _world.strategy_observation(int(p.index))
		for object in preload("res://scripts/team_ai/contracts.gd").objects(obs,"self"):
			if not object.get("structure",false): military+=float(object.get("public_cost",0))*float(object.get("health_ratio",1))
	return {"earned":earned,"military_value":military,"money":money}

func training_slot(player: int) -> int:
	for i in participants.size():
		if int(participants[i].index)==player: return i
	return -1

# Training reward reads only each learner's own filtered objects, never enemy state.
# Track initial assets only: newly spawned/recruited objects cannot inflate this score.
func training_assets() -> Array:
	var assets: Array = []
	for p in participants.slice(0,3).filter(func(player): return not player.get("human",false)):
		var obs: Dictionary = _world.strategy_observation(int(p.index))
		for object in preload("res://scripts/team_ai/contracts.gd").objects(obs,"self"):
			if not object.get("complete",true): continue
			assets.append({"player":p.index,"id":object.id,"health":object.get("health_ratio",1.0),"cost":object.get("public_cost",0)})
	return assets

func _ready():
	set_process(false)
	call_deferred("boot")

func require(ok: bool, message: String) -> bool:
	if not ok:
		errors.append(message)
		push_error("ARENA " + message)
	return ok

func fit_fixture_command_points(p: Dictionary) -> void:
	var before: Dictionary = _world.strategy_observation(int(p.index))
	var removed: Array = []
	var candidates: Array = fixtures.filter(func(o): return int(o.player)==int(p.index) and o.get("fixture_role","")=="army")
	candidates.reverse()
	for candidate in candidates:
		var obs: Dictionary = _world.strategy_observation(int(p.index))
		if int(obs.cp_used)<=int(obs.cp_limit): break
		if not require(_world.destroy_object(int(candidate.id)),"cannot trim fixture group: "+str(candidate.template)): return
		_world.advance(0.2)
		removed.append({"id":candidate.id,"template":candidate.template})
		candidate["removed_for_cp_budget"]=true
	var after: Dictionary = _world.strategy_observation(int(p.index))
	if not removed.is_empty():
		fixture_cp_adjustments.append({"fixture":true,"player":p.index,"faction":p.faction,"before_used":before.cp_used,"after_used":after.cp_used,"limit":after.cp_limit,"removed":removed})

func boot():
	var mod_path = ""
	var args = OS.get_cmdline_user_args()
	for i in args.size():
		var arg = str(args[i])
		if arg == "-mod" and i+1<args.size(): mod_path=str(args[i+1])
		if arg.begins_with("--arena-stage="): stage=arg.get_slice("=",1)
		if arg.begins_with("--arena-case="): case_name=arg.get_slice("=",1)
		if arg.begins_with("--arena-model="): model=arg.get_slice("=",1)
		if arg.begins_with("--arena-seconds="): seconds=float(arg.get_slice("=",1))
		if arg.begins_with("--arena-sim-frames="): sim_frames=int(arg.get_slice("=",1))
		if arg.begins_with("--arena-speed="): speed=float(arg.get_slice("=",1))
		if arg.begins_with("--arena-report="): report_path=arg.substr(15)
		if arg=="--arena-view": view=true
		if arg.begins_with("--arena-screenshot="): screenshot_path=arg.substr(19)
	headless_training=args.has("--arena-headless-training")
	headless_fast_poll=headless_training and OS.get_environment("OPENBFME_HEADLESS_FAST_POLL")=="1"
	if headless_fast_poll:
		OS.low_processor_usage_mode=false
		OS.low_processor_usage_mode_sleep_usec=0
		Engine.max_fps=0
	profile_enabled=headless_training and OS.get_environment("OPENBFME_INFERENCE_PROFILE")=="1"
	profile_hash_stride=maxi(1,int(OS.get_environment("OPENBFME_PROFILE_HASH_STRIDE")))
	config=JSON.parse_string(FileAccess.get_file_as_string("res://data/arena.json"))
	benchmark=bool(config.get("benchmark",false))
	benchmark_team=int(config.get("benchmark_team",1))
	var fs=ClassDB.instantiate("RetailFileSystem")
	fs.set_mods(PackedStringArray([mod_path]))
	if not require(fs.mount_retail_paths("D:/Games/RotWK","D:/Games/BFME2").ok,"retail mount failed"): finish(); return
	_world=ClassDB.instantiate("GameWorld")
	if not require(_world.setup(fs).ok,"world setup failed"): finish(); return
	var slots: Array = []
	for i in 8:
		var faction = str(config.slots[i]) if i<6 else "FactionMen"
		slots.append({"state":5 if i<6 else 1,"name":"Arena%d" % (i+1),"color":i if i<6 else -1,"start_pos":i if i<6 else -1,"player_template":int(config.template_indices[faction]),"team":1 if i<3 else 2 if i<6 else -1})
	if case_name=="human-log":
		slots[0].state=6
		_local_name="Arena1"
	config.rules[4]=int(config.stages[stage].cash)
	var prep: Dictionary = _world.prepare_new_game({"mode":"skirmish","map":config.map,"map_crc":0,"map_size":0,"seed":config.seed,"starting_cash":int(config.stages[stage].cash),"slots":slots,"rules":config.rules})
	if not require(prep.get("ok",false),"prepare: "+str(prep.get("errors",[]))): finish(); return
	var loaded: Dictionary = _world.start_new_game({"test_hooks":true,"logic_thread":false})
	if not require(loaded.get("ok",false),"start: "+str(loaded.get("errors",[]))): finish(); return
	add_child(_world)
	_world.set_auto_advance(false)
	_world.set_logic_thread(false)
	for p in _world.get_economy().get("players",[]):
		if not p.get("playable",false): continue
		var obs: Dictionary = _world.strategy_observation(int(p.index))
		var human: bool = case_name=="human-log" and str(p.name)=="Player_1"
		if human: _local_name=str(p.name)
		if not human and not require(obs.get("ok",false),"computer snapshot missing: "+str(p.name)): continue
		var bases: Array = _world.get_player_objects(str(p.name)).filter(func(o): return o.get("commandcenter",false))
		if not require(not bases.is_empty(),"base missing: "+str(p.name)): continue
		participants.append({"index":int(p.index),"name":str(p.name),"faction":str(p.faction),"human":human,"home":Vector2(bases[0].x,bases[0].y)})
	if not require(participants.size()==6,"expected six computer players"): finish(); return
	if OS.get_environment("OPENBFME_MODEL_ONLY")=="1":
		for p in participants:
			if p.get("human",false) or not model_should_control(int(p.index)): continue
			require(_world.strategy_model_control(int(p.index),true).get("ok",false),"model-only authority refused")
	training_control()
	if not benchmark:
		for p in participants: seed_player(p)
	seed_case()
	if not errors.is_empty(): finish(); return
	for i in 3: _world.advance(0.2)
	if case_name=="team" and OS.get_environment("OPENBFME_AI_BACKEND")=="decision_net_v0":
		var owner: Dictionary = participants[0]
		var farms: Array = _world.get_player_objects(owner.name).filter(func(o): return str(o.template)==str(config.factions[owner.faction].farm))
		if not farms.is_empty(): _world.damage_object(int(farms[0].id),float(_world.get_object(int(farms[0].id)).max_health)*2)
		_world.advance(0.2)
	# Focus fixtures add hostile units too: preserve legal command-point headroom.
	for p in ([] if benchmark else participants):
		if p.get("human",false): continue
		var caps: Array = _world.get_economy().get("players",[]).filter(func(row): return int(row.index)==int(p.index))
		for attempt in 6:
			var obs: Dictionary = _world.strategy_observation(p.index)
			if int(obs.cp_used)<=int(obs.cp_limit): break
			if not caps.is_empty() and int(obs.cp_limit)>=int(caps[0].cp_cap): break
			spawn(str(config.factions[p.faction].farm),p,p.home+Vector2(850+attempt*180,-700),true)
			_world.advance(0.2)
		fit_fixture_command_points(p)
	if benchmark: benchmark_meter.start(self,report_path.get_base_dir()+"/benchmark-telemetry.jsonl")
	initial=sample()
	if OS.get_environment("OPENBFME_AI_TRAINING")=="1":
		training_initial=training_assets()
		training_initial_finance=training_finance()
	for player_state in initial:
		require(int(player_state.cp_used)<=int(player_state.cp_limit),"fixture exceeds command-point limit: "+str(player_state.faction))
	if not errors.is_empty(): finish(); return
	if view: make_camera()
	if case_name=="mechanics":
		mechanics_validation=preload("res://scripts/mechanics_checks.gd").run(self)
		if not errors.is_empty(): finish(); return
	if case_name=="cp-accounting":
		var owner: Dictionary=participants[0]
		var before: int=int(_world.strategy_observation(owner.index).cp_used)
		var probe: int=spawn("AngmarThrallMaster",owner,owner.home+Vector2(200,-200))
		cp_validation=_world.debug_command_point_probe(probe)
		require(cp_validation.get("ok",false),"modifier rejection changed command-point accounting")
		_world.damage_object(probe,float(_world.get_object(probe).max_health)*2)
		_world.advance(0.4)
		cp_validation["before_spawn"]=before
		cp_validation["after_death"]=int(_world.strategy_observation(owner.index).cp_used)
		require(cp_validation.after_death==before,"test unit death did not restore command points")
		if not errors.is_empty(): finish(); return
	if case_name=="learning-feedback":
		feedback_validation=preload("res://scripts/learning_feedback_checks.gd").run(self)
		if not errors.is_empty(): finish(); return
	var human_logger=load("res://scripts/human_training_log.gd")
	if not require(human_logger!=null and human_logger.can_instantiate(),"human logger failed to compile"): finish(); return
	var controller=load("res://scripts/general_strategy.gd")
	if not require(controller!=null and controller.can_instantiate(),"controller failed to compile"): finish(); return
	driver=controller.new()
	add_child(driver)
	driver.setup(self)
	if case_name=="team" and OS.get_environment("OPENBFME_AI_BACKEND")=="decision_net_v0" and OS.get_environment("OPENBFME_MODEL_ONLY")!="1":
		support_dispatch_validation=preload("res://scripts/support_dispatch_checks.gd").run(driver.diagnostics)
		for key in support_dispatch_validation: require(bool(support_dispatch_validation[key]),"support dispatch: "+str(key))
		if not errors.is_empty(): finish(); return
	if case_name=="counters" and OS.get_environment("OPENBFME_MODEL_ONLY")!="1":
		for failure in preload("res://scripts/arena_competitive_checks.gd").run(driver.diagnostics): require(false,str(failure))
		if not errors.is_empty(): finish(); return
	_state=State.PLAYING
	if case_name=="sequence":
		driver.tick()
		seed_sequence_history()
		# The fixture needs one fresh inference on its seeded prefix; ordinary
		# commitment request suppression must still apply in real matches.
		driver.http.cancel_request()
		if not driver.pending.is_empty(): driver.team_ai.loop.finished_request(int(driver.pending.player))
		driver.pending.clear()
		var fixture_player: Dictionary = participants[0]
		driver.request_plan({"index":fixture_player.index,"faction":fixture_player.faction,"name":fixture_player.name},int(_world.get_frame()))
	if case_name=="production":
		driver.tick()
		var fixture_player: Dictionary = participants[0]
		# Explicit arena fixture: fresh idle real factory, native legal-option query.
		var producer=spawn("DwarfBarracks",fixture_player,fixture_player.home+Vector2(-650,-550),true)
		var options: Array=_world.strategy_production_options(int(fixture_player.index),true).filter(func(o): return int(o.producer)==producer)
		require(options.size()>=2,"production fixture lacks two legal recruit options")
		driver.diagnostics.write("production_options_fixture",{"fixture":true,"producer":producer,"options":options})
		driver.http.cancel_request()
		if not driver.pending.is_empty(): driver.team_ai.loop.finished_request(int(driver.pending.player))
		driver.pending.clear()
		driver.team_ai.observations[fixture_player.index]=_world.strategy_observation(int(fixture_player.index))
		driver.spec_cache.erase(fixture_player.index)
		driver.request_plan({"index":fixture_player.index,"faction":fixture_player.faction,"name":fixture_player.name},int(_world.get_frame()))
	if case_name=="human-log":
		driver.tick() # enable capture before the normal player commands below
		issue_human_probe()
	started=-1 # first scene/asset frame is warmup, outside the runtime timer
	set_process(true)
	print("ARENA_READY ",stage," ",case_name," players=",participants.size()," fixture_objects=",fixtures.size())

func spawn(template: String, p: Dictionary, at: Vector2, building: bool = false) -> int:
	var census: Dictionary = _world.get_census()
	at=Vector2(clampf(at.x,150,float(census.extent_x)-150),clampf(at.y,150,float(census.extent_y)-150))
	var id: int = _world.create_object(template,int(p.index),at.x,at.y,0)
	if not require(id>0 and _world.get_object(id).get("ok",false),"spawn failed: "+template): return 0
	if building: require(_world.debug_build_complete(id).get("ok",false),"completion refused: "+template)
	fixtures.append({"id":id,"player":p.index,"template":template,"building":building})
	return id

func seed_player(p: Dictionary):
	var settings: Dictionary = config.stages[stage]
	var faction: Dictionary = config.factions[p.faction]
	var home: Vector2 = p.home
	for i in int(settings.farms):
		var angle = TAU*float(i)/maxf(1,float(settings.farms))
		spawn(str(faction.farm),p,home+Vector2(cos(angle),sin(angle))*(700 if i%2==0 else 1000),true)
	if stage=="opening": return
	for i in faction.factories.size():
		spawn(str(faction.factories[i]),p,home+Vector2(-400+i*350,450),true)
	for i in int(settings.groups):
		var template = str(faction.units[i%faction.units.size()])
		var group: int = spawn(template,p,home+Vector2(-240+(i%5)*100,-250-int(i/5)*130))
		if group>0: fixtures[-1]["fixture_role"]="army"
	for i in int(settings.heroes):
		var id = spawn(str(faction.heroes[i]),p,home+Vector2(200+i*100,-450))
		if id>0: _world.gain_hero_levels(id,int(settings.hero_levels))
	if int(settings.siege)>0: spawn(str(faction.siege),p,home+Vector2(-300,-500))
	# Actual normal research orders remain available; this fixture does not pretend
	# that arbitrary spawned units have weapon/armour upgrades or spellbook points.

func seed_case():
	var own: Dictionary = participants[0]
	var enemy: Dictionary = participants[3]
	var at: Vector2 = own.home
	if case_name=="access":
		require(OS.get_environment("OPENBFME_MODEL_ONLY")=="1","access fixture requires model-only host")
		if errors.is_empty(): model_access_validation=preload("res://scripts/model_access_checks.gd").prepare(self)
	if case_name=="human-log":
		human_probe={"player":own.index,"visible":spawn("GoblinFighterHorde",enemy,at+Vector2(250,150)),"hidden":spawn("GondorKnightHorde",enemy,enemy.home+Vector2(0,-200))}
	if case_name in ["pressure","team","counters"]:
		for i in 3: spawn("GondorKnightHorde" if case_name=="counters" else "GoblinFighterHorde",enemy,at+Vector2(700,i*90))
	if case_name=="hero":
		var existing: Array = _world.get_player_objects(own.name).filter(func(o): return o.template=="DwarvenGloin")
		var id: int = int(existing[0].id) if not existing.is_empty() else spawn("DwarvenGloin",own,at+Vector2(700,0))
		if id>0: _world.damage_object(id,float(_world.get_object(id).max_health)*0.85)
	if case_name=="siege":
		spawn("GondorTrebuchet",own,at+Vector2(250,0))
		spawn("MordorOrcPit",enemy,at+Vector2(1200,0),true)
	if case_name=="tunnels":
		for p in participants:
			if p.faction not in ["FactionDwarves","FactionWild"]: continue
			var exit_at: Vector2 = participants[2].home+Vector2(-500,0)
			spawn(str(config.factions[p.faction].farm),p,p.home+Vector2(-300,0),true)
			spawn(str(config.factions[p.faction].farm),p,exit_at,true)
			spawn(str(config.factions[p.faction].units[0]),p,p.home+Vector2(-250,0))

func sample() -> Array:
	var result: Array = []
	for p in participants:
		var obs: Dictionary = _world.strategy_observation(p.index)
		if p.get("human",false):
			var economy: Array = _world.get_economy().get("players",[]).filter(func(e): return int(e.index)==int(p.index))
			var human_objects: Array = _world.get_player_objects(p.name)
			result.append({"player":p.index,"faction":p.faction,"money":economy[0].money,"cp_used":economy[0].cp_used,"cp_limit":economy[0].cp_limit,"groups":human_objects.filter(func(o): return not o.structure).size(),"buildings":human_objects.filter(func(o): return o.structure).size()})
			continue
		var own: Array = preload("res://scripts/team_ai/contracts.gd").objects(obs,"self")
		result.append({"player":p.index,"faction":p.faction,"money":obs.get("money",0),"cp_used":obs.get("cp_used",0),"cp_limit":obs.get("cp_limit",0),"groups":own.filter(func(o): return not o.structure).size(),"buildings":own.filter(func(o): return o.structure).size(),"farms_lost":obs.get("players",[]).filter(func(o): return o.relation=="self").map(func(o): return o.get("farms_lost",0)),"visible_enemies":preload("res://scripts/team_ai/contracts.gd").objects(obs,"enemy").size(),"queued_entries":_world.get_player_objects(p.name).filter(func(o): return o.structure).map(func(o): return _world.get_production(p.index,int(o.id)))})
	return result

func issue_human_probe():
	var p: Dictionary = participants[0]
	var own: Array = _world.get_player_objects(p.name)
	var factories: Array = own.filter(func(o): return str(o.template)==str(config.factions[p.faction].factories[0]))
	var units: Array = own.filter(func(o): return not o.structure and not o.get("dozer",false))
	if not require(not factories.is_empty() and not units.is_empty(),"human logging probe needs middle-stage factory/army"): return
	var unit_template = str(config.factions[p.faction].units[0])
	human_probe["producer"]=int(factories[0].id)
	human_probe["template"]=unit_template
	_world.queue_unit(int(p.index),int(factories[0].id),unit_template,false)
	_world.cancel_unit(int(p.index),int(factories[0].id),unit_template,false)
	_world.order_move([int(units[0].id)],p.home.x+100,p.home.y-100,{"type":"move","player":int(p.index)})
	driver.human_log.marker(_world.get_frame())

func _process(delta):
	if finished: return
	if headless_training:
		headless_training_step()
		return
	if case_name=="sequence" and sequence_validation.is_empty(): probe_sequence()
	if not paused:
		training_control()
		var first_step: bool=sim_start<0
		if first_step: sim_start=int(_world.get_frame())
		var step: float=minf(delta,0.1)*speed
		if sim_frames>0:
			step=minf(0.2 if first_step else step,float(sim_start+sim_frames-int(_world.get_frame()))/5.0)
		_world.advance(maxf(0.0,step))
		driver.tick()
		if benchmark:
			benchmark_meter.poll(self)
			if bool(_world.get_victory_report().get("single_alliance",false)): finish(); return
		training_verify_purchases()
		if case_name=="access": preload("res://scripts/model_access_checks.gd").poll(self,model_access_validation)
		if sim_frames>0 and int(_world.get_frame())>=sim_start+sim_frames: finish(); return
	if started<0:
		started=Time.get_ticks_msec()
		return
	if view:
		if not screenshot_path.is_empty():
			for player in participants:
				for message in driver.team_ai.bus.history(int(player.index)):
					if preview_messages.has(message.id): continue
					preview_messages[message.id]=true
					var faction=str(driver.team_ai.observations.get(int(message.from),{}).get("faction","Ally"))
					driver.hud.add_message(message,faction,driver.team_ai.bus.text(message),_world.get_frame())
		var movement=Vector2(float(Input.is_key_pressed(KEY_D))-float(Input.is_key_pressed(KEY_A)),float(Input.is_key_pressed(KEY_S))-float(Input.is_key_pressed(KEY_W)))
		focus+=movement*delta*camera_height
		camera.position=Vector3(focus.x,camera_height,-focus.y+camera_height*0.5)
		camera.look_at(Vector3(focus.x,0,-focus.y),Vector3.UP)
		title.text="AI TEST SAHASI | %s | %s | kare %d | x%.1f\nWASD: kamera  Tekerlek: yakınlaş  Space: duraklat  Esc: rapor ve çıkış" % [config.stages[stage].label,case_name,_world.get_frame(),speed]
		if not screenshot_path.is_empty() and not capturing and Time.get_ticks_msec()-started>=int(seconds*1000):
			capturing=true
			capture_preview()
	elif sim_frames<=0 and Time.get_ticks_msec()-started>=int(seconds*1000): finish()


func headless_training_step() -> void:
	if sim_start<0:
		sim_start=int(_world.get_frame())
		training_pace_us=Time.get_ticks_usec()
		if profile_enabled:
			profile_hashes=FileAccess.open(report_path+".hashes.jsonl",FileAccess.WRITE)
			profile_chain.start(HashingContext.HASH_SHA256)
			if not require(profile_hashes!=null,"profile hash file unavailable"): finish();return
	# Async HTTP transport runs normally, but native time is held until the
	# response is applied. No stochastic action is dropped because of speed.
	if not driver.pending.is_empty():
		if headless_fast_poll:OS.delay_usec(500)
		return
	driver.tick()
	if not driver.pending.is_empty(): return
	var frame: int=int(_world.get_frame())
	var due: int=training_pace_us+int(float(frame-sim_start)*200000.0/speed)
	if Time.get_ticks_usec()<due:
		OS.delay_usec(mini(1000,due-Time.get_ticks_usec()))
		return
	training_control()
	var advance_started: int=Time.get_ticks_usec()
	_world.advance(0.2)
	profile_advance_us+=Time.get_ticks_usec()-advance_started
	if profile_enabled and ((int(_world.get_frame())-sim_start)%profile_hash_stride==0 or int(_world.get_frame())>=sim_start+sim_frames):
		var hash_started: int=Time.get_ticks_usec()
		var line=JSON.stringify({"frame":int(_world.get_frame()),"hash":str(_world.get_state_hash())})
		profile_hashes.store_line(line)
		profile_chain.update((line+"\n").to_utf8_buffer())
		profile_hash_us+=Time.get_ticks_usec()-hash_started
		profile_hash_count+=1
	if not require(int(_world.get_frame())==frame+1,"headless step did not advance exactly one frame"): finish();return
	training_verify_purchases()
	var victory: Dictionary=_world.get_victory_report()
	if victory.get("single_alliance",false) and not victory.get("events",[]).filter(func(e): return e.kind=="alliance_victory").is_empty(): finish();return
	if int(_world.get_frame())>=sim_start+sim_frames: finish()

func capture_preview():
	await RenderingServer.frame_post_draw
	var preview=get_viewport().get_texture().get_image()
	require(preview.save_png(screenshot_path)==OK,"screenshot save failed")
	finish()

func make_camera():
	focus=participants[0].home
	camera=Camera3D.new()
	camera.far=60000
	camera.current=true
	add_child(camera)
	var env=WorldEnvironment.new()
	var settings=Environment.new()
	settings.background_mode=Environment.BG_COLOR
	settings.background_color=Color(0.15,0.18,0.2)
	settings.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
	settings.ambient_light_color=Color(0.8,0.8,0.8)
	env.environment=settings
	add_child(env)
	var layer=CanvasLayer.new()
	add_child(layer)
	title=Label.new()
	title.position=Vector2(15,15)
	layer.add_child(title)
	_world.set_shroud_drawn(false) # spectator presentation only

func _unhandled_input(event):
	if event is InputEventKey and event.pressed:
		if event.keycode==KEY_ESCAPE: finish()
		if event.keycode==KEY_SPACE: paused=not paused
	if event is InputEventMouseButton and event.pressed:
		if event.button_index==MOUSE_BUTTON_WHEEL_UP: camera_height=maxf(300,camera_height*0.85)
		if event.button_index==MOUSE_BUTTON_WHEEL_DOWN: camera_height=minf(6000,camera_height*1.15)

func seed_sequence_history() -> void:
	# Explicit fixture: eight actual accepted API commands, never invented human history.
	var player: Dictionary = participants[0]
	var obs: Dictionary = _world.strategy_observation(int(player.index))
	var units: Array = preload("res://scripts/team_ai/contracts.gd").objects(obs,"self").filter(func(o): return not o.structure and not o.get("hero",false))
	if not require(not units.is_empty(),"sequence fixture needs a regular group"): return
	var target=Vector2(units[0].x,units[0].y)+Vector2(80,0)
	for i in 8:
		var accepted: Dictionary = driver.team_ai.mapper.move(_world,int(player.index),[int(units[0].id)],target,"move" if i%2==0 else "attack",obs)
		require(accepted.get("ok",false),"sequence fixture command rejected")
	driver.diagnostics.write("sequence_history_fixture",{"fixture":true,"player":player.index,"accepted_commands":8})

func probe_sequence() -> void:
	var player: Dictionary = participants[0]
	var bridge = driver.team_ai.mapper.sequence
	if not bridge.hints.has(int(player.index)): return
	var obs: Dictionary = _world.strategy_observation(int(player.index))
	var units: Array = preload("res://scripts/team_ai/contracts.gd").objects(obs,"self").filter(func(o): return not o.structure and not o.get("hero",false) and not o.get("combat_active",false) and float(o.get("health_ratio",1))>0.8)
	if units.is_empty(): return
	var ids: Array = [int(units[0].id)]
	var goal=Vector2(units[0].x,units[0].y)+Vector2(80,0)
	var frame: int = int(obs.observed_frame)
	var hint: Dictionary = bridge.hints[int(player.index)].duplicate(true)
	var threatened: Dictionary = obs.duplicate(true)
	for owner in threatened.players:
		if owner.relation=="enemy":
			owner.objects.append({"id":990000,"x":units[0].x,"y":units[0].y,"structure":false,"category":0})
			break
	var threat_guard: bool = bridge.scout_mode(int(player.index),ids,goal,threatened,frame)=="attack"
	bridge.hints[int(player.index)].expires=frame-1
	var stale_guard: bool = bridge.scout_mode(int(player.index),ids,goal,obs,frame)=="attack"
	bridge.hints[int(player.index)]=hint
	var result: Dictionary = driver.team_ai.mapper.move(_world,int(player.index),ids,goal,"attack",obs,true)
	sequence_validation={"ok":result.get("ok",false) and result.get("sequence_mode","")=="move" and threat_guard and stale_guard,"fixture":true,"source_model":bridge.model_name,"real_order":result,"nearby_enemy_guard":threat_guard,"stale_hint_guard":stale_guard,"player":player.index,"frame":frame}
	driver.diagnostics.write("sequence_integration_probe",sequence_validation)

func finish():
	if case_name=="sequence": require(sequence_validation.get("ok",false),"sequence prediction did not produce a guarded real order")
	if finished: return
	finished=true
	set_process(false)
	var result={"schema":1,"ok":errors.is_empty(),"stage":stage,"case":case_name,"seed":config.get("seed",0),"model":model,"errors":errors,"fixtures":fixtures,"initial":initial,"scope":"3v3 prepared-state runtime smoke; does not certify behavior or long-match balance; middle/late phase timers compressed only in test mod; no seeded spellbook points or researched unit upgrades"}
	if _world!=null:
		result["frame"]=_world.get_frame()
		if headless_training:result["headless_training"]={"enabled":true,"time_scale":speed,"requested_simulation_seconds":float(sim_frames)/5.0,"simulation_seconds":float(int(_world.get_frame())-sim_start)/5.0,"synchronous_decisions":true,"render_enabled":false,"ui_enabled":false}
		if profile_enabled:
			if profile_hashes!=null:profile_hashes.close()
			result["inference_profile"]={"simulation_wall_seconds":float(Time.get_ticks_usec()-training_pace_us)/1000000.0,"native_advance_seconds":float(profile_advance_us)/1000000.0,"hash_seconds":float(profile_hash_us)/1000000.0,"hash_samples":profile_hash_count,"hash_stride":profile_hash_stride,"fast_poll":headless_fast_poll,"headless_idle_sleep_usec":OS.low_processor_usage_mode_sleep_usec,"godot_max_fps":Engine.max_fps,"state_hash":str(_world.get_state_hash()),"hash_chain_sha256":profile_chain.finish().hex_encode(),"hashes":report_path+".hashes.jsonl"}
		if benchmark:
			benchmark_meter.poll(self,true)
			result["benchmark"]={"schema":"fixed-native-benchmark-v1","model_team":benchmark_team,"model_players":participants.filter(func(p): return model_should_control(int(p.index))).map(func(p): return int(p.index)),"native_players":participants.filter(func(p): return not model_should_control(int(p.index))).map(func(p): return int(p.index)),"victory":_world.get_victory_report(),"telemetry":benchmark_meter.path,"difficulty":"Brutal","fixtures":false}
		result["simulation_window"]={"start":sim_start,"end":int(_world.get_frame()),"budget":sim_frames,"fixed":sim_frames>0}
		result["mechanics_validation"]=mechanics_validation
		result["cp_validation"]=cp_validation
		result["feedback_validation"]=feedback_validation
		result["fixture_cp_adjustments"]=fixture_cp_adjustments
		if participants.size()==6:
			result["final"]=sample()
			result.ok=result.ok and int(result.frame)>3
			var validated=0
			var active_combat=0
			for player in participants:
				var snapshot: Dictionary = _world.strategy_observation(int(player.index))
				for unit in preload("res://scripts/team_ai/contracts.gd").objects(snapshot,"self").filter(func(o): return not o.structure).slice(0,4):
					if not unit.has("combat_active"): continue
					var detail: Dictionary = _world.get_object(int(unit.id))
					var members: Array = []
					for id in detail.get("members",[]): members.append(_world.get_object(int(id)))
					var expected=preload("res://scripts/rescue_order_policy.gd").combat_active(detail,members)
					if expected: active_combat+=1
					if expected!=bool(unit.combat_active):
						errors.append("combat snapshot mismatch: "+str(unit.id))
						result.ok=false
					validated+=1
			result["combat_snapshot_validation"]={"units":validated,"actively_fighting":active_combat}
		result["runtime_report"]=_world.get_report()
		if OS.get_environment("OPENBFME_MODEL_ONLY")=="1":
			var controlled: Array = []
			for p in participants:
				if p.get("human",false): continue
				controlled.append({"player":p.index,"model_only":_world.strategy_observation(int(p.index)).get("model_only_control",false),"expected":model_should_control(int(p.index))})
			result["model_only_validation"]={"players":controlled,"fallbacks":driver.fallbacks if driver!=null else -1}
			for p in controlled: require(bool(p.model_only)==bool(p.expected),"model/native authority mismatch")
		if OS.get_environment("OPENBFME_AI_TRAINING")=="1":
			result["training"]={"reward_version":"bfme-outcome-reward-v3","initial":training_initial,"final":training_assets(),"initial_finance":training_initial_finance,"final_finance":training_finance(),"truncated":true,"terminal_win":false}
	if driver!=null:
		if driver.has_method("reward_final_samples"): result["reward_final_samples"]=driver.reward_final_samples()
		if case_name=="access":
			preload("res://scripts/model_access_checks.gd").poll(self,model_access_validation)
			result["model_access_validation"]=model_access_validation
		training_verify_purchases()
		if OS.get_environment("OPENBFME_AI_TRAINING")=="1":
			result["training_purchase_receipts"]=training_purchase_receipts
			result["training_purchase_pending"]=driver.training_pending_purchases.size()
		result["diagnostic_session"]=driver.diagnostics.session
		if case_name=="sequence": result["sequence_validation"]=sequence_validation
		if not support_dispatch_validation.is_empty(): result["support_dispatch_validation"]=support_dispatch_validation
		if case_name=="human-log" and driver.human_log!=null:
			result["human_log_session"]=driver.human_log.session
			result["human_probe"]=human_probe
		driver.human_log.close("arena_end")
		result["model_decisions"]=driver.decisions
		result["fallbacks"]=driver.fallbacks
		result["orders"]=driver.issued
		result["ai_performance"]=driver.perf.summary()
		driver.http.cancel_request()
		driver.team_ai.shutdown()
		driver.diagnostics.write("arena_end",result)
	result.ok=bool(result.ok) and errors.is_empty()
	if not report_path.is_empty():
		var file=FileAccess.open(report_path,FileAccess.WRITE)
		if file!=null: file.store_string(JSON.stringify(result,"  ")); file.close()
		else: result.ok=false
	print("ARENA_RESULT ",stage," ","PASS" if result.ok else "FAIL")
	get_tree().quit(0 if result.ok else 1)
