extends "res://scripts/general_strategy_legacy.gd"

# Only observation, bounded legal-choice construction, model transport and command
# execution. No coordinator, playbook, production policy, micro or fallback tick.
const C = preload("res://scripts/team_ai/contracts.gd")
const M = preload("res://scripts/team_ai/mechanics_observation.gd")
var model_controlled: Dictionary = {}
var reward_sensor = preload("res://scripts/team_ai/reward_sensor.gd").new()
var closed_training_matches: Dictionary = {}
var inference_profile: bool=false

func training_match_id() -> String:
	return diagnostics.session+":"+str(epoch)

func setup(owner_game: Node) -> void:
	game=owner_game
	inference_profile=OS.get_environment("OPENBFME_INFERENCE_PROFILE")=="1"
	human_log.policy_builder=self
	diagnostics.open_session()
	perf.logbook=diagnostics
	team_ai.config=JSON.parse_string(FileAccess.get_file_as_string("res://scripts/team_ai/tuning.json"))
	team_ai.mapper.logbook=diagnostics
	team_ai.mapper.sequence.logbook=diagnostics
	http=preload("res://scripts/team_ai/persistent_client.gd").new() if OS.get_environment("OPENBFME_PERSISTENT_HTTP")=="1" else preload("res://scripts/team_ai/model_client.gd").new()
	http.timeout=8
	add_child(http)
	http.request_completed.connect(response)
	if not (game.has_method("is_training_headless") and game.is_training_headless()):
		var layer=CanvasLayer.new()
		add_child(layer)
		hud=preload("res://scripts/team_ai/hud.gd").new()
		layer.add_child(hud)
		label=hud.status_line
	team_ai_ready=true
	get_tree().root.close_requested.connect(func(): human_log.close("window_closed"))
	diagnostics.write("controller_start",{"mode":"model_only","native_brain":false,"scripted_decisions":false,"fallback":false,"command_encoding":"spend-v2"})

func reset() -> void:
	http.cancel_request()
	pending.clear()
	bots.clear()
	plans.clear()
	last_request.clear()
	model_controlled.clear()
	reward_sensor.clear()
	training_pending_purchases.clear()
	next_bot=0
	epoch+=1
	last_frame=-1

func tick() -> void:
	human_log.tick(game,allowed())
	var playing: bool = game._state==game.State.PLAYING and game._world!=null
	if not playing:
		if was_playing:
			reward_final_samples()
			reset()
		was_playing=false
		return
	if not allowed(): return
	var frame: int = int(game._world.get_frame())
	if frame<last_frame: reset()
	var stride: int=int(game.model_decision_stride()) if game.has_method("model_decision_stride") else 5
	if frame-last_frame<stride and last_frame>=0: return
	last_frame=frame
	was_playing=true
	var started=Time.get_ticks_usec()
	if bots.is_empty():
		for player in game._world.get_economy().get("players",[]):
			if not player.get("playable",false): continue
			if game.has_method("model_should_control") and not game.model_should_control(int(player.index)): continue
			var obs: Dictionary = game._world.strategy_observation(int(player.index))
			if not obs.get("ok",false): continue # excludes humans/observers
			var result: Dictionary = game._world.strategy_model_control(int(player.index),true)
			if not result.get("ok",false):
				push_error("MODEL_ONLY native authority refused")
				get_tree().quit(2)
				return
			bots.append({"index":int(player.index),"name":player.name,"faction":player.faction})
			model_controlled[int(player.index)]=true
			reward_sensor.start(game._world,obs)
			diagnostics.write("model_only_authority",{"player":player.index,"frame":frame,"result":result})
	if bots.is_empty(): return
	if pending.is_empty():
		for attempt in bots.size():
			var bot: Dictionary = bots[next_bot%bots.size()]
			next_bot+=1
			if frame-int(last_request.get(bot.index,-1000))<25: continue
			if OS.get_environment("OPENBFME_BATCH_WIRE")=="1":request_same_frame([bot],frame)
			else:request_plan(bot,frame)
			break
	perf.record(frame,float(Time.get_ticks_usec()-started)/1000.0,0,0,0,game._world)

