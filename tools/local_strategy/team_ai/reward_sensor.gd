extends RefCounted

const C = preload("res://scripts/team_ai/contracts.gd")
var cursors: Dictionary = {}
var initial: Dictionary = {}

func asset(o: Dictionary) -> Dictionary:
	return {"id":o.id,"template":o.template,"health":o.get("health_ratio",1.0),"cost":o.get("own_cost",o.get("public_cost",0)),"structure":o.get("structure",false),"economy":o.get("economy",false),"factory":o.get("army_factory",false),"hero":o.get("hero",false),"complete":o.get("complete",true),"combat":o.get("combat_active",false),"x":o.x,"y":o.y,"owner":o.get("owner_index",0)}

func clear() -> void:
	cursors.clear()
	initial.clear()

func capture(world: Node, obs: Dictionary) -> Dictionary:
	var player: int = int(obs.player_index)
	var row: Dictionary = world.strategy_reward_observation(player,int(cursors.get(player,-1)))
	if not row.get("ok",false): return row
	cursors[player]=int(row.income_cursor)
	var members: Array = []
	for owner in obs.get("players",[]):
		if owner.relation in ["self","ally"]: members.append(int(owner.index))
	members.sort()
	row["team_members"]=members
	row["credit_schema"]="action-credit-v1"
	row["faction"]=obs.faction
	row["own_assets"]=C.objects(obs,"self").map(asset)
	for owner in world.get_economy().get("players",[]):
		if int(owner.index)==player:
			row["owned_present_ids"]=world.get_player_objects(str(owner.name)).map(func(o): return int(o.id))
			break
	row["ally_assets"]=C.objects(obs,"ally").map(asset)
	row["money"]=obs.money
	var book: Dictionary = world.get_spellbook(player)
	var powers: Array = []
	for source in C.objects(obs,"self").filter(func(o): return o.get("hero",false)):
		for power in world.get_object_powers(int(source.id)):
			powers.append({"source":source.id,"name":power.name,"triggers":power.get("triggers",0)})
	if int(book.get("book",0))>0:
		for power in world.get_object_powers(int(book.book)):
			powers.append({"source":book.book,"name":power.name,"triggers":power.get("triggers",0)})
	row["power_triggers"]=powers
	row["bases"]=C.objects(obs,"self").filter(func(o): return o.get("base",false)).map(func(o): return {"id":o.id,"health":o.get("health_ratio",1.0)})
	row["heroes"]=C.objects(obs,"self").filter(func(o): return o.get("hero",false)).map(func(o): return {"id":o.id,"health":o.get("health_ratio",1.0)})
	row["visible_enemies"]=C.objects(obs,"enemy").map(func(o): return {"id":o.id,"template":o.template,"health":o.get("health_ratio",1.0),"cost":o.get("public_cost",0),"structure":o.get("structure",false),"economy":o.get("economy",false),"hero":o.get("hero",false),"x":o.x,"y":o.y})
	return row

func start(world: Node, obs: Dictionary) -> void:
	initial[int(obs.player_index)]=capture(world,obs)

func for_model(world: Node, obs: Dictionary) -> Array:
	var rows: Array = []
	var player: int = int(obs.player_index)
	if initial.has(player):
		rows.append(initial[player])
		initial.erase(player)
	rows.append(capture(world,obs))
	return rows
