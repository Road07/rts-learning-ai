extends RefCounted

static func build(candidates: Array, team_members: Array, production_options: Array = []) -> Dictionary:
	var recipients = team_members.duplicate()
	if -1 not in recipients: recipients.append(-1)
	var types = preload("res://scripts/team_ai/contracts.gd").MESSAGE_TYPES
	var message = {"type": "object", "properties": {"to": {"type": "integer", "enum": recipients}, "type": {"type": "string", "enum": types}, "subject": {"type": "string", "maxLength": 64}, "payload": {"type": "object", "properties": {"action": {"type": "string", "enum": ["defend", "help", "attack", "scout"]}, "target": {"type": "integer"}, "reason": {"type": "string", "maxLength": 160}}, "additionalProperties": false}, "priority": {"type": "integer", "minimum": 0, "maximum": 100}}, "required": ["type", "payload"], "additionalProperties": false}
	message.properties["text"] = {"type": "string", "maxLength": 160}
	message.properties["tone"] = {"type": "string", "enum": ["calm", "urgent", "confident", "reassuring"]}
	var purchases: Array = ["none"]
	for operation in production_options: purchases.append(operation.id)
	return {"type": "object", "properties": {"production_id": {"type": "string", "enum": purchases}, "candidate_id": {"type": "string", "enum": candidates.map(func(c): return c.id)}, "intent": {"type": "string", "enum": ["defend", "help", "attack", "scout"]}, "target": {"type": "integer"}, "priority": {"type": "integer", "minimum": 0, "maximum": 100}, "params": {"type": "object", "properties": {}, "additionalProperties": false}, "messages": {"type": "array", "items": message, "maxItems": 3}, "tactic_tag": {"type": "string", "maxLength": 48}, "reason": {"type": "string", "maxLength": 256}}, "required": ["candidate_id", "production_id"], "additionalProperties": false}