func options(obs: Dictionary, snapshot_only: bool = false) -> Dictionary:
	var own: Array = C.objects(obs,"self")
	var enemies: Array = C.objects(obs,"enemy")
	var army: Array = M.army(own)
	if not snapshot_only and game.has_method("model_fixture_reserved_ids"):
		var reserved: Array = game.model_fixture_reserved_ids()
		army=army.filter(func(o): return int(o.id) not in reserved)
	var bases: Array = own.filter(func(o): return o.get("base",false))
	var home=Vector2.ZERO
	if not bases.is_empty(): home=Vector2(bases[0].x,bases[0].y)
	elif not own.is_empty(): home=Vector2(own[0].x,own[0].y)
	var ids: Array = army.map(func(o): return int(o.id))
	var candidates: Array = [{"id":"defend_wait","kind":"defend","units":[],"target":0,"x":home.x,"y":home.y,"description":"Keep existing orders; issue no new movement command"}]
	if not ids.is_empty():
		candidates.append({"id":"defend_home","kind":"defend","units":ids,"target":0,"x":home.x,"y":home.y,"description":"Move the army home; available own groups %d" % ids.size()})
		for unit in army.slice(0,8):
			candidates.append({"id":"defend_unit_%d" % int(unit.id),"kind":"defend","units":[int(unit.id)],"target":0,"x":home.x,"y":home.y,"description":"Move one owned group home; available own groups 1; health=%.2f" % float(unit.get("health_ratio",1))})
		for enemy in enemies.slice(0,16):
			candidates.append({"id":"attack_%d" % int(enemy.id),"kind":"attack","units":ids,"target":int(enemy.id),"x":enemy.x,"y":enemy.y,"description":"Attack a visible %s; nearby enemy groups %d, available own groups %d readiness=1.00" % ["structure" if enemy.get("structure",false) else "enemy army",enemies.size(),ids.size()]})
		for ally in C.objects(obs,"ally").filter(func(o): return o.get("base",false)):
			candidates.append({"id":"help_%d" % int(ally.id),"kind":"help","units":ids,"target":int(ally.id),"x":ally.x,"y":ally.y,"description":"Move owned army to an allied base; available own groups %d" % ids.size()})
		var extent: Dictionary = obs.get("map_extent",{})
		if extent.is_empty() and not snapshot_only: extent=game._world.get_census()
		for x in [0.2,0.5,0.8]:
			for y in [0.2,0.5,0.8]:
				candidates.append({"id":"scout_%d" % candidates.size(),"kind":"scout","units":[int(ids[0])],"target":0,"x":float(extent.extent_x)*x,"y":float(extent.extent_y)*y,"description":"Move one group to a public map coordinate to explore; available own groups 1"})
	var buildings: Dictionary = {}
	for role in 8:
		var cohort: Array=army.filter(func(o): return int(o.get("category",-1))==role)
		if cohort.is_empty() or cohort.size()==army.size(): continue
		for enemy in enemies.slice(0,2):
			candidates.append({"id":"attack_role_%d_%d" % [role,int(enemy.id)],"kind":"attack","units":cohort.map(func(o): return int(o.id)),"target":int(enemy.id),"x":enemy.x,"y":enemy.y,"description":"Attack a visible target with one owned unit class"})
	for object in own:
		if object.get("structure",false): buildings[str(object.template)]=int(buildings.get(str(object.template),0))+1
	var summary: Dictionary = {"model_only":true,"player_index":obs.player_index,"faction":obs.faction,"money":obs.money,"cp_free":int(obs.cp_limit)-int(obs.cp_used),"army_groups":army.size(),"home_emergency":false,"home_threat_groups":enemies.filter(func(o): return not o.get("structure",false) and Vector2(o.x,o.y).distance_to(home)<1100).size(),"visible_enemy_groups":enemies.filter(func(o): return not o.get("structure",false)).size(),"own_composition":composition(army),"visible_enemy_composition":composition(enemies),"own_buildings":buildings,"human_state_features":preload("res://scripts/team_ai/human_state_context.gd").collect(obs)}
	if OS.get_environment("OPENBFME_AI_TRAINING")=="1" and game.has_method("training_slot"): summary["training_slot"]=game.training_slot(int(obs.player_index))
	summary["spell_points"]=obs.get("spell_points",0) if snapshot_only or obs.has("spell_points") else game._world.get_spellbook(int(obs.player_index)).get("points",0)
	summary["match_id"]=training_match_id()
	summary["diagnostic_session"]=diagnostics.session
	summary["decision_frame"]=int(obs.observed_frame)
	summary["mechanics"]=M.collect(obs,home)
	summary["entity_state"]=M.entity_state(obs)
	summary.mechanics["spell_points"]=summary.spell_points
	summary["home_emergency"]=float(summary.mechanics.home_threat_value)>0
	for candidate in candidates: M.annotate(candidate,obs)
	return {"summary":summary,"candidates":candidates.slice(0,64),"army":army,"home":home}

