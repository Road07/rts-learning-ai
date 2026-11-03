extends RefCounted

const C = preload("res://scripts/team_ai/contracts.gd")

static func roles(objects: Array) -> Array:
	var result: Array = [0,0,0,0]
	for unit in objects:
		var category := int(unit.get("category",-1))
		if not unit.structure and not unit.get("hero",false) and category in [0,1,2,3]: result[category]+=1
	return result

static func attach(obs: Dictionary, spec: Dictionary, candidates: Array) -> Array:
	var own: Array = C.objects(obs,"self")
	var enemies: Array = C.objects(obs,"enemy")
	var friendly: Array = own+C.objects(obs,"ally")
	var heroes: Array = own.filter(func(o): return o.get("hero",false))
	var supported := 0
	for hero in heroes:
		if str(hero.template)!="AngmarHwaldar": continue
		supported=own.filter(func(o): return str(o.template) in ["AngmarRhudaurSpearmen","AngmarRhudaurSlingers"] and Vector2(o.x,o.y).distance_to(Vector2(hero.x,hero.y))<450).size()
	spec.summary["knowledge_context"]={"schema":1,"roles":roles(own),"heroes":heroes.map(func(o): return str(o.template)),"hwaldar_supported_groups":supported}
	for candidate in candidates:
		var original: Dictionary = {}
		for item in spec.candidates:
			if item.id==candidate.id: original=item; break
		var targets: Array = (enemies+friendly).filter(func(o): return int(o.id)==int(original.get("target",0)))
		if targets.is_empty(): continue
		var target: Dictionary = targets[0]
		var at := Vector2(target.x,target.y)
		candidate["facts"]={"economy":target.get("economy",false),"hero":target.get("hero",false),"structure":target.structure,"health_ratio":target.get("health_ratio",1),"distance_home":at.distance_to(spec.home),"enemy_roles":roles(enemies.filter(func(o): return Vector2(o.x,o.y).distance_to(at)<700)),"own_near":own.filter(func(o): return not o.structure and Vector2(o.x,o.y).distance_to(at)<900).size()}
	return candidates
