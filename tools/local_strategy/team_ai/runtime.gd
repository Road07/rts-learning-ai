extends RefCounted

const C = preload("res://scripts/team_ai/contracts.gd")
var board = preload("res://scripts/team_ai/blackboard.gd").new()
var bus = preload("res://scripts/team_ai/messages.gd").new()
var enemy = preload("res://scripts/team_ai/enemy_model.gd").new()
var personality = preload("res://scripts/team_ai/personality.gd").new()
var books = preload("res://scripts/team_ai/playbooks.gd").new()
var loop = preload("res://scripts/team_ai/decision_loop.gd").new()
var coordinator = preload("res://scripts/team_ai/team_coordinator.gd").new()
var economy = preload("res://scripts/team_ai/economy.gd").new()
var opening = preload("res://scripts/team_ai/build_order.gd").new()
var composition = preload("res://scripts/team_ai/composition.gd").new()
var macro = preload("res://scripts/team_ai/macro.gd").new()
var aggression = preload("res://scripts/team_ai/aggression.gd").new()
var scout = preload("res://scripts/team_ai/scouting.gd").new()
var competitive = preload("res://scripts/team_ai/competitive.gd").new()
var exploitation = preload("res://scripts/team_ai/exploitation.gd").new()
var tactics = preload("res://scripts/team_ai/tactics.gd").new()
var mapper = preload("res://scripts/team_ai/action_mapper.gd").new()
var request_skip_counts: Dictionary = {}
var micro = preload("res://scripts/team_ai/micro.gd").new()
var powers = preload("res://scripts/team_ai/hero_power.gd").new()
var conversation = preload("res://scripts/team_ai/conversation.gd").new()
var battle = preload("res://scripts/team_ai/battle_director.gd").new()
var fast_last: Dictionary = {}
var config: Dictionary = {}
var observations: Dictionary = {}
var contexts: Dictionary = {}
var native_last: Dictionary = {}
var native_signature: Dictionary = {}
var native_log_frame: Dictionary = {}
var enemy_summary_cache: Dictionary = {}
var ability_last: Dictionary = {}
var ability_cache: Dictionary = {}
var scout_goals: Dictionary = {}
var enemy_queue: Array = []
var revision: Dictionary = {}
var logbook: RefCounted
var owner_game: Node
var extent = Vector2(2000, 2000)
var hud
var human_index = -1
var tactic_cursor = 0
var recommendations: Dictionary = {}
var micro_locks: Dictionary = {}
var tactics_remaining = 0
var surprise_windows: Dictionary = {}
var enemy_task = -1
var enemy_job: RefCounted
var idle_records: Dictionary = {}
var optional_spent_usec = 0
var last_queue_log = -150

func setup(game: Node, logger: RefCounted, layer: CanvasLayer, overlay) -> bool:
	owner_game = game
	logbook = logger
	var raw = JSON.parse_string(FileAccess.get_file_as_string("res://scripts/team_ai/tuning.json"))
	var config_errors = preload("res://scripts/team_ai/config.gd").validate(raw)
	if not config_errors.is_empty():
		logbook.write("config_rejected", {"errors": config_errors})
		push_error("TEAM_AI invalid tuning")
		return false
	config = raw
	for section in ["decision", "reaction", "micro", "harass", "messages", "team", "roi", "surprise", "personality", "economy", "tactics"]:
		if not config.get(section) is Dictionary:
			push_error("TEAM_AI missing tuning section " + section)
			return false
	bus.setup(board, logbook, config.messages)
	enemy.logbook = logbook
	enemy.half_life = float(config.roi.memory_half_life_frames)
	enemy.minimum_confidence = float(config.roi.minimum_confidence)
	personality.config = config.personality
	loop.config = config.decision
	loop.logbook = logbook
	coordinator.board = board
	coordinator.bus = bus
	coordinator.config = config.team
	coordinator.config["commit_frames"] = int(config.decision.commit_frames)
	coordinator.logbook = logbook
	coordinator.ledger.board = board
	coordinator.ledger.logbook = logbook
	tactics.logbook = logbook
	tactics.config = config.tactics
	mapper.logbook = logbook
	mapper.sequence.logbook = logbook
	micro.mapper = mapper
	powers.board = board
	powers.logbook = logbook
	powers.conversation = conversation
	conversation.bus = bus
	conversation.board = board
	conversation.personality = personality
	battle.logbook = logbook
	books.load_directory("res://data/playbooks")
	for error in books.errors: logbook.write("playbook_error", error)
	hud=overlay
	logbook.write("team_runtime_start", {"schema": 1, "playbooks_loaded": books.loaded.size(), "network_enabled": false, "income_multiplier": config.economy.income_multiplier, "production_multiplier": config.economy.production_multiplier})
	return true

