extends RefCounted

# Only validated Part 3 descriptors may enable an ability. Never guess targeting/AOE.
var board: RefCounted
var logbook: RefCounted
var last_cast: Dictionary = {}
var last_purchase: Dictionary = {}
var pending_cast: Dictionary = {}
var conversation: RefCounted

func execute(world: Node, player: int, team: int, obs: Dictionary, book: Dictionary, frame: int, ttl: int) -> void:
	confirm_pending(world, player, team, obs, frame, ttl)
	if pending_cast.has(player) or frame - int(last_cast.get(player, -1000)) < ttl: return
	if obs.has("classic_opening") and repair(world,player,obs,frame): return
	if book.is_empty(): return
	var contracts = preload("res://scripts/team_ai/contracts.gd")
	var enemies: Array = contracts.objects(obs, "enemy")
	var own: Array = contracts.objects(obs, "self")
	var friendly: Array = own + contracts.objects(obs, "ally")
	var spellbook: Dictionary = world.get_spellbook(player)
	var reserve = int(book.get("phase_profile", {}).get("power_points_reserve", 0))
	for descriptor in book.get("powers", []):
		if not descriptor is Dictionary or not descriptor.get("enabled", false): continue
		var name = str(descriptor.name)
		if obs.has("classic_opening") and name=="SpellBookRebuild": continue
		var caster = 0
		var owned = false
		var ready = false
		var triggers_before = 0
		if descriptor.has("caster_template"):
			for unit in own:
				if unit.template != descriptor.caster_template or not unit.get("hero", false) or float(unit.get("health_ratio", 1)) < 0.35: continue
				for power in world.get_object_powers(int(unit.id)):
					if power.name == name and power.ready and not power.paused:
						caster = int(unit.id)
						ready = true
						owned = true
						triggers_before = int(power.get("triggers", 0))
		else:
			for power in spellbook.get("powers", []):
				if power.name == name:
					owned = bool(power.owned)
					ready = bool(power.ready)
					triggers_before = int(power.get("triggers", 0))
		if not owned and descriptor.has("science") and frame - int(last_purchase.get(player, -1000)) >= ttl:
			if int(spellbook.get("points", 0)) >= int(descriptor.get("point_cost", 0)) + reserve:
				var queued: bool = world.purchase_science(player, str(descriptor.science))
				last_purchase[player] = frame
				logbook.write("science_purchase_order", {"player": player, "frame": frame, "science": descriptor.science, "accepted": queued})
			return
		if not owned or not ready: continue
		if conversation != null and int(descriptor.get("point_cost", 0)) >= 15:
			conversation.note(player, "power_ready", "A major spellbook power is ready. I am waiting for a suitable target.", frame, 40)
		var target_type = str(descriptor.get("target", "ground_enemy"))
		var targets = friendly if target_type in ["friendly", "self"] else enemies
		for target in targets:
			if target_type == "self" and int(target.id) != caster: continue
			if target_type == "friendly" and float(target.get("health_ratio", 1)) > float(descriptor.get("heal_below", 0.5)): continue
			var at = Vector2(target.x, target.y)
			var radius = float(descriptor.get("radius", 0))
			if radius <= 0: continue
			var enemy_count = targets.filter(func(o): return not o.structure and Vector2(o.x, o.y).distance_to(at) < radius).size()
			if enemy_count < int(descriptor.get("min_targets", 3)): continue
			if target_type not in ["self", "friendly"] and descriptor.get("friendly_fire", true) and friendly.any(func(o): return Vector2(o.x, o.y).distance_to(at) < radius): continue
			var combo = str(descriptor.get("combo_group", name))
			var previous: Dictionary = board.snapshot(team).get("last_power", {}).get("value", {})
			if descriptor.has("after"):
				if not previous.get("confirmed", false) or previous.get("group", "") != descriptor.after or frame - int(previous.get("frame", -1000)) > ttl: continue
				if at.distance_to(Vector2(float(previous.get("x", -100000)), float(previous.get("y", -100000)))) > radius: continue
			var key = "power:%s:%d:%d" % [combo, int(at.x / radius), int(at.y / radius)]
			if not board.claim(team, key, player, frame, ttl): continue
			var accepted = false
			if caster > 0:
				if target_type == "ground_enemy": accepted = world.cast_object_power_at(player, caster, name, at.x, at.y)
				else: accepted = world.cast_object_power(player, caster, name, 0 if target_type == "self" else int(target.id))
			else: accepted = world.cast_special_power(player, name, at.x, at.y)
			last_cast[player] = frame
			if accepted: pending_cast[player] = {"group": combo, "frame": frame, "target": int(target.id), "caster": caster, "name": name, "x": at.x, "y": at.y, "triggers_before": triggers_before}
			if accepted and conversation != null:
				conversation.note(player, "power_order", "I ordered an ability to follow up on our ally's power." if descriptor.has("after") else "I ordered a hero ability. I will confirm when it activates." if caster > 0 else "I ordered a spellbook power and am checking its activation.", frame, 70, ttl)
			logbook.write("team_power", {"player": player, "frame": frame, "power": name, "caster": caster, "target": target.id, "accepted": accepted})
			return

func confirm_pending(world: Node, player: int, team: int, obs: Dictionary, frame: int, ttl: int) -> void:
	if not pending_cast.has(player): return
	var pending: Dictionary = pending_cast[player]
	var powers: Array = []
	if int(pending.caster) == 0:
		powers = world.get_spellbook(player).get("powers", [])
	else:
		var own: Array = preload("res://scripts/team_ai/contracts.gd").objects(obs, "self")
		if own.any(func(o): return int(o.id) == int(pending.caster)): powers = world.get_object_powers(int(pending.caster))
	for power in powers:
		if power.name == pending.name and int(power.get("triggers", 0)) > int(pending.triggers_before):
			pending.confirmed = true
			pending.frame = frame
			board.team_value(team, "last_power", pending, frame, player)
			pending_cast.erase(player)
			logbook.write("power_trigger_confirmed", {"player": player, "frame": frame, "power": pending.name, "group": pending.group})
			if conversation != null: conversation.note(player, "power_confirmed", "My ability activated. We can coordinate our attack with it.", frame, 75, ttl)
			return
	if frame - int(pending.frame) >= ttl:
		pending_cast.erase(player)
		logbook.write("power_unconfirmed", {"player": player, "frame": frame, "power": pending.name})

func repair(world: Node, player: int, obs: Dictionary, frame: int) -> bool:
	var contracts = preload("res://scripts/team_ai/contracts.gd")
	var target: Dictionary = preload("res://scripts/team_ai/user_rules.gd").repair_target(contracts.objects(obs,"self"),contracts.objects(obs,"enemy"),frame<900)
	if target.is_empty(): return false
	for power in world.get_spellbook(player).get("powers",[]):
		if str(power.name)!="SpellBookRebuild" or not power.get("owned",false) or not power.get("ready",false): continue
		var accepted: bool = world.cast_special_power(player,str(power.name),target.x,target.y)
		last_cast[player]=frame
		if accepted: pending_cast[player]={"group":"repair","frame":frame,"target":int(target.id),"caster":0,"name":str(power.name),"x":target.x,"y":target.y,"triggers_before":int(power.get("triggers",0))}
		logbook.write("repair_power_order",{"player":player,"frame":frame,"target":target.id,"health_ratio":target.health_ratio,"early":frame<900,"accepted":accepted})
		return accepted
	return false
