extends RefCounted

var model = preload("res://scripts/team_ai/enemy_model.gd").new()
var events = preload("res://scripts/team_ai/event_buffer.gd").new()
var jobs: Array = []
var revisions: Dictionary = {}

func run() -> void:
	model.logbook = events
	# Copies only: no GameWorld, Node, blackboard, HTTP or file access on this worker.
	for job in jobs:
		if model.update(int(job.team), int(job.player), job.observation, int(job.frame)):
			revisions[job.team] = int(revisions.get(job.team, 0)) + 1
