extends RefCounted

var game: Node
var logbook: RefCounted
var policy: RefCounted
var heroes: Dictionary = {}
var sites: Dictionary = {}
var transit: Dictionary = {}
var transport_cooldown: Dictionary = {}
var style_logged: Dictionary = {}
var site_attempts: Dictionary = {}
var last_tunnel_sample: Dictionary = {}
var coordination: RefCounted
var support_guards: Dictionary = {}
var fandom_roles: Dictionary = {}

func setup(owner_game: Node, diagnostics: RefCounted, order_policy: RefCounted) -> void:
	game = owner_game
	logbook = diagnostics
	policy = order_policy
	if FileAccess.file_exists("res://data/fandom_knowledge.json"):
		var knowledge = JSON.parse_string(FileAccess.get_file_as_string("res://data/fandom_knowledge.json"))
		assert(knowledge is Dictionary and knowledge.get("schema",0)==1,"Invalid Fandom hero catalogue")
		fandom_roles=knowledge.get("heroes",{})

func clear() -> void:
	heroes.clear()
	sites.clear()
	transit.clear()
	transport_cooldown.clear()
	style_logged.clear()
	site_attempts.clear()
	last_tunnel_sample.clear()
	support_guards.clear()

static func style_profile(base: Dictionary, index: int) -> Dictionary:
	var out := base.duplicate(true)
	var names := ["aggressive", "defensive", "balanced"]
	index = clampi(index, 0, 2)
	out["name"] = names[index]
	out["reserve"] = [0.15, 0.5, 0.3][index]
	out["attack_ratio"] = [0.9, 1.5, 1.15][index]
	out["attack_minimum"] = [3, 8, 5][index]
	out["style"] = [
		"Aggressive: pressure and raid when feasible, exploit exposed targets, keep a small home reserve; defend serious emergencies.",
		"Defensive: expand economy while assembling a large upgraded mixed army with heroes; protect allies; launch a coordinated counterattack when ready. Scout rather than waiting blindly.",
		"Balanced: grow economy and a mixed upgraded army with heroes; alternate pressure, support and defence according to observed opportunities."
	][index]
	return out

func observe_style(bot: Dictionary, obs: Dictionary, frame: int) -> void:
	if style_logged.has(bot.index): return
	var profile := style_profile({}, int(obs.get("personality", 2)))
	style_logged[bot.index] = true
	logbook.write("personality", {"frame": frame, "player": bot.index, "faction": bot.faction, "style": profile.name})
	print("GENERAL_AI personality player=%d faction=%s style=%s" % [int(bot.index), str(bot.faction), str(profile.name)])

static func should_retreat(ratio: float, recovering: bool) -> bool:
	return ratio < (0.8 if recovering else 0.20)

func protect_hero(bot: Dictionary, unit: Dictionary, state: Dictionary, home: Vector2, frame: int) -> bool:
	if not unit.get("hero", false): return false
	var maximum := float(state.get("max_health", 0))
	if maximum <= 0: return false
	var id := int(unit.id)
	var ratio := float(state.get("health", 0)) / maximum
	var recovering := heroes.has(id)
	if not should_retreat(ratio, recovering):
		if recovering:
			heroes.erase(id)
			policy.assignments.erase(id)
			logbook.write("hero_recovered", {"frame": frame, "player": bot.index, "unit": id, "health_ratio": ratio})
		return false
	var previous := int(heroes.get(id, -1000))
	heroes[id] = previous
	var at := Vector2(float(state.x), float(state.y))
	if at.distance_to(home) > 220 and (not state.get("moving", false) or frame - previous >= 50) and frame - previous >= 25:
		var result: Dictionary = game._world.order_move([id], home.x, home.y, {"type": "move", "player": bot.index})
		if result.get("ok", false):
			heroes[id] = frame
			policy.assignments.erase(id)
			logbook.write("hero_retreat", {"frame": frame, "player": bot.index, "unit": id, "template": unit.template, "health_ratio": ratio})
	return true

