extends RefCounted

const C = preload("res://scripts/team_ai/contracts.gd")
const HERO_FACTIONS = ["FactionWild", "FactionMordor", "FactionAngmar"]

static func help_limit(obs: Dictionary, target: int, size: int) -> int:
	for player in obs.get("players", []):
		if player.relation != "ally" or int(player.get("farms_lost", 0)) < 1: continue
		for building in player.objects:
			if int(building.id) == target and building.get("base", false):
				return int(floor(size * (0.6 if float(building.get("health_ratio", 1)) < 0.5 else 0.3)))
	return 0

static func raid(plan: Dictionary, obs: Dictionary) -> bool:
	if plan.get("kind", "") != "attack": return false
	return C.objects(obs, "enemy").any(func(o): return int(o.id) == int(plan.target) and o.get("economy", false))

static func soldiers(army: Array, plan: Dictionary, obs: Dictionary) -> Array:
	if not obs.has("classic_opening") or not raid(plan, obs): return army
	return army.filter(func(o): return not o.get("hero", false) and int(o.get("category", -1)) == 0) + army.filter(func(o): return o.get("hero", false) or int(o.get("category", -1)) != 0)

static func constrain(obs: Dictionary, spec: Dictionary) -> Dictionary:
	if not obs.has("classic_opening"): return spec
	spec["classic_rules"] = true
	var candidates: Array = []
	for item in spec.candidates:
		if item.kind == "help":
			item["max_groups"] = help_limit(obs, int(item.target), spec.army.size())
			if int(item.max_groups) == 0: continue
		elif raid(item, obs):
			item["max_groups"] = spec.army.filter(func(o): return not o.get("hero", false) and int(o.get("category", -1)) == 0).size()
			if int(item.max_groups) == 0: continue
			item.description += " Raid resource buildings with swordsmen; ranged groups stay in defence."
		candidates.append(item)
	spec.candidates = candidates
	return spec

static func repair_target(own: Array, enemies: Array, early: bool) -> Dictionary:
	var candidates: Array = own.filter(func(o): return o.structure and float(o.get("health_ratio", 1)) < 0.5 and (not o.get("base", false) if early else o.get("base", false)))
	# Early repair protects infantry production, never an arbitrary damaged farm.
	if early: candidates = candidates.filter(func(o): return o.get("army_factory",false) or str(o.template) in ["GondorBarracks", "ElvenBarracks", "DwarfBarracks", "GoblinCave", "MordorOrcPit", "IsengardUrukPit", "AngmarBarracks"])
	candidates = candidates.filter(func(o): return enemies.any(func(e): return not e.structure and Vector2(e.x, e.y).distance_to(Vector2(o.x, o.y)) < 900))
	candidates.sort_custom(func(a,b): return float(a.health_ratio) < float(b.health_ratio))
	return {} if candidates.is_empty() else candidates[0]
