extends RefCounted

func phase(own: Array, enemy: Array, critical: bool) -> String:
	var ours = own.filter(func(o): return not o.structure).size()
	var theirs = enemy.filter(func(o): return not o.structure).size()
	if critical or ours * 2 < theirs: return "stabilize"
	if ours >= 8 and ours > theirs * 1.5: return "finish"
	return "pressure" if ours >= 3 else "develop"

func opportunity(target: Dictionary, home: Vector2) -> float:
	var value = 0.0
	if target.get("economy", false): value += 0.4
	if target.get("hero", false) and float(target.get("health_ratio", 1.0)) < 0.35: value += 0.8
	if not target.structure and Vector2(target.x, target.y).distance_to(home) < 900: value += 0.25
	return value