func request_same_frame(ready_bots: Array, frame: int) -> void:
	# Caller supplies only bots already due at this frame. Never pull future turns
	# forward: the default staggered scheduler above supplies exactly one bot.
	if not pending.is_empty() or ready_bots.is_empty() or ready_bots.size()>8:return
	var requests: Array=[]
	var contexts: Array=[]
	var seen: Dictionary={}
	for bot in ready_bots:
		if seen.has(bot.index):return
		seen[bot.index]=true
	for bot in ready_bots:
		var payload: Dictionary=request_plan(bot,frame,true)
		if payload.is_empty():continue
		requests.append(payload)
		contexts.append(pending.duplicate(true))
	if requests.is_empty():
		pending.clear()
		return
	var serialization_started: int=Time.get_ticks_usec()
	var body: String=JSON.stringify({"model":"openbfme-decision-net-v0","requests":requests})
	var serialization_ms: float=float(Time.get_ticks_usec()-serialization_started)/1000.0
	var sent_us: int=Time.get_ticks_usec()
	for context in contexts:
		if inference_profile:
			context["profile_sent_us"]=sent_us
			context["profile_serialization_ms"]=serialization_ms/contexts.size()
			context["profile_request_bytes"]=body.to_utf8_buffer().size()/contexts.size()
			context.profile_prepare_ms+=serialization_ms/contexts.size()
			context.profile_parts.serialization_log_ms+=serialization_ms/contexts.size()
	pending={"batch_contexts":contexts}
	var error: int=http.request(http.chat_url,["Content-Type: application/json"],HTTPClient.METHOD_POST,body)
	if error!=OK:
		diagnostics.write("model_error",{"error":error,"batch":true,"fallback":false})
		pending.clear()

func request_plan(bot: Dictionary, frame: int, queue_only: bool=false) -> Dictionary:
	var preparation_started: int=Time.get_ticks_usec()
	var obs: Dictionary = game._world.strategy_observation(int(bot.index))
	if not obs.get("ok",false) or not obs.get("model_only_control",false): return {}
	var profile_observed: int=Time.get_ticks_usec()
	var spec: Dictionary = options(obs)
	var profile_candidates: int=Time.get_ticks_usec()
	spec.summary["decision_frame"]=frame
	spec.summary["reward_observations"]=reward_sensor.for_model(game._world,obs)
	var profile_reward: int=Time.get_ticks_usec()
	var purchases: Array = game._world.strategy_model_options(int(bot.index))
	var profile_purchases: int=Time.get_ticks_usec()
	if game.has_method("model_fixture_reserved_ids"):
		var reserved: Array = game.model_fixture_reserved_ids()
		purchases=purchases.filter(func(o): return int(o.get("producer",0)) not in reserved)
	sequence+=1
	last_request[bot.index]=frame
	pending={"epoch":epoch,"sequence":sequence,"player":int(bot.index),"observed_frame":frame,"sent_ms":Time.get_ticks_msec(),"options":spec.candidates,"production_options":purchases}
	var prompt: Array = spec.candidates.map(func(c): return {"id":c.id,"description":c.description,"mechanics":c.mechanics,"rule_refs":c.rule_refs})
	var serialization_started: int=Time.get_ticks_usec()
	var request_data: Dictionary={"observation":spec.summary,"candidates":prompt,"production_options":purchases}
	var request_body: String=""
	if not queue_only:
		var payload: Dictionary
		if OS.get_environment("OPENBFME_COMPACT_WIRE")=="1":payload={"model":"openbfme-decision-net-v0","request":request_data}
		else:payload={"model":"openbfme-decision-net-v0","messages":[{"role":"user","content":JSON.stringify(request_data)}]}
		request_body=JSON.stringify(payload)
	var serialization_ms: float=float(Time.get_ticks_usec()-serialization_started)/1000.0
	diagnostics.write("model_request",{"request":sequence,"player":bot.index,"frame":frame,"observation":spec.summary,"candidates":prompt,"production_options":purchases})
	if inference_profile:
		pending["profile_prepare_ms"]=float(Time.get_ticks_usec()-preparation_started)/1000.0
		pending["profile_parts"]={"snapshot_ms":float(profile_observed-preparation_started)/1000.0,"tactical_options_ms":float(profile_candidates-profile_observed)/1000.0,"reward_sensor_ms":float(profile_reward-profile_candidates)/1000.0,"production_options_ms":float(profile_purchases-profile_reward)/1000.0,"serialization_log_ms":float(Time.get_ticks_usec()-profile_purchases)/1000.0}
		pending["profile_sent_us"]=Time.get_ticks_usec()
		pending["profile_serialization_ms"]=serialization_ms
		pending["profile_request_bytes"]=request_body.to_utf8_buffer().size()
	if queue_only:return request_data
	var error: int = http.request(http.chat_url,["Content-Type: application/json"],HTTPClient.METHOD_POST,request_body)
	if error!=OK:
		diagnostics.write("model_error",{"request":sequence,"error":error,"fallback":false})
		pending.clear()
	return {}