func clear() -> void:
	shutdown()
	conversation.clear()
	battle.state.clear()
	fast_last.clear()
	tactics.feedback.clear()
	board.clear()
	loop.clear()
	bus.inboxes.clear()
	bus.last_sent.clear()
	bus.dedup.clear()
	bus.delivered.clear()
	bus.pending_critical.clear()
	bus.awaiting.clear()
	enemy.teams.clear()
	personality.values.clear()
	personality.rngs.clear()
	personality.last_adapt.clear()
	coordinator.commitments.clear()
	coordinator.last_help.clear()
	tactics.active.clear()
	tactics.failures.clear()
	tactics.failure_frames.clear()
	mapper.unit_locks.clear()
	mapper.sequence.clear()
	request_skip_counts.clear()
	opening.selected.clear()
	opening.execution.clear()
	economy.recovery.clear()
	economy.capacity_last.clear()
	scout.visited.clear()
	scout.failed_until.clear()
	micro.last_task.clear()
	micro.last_retreat.clear()
	powers.last_cast.clear()
	powers.last_purchase.clear()
	powers.pending_cast.clear()
	observations.clear()
	contexts.clear()
	native_last.clear()
	native_signature.clear()
	native_log_frame.clear()
	enemy_summary_cache.clear()
	ability_last.clear()
	ability_cache.clear()
	scout_goals.clear()
	enemy_queue.clear()
	revision.clear()
	recommendations.clear()
	micro_locks.clear()
	macro.last_harass.clear()
	surprise_windows.clear()
	idle_records.clear()
	hud.clear_messages()
	human_index = -1
	last_queue_log = -150
	optional_spent_usec = 0

func shutdown() -> void:
	if enemy_task >= 0:
		WorkerThreadPool.wait_for_task_completion(enemy_task)
		enemy_task = -1
		enemy_job = null

func begin(bots: Array, world: Node, frame: int) -> void:
	observations.clear()
	enemy_summary_cache.clear()
	optional_spent_usec = 0
	tactics_remaining = int(config.decision.tactic_jobs)
	var census: Dictionary = world.get_census()
	extent = Vector2(float(census.get("extent_x", 2000)), float(census.get("extent_y", 2000)))
	if human_index < 0:
		for p in world.get_economy().get("players", []):
			if p.name == owner_game._local_name: human_index = int(p.index)
	for bot in bots:
		var obs: Dictionary = world.strategy_observation(bot.index)
		if not obs.get("ok", false): continue
		var members: Array = []
		for player in obs.players:
			if player.relation in ["self", "ally"]: members.append(int(player.index))
		board.register(bot.index, members, frame)
		if human_index in members: board.team_value(board.team_of(bot.index), "human_role", {"player": human_index, "role": config.team.human_role}, frame, human_index)
		personality.seed_player(bot.index, int(obs.get("match_seed", 0)))
		obs["personality"] = personality.style(bot.index)
		if frame - int(ability_last.get(bot.index, -150)) >= int(config.decision.state_detail_frames):
			ability_last[bot.index] = frame
			ability_cache[bot.index] = {"spellbook": world.get_spellbook(bot.index), "heroes": world.get_heroes(bot.index)}
			var detail: Array = []
			var owned = C.objects(obs, "self")
			for unit in owned.slice(0, int(config.decision.state_detail_limit)):
				var item = {"id": unit.id, "upgrades": world.get_upgrades(int(unit.id)), "frame": frame, "confidence": 1.0}
				if unit.structure: item["production"] = world.get_production(bot.index, int(unit.id))
				detail.append(item)
			ability_cache[bot.index]["own_details"] = detail
			ability_cache[bot.index]["detail_frame"] = frame
		obs.merge(ability_cache.get(bot.index, {}), false)
		observations[bot.index] = obs
		# Coalesce observations: one queued update per bot, never an unbounded backlog.
		if not bot.index in enemy_queue: enemy_queue.append(bot.index)
	if enemy_task >= 0 and WorkerThreadPool.is_task_completed(enemy_task):
		WorkerThreadPool.wait_for_task_completion(enemy_task)
		enemy.teams = enemy_job.model.teams
		for team in enemy_job.revisions: revision[team] = int(revision.get(team, 0)) + int(enemy_job.revisions[team])
		for record in enemy_job.events.records: logbook.write(record.event, record.data)
		enemy_task = -1
		enemy_job = null
	if enemy_task < 0 and not enemy_queue.is_empty():
		enemy_job = preload("res://scripts/team_ai/enemy_job.gd").new()
		enemy_job.model.teams = enemy.teams.duplicate(true)
		enemy_job.model.half_life = float(config.roi.memory_half_life_frames)
		enemy_job.model.minimum_confidence = float(config.roi.minimum_confidence)
		var queued_teams: Dictionary = {}
		for i in range(mini(enemy_queue.size(), int(config.decision.enemy_jobs))):
			var player = int(enemy_queue.pop_front())
			var team=board.team_of(player)
			if queued_teams.has(team): continue
			if observations.has(player):
				queued_teams[team]=true
				enemy_job.jobs.append({"team": team, "player": player, "observation": observations[player].duplicate(true), "frame": frame})
		enemy_task = WorkerThreadPool.add_task(enemy_job.run, false, "Team AI enemy observations")
	board.prune(frame)
	bus.prune(frame, observations)
	mapper.prune(frame)
	for id in micro_locks.keys():
		if int(micro_locks[id]) <= frame: micro_locks.erase(id)

