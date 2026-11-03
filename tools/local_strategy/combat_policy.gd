extends RefCounted

static func counts(obs: Dictionary, relation: String) -> Dictionary:
	var result := {"infantry": 0, "archers": 0, "pikes": 0, "cavalry": 0}
	var keys := ["infantry", "archers", "pikes", "cavalry"]
	for player in obs.players:
		if player.relation != relation: continue
		for o in player.objects:
			if o.structure or str(o.template) == "AngmarThrallMaster": continue
			var category := int(o.get("category", -1))
			if category >= 0 and category < keys.size(): result[keys[category]] += 1
	return result

static func thrall_upgrade(own: Dictionary, enemy: Dictionary) -> String:
	if enemy.cavalry > 0 and own.pikes < maxi(2, enemy.cavalry * 2):
		return "Upgrade_ThrallMasterRhudaurSpearmen"
	if enemy.pikes > 0 and own.archers <= enemy.pikes:
		return "Upgrade_ThrallMasterRhudaurSlingers"
	if enemy.archers > 0 and enemy.pikes == 0 and own.cavalry < enemy.archers:
		return "Upgrade_ThrallMasterWolfRiders"
	if own.infantry < 2: return "Upgrade_ThrallMasterOrcWarriors"
	if own.pikes < maxi(1, own.infantry / 3): return "Upgrade_ThrallMasterRhudaurSpearmen"
	if own.archers < maxi(1, own.infantry / 2): return "Upgrade_ThrallMasterRhudaurSlingers"
	return "Upgrade_ThrallMasterOrcWarriors"

static func segment_distance(a: Vector2, b: Vector2, p: Vector2) -> float:
	var delta := b - a
	if delta.length_squared() < 1.0: return p.distance_to(a)
	var t := clampf((p - a).dot(delta) / delta.length_squared(), 0.0, 1.0)
	return p.distance_to(a + delta * t)

static func blocked(at: Vector2, goal: Vector2, pikes: Array, width := 230.0) -> bool:
	for pike in pikes:
		if segment_distance(at, goal, pike) < width: return true
	return false

static func bounded(p: Vector2, extent: Vector2) -> Vector2:
	return Vector2(clampf(p.x, 80, maxf(80, extent.x - 80)), clampf(p.y, 80, maxf(80, extent.y - 80)))

static func cavalry_move(at: Vector2, goal: Vector2, pikes: Array, extent: Vector2) -> Dictionary:
	if pikes.is_empty(): return {"avoid": false}
	var nearest: Vector2 = pikes[0]
	for pike in pikes:
		if at.distance_to(pike) < at.distance_to(nearest): nearest = pike
	if at.distance_to(nearest) < 450.0:
		var away := (at - nearest).normalized()
		if away.length_squared() < 0.5: away = Vector2(1, 0)
		var best := bounded(at + away * 650.0, extent)
		var best_score := -INF
		for i in range(8):
			var candidate := bounded(at + away.rotated(float(i) * PI / 4.0) * 650.0, extent)
			var score := INF
			for pike in pikes: score = minf(score, candidate.distance_to(pike))
			# Prefer moving away first; do not choose a safe endpoint THROUGH pikes.
			var first_step := at.lerp(candidate, 0.25)
			for pike in pikes:
				if first_step.distance_to(pike) < at.distance_to(pike) - 20.0: score -= 1000.0
			if score > best_score:
				best_score = score
				best = candidate
		return {"avoid": true, "goal": best, "reason": "nearby_pikes"}
	var forward := (goal - at).normalized()
	var lookahead := at + forward * minf(900.0, at.distance_to(goal))
	if not blocked(at, lookahead, pikes): return {"avoid": false}
	var side := Vector2(-forward.y, forward.x)
	for sign_value in [1.0, -1.0]:
		var flank := bounded(at + forward * 250.0 + side * sign_value * 600.0, extent)
		if not blocked(at, flank, pikes):
			return {"avoid": true, "goal": flank, "reason": "pike_line_flank"}
	return {"avoid": true, "goal": bounded(at - forward * 400.0, extent), "reason": "pike_line_blocked"}

static func self_check() -> bool:
	var none := {"infantry": 0, "archers": 0, "pikes": 0, "cavalry": 0}
	var cavalry := none.duplicate()
	cavalry.cavalry = 3
	if thrall_upgrade(none, cavalry) != "Upgrade_ThrallMasterRhudaurSpearmen": return false
	var archers := none.duplicate()
	archers.archers = 3
	if thrall_upgrade(none, archers) != "Upgrade_ThrallMasterWolfRiders": return false
	archers.pikes = 2
	if thrall_upgrade(none, archers) == "Upgrade_ThrallMasterWolfRiders": return false
	var extent := Vector2(4000, 4000)
	if cavalry_move(Vector2(1000, 1000), Vector2(2000, 1000), [], extent).avoid: return false
	var retreat := cavalry_move(Vector2(1000, 1000), Vector2(2000, 1000), [Vector2(1200, 1000)], extent)
	if not retreat.avoid or Vector2(retreat.goal).distance_to(Vector2(1200, 1000)) <= 200: return false
	var flank := cavalry_move(Vector2(1000, 1000), Vector2(2500, 1000), [Vector2(1700, 1000)], extent)
	if not flank.avoid or blocked(Vector2(1000, 1000), flank.goal, [Vector2(1700, 1000)]): return false
	return true