func response(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if pending.has("batch_contexts"):
		var contexts: Array=pending.batch_contexts
		pending.clear()
		var outer=JSON.parse_string(body.get_string_from_utf8())
		if result!=HTTPRequest.RESULT_SUCCESS or code!=200 or not outer is Dictionary or not outer.get("results") is Array or outer.results.size()!=contexts.size():
			diagnostics.write("model_error",{"http":code,"result":result,"batch":true,"fallback":false})
			return
		# Apply in caller order, preserving each bot's original observation/context.
		for i in contexts.size():
			pending=contexts[i]
			response(result,int(outer.results[i].status),_headers,JSON.stringify(outer.results[i].response).to_utf8_buffer())
		return
	var callback_started: int=Time.get_ticks_usec()
	var timing_request: Dictionary=pending.duplicate(false)
	_apply_profiled_model_response(result,code,_headers,body)
	if inference_profile and not timing_request.is_empty():
		diagnostics.write("model_response_timing",{"request":timing_request.sequence,"player":timing_request.player,"observed_frame":timing_request.observed_frame,"callback_ms":float(Time.get_ticks_usec()-callback_started)/1000.0,"response_bytes":body.size()})

func _apply_profiled_model_response(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var request: Dictionary = pending.duplicate(true)
	pending.clear()
	if request.is_empty() or int(request.epoch)!=epoch or game._state!=game.State.PLAYING or not allowed(): return
	if inference_profile and request.has("profile_sent_us"):
		diagnostics.write("model_inference_timing",{"request":request.sequence,"player":request.player,"observed_frame":request.observed_frame,"parts":request.profile_parts,"prepare_ms":request.profile_prepare_ms,"serialization_ms":request.profile_serialization_ms,"request_bytes":request.profile_request_bytes,"rpc_wait_ms":float(Time.get_ticks_usec()-int(request.profile_sent_us))/1000.0,"http":code,"result":result})
	if result!=HTTPRequest.RESULT_SUCCESS or code!=200:
		diagnostics.write("model_error",{"request":request.sequence,"http":code,"result":result,"fallback":false})
		return
	var outer=JSON.parse_string(body.get_string_from_utf8())
	if outer is Dictionary and outer.has("results"):
		var results: Array=outer.results
		if results.size()!=1 or int(results[0].get("status",0))!=200:return
		outer=results[0].response
	if not outer is Dictionary or not outer.get("done",false): return
	var answer=outer.get("action") if outer.has("action") else JSON.parse_string(str(outer.get("message",{}).get("content","")))
	if not answer is Dictionary: return
	var frame: int = int(game._world.get_frame())
	if frame-int(request.observed_frame)>75:
		diagnostics.write("model_stale",{"request":request.sequence,"frame":frame,"fallback":false})
		return
	var obs: Dictionary = game._world.strategy_observation(int(request.player))
	if not obs.get("ok",false): return
	var chosen: Dictionary = {}
	for candidate in request.options:
		if candidate.id==answer.get("candidate_id",""): chosen=candidate
	if chosen.is_empty(): return
	request["training_spend_id"]=outer.get("training_spend_id","")
	if not str(request.training_spend_id).is_empty(): diagnostics.write("training_spend_response",{"action_id":request.training_spend_id,"player":request.player,"frame":frame,"selected":answer.get("production_id","none")})
	var command_result: Dictionary = apply_model_command(answer,request,frame)
	decisions+=1
	diagnostics.write("model_decision",{"request":request.sequence,"player":request.player,"frame":frame,"observed_frame":request.observed_frame,"match_id":training_match_id(),"plan":chosen,"training_action_id":outer.get("training_action_id",""),"model_only":true})
	if chosen.units.is_empty():
		emit_credit(request,"tactical",chosen,{"ok":true})
		return
	var moving_units: Array = chosen.units
	if command_result.get("ok",false):
		var operation: Dictionary = command_result.get("operation",{})
		if operation.get("kind","") in ["enter","power","stop"]:
			moving_units=moving_units.filter(func(id): return int(id)!=int(operation.get("producer",0)))
	if moving_units.is_empty():
		emit_credit(request,"tactical",chosen,{"ok":false})
		return
	var result_order: Dictionary
	if chosen.kind=="attack": result_order=team_ai.mapper.attack(game._world,int(request.player),moving_units,int(chosen.target),obs)
	else: result_order=team_ai.mapper.move(game._world,int(request.player),moving_units,Vector2(chosen.x,chosen.y),"move",obs)
	if result_order.get("ok",false): issued+=1
	var actual: Dictionary = chosen.duplicate(true)
	actual["units"]=moving_units
	emit_credit(request,"tactical",actual,result_order)
	diagnostics.write("general_order" if result_order.get("ok",false) else "order_refused",{"request":request.sequence,"player":request.player,"frame":frame,"plan":chosen.id,"units":moving_units,"result":result_order,"source":"model_only"})

func emit_credit(request: Dictionary, head: String, operation: Dictionary, result: Dictionary) -> void:
	operation=operation.duplicate(true)
	operation["affordable_military"]=request.production_options.any(func(o): return o.kind=="hero" or (o.kind=="train" and int(o.get("role",-1))>=0))
	var token: String = str(request.get("training_spend_id","") if head=="spend" else "")
	diagnostics.write("decision_credit_action",{"schema":"action-credit-v1","match_id":training_match_id(),"player":request.player,"observed_frame":request.observed_frame,"frame":game._world.get_frame(),"head":head,"action_id":token,"operation":operation,"submitted":result.get("ok",false)})

func apply_model_command(answer: Dictionary, request: Dictionary, frame: int) -> Dictionary:
	var id: String = str(answer.get("production_id","none"))
	if id=="none":
		emit_credit(request,"spend",{"id":"none","kind":"wait"},{"ok":true})
		return {}
	for operation in request.production_options:
		if str(operation.id)!=id: continue
		var before_ids: Array = C.objects(game._world.strategy_observation(int(request.player)),"self").map(func(o): return int(o.id))
		var evidence: Dictionary = operation.duplicate(true)
		evidence["before_ids"]=before_ids
		if operation.kind=="power":
			for power in game._world.get_object_powers(int(operation.producer)):
				if str(power.name)==str(operation.template): evidence["power_before"]=int(power.get("triggers",0))
		var result: Dictionary = game._world.strategy_model_action(int(request.player),{"id":id})
		if result.get("ok",false) and result.has("operation"):
			evidence.merge(result.operation,true)
		emit_credit(request,"spend",evidence,result)
		diagnostics.write("model_production" if operation.kind in ["build","train"] else "model_command",{"request":request.sequence,"action_id":request.get("training_spend_id",""),"player":request.player,"frame":frame,"operation":operation,"result":result,"source":"model_only"})
		if result.get("ok",false) and operation.kind in ["build","train"] and not str(request.get("training_spend_id","")).is_empty():
			training_pending_purchases.append({"action_id":request.training_spend_id,"player":request.player,"frame":frame,"operation":result.get("operation",operation),"before_ids":before_ids})
		return result
	diagnostics.write("model_command_rejected",{"request":request.sequence,"player":request.player,"frame":frame,"reason":"command_not_offered"})
	return {}

func reward_final_samples() -> Array:
	var result: Array = []
	if is_instance_valid(game) and is_instance_valid(game._world):
		for bot in bots:
			var obs: Dictionary = game._world.strategy_observation(int(bot.index))
			if not obs.get("ok",false): continue
			for sample in reward_sensor.for_model(game._world,obs):
				result.append(sample)
				diagnostics.write("reward_final_observation",sample)
	var match_id: String = training_match_id()
	if not bots.is_empty() and not closed_training_matches.has(match_id):
		closed_training_matches[match_id]=true
		diagnostics.write("normal_match_closed",{"match_id":match_id,"fixture":Array(OS.get_cmdline_user_args()).any(func(arg): return str(arg).begins_with("--arena-stage=")),"samples":result})
		if diagnostics.file!=null: diagnostics.file.flush()
	return result

func _exit_tree() -> void:
	reward_final_samples()
	super._exit_tree()
