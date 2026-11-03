extends Node

# First enhanced LOCAL controller. Inference is async and external to simulation.
# Accepted orders are logged, but live network authority integration is not enabled.
var game: Node
var http: Node
var label: Label
var hud
var profiles: Dictionary = {}
var policy = preload("res://scripts/rescue_order_policy.gd").new()
var diagnostics = preload("res://scripts/ai_diagnostics.gd").new()
var bots: Array = []
var plans: Dictionary = {}
var last_request: Dictionary = {}
var pending: Dictionary = {}
var epoch := 0
var sequence := 0
var last_frame := -1
var next_bot := 0
var decisions := 0
var fallbacks := 0
var issued := 0
var was_playing := false
var warm := false
var checked := false
var last_choice := "No model decision yet"
var combat = preload("res://scripts/combat_policy.gd")
var thrall_requests: Dictionary = {}
var cavalry_orders: Dictionary = {}
var cavalry_encounters: Dictionary = {}
var help_budget_log: Dictionary = {}
var last_production_log: Dictionary = {}
var combat_fixture_seeded := false
var support = preload("res://scripts/strategic_support.gd").new()
var team_ai = preload("res://scripts/team_ai/runtime.gd").new()
var team_ai_ready = false
var perf = preload("res://scripts/team_ai/perf_monitor.gd").new()
var spec_cache: Dictionary = {}
var human_log = preload("res://scripts/human_training_log.gd").new()

func setup(owner_game: Node) -> void:
	game = owner_game
	get_tree().root.close_requested.connect(func(): human_log.close("window_closed"))
	if not support.self_check():
		push_error("GENERAL_AI strategic support check failed")
		get_tree().quit(2)
		return
	if not combat.self_check():
		push_error("GENERAL_AI combat policy check failed")
		get_tree().quit(2)
		return
	print("GENERAL_AI combat policy check OK")
	profiles = JSON.parse_string(FileAccess.get_file_as_string("res://data/faction_profiles.json"))
	diagnostics.open_session()
	perf.logbook=diagnostics
	support.setup(game, diagnostics, policy)
	diagnostics.write("controller_start", {"mode": "general_local_model", "model": "qwen3:4b-instruct", "version": 4, "features":"competitive_cohorts"})
	http = preload("res://scripts/team_ai/model_client.gd").new()
	diagnostics.write("model_transport", {"endpoint": http.chat_url, "managed": OS.get_environment("OPENBFME_AI_MANAGED") == "1"})
	http.timeout = 120
	add_child(http)
	http.request_completed.connect(response)
	var layer := CanvasLayer.new()
	layer.layer = 90
	add_child(layer)
	hud=preload("res://scripts/team_ai/hud.gd").new()
	layer.add_child(hud)
	label=hud.status_line
	label.text = "GENERAL AI: local model controller ready. Start a fresh skirmish."
	if not team_ai.setup(game, diagnostics, layer, hud):
		get_tree().quit(2)
		return
	http.timeout = float(team_ai.config.decision.http_timeout_seconds)
	support.coordination = team_ai
	team_ai_ready = true
	print("GENERAL_AI controller ready")

func allowed() -> bool:
	if game._campaign_flow != null and game._campaign_flow.active: return false
	return game._net_host < 0 and game._net_join.is_empty() and game._lan_mode.is_empty() and not game._lan_shell_game and not game._last_game_online and not game._replay_active and game._cli_campaign.is_empty() and game._load_file.is_empty()

func reset() -> void:
	http.cancel_request()
	pending.clear()
	plans.clear()
	spec_cache.clear()
	last_request.clear()
	policy.assignments.clear()
	policy.combat_until.clear()
	thrall_requests.clear()
	cavalry_orders.clear()
	cavalry_encounters.clear()
	help_budget_log.clear()
	last_production_log.clear()
	support.clear()
	team_ai.clear()
	combat_fixture_seeded = false
	bots.clear()
	next_bot = 0
	epoch += 1

