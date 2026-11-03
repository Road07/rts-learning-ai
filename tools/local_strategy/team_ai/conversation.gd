extends RefCounted

# Event-driven presentation through the existing typed team bus. No invented intel,
# new orders, or extra model calls; critical commitments remain coordinator-owned.
const C = preload("res://scripts/team_ai/contracts.gd")
var bus: RefCounted
var board: RefCounted
var personality: RefCounted
var records: Dictionary = {}
var queues: Dictionary = {}
var cooldowns: Dictionary = {}
var last_team: Dictionary = {}
var last_player: Dictionary = {}

func clear() -> void:
	records.clear(); queues.clear(); cooldowns.clear(); last_team.clear(); last_player.clear()

func note(player: int, topic: String, text: String, frame: int, priority: int = 40, ttl: int = 100) -> void:
	return

func flush(player: int, obs: Dictionary, frame: int) -> void:
	return

func observe(player: int, obs: Dictionary, spec: Dictionary, context: Dictionary, frame: int, world: Node) -> void:
	return

func ordered(player: int, plan: Dictionary, obs: Dictionary, frame: int) -> void:
	return
