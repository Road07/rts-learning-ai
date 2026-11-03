extends RefCounted

# Explicit fixture/API probes, never human demonstrations or expert action labels.
static func pick(world: Node, player: int, kind: String, producer: int = 0) -> Dictionary:
	for op in world.strategy_model_options(player,true):
		if str(op.kind)==kind and (producer==0 or int(op.producer)==producer): return op
	return {}

static func submit(world: Node, player: int, op: Dictionary, report: Dictionary, label: String) -> void:
	if op.is_empty():
		report.probes[label]={"offered":false}
		return
	var result: Dictionary = world.strategy_model_action(player,{"id":op.id})
	report.probes[label]={"offered":true,"operation":op,"result":result}
	world.advance(0.4)

static func prepare(arena: Node) -> Dictionary:
	var world: Node = arena._world
	var owner: Dictionary = arena.participants[0]
	var player: int = int(owner.index)
	var report: Dictionary = {"fixture":true,"scope":"legal command interface probes; not learned tactics","probes":{},"player":player}
	var thrall: int = arena.spawn("AngmarThrallMaster",owner,owner.home+Vector2(120,40))
	var pike: int = arena.spawn("IsengardPikemanHorde",owner,owner.home+Vector2(160,40))
	var entrance: int = arena.spawn("DwarvenMineShaft",owner,owner.home+Vector2(-120,0),true)
	var exit_mine: int = arena.spawn("DwarvenMineShaft",owner,owner.home+Vector2(-1050,0),true)
	var rider: int = arena.spawn("DwarvenGuardianHorde",owner,owner.home+Vector2(-115,0))
	world.debug_add_science_points(player,10)
	world.advance(0.4)
	var offered: Dictionary = {}
	for op in world.strategy_model_options(player,true): offered[str(op.kind)]=int(offered.get(str(op.kind),0))+1
	report["offered_families"]=offered
	var hero: Dictionary = pick(world,player,"hero")
	submit(world,player,hero,report,"hero_purchase")
	if not hero.is_empty():
		report.probes.hero_purchase["in_production"]=world.get_heroes(player,int(hero.producer)).any(func(h): return str(h.template)==str(hero.template) and bool(h.in_production))
		submit(world,player,pick(world,player,"cancel",int(hero.producer)),report,"production_cancel")
		report.probes.production_cancel["queue_empty"]=world.get_production(player,int(hero.producer)).get("queue",[]).is_empty()
	var existing: Array = world.get_player_objects(owner.name).filter(func(o): return str(o.template)=="DwarvenGloin")
	if not existing.is_empty():
		world.kill_hero(int(existing[0].id))
		world.advance(0.4)
		var revive: Dictionary = {}
		for op in world.strategy_model_options(player,true):
			if op.kind=="hero" and bool(op.get("reviving",false)): revive=op; break
		submit(world,player,revive,report,"hero_revive")
		if not revive.is_empty(): submit(world,player,pick(world,player,"cancel",int(revive.producer)),report,"revive_cancel")
	submit(world,player,pick(world,player,"science"),report,"science_purchase")
	var book: Dictionary = world.get_spellbook(player)
	if int(book.get("book",0))>0: world.ready_object_powers(int(book.book))
	report["spellbook"]=world.get_spellbook(player)
	var forts: Array = world.get_player_objects(owner.name).filter(func(o): return o.get("commandcenter",false))
	if not forts.is_empty(): world.damage_object(int(forts[0].id),float(world.get_object(int(forts[0].id)).max_health)*0.6)
	var power: Dictionary = pick(world,player,"power")
	var triggers = 0
	if not power.is_empty():
		for item in world.get_object_powers(int(power.producer)):
			if str(item.name)==str(power.template): triggers=int(item.get("triggers",0))
	submit(world,player,power,report,"power_cast")
	if not power.is_empty():
		for item in world.get_object_powers(int(power.producer)):
			if str(item.name)==str(power.template): report.probes.power_cast["trigger_increased"]=int(item.get("triggers",0))>triggers
	var hero_owner: Dictionary = arena.participants[3]
	for actor in preload("res://scripts/team_ai/contracts.gd").objects(world.strategy_observation(int(hero_owner.index)),"self"):
		if not actor.get("hero",false): continue
		world.gain_hero_levels(int(actor.id),5)
		world.ready_object_powers(int(actor.id))
		var ability: Dictionary = pick(world,int(hero_owner.index),"power",int(actor.id))
		var before_triggers = 0
		if not ability.is_empty():
			for item in world.get_object_powers(int(actor.id)):
				if str(item.name)==str(ability.template): before_triggers=int(item.get("triggers",0))
		submit(world,int(hero_owner.index),ability,report,"hero_ability")
		report["ability_source"]=int(actor.id)
		report["ability_triggers_before"]=before_triggers
		break
	submit(world,player,pick(world,player,"research",thrall),report,"thrall_research")
	report["thrall"]=thrall
	report["pike"]=pike
	report["original_formation"]=world.get_object(pike).get("template","")
	var before: Dictionary = world.get_object(pike)
	submit(world,player,pick(world,player,"formation",pike),report,"formation")
	report.probes.formation["template_changed"]=str(world.get_object(pike).get("template",""))!=str(before.get("template",""))
	report.probes.formation["porcupine_after_command"]=world.get_object(pike).get("horde_porcupine",false)
	submit(world,player,pick(world,player,"stance",pike),report,"stance")
	report.probes.stance["observed_stance"]=world.get_object(pike).get("stance",-1)
	var enter: Dictionary = {}
	for op in world.strategy_model_options(player,true):
		if op.kind=="enter" and int(op.producer)==rider and int(op.target)==entrance: enter=op; break
	submit(world,player,enter,report,"tunnel_enter")
	report["entrance"]=entrance
	report["exit"]=exit_mine
	report["rider"]=rider
	if not hero.is_empty():
		report["foreign_command_rejected"]=not world.strategy_model_action(int(arena.participants[3].index),{"id":hero.id}).get("ok",false)
	report["invented_command_rejected"]=not world.strategy_model_action(player,{"id":"research:999999:invented:0:0"}).get("ok",false)
	return report

