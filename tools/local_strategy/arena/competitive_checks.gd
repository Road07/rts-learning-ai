extends RefCounted

# Cheap safety regressions; invoked by the focused arena case, not normal matches.
static func run(logger: RefCounted) -> Array:
	var failures: Array = []
	var battle = preload("res://scripts/team_ai/battle_director.gd").new()
	battle.logbook=logger
	var soldier={"id":1,"x":0.0,"y":0.0,"structure":false,"hero":false,"category":0,"public_cost":300,"health_ratio":1.0}
	var cavalry=soldier.duplicate(); cavalry.category=3
	var pike=soldier.duplicate(); pike.category=2
	if battle.strength([cavalry],[pike])>=battle.strength([cavalry],[]): failures.append("cavalry_into_pikes")
	var injured=soldier.duplicate(); injured.health_ratio=0.25
	if battle.strength([injured])>=battle.strength([soldier]): failures.append("injury_strength")
	battle.observe(1,[soldier],[],0,null)
	var plan={"id":"push","kind":"attack","target":20,"x":1500.0,"y":0.0}
	var spec={"army":[soldier],"home":Vector2.ZERO,"critical":false}
	var obs={"faction":"FactionWild","players":[{"relation":"enemy","objects":[]}]}
	if battle.movement(1,plan,spec,obs,5,[]).hold!=[1]: failures.append("single_reinforcement_not_held")
	spec.critical=true
	if not battle.movement(1,plan,spec,obs,10,[]).hold.is_empty(): failures.append("assembly_blocks_emergency")
	var fighters: Array = []
	var enemies: Array = []
	for i in 3:
		var unit=soldier.duplicate(); unit.id=i+30; unit.x=1400.0; fighters.append(unit)
	for i in 8:
		var unit=pike.duplicate(); unit.id=i+50; unit.x=1500.0; enemies.append(unit)
	battle.observe(2,fighters,enemies,0,null)
	spec={"army":fighters,"home":Vector2.ZERO,"critical":false}
	obs.players[0].objects=enemies
	if not battle.movement(2,plan,spec,obs,5,[]).retreat: failures.append("bad_fight_not_rejected")
	var composition=preload("res://scripts/team_ai/composition.gd").new()
	var deficit=composition.desired([], [cavalry,cavalry,cavalry],[])
	var covered=composition.desired([pike,pike,pike,pike],[cavalry,cavalry,cavalry],[])
	if float(deficit.weights[2])<=float(covered.weights[2]): failures.append("counter_deficit_not_scaled")
	deficit.weights[2]=0.25
	composition.protect_counters(deficit)
	if float(deficit.weights[2])<2.5: failures.append("opening_diluted_visible_counter")
	var blocked=composition.desired([], [pike],[])
	blocked.weights[3]=4.0
	composition.protect_counters(blocked)
	if float(blocked.weights[3])>0.4: failures.append("cavalry_preference_overrides_visible_pikes")
	var economy=preload("res://scripts/team_ai/economy.gd").new()
	var factory={"id":90,"x":0.0,"y":0.0,"structure":true,"army_factory":true,"health_ratio":1.0}
	if not economy.pressured(1,[factory],[soldier],0): failures.append("factory_pressure_not_detected")
	var runtime=preload("res://scripts/team_ai/runtime.gd").new()
	runtime.logbook=logger
	runtime.config={"decision":{"idle_scan_frames":5,"idle_stall_frames":10}}
	runtime.contexts[1]={"readiness":1.0,"scores":{"push":3.0}}
	var idle_spec={"army":[soldier],"home":Vector2.ZERO,"critical":false,"summary":{"visible_enemy_groups":1},"candidates":[plan]}
	runtime.idle_scan(1,idle_spec,0)
	if runtime.idle_scan(1,idle_spec,15).get("kind","")!="attack": failures.append("distant_visible_enemy_blocks_idle_retask")
	soldier["combat_active"]=true
	if not runtime.idle_scan(1,idle_spec,30).is_empty(): failures.append("idle_retask_interrupts_combat")
	soldier["combat_active"]=false
	var tactics=preload("res://scripts/team_ai/tactics.gd").new()
	tactics.config={"result_frames":25,"retry_frames":300}
	tactics.logbook=logger
	var unseen={"players":[{"relation":"self","objects":[soldier]},{"relation":"enemy","objects":[]}]}
	tactics.track(1,plan,1,3,0,unseen,null)
	tactics.track(1,plan,1,0,30,unseen,null)
	if tactics.failed_count(1,"push",30)!=0: failures.append("fog_disappearance_marked_failure")
	logger.write("competitive_safety_checks",{"passed":failures.is_empty(),"failures":failures,"checks":12})
	return failures