func profile(player: int, base: Dictionary) -> Dictionary:
	if not personality.values.has(player): return base
	var v: Dictionary = personality.values[player]
	var out = base.duplicate(true)
	out.name = ["aggressive", "defensive", "balanced"][personality.style(player)]
	out.reserve = clampf(0.55 - float(v.risk) * 0.5, 0.15, 0.5)
	out.attack_ratio = 1.65 - float(v.aggression) * 0.9
	out.attack_minimum = int(round(9 - float(v.aggression) * 8))
	out.style = "Adaptive %s; aggression %.2f economy %.2f precision %.2f risk %.2f tech %.2f" % [out.name, v.aggression, v.economy, v.precision, v.risk, v.tech]
	return out

func decorate(obs: Dictionary, spec: Dictionary, frame: int) -> Dictionary:
	var player = int(obs.player_index)
	if not observations.has(player) or not spec.has("home"): return spec
	var team = board.team_of(player)
	var team_state: Dictionary = board.snapshot(team)
	if not enemy_summary_cache.has(team): enemy_summary_cache[team]=enemy.summary(team)
	var known_enemy: Dictionary = enemy_summary_cache[team]
	var own = C.objects(obs, "self")
	var enemies = C.objects(obs, "enemy")
	var allies = C.objects(obs, "ally")
	var v: Dictionary = personality.values[player]
	var phase = competitive.phase(own, enemies, spec.critical)
	if personality.adapt(player, {"critical": spec.critical, "advantage": phase == "finish", "money": obs.money}, frame):
		logbook.write("personality_adapt", {"player": player, "frame": frame, "axes": personality.values[player].duplicate()})
	var book = books.get_book(str(obs.faction))
	var role_value = coordinator.role(player, team, book.get("role_affinity", {}))
	var opening_value = opening.choose(player, v, role_value, book, spec.critical, frame)
	var economic_emergency = spec.critical or economy.pressured(player, own, enemies, frame)
	var eco = economy.evaluate(obs, own, economic_emergency, v, config.economy)
	var comp = composition.desired(own, enemies, allies)
	preload("res://scripts/team_ai/faction_identity.gd").apply(str(obs.faction),comp)
	var battle_state = battle.observe(player,spec.army,enemies,frame,owner_game._world)
	var feedback: Dictionary = tactics.feedback.get(player,{})
	if frame-int(feedback.get("frame",-1000))<150:
		comp.weights[1]=minf(4,float(comp.weights[1])*1.3)
		comp.weights[2]=minf(4,float(comp.weights[2])*1.2)
	for set_value in book.get("composition_sets", []):
		if set_value.get("opening", opening_value) == opening_value and set_value.has("weights"):
			for i in range(4): comp.weights[i] = clampf(float(comp.weights[i]) * float(set_value.weights[i]), 0.25, 4)
	var ready = aggression.readiness(spec.army, enemies, v, spec.critical)
	var opening_factor = aggression.opening_weights(opening_value, ready)
	for i in range(4): comp.weights[i] = clampf(float(comp.weights[i]) * float(opening_factor[i]), 0.25, 4)
	composition.protect_counters(comp)
	var scores: Dictionary = {}
	if spec.critical:
		for unit in own: micro_locks.erase(int(unit.id))
	var window = int(frame / int(config.surprise.minimum_interval_frames))
	if int(surprise_windows.get(player, {}).get("window", -1)) != window:
		surprise_windows[player] = {"window": window, "allowed": personality.imperfect(player, float(config.surprise.maximum_frequency))}
	if not spec.critical and ready > 0.7 and float(v.risk) > 0.5 and surprise_windows[player].allowed:
		for original in spec.candidates.duplicate():
			if original.kind != "attack": continue
			var feint = original.duplicate(true)
			var at = Vector2(original.x, original.y)
			var approach = at + (spec.home - at).normalized() * 900
			feint.id = "feint_" + str(original.target)
			feint.x = approach.x
			feint.y = approach.y
			feint.tactic_tag = "feint_push"
			if enemies.any(func(o): return not o.get("visible_activity", []).is_empty()): feint.tactic_tag = "bait"
			feint.max_groups = 2
			feint.description = "Feign pressure with two groups, then withdraw; only attempt when ready and home is safe"
			spec.candidates.append(feint)
			break
	for candidate in spec.candidates:
		scores[candidate.id] = macro.score(candidate, spec.army, enemies, spec.home, float(v.risk), config.roi)
		if candidate.kind == "help": scores[candidate.id] += 1
		if candidate.kind == "attack":
			if frame<int(battle_state.momentum_until): scores[candidate.id]+=1.0
			var shared_target: Dictionary = team_state.get("target",{}).get("value",{})
			if int(shared_target.get("target",-1))==int(candidate.target): scores[candidate.id]+=0.6
			for target in enemies:
				if int(target.id) == int(candidate.target):
					scores[candidate.id] += competitive.opportunity(target, spec.home)
					if not candidate.has("tactic_tag"):
						if target.get("hero", false) and float(target.get("health_ratio", 1)) < 0.4: candidate.tactic_tag = "hero_snipe"
						elif target.get("economy", false): candidate.tactic_tag = "harass"
		if candidate.kind == "scout":
			scout.observed(team, own, extent, frame)
			var old: Dictionary = scout_goals.get(player, {})
			if old.is_empty() or frame >= int(old.expires) or own.any(func(o): return Vector2(o.x, o.y).distance_to(old.get("point", Vector2.INF)) < 150):
				old = {"point": scout.choose(player, spec.home, extent, frame, board, team, int(config.decision.scout_goal_frames)), "expires": frame + int(config.decision.scout_goal_frames)}
				scout_goals[player] = old
			candidate.x = old.point.x
			candidate.y = old.point.y
		candidate.description += " Role=%s opening=%s readiness=%.2f ROI=%.2f" % [role_value, opening_value, ready, float(scores[candidate.id])]
	spec.candidates = spec.candidates.filter(func(c): return c.kind != "attack" or (float(scores.get(c.id, 0)) >= float(config.roi.minimum) and tactics.failed_count(player, str(c.id), frame) < int(config.tactics.failures_before_switch)))
	var exploit = exploitation.best(known_enemy, ["cavalry", "archers"], float(config.roi.minimum_confidence))
	if not exploit.is_empty():
		if exploit.response == "cavalry": comp.weights[3] = minf(4, float(comp.weights[3]) * (1.0 + float(exploit.score)))
		if exploit.response == "archers": comp.weights[1] = minf(4, float(comp.weights[1]) * (1.0 + float(exploit.score)))
	contexts[player] = {"team": team, "role": role_value, "phase": phase, "opening": opening_value, "economy": eco, "composition": comp, "readiness": ready, "scores": scores, "exploit": exploit, "frame": frame}
	spec.summary["team_role"] = role_value
	spec.summary["opening"] = opening_value
	spec.summary["phase"] = phase
	spec.summary["enemy_model"] = known_enemy
	spec.summary["exploitation"] = exploit
	spec.summary["attack_feedback"] = feedback
	spec["extent"] = extent
	spec.summary["team_target"] = team_state.get("target", {})
	spec.summary["personality_axes"] = v.duplicate()
	if not book.is_empty():
		spec.summary["faction_playbook"] = {"strengths": book.strengths.slice(0, 3), "weaknesses": book.weaknesses.slice(0, 3), "phase": book.phase_profile, "signature_tactics": book.signature_tactics.slice(0, 3)}
	spec.summary["team_messages"] = bus.history(player).slice(-3).map(func(m): return {"from": m.from, "type": m.type, "subject": m.subject, "payload": m.payload, "frame": m.timestamp})
	board.publish(player, {"role": role_value,"home":{"x":spec.home.x,"y":spec.home.y},"army_groups":spec.army.size(), "threat": spec.summary.home_threat_groups, "cooldowns": loop.states.get(player, {}), "scouting": scout_goals.get(player, {}), "composition": comp, "economy": eco}, frame)
	board.team_value(team, "scouting", scout.team_history(team), frame, player)
	return spec

