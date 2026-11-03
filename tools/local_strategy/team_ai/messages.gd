extends RefCounted

const C = preload("res://scripts/team_ai/contracts.gd")
var board: RefCounted
var logbook: RefCounted
var tuning: Dictionary
var inboxes: Dictionary = {}
var last_sent: Dictionary = {}
var dedup: Dictionary = {}
var serial = 0
var delivered: Array = []
var pending_critical: Dictionary = {}
var awaiting: Dictionary = {}

func setup(b: RefCounted, logger: RefCounted, config: Dictionary) -> void:
	board = b
	logbook = logger
	tuning = config

func send(sender: int, recipient: int, type: String, subject: String, payload: Dictionary, priority: int, frame: int, obs: Dictionary, expects_reply: bool = false, tone: String = "calm", utterance: String = "") -> Dictionary:
	var team = board.team_of(sender)
	var state: Dictionary = board.snapshot(team)
	var reason = ""
	if team < 0 or not state.get("bots", {}).has(sender): reason = "invalid_sender"
	elif recipient != -1 and not state.get("bots", {}).has(recipient): reason = "invalid_recipient"
	elif type not in C.MESSAGE_TYPES: reason = "invalid_type"
	elif payload.has("action") and str(payload.action) not in C.ACTIONS: reason = "unsupported_action"
	elif payload.has("target") and int(payload.target) != 0 and not int(payload.target) in C.visible_ids(obs) and not int(payload.target) in C.objects(obs, "ally").map(func(o): return int(o.id)) and not int(payload.target) in C.objects(obs, "self").map(func(o): return int(o.id)): reason = "unobserved_target"
	for key in payload:
		if key not in ["action", "target", "plan_id", "reason", "start_frame", "commitment_id"]: reason = "unsupported_payload"
	if tone not in ["calm", "urgent", "confident", "reassuring"] or utterance.length() > 160: reason = "invalid_presentation"
	if not reason.is_empty():
		logbook.write("message_rejected", {"from": sender, "frame": frame, "reason": reason})
		return {}
	var key = "%d:%d:%s:%s:%s" % [sender, recipient, type, subject, JSON.stringify(payload)]
	var critical = type in C.CRITICAL
	var interval = int(tuning.critical_interval_frames if critical else tuning.interval_frames)
	var channel = "%d:%s" % [sender, type if critical else "ordinary"]
	if frame - int(dedup.get(key, -100000)) < int(tuning.dedup_frames): return {}
	if frame - int(last_sent.get(channel, -100000)) < interval:
		if critical:
			pending_critical[key] = {"sender": sender, "recipient": recipient, "type": type, "subject": subject, "payload": payload.duplicate(true), "priority": priority, "created": frame, "expires": frame + int(tuning.ttl_frames), "obs": obs.duplicate(true), "expects_reply": expects_reply}
			logbook.write("critical_message_queued", {"from": sender, "type": type, "frame": frame, "subject": subject})
		return {}
	if not critical and frame - int(last_sent.get("%d:silence" % sender, -100000)) < int(tuning.silence_frames): return {}
	serial += 1
	var message = {"id": str(serial), "from": sender, "to": recipient, "timestamp": frame, "confidence": 1.0, "type": type, "subject": subject.left(64), "payload": payload.duplicate(true), "priority": clampi(priority, 0, 100), "expects_reply": expects_reply, "timeout": frame + int(tuning.timeout_frames), "expires": frame + int(tuning.ttl_frames), "tone": "calm"}
	message.tone = "urgent" if type == "WARN" else tone
	message["text"] = utterance.replace("\n", " ").replace("\r", " ").strip_edges() if not critical else ""
	var targets: Array = []
	dedup[key] = frame
	last_sent[channel] = frame
	last_sent["%d:silence" % sender] = frame
	for player in state.bots:
		if int(player) == sender or (recipient != -1 and int(player) != recipient): continue
		targets.append(int(player))
		if not inboxes.has(player): inboxes[player] = []
		inboxes[player].append(message.duplicate(true))
		inboxes[player].sort_custom(func(a, b): return a.priority > b.priority if a.priority != b.priority else int(a.id) < int(b.id))
		while inboxes[player].size() > int(tuning.queue_limit): inboxes[player].pop_back()
	board.append_message(team, message, int(tuning.history_limit) * maxi(1, state.bots.size()))
	if expects_reply and not targets.is_empty(): awaiting[message.id] = {"message": message.duplicate(true), "pending": targets, "acknowledged": []}
	if type in ["ACK", "ACCEPT", "REJECT", "COMMIT"] and awaiting.has(subject):
		var pending_reply: Dictionary = awaiting[subject]
		if type == "ACK": pending_reply.acknowledged.append(sender)
		else: pending_reply.pending.erase(sender)
		if pending_reply.pending.is_empty(): awaiting.erase(subject)
	delivered.append(message)
	while delivered.size() > int(tuning.queue_limit): delivered.pop_front()
	logbook.write("team_message", message)
	return message

