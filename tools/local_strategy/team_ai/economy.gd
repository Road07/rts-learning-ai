extends RefCounted

var recovery: Dictionary = {}
var capacity_last: Dictionary = {}

func pressured(player: int, own: Array, enemies: Array, frame: int) -> bool:
	var assets = own.filter(func(o): return o.get("structure", false) and (o.get("base", false) or o.get("economy", false) or o.get("army_factory", false)))
	var threatened = enemies.any(func(e): return not e.get("structure", false) and int(e.get("category", -1)) >= 0 and assets.any(func(b): return Vector2(b.x, b.y).distance_to(Vector2(e.x, e.y)) < 1100))
	var previous: Dictionary = recovery.get(player, {"until": -1, "assets": {}})
	var current := {}
	for building in assets:
		current[int(building.id)] = float(building.get("health_ratio", 1.0))
		if previous.assets.has(int(building.id)) and float(current[int(building.id)]) < float(previous.assets[int(building.id)]) - 0.02: threatened = true
	for id in previous.assets:
		if not current.has(id): threatened = true
	if threatened: previous.until = frame + 75
	previous.assets = current
	recovery[player] = previous
	return frame < int(previous.until)

func evaluate(obs: Dictionary, own: Array, critical: bool, personality: Dictionary, config: Dictionary) -> Dictionary:
	var cp_free = int(obs.cp_limit) - int(obs.cp_used)
	var farms = own.filter(func(o): return o.get("economy", false)).size()
	var factories = own.filter(func(o): return o.get("army_factory",false) and o.get("complete",false) and not o.get("factory_disabled",false))
	var idle = factories.filter(func(o): return int(o.get("queue_count",0))==0).size()
	var saturated = factories.size()>0 and idle==0
	return {"emergency": critical, "expand": not critical and int(obs.money) >= int(config.expand_money) and not (idle>0 and cp_free>=50 and int(obs.money)<1500), "supply_pressure": cp_free < int(config.cp_margin), "farm_count": farms, "economy_priority": 0.5 if critical or idle>0 else clampf(0.7 + float(personality.economy) + (0.5 if cp_free < int(config.cp_margin) else 0.0), 0.5, 2.0), "reserve": 0,"idle_factories":idle,"saturated":saturated,"add_capacity":saturated and int(obs.money)>=1800 and cp_free>=80}

func capacity(world: Node, player: int, obs: Dictionary, spec: Dictionary, decision: Dictionary, frame: int, logger: RefCounted) -> void:
	if not decision.get("add_capacity",false) or frame-int(capacity_last.get(player,-1000))<75: return
	var own = preload("res://scripts/team_ai/contracts.gd").objects(obs,"self")
	var factories = own.filter(func(o): return o.get("army_factory",false))
	var limit = int(preload("res://scripts/team_ai/faction_identity.gd").PROFILES.get(obs.faction,{"capacity":2}).capacity)+1
	if factories.size()>=limit or factories.any(func(o): return not o.get("complete",false)): return
	var builders: Array = obs.get("builders",[]).filter(func(b): return b.idle and not b.get("moving",false))
	if builders.is_empty() or factories.is_empty(): return
	capacity_last[player]=frame
	# Duplicate a real, already owned legal producer, never an invented faction action.
	var template = str(factories[0].template)
	var visible_enemies = preload("res://scripts/team_ai/contracts.gd").objects(obs,"enemy")
	for direction in [Vector2(1,0),Vector2(0,1),Vector2(-1,0),Vector2(0,-1),Vector2(0.7,0.7),Vector2(-0.7,-0.7)]:
		var at: Vector2 = spec.home+direction*650
		if own.any(func(o): return o.structure and Vector2(o.x,o.y).distance_to(at)<300): continue
		if visible_enemies.any(func(o): return not o.structure and Vector2(o.x,o.y).distance_to(at)<900): continue
		var result: Dictionary = world.strategy_construct(player,int(builders[0].id),template,at.x,at.y)
		logger.write("production_capacity",{"player":player,"frame":frame,"template":template,"result":result})
		if result.get("ok",false): return

func expansion_claim(board: RefCounted, team: int, player: int, at: Vector2, frame: int, ttl: int) -> bool:
	return board.claim(team, "expansion:%d:%d" % [int(at.x / 350), int(at.y / 350)], player, frame, ttl)