func step(player: int, obs: Dictionary, spec: Dictionary, frame: int, world: Node) -> void:
	if not contexts.has(player): return
	var context: Dictionary = contexts[player]
	coordinator.process(player, obs, spec, frame)
	conversation.observe(player, obs, spec, context, frame, world)
	if not context.economy.emergency and not obs.get("training_economy_control",false):
		opening.execute(world, player, obs, spec, books.get_book(str(obs.faction)), board, int(context.team), frame, int(config.decision.build_interval_frames), logbook)
	if not obs.get("training_economy_control",false): economy.capacity(world,player,obs,spec,context.economy,frame,logbook)
	if frame - int(native_last.get(player, -5)) >= 5:
		native_last[player] = frame
		if world.has_method("strategy_set_policy"):
			var result: Dictionary = world.strategy_set_policy(player, {"weights": context.composition.weights, "emergency": context.economy.emergency, "economy_priority": context.economy.economy_priority, "expand": context.economy.expand or context.economy.supply_pressure, "tech_priority": 0.5 if context.economy.emergency else 0.7 + float(personality.values[player].tech) + (0.4 if context.opening == "tech" else 0.0)})
			var signature=JSON.stringify([context.composition.weights.map(func(w): return snappedf(float(w),0.01)),context.economy,context.opening])
			if signature!=str(native_signature.get(player,"")) or frame-int(native_log_frame.get(player,-150))>=150 or not result.get("ok",false):
				native_signature[player]=signature
				native_log_frame[player]=frame
				logbook.write("strategy_production_policy", {"player": player, "frame": frame, "opening": context.opening, "weights": context.composition.weights, "economy": context.economy, "result": result})
	# Separate bounded tactic queue; rotate work across bots rather than evaluate all every frame.
	if optional_spent_usec < int(config.decision.budget_usec) and tactics_remaining > 0 and frame - int(recommendations.get(player, {}).get("frame", -25)) >= 25:
		var started = Time.get_ticks_usec()
		tactics_remaining -= 1
		var choice = tactics.choose(player, spec.candidates, context.scores, context.phase, context.opening, frame)
		if not choice.is_empty(): recommendations[player] = {"plan": choice, "frame": frame}
		optional_spent_usec += Time.get_ticks_usec() - started
	powers.execute(world, player, int(context.team), obs, books.get_book(str(obs.faction)), frame, int(config.team.power_lock_frames))
	show_messages(frame)