func tick() -> void:
	if not team_ai_ready: return
	human_log.tick(game, allowed())
	diagnostics.phase_changed(int(game._state), last_frame)
	var playing: bool = game._state == game.State.PLAYING and game._world != null
	if not playing:
		hud.visible=false
		if was_playing:
			reset()
			was_playing = false
		return
	if not allowed():
		hud.visible=false
		label.text = "GENERAL AI: disabled outside fresh local skirmish"
		return
	var world: Node = game._world
	if not world.has_method("strategy_observation"):
		label.text = "GENERAL AI: wrong engine DLL (strategy_observation missing)"
		return
	var frame: int = world.get_frame()
	if frame < last_frame:
		reset()
		last_frame = -1
	if frame - last_frame < int(team_ai.config.decision.scan_frames) and last_frame >= 0:
		return
	last_frame = frame
	var tick_started=Time.get_ticks_usec()
	var decision_usec=0
	var orders_usec=0
	spec_cache.clear()
	was_playing = true
	if bots.is_empty():
		for p in world.get_economy().get("players", []):
			if p.get("playable", false) and p.name != game._local_name:
				var obs: Dictionary = world.strategy_observation(int(p.index))
				if obs.get("ok", false): bots.append({"index": int(p.index), "name": p.name, "faction": p.faction})
		if bots.is_empty(): return
		if not checked and OS.get_cmdline_user_args().has("--general-check"):
			checked = true
			if not verify_observations(world):
				get_tree().quit(2)
				return
		print("GENERAL_AI bots ", JSON.stringify(bots))
		diagnostics.write("general_bots", {"bots": bots})
	if not combat_fixture_seeded and OS.get_cmdline_user_args().has("--combat-check"):
		combat_fixture_seeded = true
		seed_combat_fixture(world)
	if not combat_fixture_seeded and OS.get_cmdline_user_args().has("--support-check"):
		combat_fixture_seeded = true
		for bot in bots:
			world.give_money(bot.index, 8000)
			var fixture_obs: Dictionary = world.strategy_observation(bot.index)
			var fixture_spec := options(fixture_obs)
			if not fixture_spec.has("home"): continue
			var home: Vector2 = fixture_spec.home
			for i in range(4):
				world.create_object("GondorFighterHorde", bot.index, home.x + i * 45, home.y + 150, 0)
			if bot.faction == "FactionDwarves":
				var hero: int = world.create_object("DwarvenGloin", bot.index, home.x + 700, home.y, 0)
				var hero_state: Dictionary = world.get_object(hero)
				world.build2_damage(hero, float(hero_state.get("max_health", 0)) * 0.75)
				diagnostics.write("support_fixture", {"hero": hero, "player": bot.index})
	var snapshot_started=Time.get_ticks_usec()
	team_ai.begin(bots, world, frame)
	var snapshot_usec=Time.get_ticks_usec()-snapshot_started
	for bot in bots:
		var obs: Dictionary = team_ai.observations.get(bot.index, {})
		if not obs.get("ok", false): continue
		var decision_started=Time.get_ticks_usec()
		var spec := options(obs)
		spec_cache[bot.index]=spec
		team_ai.step(bot.index, obs, spec, frame, world)
		decision_usec+=Time.get_ticks_usec()-decision_started
		var orders_started=Time.get_ticks_usec()
		var idle_plan: Dictionary = team_ai.idle_scan(bot.index, spec, frame)
		if not idle_plan.is_empty():
			plans[bot.index] = idle_plan
			diagnostics.write("fallback_plan", {"player": bot.index, "frame": frame, "reason": "idle_scan", "plan": idle_plan})
		support.observe_style(bot, obs, frame)
		summon_thralls(bot, obs, frame)
		if frame - int(last_production_log.get(bot.index, -150)) >= 150 or (OS.get_cmdline_user_args().has("--combat-check") and frame < 100):
			diagnostics.write("counter_production", {"frame": frame, "player": bot.index, "seen_enemy": combat.counts(obs, "enemy"), "desired": obs.get("production_plan", []), "hero_requests": obs.get("hero_requests", 0), "upgrade_requests": obs.get("upgrade_requests", 0)})
			last_production_log[bot.index] = frame
		if not plans.has(bot.index):
			install_fallback(bot.index, spec, frame, "initial_plan")
		var tactical: Dictionary = team_ai.fast_plan(bot.index,plans.get(bot.index,{}),spec,frame)
		if not tactical.is_empty(): plans[bot.index]=tactical
		var commitment: Dictionary = team_ai.forced(bot.index, frame)
		if not commitment.is_empty() and not spec.critical: plans[bot.index] = commitment
		if plans.has(bot.index): support.logistics(bot, obs, spec, plans[bot.index], frame)
		var free_spec := spec.duplicate(false)
		free_spec.army = spec.army.filter(func(o): return not support.in_transit(int(o.id), frame))
		if plans.has(bot.index): team_ai.macro_step(bot.index, plans[bot.index], obs, free_spec, frame, world, policy)
		apply_plan(bot, obs, spec, frame)
		team_ai.micro_step(bot.index, obs, free_spec, frame, world, policy)
		if plans.has(bot.index): team_ai.tactics.track(bot.index, plans[bot.index], spec.army.size(), int(spec.get("summary", {}).get("visible_enemy_groups", 0)), frame,obs,world)
		orders_usec+=Time.get_ticks_usec()-orders_started
	diagnostics.sample(world, bots.map(func(bot): return bot.name), frame)
	team_ai.finish_tick(frame)
	if pending.is_empty():
		var bot: Dictionary = bots[next_bot % bots.size()]
		next_bot += 1
		var spec: Dictionary = spec_cache.get(bot.index,{})
		if spec.has("summary") and team_ai.ready(bot.index, spec, frame):
			request_plan(bot, frame)
	hud.set_status(true,decisions,issued,last_choice,bots.size())
	perf.record(frame,float(Time.get_ticks_usec()-tick_started)/1000.0,float(snapshot_usec)/1000.0,float(decision_usec)/1000.0,float(orders_usec)/1000.0,world)