func escort_hero(bot: Dictionary, unit: Dictionary, state: Dictionary, army: Array, home: Vector2, frame: int) -> bool:
	if not unit.get("hero",false): return false
	var soldiers: Array = army.filter(func(o): return not o.get("hero",false) and int(o.get("category",-1)) in [0,1,2,3] and not in_transit(int(o.id),frame))
	var at = Vector2(state.x,state.y)
	var beneficiaries: Array = fandom_roles.get(str(unit.template),{}).get("beneficiaries",[])
	if not beneficiaries.is_empty():
		var compatible: Array = soldiers.filter(func(o): return str(o.template) in beneficiaries and Vector2(o.x,o.y).distance_to(at)<1000)
		if not compatible.is_empty(): soldiers=compatible
	soldiers.sort_custom(func(a,b): return Vector2(a.x,a.y).distance_squared_to(at)<Vector2(b.x,b.y).distance_squared_to(at))
	var anchor = home
	if not soldiers.is_empty():
		anchor=Vector2(soldiers[0].x,soldiers[0].y)
		anchor+=(home-anchor).normalized()*140
	var members: Array = []
	if not policy.combat_active(state,members) and policy.needs_order(int(unit.id),at,anchor,anchor,frame,bool(state.get("moving",false)),false,true):
		var result: Dictionary = game._world.order_move([unit.id],anchor.x,anchor.y,{"type":"move","player":bot.index})
		logbook.write("hero_escort",{"player":bot.index,"frame":frame,"hero":unit.id,"result":result})
	return true

func logistics(bot: Dictionary, obs: Dictionary, spec: Dictionary, plan: Dictionary, frame: int) -> void:
	if bot.faction not in ["FactionDwarves", "FactionWild"] or not spec.has("home"): return
	for id in support_guards.keys():
		var guard: Dictionary = support_guards[id]
		if guard.player != bot.index: continue
		var state: Dictionary = game._world.get_object(int(id))
		if spec.critical or plan.get("kind", "defend") in ["attack", "help"] or not state.get("ok", false):
			support_guards.erase(id)
			transit.erase(id)
			policy.assignments.erase(id)
			continue
		transit[id] = frame
		if not guard.get("ordered", false) and int(state.get("contained_by", 0)) == 0:
			var result: Dictionary = game._world.order_move([id], guard.at.x, guard.at.y, {"type": "move", "player": bot.index})
			guard.ordered = result.get("ok", false)
			support_guards[id] = guard
	var own: Array = []
	var enemies: Array = []
	var allies: Array = []
	for p in obs.players:
		if p.relation == "self": own = p.objects
		elif p.relation == "enemy": enemies.append_array(p.objects)
		elif p.relation == "ally": allies.append_array(p.objects)
	var tunnels: Array = own.filter(func(o): return o.get("tunnel", false) and o.get("complete", false))
	# Release any tunnel riders at a safe exit even if the strategic plan changes.
	if tunnels.size() >= 2:
		transport(bot, tunnels, own, enemies, spec, plan, frame)
	if obs.get("training_economy_control",false): return # model owns new construction in training
	var home: Vector2 = spec.home
	if spec.critical or tunnels.is_empty(): return
	if coordination != null and coordination.contexts.get(bot.index, {}).get("economy", {}).get("emergency", false): return
	# First link goes to a living ally, independently of LocalModel's current attack plan.
	var ally_bases: Array = allies.filter(func(o): return o.get("base", false) and o.get("complete", false) and Vector2(o.x, o.y).distance_to(home) > 900)
	ally_bases.sort_custom(func(a, b): return Vector2(a.x, a.y).distance_squared_to(home) < Vector2(b.x, b.y).distance_squared_to(home))
	var support_link := not ally_bases.is_empty()
	var target: Vector2 = Vector2(ally_bases[0].x, ally_bases[0].y) if support_link else Vector2(float(plan.get("x", home.x)), float(plan.get("y", home.y)))
	if support_link:
		for building in own:
			if building.get("tunnel", false) and Vector2(building.x, building.y).distance_to(target) < 900:
				support_link = false
				break
		if not support_link: target = Vector2(float(plan.get("x", home.x)), float(plan.get("y", home.y)))
	if support_link:
		if frame < 25 or spec.army.is_empty() or int(obs.money) < 500: return
	else:
		if plan.get("kind", "defend") != "attack" or spec.army.size() < 3 or int(obs.money) < 700 or frame < 300: return
		if home.distance_to(target) < 1800: return
		for tunnel in tunnels:
			if Vector2(tunnel.x, tunnel.y).distance_to(target) < 1500: return
	var job: Dictionary = sites.get(bot.index, {})
	if not job.is_empty() and frame - int(job.since) > 600:
		sites.erase(bot.index)
		site_attempts[bot.index] = int(site_attempts.get(bot.index, 0)) + 1
		return
	if job.is_empty():
		var builders: Array = obs.get("builders", []).filter(func(b): return b.idle and not b.get("moving", false))
		if builders.is_empty(): return
		var direction := (target - home).normalized()
		var side := Vector2(-direction.y, direction.x)
		var size: Dictionary = game._world.get_census()
		var extent := Vector2(float(size.get("extent_x", 2000)), float(size.get("extent_y", 2000)))
		var offsets := [350.0, -350.0, 550.0, -550.0] if support_link else [700.0, -700.0, 1000.0, -1000.0]
		for i in range(offsets.size()):
			var offset: float = offsets[(i + int(site_attempts.get(bot.index, 0))) % offsets.size()]
			var site: Vector2 = preload("res://scripts/combat_policy.gd").bounded(target - direction * (450.0 if support_link else 1100.0) + side * offset, extent)
			if unsafe(site, enemies, 650): continue
			var overlap := false
			for building in own:
				if building.structure and Vector2(building.x, building.y).distance_to(site) < 350: overlap = true
			if overlap: continue
			if coordination != null and not coordination.allow_expansion(bot.index, site, frame): continue
			job = {"builder": int(builders[0].id), "site": site, "since": frame, "last": -1000, "requested": false, "support_link": support_link}
			sites[bot.index] = job
			logbook.write("forward_tunnel_plan", {"frame": frame, "player": bot.index, "builder": job.builder, "x": site.x, "y": site.y, "support_link": support_link})
			break
	if job.is_empty() or job.requested or frame - int(job.last) < 10: return
	var state: Dictionary = game._world.get_object(int(job.builder))
	if not state.get("ok", false) or state.get("destroyed", false) or unsafe(job.site, enemies, 650):
		sites.erase(bot.index)
		return
	var result: Dictionary = game._world.strategy_build_forward(bot.index, job.builder, job.site.x, job.site.y)
	job.last = frame
	if result.get("ok", false):
		job.requested = true
		logbook.write("forward_tunnel_build", {"frame": frame, "player": bot.index, "builder": job.builder, "x": job.site.x, "y": job.site.y})
	elif result.get("reason", "") == "unexplored":
		game._world.order_move([job.builder], job.site.x, job.site.y, {"type": "move", "player": bot.index})
	elif result.get("reason", "") == "illegal_site":
		sites.erase(bot.index)
		site_attempts[bot.index] = int(site_attempts.get(bot.index, 0)) + 1
		logbook.write("forward_tunnel_refused", {"frame": frame, "player": bot.index, "reason": "illegal_site"})
		return
	elif result.get("reason", "") == "builder_busy":
		sites.erase(bot.index)
		return
	# Busy builders are not interrupted; the plan will retry after the cooldown.
	sites[bot.index] = job

