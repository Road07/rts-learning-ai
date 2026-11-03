extends RefCounted

const POOL = ["early_rush", "harass", "fast_expand", "tech_rush", "turtle_counter", "feint_push", "split_push", "bait", "hero_snipe", "siege_stall", "map_control"]
var active: Dictionary = {}
var failures: Dictionary = {}
var failure_frames: Dictionary = {}
var feedback: Dictionary = {}
var logbook: RefCounted
var config: Dictionary

func failed_count(player: int, candidate: String, frame: int) -> int:
	var key = "%d:%s" % [player, candidate]
	if frame - int(failure_frames.get(key, -1000)) >= int(config.retry_frames): return 0
	return int(failures.get(key, 0))

func choose(player: int, candidates: Array, scores: Dictionary, phase: String, opening: String, frame: int) -> Dictionary:
	var selected: Dictionary = {}
	var best_score = -INF
	var alternatives = candidates.filter(func(c): return failed_count(player, str(c.id), frame) < int(config.failures_before_switch))
	for candidate in candidates:
		if not alternatives.is_empty() and failed_count(player, str(candidate.id), frame) >= int(config.failures_before_switch): continue
		var score = float(scores.get(candidate.id, 0))
		if candidate.kind == "defend" and phase == "stabilize": score += 10
		if candidate.kind == "scout" and phase == "develop": score += 1
		if candidate.kind == "attack" and phase == "finish": score += 1
		var fail_key = "%d:%s" % [player, candidate.id]
		score -= int(failures.get(fail_key, 0)) * 0.75
		if score > best_score:
			best_score = score
			selected = candidate.duplicate(true)
	if selected.is_empty(): return selected
	if not selected.has("tactic_tag"): selected.tactic_tag = "turtle_counter" if phase == "stabilize" else "early_rush" if opening == "rush" and frame < 900 else "map_control" if selected.kind == "scout" else "timing_push" if selected.kind == "attack" else selected.kind
	selected.reason = "phase=%s opening=%s ROI=%.2f" % [phase, opening, best_score]
	return selected

func track(player: int, plan: Dictionary, army_count: int, enemy_count: int, frame: int, obs: Dictionary = {}, world: Node = null) -> void:
	var previous: Dictionary = active.get(player, {})
	if not previous.is_empty() and frame - int(previous.frame) >= int(config.result_frames):
		var own = preload("res://scripts/team_ai/contracts.gd").objects(obs,"self")
		var seen = preload("res://scripts/team_ai/contracts.gd").objects(obs,"enemy")
		var losses = 0
		if world!=null:
			for id in previous.get("units",[]):
				if not world.get_object(int(id)).get("ok",false): losses+=1
		var target: Array = seen.filter(func(o): return int(o.id)==int(previous.plan.target))
		var damage = not target.is_empty() and float(target[0].get("health_ratio",1))<float(previous.get("target_health",1))-0.05
		var at = Vector2(previous.plan.x,previous.plan.y)
		var contact = own.any(func(o): return not o.structure and Vector2(o.x,o.y).distance_to(at)<800)
		var success = damage and losses<=maxi(1,int(previous.army)/3)
		var failed = losses>=2 or (contact and not target.is_empty() and not damage)
		var key = "%d:%s" % [player, previous.plan.id]
		if previous.plan.kind == "attack" and (success or failed):
			failures[key] = 0 if success else failed_count(player, str(previous.plan.id), frame) + 1
			failure_frames[key] = frame
			if failed: feedback[player]={"frame":frame,"reason":"attrition" if losses>=2 else "stalled","target":previous.plan.target}
		logbook.write("tactic_result", {"player": player, "frame": frame, "tactic_tag": previous.plan.get("tactic_tag", "legacy"), "target_damage_observed": success, "failed":failed,"own_losses": losses, "reason": "own object losses and currently visible target health; fog disappearance is not a kill"})
		active.erase(player)
	if not active.has(player):
		var own = preload("res://scripts/team_ai/contracts.gd").objects(obs,"self")
		var targets = preload("res://scripts/team_ai/contracts.gd").objects(obs,"enemy").filter(func(o): return int(o.id)==int(plan.target))
		active[player] = {"plan": plan.duplicate(true), "army": army_count, "enemies": enemy_count, "frame": frame,"units":own.filter(func(o): return not o.structure).map(func(o): return int(o.id)),"target_health":float(targets[0].get("health_ratio",1)) if not targets.is_empty() else 1.0}