func finish_tick(frame: int) -> void:
	mapper.sequence.flush_metrics(frame)
	if frame - last_queue_log >= 150:
		last_queue_log = frame
		if not request_skip_counts.is_empty():
			logbook.write("decision_request_skips",{"frame":frame,"counts":request_skip_counts.duplicate(true)})
			request_skip_counts.clear()
		logbook.write("team_queue_metrics", {"frame": frame, "enemy_queue": enemy_queue.size(), "enemy_worker_busy": enemy_task >= 0, "optional_cpu_usec": optional_spent_usec, "tactic_jobs_remaining": tactics_remaining})

func recommended(player: int) -> Dictionary:
	return recommendations.get(player, {}).get("plan", {}).duplicate(true)

func fast_plan(player: int, current: Dictionary, spec: Dictionary, frame: int) -> Dictionary:
	if spec.critical: return spec.candidates[0].duplicate(true) if not spec.candidates.is_empty() else {}
	if not forced(player,frame).is_empty() or frame-int(fast_last.get(player,-1000))<25: return {}
	var record: Dictionary = battle.state.get(player,{})
	var failed = not current.is_empty() and tactics.failed_count(player,str(current.id),frame)>=int(config.tactics.failures_before_switch)
	var momentum = frame<int(record.get("momentum_until",-1)) and current.get("kind","")=="attack"
	if not failed and not momentum: return {}
	fast_last[player]=frame
	var context: Dictionary = contexts.get(player,{})
	var selected: Dictionary = tactics.choose(player,spec.candidates,context.get("scores",{}),str(context.get("phase","develop")),str(context.get("opening","rush")),frame)
	if selected.is_empty() or selected.id==current.get("id",""): return {}
	logbook.write("fast_tactical_plan",{"player":player,"frame":frame,"reason":"failed_attack" if failed else "visible_front_opportunity","plan":selected})
	return selected

