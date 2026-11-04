extends RefCounted

static func run(arena: Node) -> Dictionary:
	var world: Node=arena._world
	var owner: Dictionary=arena.participants[0]
	var player: int=int(owner.index)
	var proof={"fixture":true,"scope":"mechanics API probes, not learned expert actions"}
	var options: Array=world.strategy_production_options(player)
	var farms: Array=options.filter(func(o): return o.kind=="build" and o.get("economy",false))
	proof["farm_sites"]=farms
	arena.require(farms.size()>=2,"mechanics: multiple farm positions missing")
	var names: Dictionary={}
	for farm in farms:
		names[str(farm.id)]=true
		arena.require(float(farm.farm_share)>=0 and float(farm.farm_share)<=1,"mechanics: invalid native farm share")
	arena.require(names.size()==farms.size(),"mechanics: duplicate coordinate identities")
	var hub: int=arena.spawn("DwarvenWallHubSmall",owner,owner.home+Vector2(400,-650),true)
	world.advance(0.4)
	var all: Array=world.strategy_model_options(player,true)
	proof["seed_blocked_after_anchor"]=not all.any(func(o): return o.get("wall_seed",false))
	arena.require(proof.seed_blocked_after_anchor,"mechanics: independent hub still offered")
	var spans: Array=all.filter(func(o): return o.kind=="wall" and int(o.producer)==hub)
	proof["span_choices"]=spans
	arena.require(not spans.is_empty(),"mechanics: native connected wall plans missing")
	if not spans.is_empty():
		var before: Array=world.get_player_objects(str(owner.name)).map(func(o): return int(o.id))
		var result: Dictionary=world.strategy_model_action(player,{"id":spans[0].id})
		world.advance(0.6)
		var created: Array=world.get_player_objects(str(owner.name)).filter(func(o): return int(o.id) not in before)
		proof["span_result"]=result
		proof["created_wall_objects"]=created
		arena.require(result.get("ok",false) and created.size()>1,"mechanics: wall span did not create connected pieces")
	if not farms.is_empty():
		var result: Dictionary=world.strategy_model_action(player,{"id":farms[0].id})
		proof["farm_result"]=result
		if result.get("ok",false):
			arena.require(str(result.operation.id)==str(farms[0].id) and float(result.operation.x)==float(farms[0].x) and float(result.operation.y)==float(farms[0].y),"mechanics: farm target moved during dispatch")
		else: arena.require(false,"mechanics: farm option was not dispatchable")
	return proof
