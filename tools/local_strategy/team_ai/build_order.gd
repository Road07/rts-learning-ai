extends RefCounted

# Opening strategies, not faction build lists; actual faction content belongs to Part 3.
const OPENINGS = ["rush", "fast_expand", "turtle", "tech", "harass"]
var selected: Dictionary = {}
var execution: Dictionary = {}

func choose(player: int, personality: Dictionary, role: String, playbook: Dictionary, critical: bool, frame: int) -> String:
	if not selected.has(player):
		var scores = {"rush": float(personality.aggression), "fast_expand": float(personality.economy), "turtle": 1.0 - float(personality.risk), "tech": float(personality.tech), "harass": (float(personality.aggression) + float(personality.precision)) / 2.0}
		if role == "economy": scores.fast_expand += 0.2
		if role == "pressure": scores.rush += 0.2
		if role == "defender": scores.turtle += 0.2
		var best = "rush"
		for name in OPENINGS:
			if scores[name] > scores[best]: best = name
		selected[player] = {"name": best, "frame": frame, "confidence": 1.0}
	if critical and selected[player].name in ["tech", "fast_expand"]: selected[player] = {"name": "turtle", "frame": frame, "confidence": 1.0}
	if playbook.has("openings") and not selected[player].name in playbook.openings: return "balanced"
	return selected[player].name

func execute(world: Node, player: int, obs: Dictionary, spec: Dictionary, book: Dictionary, board: RefCounted, team: int, frame: int, interval: int, logger: RefCounted) -> void:
	if book.is_empty() or not selected.has(player) or not spec.has("home"): return
	var name = str(selected[player].name)
	var steps: Array = book.get("opening_steps", {}).get(name, [])
	if steps.is_empty(): return
	var state: Dictionary = execution.get(player, {"last": -1000, "site": 0})
	if frame - int(state.last) < interval: return
	var own = preload("res://scripts/team_ai/contracts.gd").objects(obs, "self")
	for step_value in steps:
		var count = own.filter(func(o): return o.template == step_value.template and (o.complete or not step_value.get("wait_complete", true))).size()
		if count >= int(step_value.get("count", 1)): continue
		if int(obs.money) < int(step_value.get("min_money", 0)): return
		var builders: Array = obs.get("builders", []).filter(func(b): return b.idle and not b.get("moving", false))
		if builders.is_empty(): return
		var angles = [Vector2(1, 0), Vector2(0, 1), Vector2(-1, 0), Vector2(0, -1), Vector2(0.7, 0.7), Vector2(-0.7, 0.7), Vector2(-0.7, -0.7), Vector2(0.7, -0.7)]
		var at: Vector2 = spec.home + angles[int(state.site) % angles.size()] * float(step_value.get("home_distance", 450))
		state.site = int(state.site) + 1
		state.last = frame
		execution[player] = state
		if own.any(func(o): return o.structure and Vector2(o.x, o.y).distance_to(at) < 250): return
		if not board.claim(team, "expansion:%d:%d" % [int(at.x / 350), int(at.y / 350)], player, frame, interval * 2): return
		var result: Dictionary = world.strategy_construct(player, int(builders[0].id), str(step_value.template), at.x, at.y)
		logger.write("opening_build_order", {"player": player, "frame": frame, "opening": name, "template": step_value.template, "result": result})
		return
