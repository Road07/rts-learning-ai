extends RefCounted

const C=preload("res://scripts/team_ai/contracts.gd")

static func army(objects: Array) -> Array:
	return objects.filter(func(o): return not o.get("structure",false) and o.get("mobile",false) and not o.get("builder",false))

static func value(objects: Array) -> float:
	var total=0.0
	for o in objects: total+=float(o.get("own_cost",o.get("public_cost",0)))*float(o.get("health_ratio",1.0))
	return total

static func collect(obs: Dictionary, home: Vector2) -> Dictionary:
	var own: Array=C.objects(obs,"self")
	var enemies: Array=C.objects(obs,"enemy")
	var troops: Array=army(own)
	var farms: Array=own.filter(func(o): return o.get("economy",false))
	var factories: Array=own.filter(func(o): return o.get("army_factory",false))
	var heroes: Array=own.filter(func(o): return o.get("hero",false))
	var bases: Array=own.filter(func(o): return o.get("base",false))
	var result={"schema":"rts-mechanics-v1","economy_count":farms.size(),"economy_mean_share":0.0,"income_base_per_second":0.0,"factories":factories.size(),"idle_factories":0,"queued_items":0,"builders":own.filter(func(o): return o.get("builder",false)).size(),"unfinished_buildings":own.filter(func(o): return o.get("structure",false) and not o.get("complete",true)).size(),"army_value":value(troops),"hero_value":value(heroes),"hero_lowest_health":1.0,"base_health":0.0,"cp_used_fraction":float(obs.cp_used)/maxf(1,float(obs.cp_limit)),"wall_hubs":own.filter(func(o): return o.get("wall_hub",false)).size(),"wall_segments":own.filter(func(o): return o.get("wall_segment",false)).size(),"home_threat_value":0.0,"ally_threat_value":0.0,"army_home_fraction":0.0}
	for o in farms:
		result.economy_mean_share+=float(o.get("resource_share",0))
		result.income_base_per_second+=float(o.get("base_income_per_second",0))
	result.economy_mean_share/=maxi(1,farms.size())
	for o in factories:
		result.queued_items+=int(o.get("queue_count",0))
		if int(o.get("queue_count",0))==0 and o.get("complete",true) and not o.get("factory_disabled",false): result.idle_factories+=1
	for o in heroes: result.hero_lowest_health=minf(result.hero_lowest_health,float(o.get("health_ratio",1)))
	for o in bases: result.base_health+=float(o.get("health_ratio",1))
	result.base_health/=maxi(1,bases.size())
	var names=["swords","ranged","pikes","cavalry"]
	for role in 4:
		result["own_"+names[role]]=troops.filter(func(o): return int(o.get("category",-1))==role).size()
		result["enemy_"+names[role]]=enemies.filter(func(o): return int(o.get("category",-1))==role).size()
	result.home_threat_value=value(enemies.filter(func(o): return o.get("armed",false) and Vector2(o.x,o.y).distance_to(home)<1100))
	result.army_home_fraction=float(troops.filter(func(o): return Vector2(o.x,o.y).distance_to(home)<1100).size())/maxi(1,troops.size())
	var ally_bases: Array=C.objects(obs,"ally").filter(func(o): return o.get("base",false))
	result.ally_threat_value=value(enemies.filter(func(o): return o.get("armed",false) and ally_bases.any(func(b): return Vector2(o.x,o.y).distance_to(Vector2(b.x,b.y))<1100)))
	result["game_seconds"]=float(obs.observed_frame)/5.0
	return result

static func annotate(candidate: Dictionary, obs: Dictionary) -> void:
	var ids: Array=candidate.get("units",[])
	var selected: Array=army(C.objects(obs,"self")).filter(func(o): return int(o.id) in ids)
	var enemies: Array=C.objects(obs,"enemy")
	var target: Array=(enemies+C.objects(obs,"ally")).filter(func(o): return int(o.id)==int(candidate.get("target",0)))
	var at=Vector2(float(candidate.get("x",0)),float(candidate.get("y",0)))
	var center=Vector2.ZERO
	var hp=0.0
	for o in selected:
		center+=Vector2(o.x,o.y)
		hp+=float(o.get("health_ratio",1))
	if not selected.is_empty(): center/=selected.size(); hp/=selected.size()
	var m={"selected_value":value(selected),"selected_health":hp,"group_fraction":float(selected.size())/maxi(1,army(C.objects(obs,"self")).size()),"selected_cavalry_fraction":float(selected.filter(func(o): return int(o.get("category",-1))==3).size())/maxi(1,selected.size()),"target_distance":center.distance_to(at) if not selected.is_empty() else 0.0,"enemy_local_value":value(enemies.filter(func(o): return Vector2(o.x,o.y).distance_to(at)<650)),"own_local_value":value(army(C.objects(obs,"self")).filter(func(o): return Vector2(o.x,o.y).distance_to(at)<650))}
	if not target.is_empty():
		m["target_health"]=float(target[0].get("health_ratio",1))
		m["target_value"]=float(target[0].get("public_cost",0))
		m["target_economy"]=float(bool(target[0].get("economy",false)))
		m["target_pikes"]=float(int(target[0].get("category",-1))==2)
	candidate["mechanics"]=m
	var templates: Dictionary={}
	for o in selected: templates[str(o.template)]=int(templates.get(str(o.template),0))+1
	candidate["rule_refs"]={"selected":templates,"target":str(target[0].template) if not target.is_empty() else ""}