func idle_scan(player: int, spec: Dictionary, frame: int) -> Dictionary:
	if spec.army.is_empty() or not spec.has("home"): return {}
	var points = spec.army.slice(0, 8).map(func(o): return Vector2(o.x, o.y))
	var state: Dictionary = idle_records.get(player, {"points": points, "since": frame, "last": frame})
	var changed = points.size() != state.points.size()
	if not changed:
		for i in range(points.size()):
			if points[i].distance_to(state.points[i]) > 50: changed = true
	if changed:
		state.points = points
		state.since = frame
	idle_records[player] = state
	if frame - int(state.last) < int(config.decision.idle_scan_frames): return {}
	state.last = frame
	logbook.write("idle_scan", {"player": player, "frame": frame, "stationary_frames": frame - int(state.since), "army": spec.army.size()})
	if spec.critical or not forced(player, frame).is_empty() or frame - int(state.since) < int(config.decision.idle_stall_frames): return {}
	# Stationary fighters are not idle; never replace active combat or hero recovery.
	if spec.army.any(func(o): return o.get("combat_active",false) or o.get("moving",false) or (o.get("hero",false) and float(o.get("health_ratio",1.0))<0.8)): return {}
	if scout_goals.has(player):
		scout.failed(board.team_of(player), scout_goals[player].point, frame, int(config.decision.scout_goal_frames))
		scout_goals.erase(player)
	state.since = frame
	loop.trigger(player, frame)
	var context: Dictionary = contexts.get(player,{})
	var choices: Array = spec.candidates.filter(func(c): return c.kind in ["attack","help"] and float(context.get("readiness",0))>=0.45)
	if choices.is_empty(): choices=spec.candidates.filter(func(c): return c.kind=="scout")
	choices.sort_custom(func(a,b): return float(context.get("scores",{}).get(a.id,0))>float(context.get("scores",{}).get(b.id,0)))
	if not choices.is_empty():
		logbook.write("idle_retask",{"player":player,"frame":frame,"candidate":choices[0].id,"kind":choices[0].kind})
		return choices[0].duplicate(true)
	return {}

func forced(player: int, frame: int) -> Dictionary:
	return coordinator.forced_plan(player, frame)

func ready(player: int, spec: Dictionary, frame: int) -> bool:
	if not contexts.has(player): return false
	if spec.get("classic_rules",false) and not observations.get(player,{}).get("training_economy_control",false):
		var skip_reason = "single_legal_choice" if spec.candidates.size()<=1 else "active_commitment" if not spec.critical and not forced(player,frame).is_empty() else ""
		if not skip_reason.is_empty():
			var counts: Dictionary = request_skip_counts.get(player,{})
			counts[skip_reason]=int(counts.get(skip_reason,0))+1
			request_skip_counts[player]=counts
			return false
	var team = int(contexts[player].team)
	var delay = personality.reaction(player, int(config.reaction.min_frames), int(config.reaction.max_frames))
	return loop.consider(player, spec.summary, bool(spec.critical), int(revision.get(team, 0)), frame, delay)

