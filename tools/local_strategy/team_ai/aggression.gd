extends RefCounted

func readiness(army: Array, enemies: Array, personality: Dictionary, critical: bool) -> float:
	if critical: return 0.0
	var healthy = 0.0
	for unit in army: healthy += float(unit.get("health_ratio", 1.0))
	var enemy_count = enemies.filter(func(o): return not o.structure).size()
	return clampf(healthy / maxf(5.0, enemy_count * 1.4) * (0.6 + float(personality.aggression)), 0, 1)

func opening_weights(opening: String, readiness_score: float) -> Array:
	match opening:
		"rush": return [1.5, 1.0, 1.0, 1.0]
		"harass": return [1.0, 1.0, 1.0, 1.4]
		"turtle": return [1.0, 1.3, 1.4, 0.7]
		"tech": return [0.8, 1.2, 1.2, 1.0]
	return [1.0, 1.0, 1.0, 1.0] if readiness_score < 0.8 else [1.1, 1.1, 1.0, 1.1]
