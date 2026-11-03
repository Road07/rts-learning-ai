extends RefCounted

const FACTIONS = ["FactionMen", "FactionElves", "FactionDwarves", "FactionIsengard", "FactionMordor", "FactionWild", "FactionAngmar"]
const ACTIONS = ["defend", "help", "attack", "scout"]
const MESSAGE_TYPES = ["INFORM", "WARN", "REQUEST", "PROPOSE", "ACCEPT", "REJECT", "ACK", "CANCEL", "COMMIT", "STATUS"]
const CRITICAL = ["WARN", "ACK", "COMMIT", "CANCEL"]

static func integral(value: Variant) -> bool:
	return value is int or (value is float and is_finite(value) and value == floor(value))

static func record(value: Variant, frame: int, source: int, confidence: float = 1.0) -> Dictionary:
	var copy = value.duplicate(true) if value is Dictionary or value is Array else value
	return {"value": copy, "frame": frame, "source": source, "confidence": clampf(confidence, 0, 1) if is_finite(confidence) else 0.0}

static func objects(obs: Dictionary, relation: String) -> Array:
	var result: Array = []
	for p in obs.get("players", []):
		if p.relation == relation: result.append_array(p.objects)
	return result

static func visible_ids(obs: Dictionary) -> Array:
	return objects(obs, "enemy").map(func(o): return int(o.id))

static func validate_intent(intent: Dictionary, candidates: Array) -> String:
	for key in intent:
		if key not in ["candidate_id", "production_id", "intent", "target", "priority", "params", "messages", "tactic_tag", "reason"]: return "unknown_field"
	if intent.has("production_id") and not intent.production_id is String: return "invalid_production"
	if not intent.get("candidate_id") is String: return "missing_candidate"
	var match_candidate: Dictionary = {}
	for c in candidates:
		if c.id == intent.candidate_id: match_candidate = c
	if match_candidate.is_empty(): return "candidate_not_legal"
	if intent.has("intent") and intent.intent != match_candidate.kind: return "action_mismatch"
	if intent.has("target") and (not integral(intent.target) or int(intent.target) != int(match_candidate.target)): return "target_mismatch"
	if intent.has("params") and (not intent.params is Dictionary or not intent.params.is_empty()): return "unimplemented_params"
	if intent.has("priority") and (not (intent.priority is int or intent.priority is float) or not is_finite(float(intent.priority)) or float(intent.priority) < 0 or float(intent.priority) > 100): return "invalid_priority"
	if intent.has("messages") and (not intent.messages is Array or intent.messages.size() > 3): return "invalid_messages"
	for message in intent.get("messages", []):
		if not message is Dictionary or not message.get("type", "") is String or not message.get("payload", {}) is Dictionary: return "invalid_message_schema"
		if message.get("type", "") not in MESSAGE_TYPES: return "invalid_message_type"
		if message.get("payload", {}).has("target") and not integral(message.payload.target): return "invalid_message_target"
		if message.has("to") and not integral(message.to): return "invalid_recipient_type"
		if message.has("priority") and (not integral(message.priority) or float(message.priority) < 0 or float(message.priority) > 100): return "invalid_message_priority"
		if message.has("text") and (not message.text is String or message.text.length() > 160): return "invalid_message_text"
		if message.has("tone") and message.tone not in ["calm", "urgent", "confident", "reassuring"]: return "invalid_message_tone"
		for key in message:
			if key not in ["to", "type", "subject", "payload", "priority", "text", "tone"]: return "unknown_message_field"
	if intent.has("tactic_tag") and (not intent.tactic_tag is String or intent.tactic_tag.length() > 48): return "invalid_tactic_tag"
	if intent.has("tactic_tag") and intent.tactic_tag != match_candidate.get("tactic_tag", match_candidate.kind): return "unsupported_tactic"
	if intent.has("reason") and (not intent.reason is String or intent.reason.length() > 256): return "invalid_reason"
	return ""