static func poll(arena: Node, report: Dictionary) -> void:
	if report.is_empty(): return
	var world: Node = arena._world
	var player: int = int(report.player)
	if report.probes.get("hero_ability",{}).get("offered",false):
		for item in world.get_object_powers(int(report.get("ability_source",0))):
			if str(item.name)==str(report.probes.hero_ability.operation.template): report.probes.hero_ability["trigger_increased"]=int(item.get("triggers",0))>int(report.ability_triggers_before)
	report["thrall_object_upgrades"]=world.get_upgrades(int(report.thrall)).get("object",[])
	report["thrall_result_template"]=world.get_object(int(report.thrall)).get("template","")
	var player_name: String = str(arena.participants[0].name)
	report["summoned_hordes"]=world.get_player_objects(player_name).filter(func(o): return str(o.template)=="AngmarOrcWarriors").map(func(o): return int(o.id))
	report["formation_final_template"]=world.get_object(int(report.pike)).get("template","")
	report["formation_porcupine"]=world.get_object(int(report.pike)).get("horde_porcupine",false)
	var garrison: Dictionary = world.get_garrison(int(report.entrance))
	report["tunnel_state"]=garrison
	if int(garrison.get("count",0))>0 and not report.probes.has("tunnel_exit"):
		var exit_op: Dictionary = pick(world,player,"exit",int(report.exit))
		if not exit_op.is_empty():
			# The game applies this through its normal command stream next frame.
			report.probes["tunnel_exit"]={"offered":true,"operation":exit_op,"result":world.strategy_model_action(player,{"id":exit_op.id})}
	if report.probes.has("tunnel_exit"): report["riders_after_exit"]=world.get_garrison(int(report.exit)).get("count",-1)
	var rider: Dictionary = world.get_object(int(report.rider))
	var exit_object: Dictionary = world.get_object(int(report.exit))
	report["rider_after_exit"]=rider
	if rider.get("ok",false) and exit_object.get("ok",false):
		report["rider_near_exit"]=Vector2(rider.x,rider.y).distance_to(Vector2(exit_object.x,exit_object.y))<300 and int(rider.get("contained_by",0))==0