func accept(player: int, plan: Dictionary, spec: Dictionary, frame: int) -> bool:
	var forced_value = forced(player, frame)
	if not forced_value.is_empty() and forced_value.id != plan.id and not spec.critical:
		if frame >= int(forced_value.locked_until) and int(plan.get("priority", 50)) > int(forced_value.priority) + 10:
			var entry: Dictionary = coordinator.commitments[player]
			coordinator.cancel(player, str(entry.id), "a higher-priority task needs attention", observations[player], frame)
		else:
			logbook.write("intent_rejected", {"player": player, "frame": frame, "reason": "active_commitment"})
			return false
	var state: Dictionary = loop.states.get(player, {})
	if not spec.critical and frame < int(state.get("lock_until", 0)) and not forced_value.is_empty() and plan.id != forced_value.id: return false
	var context: Dictionary = contexts.get(player, {})
	if not context.is_empty():
		plan["tactic_tag"] = plan.get("tactic_tag", "model_" + str(plan.kind))
		plan["reason"] = "model_choice; phase=" + str(context.phase)
		plan["issued_frame"] = frame
		board.publish(player, {"plan": plan, "focus_target": plan.target, "attack_timing": frame}, frame)
		coordinator.propose(player, plan, observations[player], frame)
	loop.accepted(player, frame, plan)
	return true

func macro_step(player: int, plan: Dictionary, obs: Dictionary, spec: Dictionary, frame: int, world: Node, order_policy: RefCounted) -> void:
	if optional_spent_usec >= int(config.decision.budget_usec): return
	var started = Time.get_ticks_usec()
	var selection = macro.detachment(player, plan, spec, C.objects(obs, "enemy"), frame, config.harass)
	optional_spent_usec += Time.get_ticks_usec() - started
	if selection.is_empty() or selection.units.is_empty(): return
	var team = board.team_of(player)
	if not board.claim(team, "harass:%d" % int(selection.target.id), player, frame, int(config.team.claim_frames)): return
	var group: Array = []
	for id in selection.units:
		if micro_locks.has(id): continue
		var state: Dictionary = world.get_object(id)
		var members: Array = []
		for member in state.get("members", []): members.append(world.get_object(int(member)))
		if state.get("ok", false) and not order_policy.combat_active(state, members): group.append(id)
	if group.is_empty(): return
	var result: Dictionary = mapper.attack(world, player, group, int(selection.target.id), obs)
	macro.last_harass[player] = frame
	if result.get("ok", false):
		for id in group: micro_locks[id] = frame + int(config.team.claim_frames)
		conversation.note(player, "division", "I detached a raiding group to pressure their economy. My main army is continuing its mission.", frame, 60)
	logbook.write("harass_detachment", {"player": player, "frame": frame, "units": group, "target": selection.target.id, "result": result, "tactic_tag": "split_push"})

func allow_expansion(player: int, at: Vector2, frame: int) -> bool:
	return economy.expansion_claim(board, board.team_of(player), player, at, frame, int(config.team.claim_frames))

func micro_step(player: int, obs: Dictionary, spec: Dictionary, frame: int, world: Node, order_policy: RefCounted) -> void:
	if not spec.has("home"): return
	if optional_spent_usec >= int(config.decision.budget_usec): return
	var own: Array = spec.army
	var micro_config = config.micro.duplicate()
	micro_config.error_probability = clampf(float(config.micro.error_probability) + (0.5 - float(personality.values[player].precision)) * 0.1, 0.05, 0.1)
	var started = Time.get_ticks_usec()
	var task_value = micro.task(player, own, C.objects(obs, "enemy"), C.objects(obs, "ally"), frame, micro_config, personality, spec.home)
	optional_spent_usec += Time.get_ticks_usec() - started
	if task_value.is_empty(): return
	if task_value.kind != "retreat" and micro_locks.has(int(task_value.unit)): return
	var state: Dictionary = world.get_object(int(task_value.unit))
	var members: Array = []
	for id in state.get("members", []): members.append(world.get_object(int(id)))
	if not state.get("ok", false) or (task_value.kind != "retreat" and order_policy.combat_active(state, members)): return
	if task_value.kind == "formation" and state.get("horde_porcupine", false): return
	if task_value.kind in ["kite", "retreat"]: task_value.point = preload("res://scripts/combat_policy.gd").bounded(task_value.point, extent)
	if not mapper.claim_unit(int(task_value.unit), player, frame, int(config.micro.cooldown_frames)): return
	var result = micro.execute(world, task_value, player, frame, obs)
	if result.get("ok", false): micro_locks[int(task_value.unit)] = frame + int(config.micro.cooldown_frames)
	logbook.write("micro_task", {"player": player, "frame": frame, "task": task_value, "result": result})

func show_messages(_frame: int) -> void:
	# Structured coordination is internal; bots never display dialogue.
	bus.delivered.clear()
