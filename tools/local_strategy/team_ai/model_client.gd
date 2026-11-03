extends Node

# The worker performs HTTP only. It never reads GameWorld or mutable team state.
signal request_completed(result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray)
var transport = HTTPRequest.new()
var busy = false
var chat_url := "http://127.0.0.1:11434/api/chat"
var timeout: float = 8.0:
	set(value):
		timeout = clampf(value, 1, 120)
		transport.timeout = timeout

func _init() -> void:
	var configured := OS.get_environment("OPENBFME_AI_URL")
	if not configured.is_empty():
		var local_url := RegEx.new()
		local_url.compile("^http://127\\.0\\.0\\.1:([0-9]{1,5})$")
		var matched := local_url.search(configured)
		if matched != null and int(matched.get_string(1)) > 0 and int(matched.get_string(1)) <= 65535:
			chat_url = configured + "/api/chat"
		else:
			chat_url = ""
			push_error("GENERAL_AI invalid local model endpoint")
	transport.use_threads = true
	transport.max_redirects = 0
	transport.body_size_limit = 65536
	add_child(transport)
	transport.request_completed.connect(_finished)

func request(url: String, headers: PackedStringArray, method: int, body: String) -> int:
	if busy: return ERR_BUSY
	if chat_url.is_empty() or url != chat_url: return ERR_UNAUTHORIZED
	busy = true
	var error = transport.request(url, headers, method, body)
	if error != OK: busy = false
	return error

func cancel_request() -> void:
	transport.cancel_request()
	busy = false

func _finished(result: int, code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	busy = false
	request_completed.emit(result, code, headers, body)