func point(o: Dictionary) -> Vector2:
	return Vector2(float(o.x), float(o.y))

func options(obs: Dictionary) -> Dictionary:
	var profile: Dictionary = support.style_profile(profiles.get(obs.faction, profiles.FactionMen), int(obs.get("personality", 2)))
	if obs.has("classic_opening") and obs.faction in ["FactionWild","FactionMordor","FactionAngmar"] and int(obs.observed_frame)<900:
		profile.attack_minimum=mini(3,int(profile.attack_minimum))
	profile = team_ai.profile(int(obs.player_index), profile)
	var own: Array = []
	var allies: Array = []
	var enemies: Array = []
	var base: Dictionary = {}
	var army: Array = []
	for p in obs.players:
		if p.relation == "self": own = p.objects
		elif p.relation == "ally": allies.append(p)
		elif p.relation == "enemy": enemies.append_array(p.objects)
	for o in own:
		if o.base: base = o
		elif not o.structure and str(o.get("template", "")) != "AngmarThrallMaster": army.append(o)
	if base.is_empty():
		for o in own:
			if o.structure:
				base = o
				break
	if base.is_empty(): return {"candidates": [], "army": army, "critical": false}
	var center := point(base)
	var home_threat := nearby(enemies, center, 1100.0)
	var local_defenders := nearby(army, center, 1100.0)
	var approaching: Array = team_ai.battle.near(enemies,center,1100).filter(func(o): return not o.structure)
	var attackers: Dictionary = {}
	for enemy in approaching: attackers[int(enemy.get("owner_index",-1))]=true
	var defenders: Array = team_ai.battle.near(army,center,1100)
	var critical: bool = home_threat > 0 and (attackers.size()>=2 or team_ai.battle.strength(approaching,defenders)>=maxf(0.5,team_ai.battle.strength(defenders,approaching))*0.8 or home_threat >= maxi(1, int(local_defenders * 0.6)) or float(base.get("health_ratio", 1.0)) < 0.85)
	var candidates: Array = [{"id": "defend", "kind": "defend", "target": int(base.id), "x": center.x, "y": center.y,
		"description": "Hold the army at home; visible nearby enemy combat groups: %d. With no threat this gains no scouting information or pressure." % home_threat}]
	if not critical and army.size() >= 2:
		for ally in allies:
			for building in ally.objects:
				if not building.base: continue
				var threat := nearby(enemies, point(building), 1100.0)
				if threat <= 0: continue
				candidates.append({"id": "help_%d" % building.id, "kind": "help", "target": int(building.id), "x": building.x, "y": building.y,
					"description": "Help ally base threatened by %d visible enemy groups; keep home reserve" % threat})
	if not critical and army.size() >= int(profile.attack_minimum):
		var targets := 0
		var prioritized: Array = enemies.duplicate()
		prioritized.sort_custom(func(a,b): return (2 if a.structure and not a.base else 1 if a.structure else 0) > (2 if b.structure and not b.base else 1 if b.structure else 0))
		for enemy in prioritized:
			if targets >= 8: break
			var threat := nearby(enemies, point(enemy), 600.0)
			if army.size() < maxi(2, int(ceil(threat * float(profile.attack_ratio)))): continue
			candidates.append({"id": "attack_%d" % enemy.id, "kind": "attack", "target": int(enemy.id), "x": enemy.x, "y": enemy.y,
				"description": "Attack a currently visible enemy %s; nearby enemy groups %d, available own groups %d" % ["structure" if enemy.structure else "army", threat, army.size()]})
			targets += 1
	if not critical and not army.is_empty():
		var extent: Dictionary = game._world.get_census()
		# Explore public map geometry rather than hidden enemy coordinates. Hold
		# each waypoint for three game minutes so a scout can actually reach it.
		var locations: Array = []
		for x in [0.2, 0.5, 0.8]:
			for y in [0.2, 0.5, 0.8]:
				var spot := Vector2(float(extent.get("extent_x", 2000)) * x, float(extent.get("extent_y", 2000)) * y)
				if spot.distance_to(center) > 400.0: locations.append(spot)
		if locations.is_empty(): locations.append(center + Vector2(500, 0))
		var scout_point: Vector2 = locations[(int(obs.observed_frame) / 900 + int(obs.player_index) * 2) % locations.size()]
		scout_point.x = clampf(scout_point.x, 100, maxf(100, float(extent.get("extent_x", 2000)) - 100))
		scout_point.y = clampf(scout_point.y, 100, maxf(100, float(extent.get("extent_y", 2000)) - 100))
		candidates.append({"id": "scout", "kind": "scout", "target": 0, "x": scout_point.x, "y": scout_point.y, "description": "Find the enemy and reveal opportunities with one scouting group; all remaining groups defend home"})
	var summary := {"faction": obs.faction, "personality": profile.name, "style": profile.style, "money": obs.money, "army_groups": army.size(),
		"home_threat_groups": home_threat, "home_emergency": critical, "visible_enemy_groups": enemies.filter(func(o): return not o.structure).size(),
		"own_composition": composition(army), "visible_enemy_composition": composition(enemies)}
	var allied_bases: Array = []
	for ally in allies:
		for building in ally.objects:
			if building.get("base", false): allied_bases.append(building)
	return preload("res://scripts/team_ai/user_rules.gd").constrain(obs, team_ai.decorate(obs, {"candidates": candidates, "army": army, "critical": critical, "summary": summary, "reserve": profile.reserve, "home": center, "allied_bases": allied_bases}, int(obs.observed_frame)))

