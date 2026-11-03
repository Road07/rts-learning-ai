extends RefCounted

# Read-only synthetic regression checks, confined to the decision-net team arena.
static func run(logger: RefCounted) -> Dictionary:
	var director=preload("res://scripts/team_ai/battle_director.gd").new()
	director.logbook=logger
	var own={"id":990001,"x":600.0,"y":0.0,"structure":false,"hero":false,"category":0,"public_cost":300,"health_ratio":1.0}
	var enemies: Array=[]
	for i in 3: enemies.append({"id":990010+i,"x":3000.0,"y":float(i*20),"structure":false,"hero":false,"category":0,"public_cost":300,"health_ratio":1.0})
	var spec={"home":Vector2.ZERO,"critical":false,"army":[own],"summary":{}}
	var obs={"faction":"FactionMen","players":[{"relation":"enemy","objects":enemies}]}
	var help={"id":"help_probe","kind":"help","target":999,"x":3000.0,"y":0.0,"priority":100}
	var initial={"plan":"","cohort":[],"loss_until":-1,"losses":0,"momentum_until":-1,"last_log":-1000}
	director.state[999]=initial.duplicate(true)
	var support: Dictionary=director.movement(999,help,spec,obs,1,[])
	director.state[999]=initial.duplicate(true)
	var attack=help.duplicate(true)
	attack.kind="attack"
	attack.id="attack_probe"
	var offensive: Dictionary=director.movement(999,attack,spec,obs,2,[])
	director.state[999]=initial.duplicate(true)
	var exposed=own.duplicate(true)
	exposed.x=3000.0
	spec.army=[exposed]
	var unsafe: Dictionary=director.movement(999,help,spec,obs,3,[])
	var checks={"single_available_support_released":support.hold.is_empty() and support.reason=="support_dispatch", "attack_cohort_guard_preserved":not offensive.hold.is_empty(), "unfavorable_fight_retreat_preserved":unsafe.retreat}
	logger.write("support_dispatch_validation",{"fixture":true,"checks":checks})
	return checks