static func unsafe(at: Vector2, enemies: Array, radius: float) -> bool:
	for enemy in enemies:
		if Vector2(enemy.x, enemy.y).distance_to(at) < radius: return true
	return false

func transport(bot: Dictionary, tunnels: Array, own: Array, enemies: Array, spec: Dictionary, plan: Dictionary, frame: int) -> void:
	var home: Vector2 = spec.home
	var target := Vector2(float(plan.get("x", home.x)), float(plan.get("y", home.y)))
	var support_route: bool = plan.get("kind", "defend") not in ["attack", "help"]
	if obs_classic(spec) and support_route: return
	if support_route and not spec.critical:
		var nearest := INF
		for p in spec.get("allied_bases", []):
			var distance := home.distance_to(Vector2(p.x, p.y))
			if distance < nearest and distance > 900:
				nearest = distance
				target = Vector2(p.x, p.y)
	var entrance: Dictionary = tunnels[0]
	var exit_tunnel: Dictionary = tunnels[0]
	for tunnel in tunnels:
		if Vector2(tunnel.x, tunnel.y).distance_to(home) < Vector2(entrance.x, entrance.y).distance_to(home): entrance = tunnel
		if Vector2(tunnel.x, tunnel.y).distance_to(target) < Vector2(exit_tunnel.x, exit_tunnel.y).distance_to(target): exit_tunnel = tunnel
	if spec.critical or unsafe(Vector2(exit_tunnel.x, exit_tunnel.y), enemies, 500): exit_tunnel = entrance
	var garrison: Dictionary = game._world.get_garrison(int(exit_tunnel.id))
	if frame - int(last_tunnel_sample.get(bot.index, -150)) >= 150:
		last_tunnel_sample[bot.index] = frame
		logbook.write("tunnel_status", {"frame": frame, "player": bot.index, "entrance": entrance.id, "exit": exit_tunnel.id, "garrison": garrison})
	if int(garrison.get("count", 0)) > 0 and int(garrison.get("entering", 0)) == 0 and frame - int(transport_cooldown.get(bot.index, -1000)) >= 5:
		var result: Dictionary = game._world.order_evacuate(int(exit_tunnel.id))
		if result.get("ok", false):
			transport_cooldown[bot.index] = frame
			if support_route and exit_tunnel.id != entrance.id:
				for id in garrison.get("riders", []): support_guards[int(id)] = {"player": bot.index, "at": target, "ordered": false}
			logbook.write("tunnel_exit", {"frame": frame, "player": bot.index, "exit": exit_tunnel.id, "riders": garrison.get("riders", [])})
	for unit in own:
		var id := int(unit.id)
		if transit.has(id) and Vector2(unit.x, unit.y).distance_to(Vector2(exit_tunnel.x, exit_tunnel.y)) < 400 and frame - int(transit[id]) > 10:
			transit.erase(id)
			policy.assignments.erase(id)
	if spec.critical or exit_tunnel.id == entrance.id or Vector2(exit_tunnel.x, exit_tunnel.y).distance_to(Vector2(entrance.x, entrance.y)) < 700: return
	if frame<int(plan.get("wait_until",0)): return
	if frame - int(transport_cooldown.get(bot.index, -1000)) < 5: return
	if int(garrison.get("count", 0)) > 0: return
	var group: Array = []
	var count := maxi(1, spec.army.size() - maxi(1, int(ceil(spec.army.size() * float(spec.reserve)))))
	if obs_classic(spec) and plan.kind=="help": count=mini(count,preload("res://scripts/team_ai/user_rules.gd").help_limit(coordination.observations.get(bot.index,{}),int(plan.target),spec.army.size()))
	if count<=0: return
	for unit in spec.army:
		if unit.get("hero", false) or int(unit.get("category", -1)) not in [0, 1, 2, 3] or in_transit(int(unit.id), frame): continue
		var at := Vector2(unit.x, unit.y)
		var via := at.distance_to(Vector2(entrance.x, entrance.y)) + Vector2(exit_tunnel.x, exit_tunnel.y).distance_to(target)
		if at.distance_to(Vector2(entrance.x, entrance.y)) < 800 and via + 250 < at.distance_to(target):
			var state: Dictionary = game._world.get_object(int(unit.id))
			var members: Array = []
			for id in state.get("members", []): members.append(game._world.get_object(int(id)))
			if int(state.get("contained_by", 0)) != 0 or policy.combat_active(state, members): continue
			group.append(int(unit.id))
			if group.size() >= mini(3, count): break
	if group.is_empty(): return
	var result: Dictionary = game._world.order_garrison(group, int(entrance.id))
	if result.get("ok", false):
		transport_cooldown[bot.index] = frame
		for id in group: transit[id] = frame
		logbook.write("tunnel_enter", {"frame": frame, "player": bot.index, "entrance": entrance.id, "destination": exit_tunnel.id, "units": group})

func in_transit(id: int, frame: int) -> bool:
	if not transit.has(id): return false
	if frame - int(transit[id]) > 150:
		transit.erase(id)
		return false
	return true

static func self_check() -> bool:
	if not should_retreat(0.19, false) or should_retreat(0.20, false) or should_retreat(0.3, false): return false
	if not should_retreat(0.6, true) or should_retreat(0.85, true): return false
	for i in range(3):
		if style_profile({"style": "old"}, i).name != ["aggressive", "defensive", "balanced"][i]: return false
	if not unsafe(Vector2.ZERO, [{"x": 10, "y": 10}], 100): return false
	return true

static func obs_classic(spec: Dictionary) -> bool:
	return bool(spec.get("classic_rules",false))