func nearby(objects: Array, at: Vector2, radius: float) -> int:
	var count := 0
	for o in objects:
		if not o.structure and point(o).distance_to(at) < radius: count += 1
	return count

func composition(objects: Array) -> Dictionary:
	var result: Dictionary = {}
	for o in objects:
		if o.structure: continue
		var name := str(o.get("template", "unknown"))
		result[name] = int(result.get(name, 0)) + 1
	return result

func install_fallback(player: int, spec: Dictionary, frame: int, reason: String) -> void:
	if spec.candidates.is_empty(): return
	var choice: Dictionary = spec.candidates[0]
	if not spec.critical:
		for candidate in spec.candidates:
			if candidate.kind == "attack" or candidate.kind == "help":
				choice = candidate
				break
		if choice.kind == "defend" and spec.candidates.size() > 1: choice = spec.candidates[-1]
		var recommendation: Dictionary = team_ai.recommended(player)
		for candidate in spec.candidates:
			if candidate.id == recommendation.get("id", ""): choice = recommendation
	plans[player] = choice.duplicate(true)
	fallbacks += 1
	diagnostics.write("fallback_plan", {"frame": frame, "player": player, "plan": choice, "reason": reason})

func request_plan(bot: Dictionary, frame: int) -> void:
	var obs: Dictionary = team_ai.observations.get(bot.index,{})
	if int(obs.get("observed_frame",-1))!=frame: obs=game._world.strategy_observation(bot.index)
	if not obs.get("ok", false): return
	var spec: Dictionary = spec_cache.get(bot.index,{}) if int(obs.observed_frame)==last_frame else {}
	if spec.is_empty(): spec=options(obs)
	if spec.candidates.is_empty(): return
	var purchases: Array = game._world.strategy_production_options(int(bot.index))
	var buildings := {}
	for object in preload("res://scripts/team_ai/contracts.gd").objects(obs, "self"):
		if object.get("structure", false):
			var key := str(object.template) + (" (building)" if not object.get("complete", false) else "")
			buildings[key] = int(buildings.get(key, 0)) + 1
	spec.summary["own_buildings"] = buildings
	spec.summary["cp_free"] = int(obs.cp_limit) - int(obs.cp_used)
	if obs.has("classic_opening"):
		spec.summary["command_history"]=team_ai.mapper.sequence.context(bot.index)
		spec.summary["player_index"]=int(bot.index)
	var prompt_purchases: Array = purchases.map(func(op): return {"id": op.id, "cost": op.cost})
	sequence += 1
	var schema: Dictionary = preload("res://scripts/team_ai/intent_schema.gd").build(spec.candidates, team_ai.board.snapshot(team_ai.board.team_of(bot.index)).get("bots", {}).keys(), purchases)
	var prompt_candidates: Array = spec.candidates.map(func(c): return {"id": c.id, "description": c.description})
	var payload := {"model": str(team_ai.config.decision.model), "stream": false, "format": schema, "keep_alive": "15m",
		"options": {"temperature": 0, "num_ctx": int(team_ai.config.decision.num_ctx), "num_predict": int(team_ai.config.decision.num_predict)},
		"messages": [{"role": "system", "content": "You command an RTS faction. Choose one candidate_id AND one production_id from production_options (or none). You have authority to buy exactly one building or unit per response, at normal cost. Favor training counters and reinforcing an army under pressure; grow economy and production when safe. Prefer useful affordable purchases over saving without purpose. Never invent a producer or template. Use faction style as a preference, not a fixed build order. Respond to observed threats and opportunities. Do not assume unseen enemies. Protect home when critically threatened. Seek information to locate the enemy when home is safe; avoid indefinite waiting without a purpose. Scout and attack actions automatically retain the stated home reserve. Do not generate dialogue or assistance requests; return an empty messages array. Return only the required JSON."},
			{"role": "user", "content": JSON.stringify({"observation": spec.summary, "candidates": prompt_candidates, "production_options": prompt_purchases})}]}
	pending = {"epoch": epoch, "sequence": sequence, "player": bot.index, "observed_frame": frame, "sent_ms": Time.get_ticks_msec(), "options": spec.candidates, "production_options": purchases}
	team_ai.loop.sent(bot.index, frame)
	last_request[bot.index] = frame
	diagnostics.write("model_request", {"request": sequence, "frame": frame, "player": bot.index, "observation": spec.summary, "candidates": prompt_candidates, "production_options": purchases})
	var error: int = http.request(http.chat_url, ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(payload))
	if error != OK:
		diagnostics.write("model_error", {"error": error, "request": sequence})
		pending.clear()
		team_ai.loop.finished_request(bot.index)