func take(player: int, frame: int, limit: int = 4) -> Array:
	var output: Array = []
	var queue: Array = inboxes.get(player, [])
	while not queue.is_empty() and output.size() < limit:
		var message: Dictionary = queue.pop_front()
		if int(message.expires) > frame: output.append(message)
	inboxes[player] = queue
	return output

func prune(frame: int, observations: Dictionary = {}) -> void:
	for key in awaiting.keys():
		var item: Dictionary = awaiting[key]
		if int(item.message.timeout) <= frame:
			logbook.write("message_timeout", {"id": key, "from": item.message.from, "pending": item.pending, "frame": frame})
			awaiting.erase(key)
	for key in pending_critical.keys():
		var item: Dictionary = pending_critical[key]
		if int(item.expires) <= frame:
			logbook.write("critical_message_expired", {"from": item.sender, "type": item.type, "frame": frame, "subject": item.subject})
			pending_critical.erase(key)
		elif frame - int(last_sent.get("%d:%s" % [item.sender, item.type], -100000)) >= int(tuning.critical_interval_frames):
			pending_critical.erase(key)
			send(item.sender, item.recipient, item.type, item.subject, item.payload, item.priority, frame, observations.get(item.sender, item.obs), item.expects_reply)
	for key in dedup.keys():
		if frame - int(dedup[key]) > int(tuning.dedup_frames): dedup.erase(key)
	for player in inboxes:
		inboxes[player] = inboxes[player].filter(func(m): return int(m.expires) > frame)
	var teams: Dictionary = {}
	for player in inboxes:
		var team = board.team_of(int(player))
		if not teams.has(team): teams[team] = {}
		teams[team][player] = inboxes[player].duplicate(true)
	for team in teams: board.team_value(int(team), "messages", teams[team], frame, -1)

func history(player: int) -> Array:
	var out: Array = board.snapshot(board.team_of(player)).get("history", []).filter(func(m): return int(m.from) == player or int(m.to) in [-1, player])
	return out.slice(maxi(0, out.size() - int(tuning.history_limit)))

static func text(message: Dictionary) -> String:
	if message.type not in C.CRITICAL and not str(message.get("text", "")).is_empty(): return str(message.text)
	match str(message.type):
		"WARN": return "My base is under attack. I need support!"
		"ACK": return "Message received."
		"COMMIT": return "I committed to the joint attack and will move at the agreed time." if message.payload.get("action", "") == "attack" else "I committed to supporting you and am preparing my troops."
		"CANCEL": return "Canceling the plan: " + str(message.payload.get("reason", "the situation changed"))
		"PROPOSE": return "Let us attack the same target together. Who is ready?"
		"ACCEPT": return "I am ready and can join the attack."
		"REJECT": return "I am already committed to another task." if message.payload.get("reason", "") == "already_committed" else "I cannot join right now. My army or route is not ready."
		"STATUS": return "I am regrouping my army and watching for an opening."
		"REQUEST": return "I need help with this target."
	return "I have new information to share."
