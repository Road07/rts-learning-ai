extends RefCounted

const C = preload("res://scripts/team_ai/contracts.gd")
var board: RefCounted
var bus: RefCounted
var config: Dictionary
var logbook: RefCounted
var commitments: Dictionary = {}
var last_help: Dictionary = {}
var ledger = preload("res://scripts/team_ai/commitments.gd").new()

func travel(home: Vector2, target: Vector2) -> int:
	return int(home.distance_to(target)/float(config.travel_units_per_second)*5)

func arrival_time(player: int, plan: Dictionary, frame: int) -> int:
	var slowest = 0
	for member in board.snapshot(board.team_of(player)).get("bots",{}).values():
		if int(member.get("army_groups",{}).get("value",0))<2: continue
		var home: Dictionary = member.get("home",{}).get("value",{})
		if home.is_empty(): continue
		slowest=maxi(slowest,travel(Vector2(home.x,home.y),Vector2(plan.x,plan.y)))
	return frame+mini(int(config.commitment_max_frames)-int(config.push_window_frames),slowest)+int(config.push_window_frames)

func deadline(plan: Dictionary, home: Vector2, frame: int) -> int:
	var travel_frames = int(home.distance_to(Vector2(plan.x, plan.y)) / float(config.travel_units_per_second) * 5)
	return frame + mini(int(config.commitment_max_frames), maxi(int(config.push_window_frames), travel_frames + int(config.push_window_frames)))

func completed(entry: Dictionary, obs: Dictionary, spec: Dictionary) -> bool:
	var target = Vector2(entry.plan.x, entry.plan.y)
	if entry.plan.kind == "help":
		var ally_base = C.objects(obs, "ally").any(func(o): return int(o.id) == int(entry.plan.target))
		return ally_base and not C.objects(obs, "enemy").any(func(o): return not o.structure and Vector2(o.x, o.y).distance_to(target) < float(config.help_radius))
	if entry.plan.kind == "attack": return spec.army.any(func(o): return Vector2(o.x, o.y).distance_to(target) < float(config.arrival_radius))
	return false

func role(player: int, team: int, affinity: Dictionary = {}) -> String:
	var state: Dictionary = board.snapshot(team)
	var own: Dictionary = state.get("bots", {}).get(player, {})
	if own.has("role"): return str(own.role.value)
	var members: Array = state.get("bots", {}).keys()
	members.sort()
	var index = members.find(player)
	var selected = ["pressure", "economy", "defender", "flex"][mini(3, maxi(0, index))]
	var preferred = selected
	var occupied: Array = []
	for other in state.get("bots", {}):
		if int(other) != player and state.bots[other].has("role"): occupied.append(str(state.bots[other].role.value))
	var best = -INF
	for candidate in ["pressure", "economy", "defender", "flex"]:
		if candidate in occupied: continue
		var score = float(affinity.get(candidate, 0.0)) + (0.1 if candidate == preferred else 0.0)
		if score > best:
			best = score
			selected = candidate
	return selected

func process(player: int, obs: Dictionary, spec: Dictionary, frame: int) -> void:
	var team = board.team_of(player)
	var entries: Dictionary = board.snapshot(team).get("commitments", {})
	for id in entries:
		var entry: Dictionary = entries[id]
		if int(entry.owner) != player or entry.status != "active": continue
		if not spec.critical and completed(entry, obs, spec):
			ledger.transition(team, id, entry, "fulfilled", "support no longer needed or attack force arrived", frame)
			board.release(team, "commitment:%d" % player, player)
			commitments.erase(player)
		elif ledger.expired(entry, frame):
			ledger.transition(team, id, entry, "timed_out", "travel deadline", frame)
			commitments.erase(player)
			board.release(team, "commitment:%d" % player, player)
			bus.send(player, -1, "CANCEL", str(entry.id), {"reason": "I could not reach the target in time"}, 100, frame, obs)
		elif spec.critical or not plan_legal(entry.plan, spec.candidates):
			cancel(player, id, "my base is in danger" if spec.critical else "the target or timing changed", obs, frame)
	automatic_support(player, obs, spec, frame)
	for message in bus.take(player, frame):
		if str(message.payload.get("action",""))=="help": continue
		match str(message.type):
			"WARN", "REQUEST", "PROPOSE":
				bus.send(player, int(message.from), "ACK", str(message.id), {}, 90, frame, obs)
				var candidate: Dictionary = {}
				for item in spec.candidates:
					if int(item.target) == int(message.payload.get("target", -1)) and item.kind == str(message.payload.get("action", "help")): candidate = item
				if spec.critical or spec.army.size() < 2 or candidate.is_empty():
					bus.send(player, int(message.from), "REJECT", str(message.id), {"reason": "unsafe_or_unavailable"}, 80, frame, obs)
				else:
					var current: Dictionary = forced_plan(player, frame)
					if not current.is_empty() and current.id != candidate.id:
						if int(message.priority) > int(current.priority): cancel(player, str(commitments[player].id), "a more urgent team request", obs, frame)
						else:
							bus.send(player, int(message.from), "REJECT", str(message.id), {"reason": "already_committed"}, 80, frame, obs)
							continue
					var entry = {"id": str(message.id), "owner": player, "requester": int(message.from), "plan": candidate.duplicate(true), "status": "active", "frame": frame, "confidence": 1.0, "expires": deadline(candidate, spec.home, frame), "locked_until": frame + int(config.commit_frames), "priority": int(message.priority), "start_frame": maxi(frame, int(message.payload.get("start_frame", frame))), "reason": "team_request"}
					if candidate.kind=="attack":
						var arrival = int(message.payload.get("start_frame",frame))
						entry.start_frame=maxi(frame,arrival-travel(spec.home,Vector2(candidate.x,candidate.y)))
						entry.expires=maxi(int(entry.expires),arrival+int(config.push_window_frames))
					var lock_key = "commitment:%d" % player
					if board.claim(team, lock_key, player, frame, int(config.push_window_frames)):
						commitments[player] = entry
						board.commitment(team, "%d:%s" % [player, message.id], entry)
						bus.send(player, int(message.from), "ACCEPT", str(message.id), {}, 80, frame, obs)
						bus.send(player, -1, "COMMIT", str(message.id), {"action": candidate.kind, "target": candidate.target, "start_frame": entry.start_frame}, 95, frame, obs)
						logbook.write("commitment", entry)
			"CANCEL":
				if commitments.has(player) and int(commitments[player].requester) == int(message.from) and str(commitments[player].id) == str(message.subject): cancel(player, str(commitments[player].id), "the request was withdrawn", obs, frame)
			"ACCEPT":
				logbook.write("push_accepted", {"player": player, "from": message.from, "frame": frame, "proposal": message.subject})

