extends RefCounted

# All mutation is under the mutex; callers receive deep copies, never live state.
var _mutex = Mutex.new()
var _teams: Dictionary = {}
var _membership: Dictionary = {}

func clear() -> void:
	_mutex.lock()
	_teams.clear()
	_membership.clear()
	_mutex.unlock()

func register(player: int, members: Array, frame: int) -> int:
	members = members.duplicate()
	members.sort()
	var team = int(members[0])
	_mutex.lock()
	_membership[player] = team
	if not _teams.has(team): _teams[team] = {"members": members, "bots": {}, "claims": {}, "commitments": {}, "history": [], "messages": [], "scouting": {}, "threat": {}, "target": {}, "frame": frame, "confidence": 1.0}
	if not _teams[team].bots.has(player): _teams[team].bots[player] = {}
	_mutex.unlock()
	return team

func team_of(player: int) -> int:
	_mutex.lock()
	var team = int(_membership.get(player, -1))
	_mutex.unlock()
	return team

func snapshot(team: int) -> Dictionary:
	_mutex.lock()
	var result: Dictionary = _teams.get(team, {}).duplicate(true)
	_mutex.unlock()
	return result

func publish(player: int, values: Dictionary, frame: int) -> void:
	_mutex.lock()
	var team = int(_membership.get(player, -1))
	if _teams.has(team):
		for key in values: _teams[team].bots[player][key] = preload("res://scripts/team_ai/contracts.gd").record(values[key], frame, player)
		_teams[team].frame = frame
	_mutex.unlock()

func team_value(team: int, key: String, value: Variant, frame: int, source: int, confidence: float = 1.0) -> void:
	_mutex.lock()
	if _teams.has(team): _teams[team][key] = preload("res://scripts/team_ai/contracts.gd").record(value, frame, source, confidence)
	_mutex.unlock()

func claim(team: int, key: String, owner: int, frame: int, ttl: int, priority: int = 0) -> bool:
	_mutex.lock()
	var accepted = false
	if _teams.has(team):
		var old: Dictionary = _teams[team].claims.get(key, {})
		if old.is_empty() or int(old.expires) <= frame or int(old.owner) == owner:
			_teams[team].claims[key] = {"owner": owner, "frame": frame, "expires": frame + ttl, "priority": priority, "confidence": 1.0}
			accepted = true
	_mutex.unlock()
	return accepted

func release(team: int, key: String, owner: int) -> void:
	_mutex.lock()
	if _teams.has(team) and int(_teams[team].claims.get(key, {}).get("owner", -1)) == owner: _teams[team].claims.erase(key)
	_mutex.unlock()

func commitment(team: int, id: String, value: Dictionary) -> void:
	_mutex.lock()
	if _teams.has(team): _teams[team].commitments[id] = value.duplicate(true)
	_mutex.unlock()

func append_message(team: int, message: Dictionary, limit: int) -> void:
	_mutex.lock()
	if _teams.has(team):
		_teams[team].history.append(message.duplicate(true))
		while _teams[team].history.size() > limit: _teams[team].history.pop_front()
	_mutex.unlock()

func prune(frame: int) -> void:
	_mutex.lock()
	for team in _teams.values():
		for key in team.claims.keys():
			if int(team.claims[key].expires) <= frame: team.claims.erase(key)
		for key in team.commitments.keys():
			if team.commitments[key].get("status", "") != "active" and frame - int(team.commitments[key].get("frame", frame)) > 300: team.commitments.erase(key)
	_mutex.unlock()
