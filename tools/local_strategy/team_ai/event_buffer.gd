extends RefCounted

# Worker-owned, drained only after WorkerThreadPool signals completion.
var records: Array = []

func write(event: String, data: Dictionary) -> void:
	if records.size() < 256: records.append({"event": event, "data": data.duplicate(true)})
