extends RefCounted

const C = preload("res://scripts/team_ai/contracts.gd")

# Same pre-command fields as the human dataset. No post-state or hidden enemies.
static func collect(obs: Dictionary) -> Dictionary:
	var own := {}
	var enemy := {}
	var public_costs := {}
	for pair in [["self",own],["enemy",enemy]]:
		for object in C.objects(obs,pair[0]):
			var name = str(object.template)
			pair[1][name] = int(pair[1].get(name,0))+1
			if object.has("public_cost"): public_costs[name]=object.public_cost
	return {"faction":obs.faction,"money":obs.money,"cp_used":obs.cp_used,"cp_limit":obs.cp_limit,"own_templates":own,"visible_enemy_templates":enemy,"public_template_costs":public_costs}
