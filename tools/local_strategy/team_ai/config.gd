extends RefCounted

const KEYS = {
	"decision": ["scan_frames", "min_frames", "max_frames", "deadline_frames", "commit_frames", "http_timeout_seconds", "enemy_jobs", "tactic_jobs", "budget_usec", "model", "num_ctx", "num_predict", "build_interval_frames", "state_detail_frames", "state_detail_limit", "idle_scan_frames", "idle_stall_frames", "scout_goal_frames"],
	"reaction": ["min_frames", "max_frames", "emergency_frames"],
	"micro": ["cooldown_frames", "retreat_ratio", "kite_distance", "focus_radius", "error_probability"],
	"harass": ["max_fraction", "min_army", "interval_frames", "front_separation", "guard_radius", "maximum_guards"],
	"messages": ["interval_frames", "critical_interval_frames", "ttl_frames", "timeout_frames", "history_limit", "queue_limit", "dedup_frames", "silence_frames"],
	"team": ["claim_frames", "help_radius", "help_cooldown_frames", "power_lock_frames", "push_window_frames", "human_role", "commitment_max_frames", "travel_units_per_second", "arrival_radius"],
	"roi": ["risk_weight", "minimum", "memory_half_life_frames", "minimum_confidence"],
	"surprise": ["minimum_interval_frames", "maximum_frequency"],
	"personality": ["adapt_frames", "max_step", "minimum", "maximum"],
	"economy": ["expand_money", "emergency_reserve", "cp_margin", "income_multiplier", "production_multiplier"],
	"tactics": ["failures_before_switch", "result_frames", "plan_ttl_frames", "retry_frames"]
}

static func validate(value: Variant) -> Array:
	var errors: Array = []
	if not value is Dictionary or int(value.get("schema", -1)) != 1: return ["unsupported_config_schema"]
	for section in KEYS:
		if not value.get(section) is Dictionary:
			errors.append("missing_section:" + section)
			continue
		for key in KEYS[section]:
			if not value[section].has(key):
				errors.append("missing:" + section + "." + key)
				continue
			var item = value[section][key]
			if key in ["model", "human_role"]:
				if not item is String or item.is_empty(): errors.append("invalid_text:" + key)
			elif not (item is int or item is float) or not is_finite(float(item)) or float(item) < 0:
				errors.append("invalid_number:" + key)
			elif (key.ends_with("frames") or key.ends_with("jobs") or key in ["queue_limit", "history_limit", "num_ctx", "num_predict", "budget_usec"]) and key != "emergency_frames" and float(item) < 1:
				errors.append("nonpositive:" + key)
	if not errors.is_empty(): return errors
	if int(value.decision.commit_frames) < 15 or int(value.decision.commit_frames) > 40: errors.append("commitment_requires_3_to_8_seconds")
	if int(value.reaction.min_frames) < 3 or int(value.reaction.max_frames) > 15 or int(value.reaction.min_frames) > int(value.reaction.max_frames): errors.append("reaction_out_of_range")
	if int(value.decision.min_frames) > int(value.decision.max_frames): errors.append("decision_interval_order")
	if float(value.personality.minimum) > float(value.personality.maximum) or float(value.personality.minimum) < 0 or float(value.personality.maximum) > 1 or float(value.personality.max_step) > 0.1: errors.append("personality_out_of_range")
	for key in ["income_multiplier", "production_multiplier"]:
		if float(value.economy[key]) < 1 or float(value.economy[key]) > 2: errors.append("invalid_multiplier:" + key)
	if float(value.micro.error_probability) > 0.1 or float(value.harass.max_fraction) > 0.3 or float(value.surprise.maximum_frequency) > 0.1: errors.append("optional_error_or_detachment_out_of_range")
	return errors
