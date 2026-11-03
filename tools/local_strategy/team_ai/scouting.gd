extends RefCounted

var visited: Dictionary = {}
var failed_until: Dictionary = {}

func team_history(team: int) -> Dictionary:
	var result: Dictionary = {}
	var prefix = "%d:" % team
	for key in visited:
		if str(key).begins_with(prefix): result[key] = visited[key]
	return result

func choose(player: int, home: Vector2, extent: Vector2, frame: int, board: RefCounted, team: int, ttl: int) -> Vector2:
	var best = home
	var oldest = 9223372036854775807
	for x in [0.2, 0.5, 0.8]:
		for y in [0.2, 0.5, 0.8]:
			var at = Vector2(extent.x * x, extent.y * y)
			if at.distance_to(home) < 400: continue
			var key = "%d:%d:%d" % [team, int(at.x), int(at.y)]
			if int(failed_until.get(key, 0)) > frame: continue
			var last = int(visited.get(key, -1000))
			if last < oldest and board.claim(team, "scout:" + key, player, frame, ttl):
				if best != home: board.release(team, "scout:%d:%d:%d" % [team, int(best.x), int(best.y)], player)
				best = at
				oldest = last
	return best

func failed(team: int, at: Vector2, frame: int, ttl: int) -> void:
	failed_until["%d:%d:%d" % [team, int(at.x), int(at.y)]] = frame + ttl

func observed(team: int, own: Array, extent: Vector2, frame: int) -> void:
	for x in [0.2, 0.5, 0.8]:
		for y in [0.2, 0.5, 0.8]:
			var at = Vector2(extent.x * x, extent.y * y)
			for unit in own:
				if Vector2(unit.x, unit.y).distance_to(at) < 150: visited["%d:%d:%d" % [team, int(at.x), int(at.y)]] = frame
