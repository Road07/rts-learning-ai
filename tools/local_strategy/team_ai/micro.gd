extends RefCounted

var last_task: Dictionary = {}
var mapper: RefCounted
var last_retreat: Dictionary = {}

func task(player: int, army: Array, enemies: Array, allies: Array, frame: int, config: Dictionary, personality: RefCounted, home: Vector2) -> Dictionary:
	if frame - int(last_task.get(player, -1000)) < int(config.cooldown_frames): return {}
	var best: Dictionary = {}
	var best_score = -INF
	for id in last_retreat.keys():
		if frame-int(last_retreat[id])>150: last_retreat.erase(id)
	for unit in army:
		if not unit.get("hero", false) and float(unit.get("health_ratio", 1.0)) < float(config.retreat_ratio):
			if Vector2(unit.x,unit.y).distance_to(home)<=320 or frame-int(last_retreat.get(int(unit.id),-1000))<50: continue
			return {"kind": "retreat", "unit": int(unit.id), "point": home}
	if personality.imperfect(player, float(config.error_probability)): return {}
	for target in enemies:
		if target.structure: continue
		for unit in army:
			if unit.get("hero", false) or int(unit.get("category", -1)) == 7: continue
			if float(unit.get("health_ratio",1))<float(config.retreat_ratio): continue
			var distance = Vector2(unit.x, unit.y).distance_to(Vector2(target.x, target.y))
			if distance > float(config.focus_radius): continue
			if int(unit.get("category", -1)) == 2 and int(target.get("category", -1)) == 3:
				return {"kind": "formation", "unit": int(unit.id)}
			if int(unit.get("category", -1)) == 1 and int(target.get("category", -1)) == 0 and distance < float(config.kite_distance):
				var away = (Vector2(unit.x, unit.y) - Vector2(target.x, target.y)).normalized()
				return {"kind": "kite", "unit": int(unit.id), "point": Vector2(unit.x, unit.y) + away * 150}
			var score = 1.0 - float(target.get("health_ratio", 1.0)) + (1.5 if target.get("hero", false) else 0.0)
			if int(target.get("category", -1)) == 2 and int(unit.get("category", -1)) == 3: continue
			if score > best_score:
				best_score = score
				best = {"kind": "focus", "unit": int(unit.id), "target": int(target.id)}
	return best

func execute(world: Node, task_value: Dictionary, player: int, frame: int, obs: Dictionary) -> Dictionary:
	if task_value.is_empty(): return {}
	last_task[player] = frame
	if task_value.kind in ["kite", "retreat"]:
		var at: Vector2 = task_value.point
		var result: Dictionary = mapper.move(world, player, [task_value.unit], at, "move", obs)
		if task_value.kind=="retreat" and result.get("ok",false): last_retreat[int(task_value.unit)]=frame
		return result
	if task_value.kind == "formation": return mapper.formation(world, player, int(task_value.unit), obs)
	return mapper.attack(world, player, [task_value.unit], int(task_value.target), obs)
