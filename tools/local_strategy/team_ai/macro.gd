extends RefCounted

var last_harass: Dictionary = {}

func score(candidate: Dictionary, own: Array, enemies: Array, home: Vector2, risk: float, config: Dictionary) -> float:
	var at = Vector2(candidate.x, candidate.y)
	var threat = enemies.filter(func(o): return not o.structure and Vector2(o.x, o.y).distance_to(at) < 600).size()
	if candidate.kind == "defend": return 1.0
	if candidate.kind == "scout": return 1.5
	var committed = own.slice(0, int(candidate.get("max_groups", own.size())))
	var damage_potential = 0.0
	var committed_cost = 0.0
	for unit in committed:
		var cost = maxf(100, float(unit.get("public_cost", 300))) / 300.0
		damage_potential += cost * float(unit.get("health_ratio", 1))
		committed_cost += cost
	var enemy_strength = 0.0
	for unit in enemies:
		if Vector2(unit.x, unit.y).distance_to(at) >= 600: continue
		if unit.structure and not unit.get("armed", false): continue
		var cost = maxf(100, float(unit.get("public_cost", 300))) / (1500.0 if unit.structure else 300.0)
		enemy_strength += cost * float(unit.get("health_ratio", 1))
	var success = clampf(damage_potential / maxf(0.1, damage_potential + enemy_strength), 0.1, 1.0)
	var value = 1.5 if candidate.kind == "help" else 1.0
	for enemy in enemies:
		if int(enemy.id) == int(candidate.target):
			value += 1.0 if enemy.get("economy", false) else 0.0
			value += 1.2 if enemy.get("hero", false) and float(enemy.get("health_ratio", 1)) < 0.4 else 0.0
			if enemy.structure and not enemy.get("economy",false) and not enemy.get("base",false):
				var name = str(enemy.template).to_lower()
				if ["barrack","pit","stable","palace","den","range","fissure"].any(func(token): return token in name): value+=1.2
	# Penalize local counter mismatches and the loss of fighting health.
	var effective = preload("res://scripts/team_ai/battle_director.gd").strength(committed,preload("res://scripts/team_ai/battle_director.gd").near(enemies,at,700))
	if committed.size()>0: damage_potential*=effective/maxf(0.1,float(committed.size()))
	success=clampf(damage_potential/maxf(0.1,damage_potential+enemy_strength),0.1,1.0)
	var exposure = at.distance_to(home) / 2000.0 * (1.0 - risk)
	var expected_cost = committed_cost * (1.0 - success)
	var defence_gap = exposure + threat * 0.1 * float(config.risk_weight)
	return value * damage_potential * success / maxf(0.2, 0.5 + expected_cost + defence_gap)

func detachment(player: int, plan: Dictionary, spec: Dictionary, enemies: Array, frame: int, config: Dictionary) -> Dictionary:
	if spec.critical or plan.kind != "attack" or spec.army.size() < int(config.min_army): return {}
	if frame - int(last_harass.get(player, -1000)) < int(config.interval_frames): return {}
	var main = Vector2(plan.x, plan.y)
	var target: Dictionary = {}
	for enemy in enemies:
		if enemy.structure and enemy.get("economy", false) and Vector2(enemy.x, enemy.y).distance_to(main) > float(config.front_separation):
			var guards = enemies.filter(func(o): return not o.structure and Vector2(o.x, o.y).distance_to(Vector2(enemy.x, enemy.y)) < float(config.guard_radius)).size()
			if guards <= int(config.maximum_guards): target = enemy
	if target.is_empty(): return {}
	var group: Array = []
	var active_count = maxi(0, spec.army.size() - maxi(1, int(ceil(spec.army.size() * float(spec.reserve)))))
	var maximum = maxi(1, int(spec.army.size() * float(config.max_fraction)))
	for i in range(active_count - 1, -1, -1):
		var unit: Dictionary = spec.army[i]
		if unit.get("hero", false) or int(unit.get("category", -1)) == 7 or float(unit.get("health_ratio",1))<0.45: continue
		if spec.get("classic_rules",false) and int(unit.get("category",-1))!=0: continue
		group.append(int(unit.id))
		if group.size() >= maximum: break
	return {"units": group, "target": target}