func automatic_support(player: int, obs: Dictionary, spec: Dictionary, frame: int) -> void:
	if spec.critical or spec.army.is_empty(): return
	var current: Dictionary = forced_plan(player,frame)
	if not current.is_empty() and (current.kind=="help" or int(current.priority)>=90): return
	if frame-int(last_help.get(player,-1000))<int(config.help_cooldown_frames): return
	var choices: Array = spec.candidates.filter(func(c): return c.kind=="help" and int(c.get("max_groups",1))>0)
	if choices.is_empty(): return
	choices.sort_custom(func(a,b): return spec.home.distance_squared_to(Vector2(a.x,a.y))<spec.home.distance_squared_to(Vector2(b.x,b.y)))
	var plan: Dictionary = choices[0].duplicate(true)
	var team = board.team_of(player)
	if not current.is_empty(): cancel(player,str(commitments[player].id),"automatic ally defence",obs,frame)
	var id="auto_support_%d_%d" % [player,frame]
	var entry={"id":id,"owner":player,"requester":player,"plan":plan,"status":"active","frame":frame,"confidence":1.0,"expires":deadline(plan,spec.home,frame),"locked_until":frame+int(config.commit_frames),"priority":90,"start_frame":frame,"reason":"automatic_visible_ally_threat"}
	if not board.claim(team,"commitment:%d" % player,player,frame,int(config.push_window_frames)): return
	commitments[player]=entry
	board.commitment(team,"%d:%s" % [player,id],entry)
	last_help[player]=frame
	logbook.write("automatic_support",{"player":player,"frame":frame,"target":plan.target,"max_groups":plan.get("max_groups",1),"request_message_required":false})

func cancel(player: int, id: String, reason: String, obs: Dictionary, frame: int) -> void:
	var team = board.team_of(player)
	var entry: Dictionary = commitments.get(player, {})
	if entry.is_empty(): return
	ledger.transition(team, "%d:%s" % [player, entry.id], entry, "cancelled", reason, frame)
	board.release(team, "commitment:%d" % player, player)
	commitments.erase(player)
	bus.send(player, -1, "CANCEL", str(entry.id), {"reason": reason}, 100, frame, obs)
	logbook.write("commitment_cancelled", entry)

func forced_plan(player: int, frame: int) -> Dictionary:
	var entry: Dictionary = commitments.get(player, {})
	if entry.is_empty() or entry.status != "active" or int(entry.expires) <= frame: return {}
	var plan: Dictionary = entry.plan.duplicate(true)
	if frame < int(entry.start_frame): plan["wait_until"] = entry.start_frame
	plan["tactic_tag"] = "coordinated_" + str(plan.kind)
	plan["locked_until"] = int(entry.locked_until)
	plan["priority"] = int(entry.priority)
	return plan

func propose(player: int, plan: Dictionary, obs: Dictionary, frame: int) -> void:
	if plan.kind != "attack": return
	var team = board.team_of(player)
	if not forced_plan(player, frame).is_empty(): return
	if not board.claim(team, "push_proposal", player, frame, int(config.push_window_frames)): return
	var start = arrival_time(player,plan,frame)
	var message: Dictionary = bus.send(player, -1, "PROPOSE", "push", {"action": "attack", "target": plan.target, "start_frame": start}, 70, frame, obs, true)
	if message.is_empty(): return
	var home = Vector2(plan.x, plan.y)
	for object in C.objects(obs, "self"):
		if object.base: home = Vector2(object.x, object.y)
	var entry = {"id": str(message.id), "owner": player, "requester": player, "plan": plan.duplicate(true), "status": "active", "frame": frame, "confidence": 1.0, "expires": deadline(plan, home, frame), "locked_until": frame + int(config.commit_frames), "priority": 70, "start_frame": start, "reason": "push_leader"}
	entry.start_frame=maxi(frame,start-travel(home,Vector2(plan.x,plan.y)))
	entry.expires=maxi(int(entry.expires),start+int(config.push_window_frames))
	commitments[player] = entry
	board.commitment(team, "%d:%s" % [player, message.id], entry)
	bus.send(player, -1, "COMMIT", str(message.id), {"action": "attack", "target": plan.target, "start_frame": start}, 95, frame, obs)
	board.team_value(team, "target", plan, frame, player)

static func plan_legal(plan: Dictionary, candidates: Array) -> bool:
	for candidate in candidates:
		if candidate.id == plan.id: return true
	return false
