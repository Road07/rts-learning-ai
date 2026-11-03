extends RefCounted

# Fast tactical safety, separate from model inference. Reads filtered observations only.
var state: Dictionary = {}
var logbook: RefCounted

static func strength(units: Array, opponent: Array = []) -> float:
	var total = 0.0
	var pikes = opponent.filter(func(o): return not o.structure and int(o.get("category",-1))==2).size()
	for unit in units:
		if unit.get("structure",false):
			if unit.get("armed",false): total += 1.5*float(unit.get("health_ratio",1))
			continue
		var value = sqrt(maxf(80,float(unit.get("public_cost",300)))/300.0)
		value *= float(unit.get("health_ratio",1))
		if unit.get("hero",false): value *= 1.4
		if int(unit.get("category",-1))==3 and pikes>0: value *= 0.45
		total += value
	return total

static func near(units: Array, at: Vector2, radius: float) -> Array:
	return units.filter(func(o): return Vector2(o.x,o.y).distance_to(at)<radius)

func observe(player: int, own: Array, enemies: Array, frame: int, world: Node) -> Dictionary:
	var record: Dictionary = state.get(player,{"known":[],"loss_until":-1,"losses":0,"front_enemy":0.0,"momentum_until":-1,"cohort":[],"plan":"","last_log":-1000})
	if int(record.get("observed",-1))==frame: return record
	record.observed=frame
	var ids: Array = own.map(func(o): return int(o.id))
	var lost = 0
	for id in record.known:
		if not ids.has(id) and not world.get_object(int(id)).get("ok",false): lost+=1
	if lost>0:
		record.loss_until=frame+100
		record.losses=int(record.losses)+lost
		record.cohort=record.cohort.filter(func(id): return ids.has(id))
		logbook.write("battle_losses",{"player":player,"frame":frame,"confirmed_own_losses":lost})
	elif frame>=int(record.loss_until): record.losses=0
	var contact: Array = enemies.filter(func(e): return own.any(func(o): return Vector2(o.x,o.y).distance_to(Vector2(e.x,e.y))<800))
	var power = strength(contact,own)
	# A clearing visible front is an opportunity estimate, never a claimed enemy kill.
	if float(record.front_enemy)>1.5 and power<float(record.front_enemy)*0.45 and lost==0 and own.size()>=3:
		record.momentum_until=frame+75
	record.front_enemy=power
	record.known=ids
	state[player]=record
	return record

func movement(player: int, plan: Dictionary, spec: Dictionary, obs: Dictionary, frame: int, excluded: Array) -> Dictionary:
	var result={"hold":[],"rally":spec.home,"retreat":false,"reason":"advance","approach":Vector2(plan.x,plan.y)}
	if plan.kind not in ["attack","help"] or spec.critical: return result
	var record: Dictionary = state.get(player,{})
	if record.is_empty(): return result
	var army: Array = spec.army.filter(func(o): return not excluded.has(int(o.id)) and not o.get("hero",false) and int(o.get("category",-1))!=7)
	if army.is_empty(): return result
	var goal = Vector2(plan.x,plan.y)
	var enemies = preload("res://scripts/team_ai/contracts.gd").objects(obs,"enemy")
	var friendly = army+preload("res://scripts/team_ai/contracts.gd").objects(obs,"ally").filter(func(o): return not o.structure and Vector2(o.x,o.y).distance_to(goal)<1200)
	var front = near(enemies,goal,850)
	var local = near(friendly,goal,1000)
	var ratio = strength(local,front)/maxf(0.5,strength(front,local))
	var center = Vector2.ZERO
	for unit in army: center+=Vector2(unit.x,unit.y)
	center/=army.size()
	result.rally=spec.home.lerp(goal,minf(0.3,600.0/maxf(1,spec.home.distance_to(goal))))
	if near(enemies,result.rally,700).size()>0: result.rally=spec.home
	if record.plan!=plan.id:
		record.plan=plan.id
		record.cohort=[]
		record.released=false
		record.flanked=false
	var feedback: Dictionary = spec.get("summary",{}).get("attack_feedback",{})
	if not record.get("flanked",false) and feedback.get("reason","")=="stalled" and int(feedback.get("target",-1))==int(plan.target) and frame-int(feedback.get("frame",-1000))<150:
		var direction=(spec.home-goal).normalized()
		var waypoint=goal+direction*800+Vector2(-direction.y,direction.x)*(500 if player%2==0 else -500)
		waypoint=preload("res://scripts/combat_policy.gd").bounded(waypoint,spec.get("extent",Vector2(10000,10000)))
		if near(army,waypoint,400).is_empty(): result.approach=waypoint
		else: record.flanked=true
	var minimum = 3 if plan.kind=="attack" and obs.faction in ["FactionWild","FactionMordor"] else 2
	if plan.get("tactic_tag","") in ["feint_push","bait"]: minimum=1
	if obs.has("classic_opening") and preload("res://scripts/team_ai/user_rules.gd").raid(plan,obs): minimum=mini(minimum,army.size())
	if record.cohort.filter(func(id): return army.any(func(o): return int(o.id)==int(id))).size()<minimum: record.released=false
	var at_rally = near(army,result.rally,550)
	var fighting = near(army,goal,1000)
	var bad_fight = not front.is_empty() and not fighting.is_empty() and ratio<0.65
	if bad_fight:
		result.retreat=true
		result.reason="unfavorable_local_fight"
		record.cohort=[]
		record.released=false
	elif not record.get("released",false):
		var recovering = frame<int(record.loss_until) and army.size()<minimum+mini(2,int(record.losses)/2)
		var enough = (at_rally.size()>=minimum or fighting.size()>=minimum) and (front.is_empty() or strength(friendly,front)>=strength(front,friendly)*0.9)
		if enough and not recovering:
			record.cohort=army.map(func(o): return int(o.id))
			record.released=true
		else:
			result.hold=army.map(func(o): return int(o.id))
			result.reason="assemble_after_losses" if recovering else "assemble_cohort"
	else:
		var newcomers = army.filter(func(o): return not record.cohort.has(int(o.id)))
		var gathered = near(newcomers,result.rally,550)
		if gathered.size()>=2 or (front.is_empty() and frame<int(record.momentum_until)):
			for unit in gathered: record.cohort.append(int(unit.id))
		result.hold=newcomers.filter(func(o): return not record.cohort.has(int(o.id))).map(func(o): return int(o.id))
	if frame-int(record.last_log)>=25:
		logbook.write("battle_directive",{"player":player,"frame":frame,"plan":plan.id,"reason":result.reason,"hold":result.hold,"local_ratio":ratio,"cohort":record.cohort})
		record.last_log=frame
	state[player]=record
	return result
