extends RefCounted

const C = preload("res://scripts/team_ai/contracts.gd")
var histories: Dictionary = {}
var hints: Dictionary = {}
var logbook: RefCounted
var metrics: Dictionary = {}
var last_metrics := -150
var model_name := ""

func _init() -> void:
	if FileAccess.file_exists("res://data/replay_sequence.json"):
		var config=JSON.parse_string(FileAccess.get_file_as_string("res://data/replay_sequence.json"))
		assert(config is Dictionary and int(config.get("schema",0))==1,"Invalid replay sequence runtime config")
		model_name=str(config.model)

func clear() -> void:
	histories.clear()
	hints.clear()
	metrics.clear()
	last_metrics=-150

func count(player: int, reason: String) -> void:
	var counts: Dictionary = metrics.get(player,{})
	counts[reason]=int(counts.get(reason,0))+1
	metrics[player]=counts

func reject(player: int, reason: String) -> String:
	count(player,reason)
	return "attack"

func flush_metrics(frame: int) -> void:
	if metrics.is_empty() or frame-last_metrics<150: return
	logbook.write("replay_sequence_metrics",{"frame":frame,"counts":metrics.duplicate(true)})
	last_metrics=frame
	metrics.clear()

func record(player: int, family: String, frame: int, result: Dictionary) -> void:
	if not result.get("ok",false): return
	var state: Dictionary = histories.get(player,{"revision":0,"events":[]})
	var events: Array = state.events
	var event = {"family":family,"frame":frame}
	if not events.is_empty() and events[-1].family==family: events[-1]=event
	else: events.append(event)
	while events.size()>8: events.pop_front()
	state.revision=int(state.revision)+1
	histories[player]=state
	# A model answer is tied to its exact observed command prefix.
	if hints.has(player) and not hints[player].get("used",false): count(player,"prefix_changed_by_"+family)
	hints.erase(player)

func context(player: int) -> Dictionary:
	return histories.get(player,{"revision":0,"events":[]}).duplicate(true)

func accept(player: int, hint: Dictionary, frame: int) -> void:
	if not hint.get("ready",false): return
	if model_name.is_empty() or str(hint.get("model",""))!=model_name: return
	if histories.get(player,{}).get("events",[]).size()!=8: return
	if int(hint.get("revision",-1))!=int(histories.get(player,{}).get("revision",0)): return
	if not hint.get("probabilities",{}) is Dictionary: return
	var stored=hint.duplicate(true)
	stored["expires"]=frame+50
	if hints.has(player) and not hints[player].get("used",false): count(player,"replaced_before_use")
	hints[player]=stored
	logbook.write("replay_sequence_hint",{"player":player,"frame":frame,"revision":hint.revision,"model":hint.model,"probabilities":hint.probabilities})

func scout_mode(player: int, ids: Array, goal: Vector2, obs: Dictionary, frame: int) -> String:
	var hint: Dictionary = hints.get(player,{})
	if hint.is_empty(): return reject(player,"no_current_hint")
	if frame>int(hint.expires): return reject(player,"expired_hint")
	if int(hint.revision)!=int(histories.get(player,{}).get("revision",0)): return reject(player,"stale_prefix")
	var own: Array = C.objects(obs,"self").filter(func(o): return int(o.id) in ids)
	var enemies: Array = C.objects(obs,"enemy")
	for unit in own:
		if unit.get("hero",false) or float(unit.get("health_ratio",1))<0.45 or unit.get("combat_active",false): return reject(player,"unit_safety_guard")
		var at=Vector2(unit.x,unit.y)
		for enemy in enemies:
			if enemy.structure and not enemy.get("armed",false): continue
			var distance: float = preload("res://scripts/combat_policy.gd").segment_distance(at,goal,Vector2(enemy.x,enemy.y))
			if distance<900: return reject(player,"visible_threat_guard")
	var probabilities: Dictionary = hint.probabilities
	var move_chance=float(probabilities.get("move",0))
	var attack_chance=float(probabilities.get("attack",0))
	if not is_finite(move_chance) or not is_finite(attack_chance): return reject(player,"invalid_probability")
	var mass=move_chance+attack_chance
	if mass<0.20 or move_chance/mass<0.65: return reject(player,"model_prefers_other_orders")
	hints[player]["used"]=true
	count(player,"selected_move")
	return "move"
