extends RefCounted

const C = preload("res://scripts/team_ai/contracts.gd")
var cursors: Dictionary = {}
var initial: Dictionary = {}
var production_cursors: Dictionary = {}

func asset(o: Dictionary) -> Dictionary:
	return {"id":o.id,"template":o.template,"health":o.get("health_ratio",1.0),"cost":o.get("own_cost",o.get("public_cost",0)),"structure":o.get("structure",false),"economy":o.get("economy",false),"factory":o.get("army_factory",false),"hero":o.get("hero",false),"complete":o.get("complete",true),"combat":o.get("combat_active",false),"x":o.x,"y":o.y,"owner":o.get("owner_index",0),"resource_share":o.get("resource_share",0),"queue_count":o.get("queue_count",0),"factory_disabled":o.get("factory_disabled",false),"mobile":o.get("mobile",false),"builder":o.get("builder",false)}

func clear() -> void:
	cursors.clear()
	initial.clear()
	production_cursors.clear()

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
	var own_objects: Array=C.objects(obs,"self")
	row["own_assets"]=own_objects.map(asset)
	for index in row.own_assets.size():
		var original: Dictionary=own_objects[index]
		if original.has("paid_cost"): row.own_assets[index]["paid_cost"]=original.paid_cost
	var receipts: Array=[]
	var receipts_complete: bool=true
	for source in own_objects.filter(func(o): return o.has("queue_count")):
		var production: Dictionary=world.get_production(player,int(source.id))
		if not production.get("ok",false) or not production.has("receipt_cursor"): continue
		var cursor_key: String=str(player)+":"+str(source.id)
		var after: int=int(production_cursors.get(cursor_key,0))
		if after<int(production.get("receipt_first",1))-1: receipts_complete=false
		for receipt in production.get("production_receipts",[]):
			if int(receipt.serial)>after: receipts.append(receipt)
		production_cursors[cursor_key]=int(production.receipt_cursor)
	row["production_receipts"]=receipts
	row["production_receipts_complete"]=receipts_complete
	for owner in world.get_economy().get("players",[]):
		if int(owner.index)==player:
			row["owned_present_ids"]=world.get_player_objects(str(owner.name)).map(func(o): return int(o.id))
			break
	row["ally_assets"]=C.objects(obs,"ally").map(asset)
	row["money"]=obs.money
	row["economy_evaluation"]={"schema":"economy-production-eval-v1","cp_used":obs.cp_used,"cp_limit":obs.cp_limit}
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