func response(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var request := pending.duplicate(true)
	pending.clear()
	if not request.is_empty(): team_ai.loop.finished_request(int(request.player))
	if request.is_empty() or int(request.epoch) != epoch or game._state != game.State.PLAYING or not allowed(): return
	var frame: int = game._world.get_frame()
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		diagnostics.write("model_error", {"request": request.sequence, "result": result, "http": code})
		return
	var outer = JSON.parse_string(body.get_string_from_utf8())
	if not outer is Dictionary or not outer.get("done", false):
		diagnostics.write("model_rejected", {"request": request.sequence, "reason": "incomplete or invalid response"})
		return
	var answer = JSON.parse_string(str(outer.get("message", {}).get("content", "")))
	if not answer is Dictionary or not answer.get("candidate_id") is String:
		diagnostics.write("model_rejected", {"request": request.sequence, "reason": "invalid decision schema"})
		return
	var obs: Dictionary = game._world.strategy_observation(int(request.player))
	if not obs.get("ok", false): return
	var fresh := options(obs)
	# Allow cold loading to finish once; ordinary responses older than 15 game
	# seconds are discarded. Every target must still be legal in the current view.
	if warm and frame - int(request.observed_frame) > int(team_ai.config.decision.deadline_frames):
		diagnostics.write("model_stale", {"request": request.sequence, "frame": frame})
		return
	warm = true
	if obs.has("classic_opening") and outer.get("sequence_hint",{}) is Dictionary: team_ai.mapper.sequence.accept(int(request.player),outer.get("sequence_hint",{}),frame)
	var originally_offered := false
	for candidate in request.options:
		if candidate.id == answer.candidate_id: originally_offered = true
	if not originally_offered: return
	for candidate in fresh.candidates:
		if candidate.id == answer.candidate_id:
			var validation: String = team_ai.mapper.validate(answer, obs, fresh.candidates)
			if not validation.is_empty():
				diagnostics.write("intent_rejected", {"request": request.sequence, "reason": validation})
				return
			candidate["priority"] = int(answer.get("priority", 50))
			candidate["model_reason"] = str(answer.get("reason", ""))
			apply_model_production(answer, request, frame)
			if not team_ai.accept(int(request.player), candidate, fresh, frame): return
			plans[int(request.player)] = candidate.duplicate(true)
			decisions += 1
			last_choice = "%s/%s: %s" % [str(obs.faction).trim_prefix("Faction"), str(fresh.summary.personality), str(candidate.kind)]
			diagnostics.write("model_decision", {"request": request.sequence, "frame": frame, "observed_frame": request.observed_frame, "player": request.player, "plan": candidate, "latency_ms": Time.get_ticks_msec() - int(request.sent_ms)})
			print("GENERAL_AI model player=%d plan=%s frame=%d" % [int(request.player), str(candidate.id), frame])
			return
	diagnostics.write("model_rejected", {"request": request.sequence, "reason": "plan no longer legal"})

func apply_model_production(answer: Dictionary, request: Dictionary, frame: int) -> void:
	var id := str(answer.get("production_id", "none"))
	if id == "none": return
	for operation in request.get("production_options", []):
		if str(operation.id) != id: continue
		var result: Dictionary = game._world.strategy_produce(int(request.player), operation)
		diagnostics.write("model_production", {"request": request.sequence, "player": request.player, "frame": frame, "operation": operation, "result": result})
		return
	diagnostics.write("model_production_rejected", {"request": request.sequence, "player": request.player, "frame": frame, "reason": "purchase_not_offered", "id": id})

func apply_plan(bot: Dictionary, obs: Dictionary, spec: Dictionary, frame: int) -> void:
	if spec.candidates.is_empty() or not plans.has(bot.index): return
	var plan: Dictionary = plans[bot.index]
	if frame < int(plan.get("wait_until", 0)):
		plan = {"id": "rally", "kind": "defend", "target": 0, "x": spec.home.x, "y": spec.home.y}
	var legal: bool = plan.id == "rally"
	for candidate in spec.candidates:
		if candidate.id == plan.id:
			legal = true
			var previous_plan: Dictionary = plan
			plan = candidate.duplicate(true)
			for key in ["tactic_tag", "reason", "issued_frame", "max_groups"]:
				if previous_plan.has(key): plan[key] = previous_plan[key]
	if not legal:
		install_fallback(bot.index, spec, frame, "world_changed")
		plan = plans[bot.index]
	var army: Array = preload("res://scripts/team_ai/user_rules.gd").soldiers(spec.army,plan,obs)
	var count := army.size()
	if plan.kind == "scout": count = mini(1, count)
	elif plan.kind == "attack" or plan.kind == "help": count = maxi(0, count - maxi(1, int(ceil(count * float(spec.reserve)))))
	var goal := Vector2(float(plan.x), float(plan.y))
	if plan.has("max_groups"): count = mini(count, int(plan.max_groups))
	if obs.has("classic_opening") and plan.kind=="help": count=mini(count,preload("res://scripts/team_ai/user_rules.gd").help_limit(obs,int(plan.target),army.size()))
	if obs.has("classic_opening") and plan.kind=="help":
		var budget_signature := str([plan.target,army.size(),count])
		if str(help_budget_log.get(bot.index,""))!=budget_signature:
			diagnostics.write("help_budget",{"player":bot.index,"frame":frame,"target":plan.target,"army_groups":army.size(),"sent_limit":count,"selected":army.slice(0,count).map(func(o): return int(o.id))})
			help_budget_log[bot.index]=budget_signature
	if plan.get("tactic_tag", "") in ["feint_push", "bait"] and frame - int(plan.get("issued_frame", frame)) >= int(team_ai.config.decision.commit_frames): goal = spec.home
	var ids: Array = []
	var reserves: Array = []
	var assembly: Array = []
	var retreating: Array = []
	var excluded: Array = army.slice(count).map(func(o): return int(o.id))
	for unit in army:
		if support.in_transit(int(unit.id),frame): excluded.append(int(unit.id))
	var movement_spec: Dictionary = spec.duplicate(false)
	if obs.has("classic_opening") and (plan.kind=="help" or preload("res://scripts/team_ai/user_rules.gd").raid(plan,obs)): movement_spec.army=army.slice(0,count)
	var directive: Dictionary = team_ai.battle.movement(bot.index,plan,movement_spec,obs,frame,excluded)
	goal=directive.approach
	var pikes: Array = []
	for player in obs.players:
		if player.relation != "enemy": continue
		for enemy in player.objects:
			if not enemy.structure and int(enemy.get("category", -1)) == 2: pikes.append(point(enemy))
	for i in range(army.size()):
		var o: Dictionary = army[i] if army[i].has("combat_active") else game._world.get_object(int(army[i].id))
		if not o.get("ok", false): continue
		if support.in_transit(int(army[i].id), frame): continue
		if support.protect_hero(bot, army[i], o, spec.home, frame): continue
		if support.escort_hero(bot,army[i],o,army,spec.home,frame): continue
		# Injured groups belong to the recovery micro, not another simultaneous advance.
		if float(army[i].get("health_ratio",1))<float(team_ai.config.micro.retreat_ratio): continue
		if i<count and directive.retreat:
			var previous: Dictionary = policy.assignments.get(int(army[i].id),{})
			if frame-int(previous.get("issued",-1000))>=25:
				retreating.append(int(army[i].id))
				policy.assignments[int(army[i].id)]={"goal":directive.rally,"issued":frame,"phase":"retreat"}
			continue
		if team_ai.micro_locks.has(int(army[i].id)): continue
		var unit_goal: Vector2 = goal if i < count else spec.home
		var gathering: bool = i<count and int(army[i].id) in directive.hold
		if gathering: unit_goal=directive.rally
		var guarding: bool = i >= count or plan.kind == "defend" or plan.kind == "help"
		guarding=guarding or gathering
		if int(army[i].get("category", -1)) == 3 and cavalry_safety(bot, army[i], o, unit_goal, pikes, frame): continue
		var members: Array = []
		for id in o.get("members", []): members.append(game._world.get_object(int(id)))
		var engaged: bool = policy.combat_active(o, members)
		if policy.needs_order(int(army[i].id), point(army[i]), unit_goal, unit_goal, frame, bool(o.get("moving", false)), engaged, guarding):
			if gathering: assembly.append(int(army[i].id))
			elif i < count: ids.append(int(army[i].id))
			else: reserves.append(int(army[i].id))
	for batch in [{"units":assembly,"kind":"assembly"},{"units":retreating,"kind":"tactical_retreat"}]:
		if batch.units.is_empty(): continue
		var result: Dictionary = team_ai.mapper.move(game._world,bot.index,batch.units,directive.rally,"move",obs)
		diagnostics.write("cohort_order",{"player":bot.index,"frame":frame,"kind":batch.kind,"units":batch.units,"reason":directive.reason,"result":result})
		if result.get("ok",false):
			issued+=1
			for id in batch.units: team_ai.micro_locks[int(id)]=frame+15
		else:
			for id in batch.units: policy.assignments.erase(int(id))
	for id in directive.hold: team_ai.micro_locks[int(id)]=frame+int(team_ai.config.decision.scan_frames)
	if not ids.is_empty():
		var result: Dictionary = team_ai.mapper.move(game._world, bot.index, ids, goal, "move" if plan.kind == "defend" or plan.kind == "help" or plan.get("tactic_tag", "") in ["feint_push", "bait"] else "attack", obs,plan.kind=="scout" and not spec.critical)
		issued += 1
		diagnostics.write("general_order" if result.get("ok", false) else "order_refused", {"frame": frame, "player": bot.index, "plan": plan.id, "units": ids, "result": result})
		if result.get("ok", false): team_ai.conversation.ordered(bot.index, plan, obs, frame)
		if not result.get("ok", false):
			for id in ids: policy.assignments.erase(id)
	if not reserves.is_empty():
		var home: Vector2 = spec.home
		var result: Dictionary = team_ai.mapper.move(game._world, bot.index, reserves, home, "move", obs)
		issued += 1
		diagnostics.write("general_order" if result.get("ok", false) else "order_refused", {"frame": frame, "player": bot.index, "plan": "home_reserve", "units": reserves, "result": result})
		if not result.get("ok", false):
			for id in reserves: policy.assignments.erase(id)

func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_F8:
		var marker={"frame":last_frame,"controller":"general","performance":perf.summary()}
		if game._world!=null: marker["engine"]=game._world.get_frame_timings()
		diagnostics.write("user_marker",marker)
		human_log.marker(int(game._world.get_frame()) if is_instance_valid(game._world) else last_frame)

func verify_observations(world: Node) -> bool:
	var local_index := -1
	for p in world.get_economy().get("players", []):
		if p.name == game._local_name: local_index = int(p.index)
	if local_index < 0 or world.strategy_observation(local_index).get("ok", false):
		push_error("GENERAL_AI CHECK: human observer must be refused")
		return false
	for bot in bots:
		var obs: Dictionary = world.strategy_observation(bot.index)
		if not obs.get("ok", false): return false
		# Independent public shroud query under the same player's client view.
		# Only the test changes the viewer, restoring it before issuing orders.
		world.set_local_player(bot.index)
		var valid := true
		for p in obs.players:
			if p.relation == "enemy":
				for o in p.objects:
					if world.get_object_shroud_status(int(o.id)) >= 3: valid = false
		world.set_local_player(local_index)
		if not valid:
			push_error("GENERAL_AI CHECK: unseen enemy leaked into observation")
			return false
	var fixture := {"faction": "FactionMen", "player_index": 2, "observed_frame": 100, "money": 1000,
		"players": [{"relation": "self", "objects": [{"id": 1, "base": true, "structure": true, "x": 1000, "y": 1000},
			{"id": 2, "base": false, "structure": false, "x": 1000, "y": 1000}]},
			{"relation": "enemy", "objects": [{"id": 3, "base": false, "structure": false, "x": 1100, "y": 1000}]}]}
	var emergency := options(fixture)
	if not emergency.critical or emergency.candidates.size() != 1 or emergency.candidates[0].id != "defend":
		push_error("GENERAL_AI CHECK: home emergency must exclude unsafe plans")
		return false
	print("GENERAL_AI CHECK OK: human refusal, per-bot fog and emergency action legality")
	diagnostics.write("general_check", {"ok": true})
	return true

func _exit_tree() -> void:
	human_log.close("game_closed")
	if http != null: http.cancel_request()
	team_ai.shutdown()
	diagnostics.close_session()

func summon_thralls(bot: Dictionary, obs: Dictionary, frame: int) -> void:
	if bot.faction != "FactionAngmar": return
	for player in obs.players:
		if player.relation != "self": continue
		for unit in player.objects:
			if str(unit.template) != "AngmarThrallMaster": continue
			var id := int(unit.id)
			var upgrades: Dictionary = game._world.get_upgrades(id)
			var converted := false
			for upgrade in upgrades.get("object", []):
				if str(upgrade).begins_with("Upgrade_ThrallMaster"): converted = true
			if converted: continue
			if frame - int(thrall_requests.get(id, -1000)) < 75: continue
			var production: Dictionary = game._world.get_production(bot.index, id)
			if not production.get("ok", false) or not production.get("queue", []).is_empty(): continue
			var upgrade: String = combat.thrall_upgrade(combat.counts(obs, "self"), combat.counts(obs, "enemy"))
			if obs.has("classic_opening"):
				var own_counts: Dictionary = combat.counts(obs,"self")
				var losses := 0
				for owner in obs.players:
					if owner.relation=="self": losses=int(owner.get("farms_lost",0))
				if not obs.classic_opening.get("first_sword",false): upgrade="Upgrade_ThrallMasterOrcWarriors"
				elif losses>0 and own_counts.archers<2: upgrade="Upgrade_ThrallMasterRhudaurSlingers"
				if (upgrade=="Upgrade_ThrallMasterRhudaurSlingers" and own_counts.archers>=3) or (upgrade=="Upgrade_ThrallMasterWolfRiders" and own_counts.cavalry>=2): upgrade="Upgrade_ThrallMasterOrcWarriors"

			game._world.queue_upgrade(bot.index, id, upgrade)
			thrall_requests[id] = frame
			diagnostics.write("thrall_summon_order", {"frame": frame, "player": bot.index, "unit": id, "upgrade": upgrade})
			return # one purchase per bot/tick; normal engine affordability checks apply

func cavalry_safety(bot: Dictionary, unit: Dictionary, state: Dictionary, goal: Vector2, pikes: Array, frame: int) -> bool:
	var id := int(unit.id)
	var choice: Dictionary = combat.cavalry_move(point(unit), goal, pikes, team_ai.extent)
	if not choice.avoid:
		var encounter: Dictionary = cavalry_encounters.get(id, {})
		if frame-int(encounter.get("last_seen",-1000))>50: cavalry_encounters.erase(id)
		if cavalry_orders.has(id):
			cavalry_orders.erase(id)
			policy.assignments.erase(id)
		return false
	var encounter: Dictionary = cavalry_encounters.get(id, {})
	if encounter.is_empty():
		encounter={"attack":team_ai.personality.imperfect(bot.index,0.15),"last_seen":frame,"last_order":-1000}
		diagnostics.write("cavalry_pike_choice",{"player":bot.index,"unit":id,"frame":frame,"attack":encounter.attack,"probability":0.15})
	encounter.last_seen=frame
	cavalry_encounters[id]=encounter
	if encounter.attack:
		var obs: Dictionary = team_ai.observations.get(bot.index,{})
		var target: Dictionary = {}
		var distance := INF
		for player in obs.get("players",[]):
			if player.relation!="enemy": continue
			for enemy in player.objects:
				if enemy.structure or int(enemy.get("category",-1))!=2: continue
				var candidate_distance: float = point(unit).distance_squared_to(point(enemy))
				if candidate_distance<distance:
					distance=candidate_distance
					target=enemy
		if not target.is_empty():
			if frame-int(encounter.last_order)>=25:
				var attack_result: Dictionary = team_ai.mapper.attack(game._world,bot.index,[id],int(target.id),obs)
				if attack_result.get("ok",false):
					encounter.last_order=frame
					cavalry_encounters[id]=encounter
					policy.assignments.erase(id)
					diagnostics.write("cavalry_pike_attack",{"player":bot.index,"unit":id,"target":target.id,"frame":frame,"result":attack_result})
			return true
	var previous: Dictionary = cavalry_orders.get(id, {})
	if not previous.is_empty() and frame - int(previous.frame) < 20:
		return true
	var target: Vector2 = choice.goal
	var result: Dictionary = game._world.order_move([id], target.x, target.y, {"type": "move", "player": bot.index})
	if result.get("ok", false):
		cavalry_orders[id] = {"frame": frame, "goal": target}
		policy.assignments.erase(id)
		issued += 1
		diagnostics.write("cavalry_avoidance", {"frame": frame, "player": bot.index, "unit": id, "reason": choice.reason, "x": target.x, "y": target.y, "visible_pikes": pikes.size()})
	return true

func seed_combat_fixture(world: Node) -> void:
	# Explicit headless verification hook only; never used in ordinary matches.
	if bots.size() != 7:
		push_error("COMBAT_CHECK requires the seven-faction matrix")
		return
	var extent: Dictionary = world.get_census()
	var size := Vector2(float(extent.get("extent_x", 2000)), float(extent.get("extent_y", 2000)))
	for bot in bots:
		if bot.faction not in ["FactionDwarves", "FactionWild", "FactionAngmar"]: continue
		var obs: Dictionary = world.strategy_observation(bot.index)
		var center := Vector2.ZERO
		for player in obs.players:
			if player.relation != "self": continue
			for o in player.objects:
				if o.base: center = point(o)
		var enemy_index := int(bots[3].index) if bot.faction != "FactionAngmar" else int(bots[0].index)
		var enemy_point: Vector2 = combat.bounded(center + Vector2(220, 0), size)
		if bot.faction == "FactionWild":
			var cavalry: int = world.create_object("GoblinSpiderRiderHorde", bot.index, center.x, center.y + 100, 0)
			var pike: int = world.create_object("GondorTowerShieldGuardHorde", enemy_index, enemy_point.x, enemy_point.y + 100, 0)
			diagnostics.write("combat_fixture", {"test": "cavalry_safety", "cavalry": cavalry, "pike": pike})
		else:
			var rider: int = world.create_object("GondorKnightHorde", enemy_index, enemy_point.x, enemy_point.y, 0)
			if bot.faction == "FactionAngmar":
				var master: int = world.create_object("AngmarThrallMaster", bot.index, center.x, center.y + 100, 0)
				diagnostics.write("combat_fixture", {"test": "thrall_counter", "master": master, "cavalry": rider})
			else:
				world.create_object("DwarfBarracks", bot.index, center.x - 140, center.y + 140, 0)
				diagnostics.write("combat_fixture", {"test": "counter_production", "cavalry": rider})
