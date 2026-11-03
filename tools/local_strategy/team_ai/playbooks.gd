extends RefCounted

const FACTIONS = preload("res://scripts/team_ai/contracts.gd").FACTIONS
const REQUIRED = ["strengths", "weaknesses", "phase_profile", "power_spikes", "vulnerable_windows", "composition_sets", "counter_table", "anti_x", "harass", "anti_harass", "heroes", "powers", "signature_tactics", "matchup_notes", "role_affinity", "personality_fit"]
var loaded: Dictionary = {}
var errors: Array = []

func validate(value: Variant, faction: String, capabilities: Array = []) -> Array:
	var output: Array = []
	if not value is Dictionary: return ["playbook_not_object"]
	if faction not in FACTIONS or value.get("faction", "") != faction: output.append("faction_mismatch")
	if int(value.get("schema", -1)) != 1: output.append("unsupported_schema")
	for key in REQUIRED:
		if not value.has(key): output.append("missing:" + key)
		elif key in ["phase_profile", "counter_table", "anti_x", "harass", "anti_harass", "matchup_notes", "role_affinity", "personality_fit"]:
			if not value[key] is Dictionary: output.append("expected_object:" + key)
		elif not value[key] is Array: output.append("expected_array:" + key)
	if not output.is_empty(): return output
	for role in value.role_affinity:
		if role not in ["pressure", "economy", "defender", "flex"] or not (value.role_affinity[role] is float or value.role_affinity[role] is int): output.append("invalid_role_affinity")
	for hero in value.get("heroes", []):
		if not hero is String or "ringhero" in str(hero).to_lower() or str(hero) in ["MordorSauron", "MordorSauron_RingHero", "ElvenGaladriel"]: output.append("invalid_or_ring_hero")
	for tactic in value.get("signature_tactics", []):
		if not tactic is String: output.append("invalid_tactic")
	for set_value in value.get("composition_sets", []):
		if not set_value is Dictionary:
			output.append("invalid_composition_set")
			continue
		if set_value.has("weights"):
			if not set_value.weights is Array or set_value.weights.size() != 4: output.append("four_role_weights_required")
			else:
				for weight in set_value.weights:
					if not (weight is float or weight is int) or not is_finite(float(weight)) or float(weight) < 0.25 or float(weight) > 4: output.append("invalid_role_weight")
	for power in value.get("powers", []):
		if not power is Dictionary:
			output.append("power_descriptor_required")
			continue
		if not power.get("name") is String or str(power.get("name", "")).is_empty(): output.append("missing_power_name")
		if not power.get("radius", 0) is float and not power.get("radius", 0) is int: output.append("invalid_power_radius")
		elif not is_finite(float(power.get("radius", 0))) or float(power.get("radius", 0)) <= 0: output.append("invalid_power_radius")
		if power.get("target", "ground_enemy") not in ["ground_enemy", "enemy", "friendly", "self"]: output.append("invalid_power_target")
		if power.get("target", "ground_enemy") == "self" and not power.has("caster_template"): output.append("self_power_requires_caster")
		if power.has("science") and (not preload("res://scripts/team_ai/contracts.gd").integral(power.get("point_cost")) or int(power.get("point_cost", -1)) < 0): output.append("science_cost_required")
	if not capabilities.is_empty():
		for set_value in value.get("composition_sets", []):
			if not set_value is Dictionary: output.append("invalid_composition_set")
			else:
				for unit in set_value.get("units", []):
					if str(unit) not in capabilities: output.append("unknown_unit:" + str(unit))
	if value.has("opening_steps"):
		if not value.opening_steps is Dictionary: output.append("opening_steps_not_object")
		else:
			for name in value.opening_steps:
				if name not in ["rush", "fast_expand", "turtle", "tech", "harass"] or not value.opening_steps[name] is Array:
					output.append("invalid_opening")
					continue
				for step_value in value.opening_steps[name]:
					if not step_value is Dictionary or not step_value.get("template") is String: output.append("invalid_opening_step")
					elif int(step_value.get("count", 1)) < 1 or float(step_value.get("home_distance", 450)) <= 0: output.append("invalid_opening_step_range")
	return output

func load_directory(path: String) -> void:
	loaded.clear()
	errors.clear()
	# No faction content is supplied in Part 2. Existing retail policies remain active.
	for faction in FACTIONS:
		var file = path.path_join(faction + ".json")
		if not FileAccess.file_exists(file): continue
		var data = JSON.parse_string(FileAccess.get_file_as_string(file))
		var issues = validate(data, faction)
		if issues.is_empty(): loaded[faction] = data
		else: errors.append({"file": file, "errors": issues})

func get_book(faction: String) -> Dictionary:
	return loaded.get(faction, {}).duplicate(true)
