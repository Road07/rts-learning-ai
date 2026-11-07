extends "res://scripts/team_ai/model_client.gd"

# One reusable localhost HTTP/1.1 connection, polled on the owning scene thread.
# No world access, background callbacks or automatic replay of an uncertain POST.
var client: HTTPClient=HTTPClient.new()
var queued_body: String=""
var queued_headers: PackedStringArray=[]
var sent: bool=false
var received: PackedByteArray=[]
var response_headers: PackedStringArray=[]
var response_code: int=0
var expected_bytes: int=-1
var deadline_us: int=0

func request_many(requests: Array, model: String) -> int:
	if requests.is_empty() or requests.size()>8:return ERR_INVALID_PARAMETER
	var seen: Dictionary={}
	var observation: Dictionary=requests[0].get("observation",{})
	if not observation.has("match_id") or not observation.has("decision_frame"):return ERR_INVALID_PARAMETER
	for item in requests:
		var obs: Dictionary=item.get("observation",{})
		if obs.get("match_id")!=observation.match_id or obs.get("decision_frame")!=observation.decision_frame or not obs.has("player_index") or seen.has(obs.player_index):return ERR_INVALID_PARAMETER
		seen[obs.player_index]=true
	return request(chat_url,["Content-Type: application/json"],HTTPClient.METHOD_POST,JSON.stringify({"model":model,"requests":requests}))

func request(url: String, headers: PackedStringArray, method: int, body: String) -> int:
	if busy:return ERR_BUSY
	if chat_url.is_empty() or url!=chat_url or method!=HTTPClient.METHOD_POST:return ERR_UNAUTHORIZED
	queued_body=body
	queued_headers=headers
	sent=false
	received.clear()
	response_headers.clear()
	response_code=0
	expected_bytes=-1
	deadline_us=Time.get_ticks_usec()+int(timeout*1000000)
	# Observe an idle peer close before writing; reconnecting here cannot replay a POST.
	client.poll()
	if client.get_status()!=HTTPClient.STATUS_CONNECTED:
		client.close()
		var port: int=int(chat_url.get_slice(":",2).get_slice("/",0))
		var error: int=client.connect_to_host("127.0.0.1",port)
		if error!=OK:return error
	busy=true
	return OK

func cancel_request() -> void:
	client.close()
	busy=false
	queued_body=""
	received.clear()

func _exit_tree() -> void:
	client.close()

func complete(result: int) -> void:
	busy=false
	queued_body=""
	if result!=HTTPRequest.RESULT_SUCCESS:client.close()
	request_completed.emit(result,response_code,response_headers,received)

func _process(_delta: float) -> void:
	if not busy:return
	if Time.get_ticks_usec()>deadline_us:
		complete(HTTPRequest.RESULT_TIMEOUT)
		return
	if client.poll()!=OK:
		complete(HTTPRequest.RESULT_CONNECTION_ERROR)
		return
	var status: int=client.get_status()
	if status==HTTPClient.STATUS_CONNECTED:
		if not sent:
			if client.request(HTTPClient.METHOD_POST,"/api/chat",queued_headers,queued_body)!=OK:
				complete(HTTPRequest.RESULT_CONNECTION_ERROR)
				return
			sent=true
		elif expected_bytes>=0 and received.size()==expected_bytes:
			complete(HTTPRequest.RESULT_SUCCESS)
	elif status==HTTPClient.STATUS_BODY:
		if expected_bytes<0:
			response_code=client.get_response_code()
			response_headers=client.get_response_headers()
			expected_bytes=client.get_response_body_length()
			if expected_bytes<0 or expected_bytes>65536:
				complete(HTTPRequest.RESULT_BODY_SIZE_LIMIT_EXCEEDED)
				return
		# Drain available chunks without a frame delay per chunk.
		while client.get_status()==HTTPClient.STATUS_BODY:
			var chunk: PackedByteArray=client.read_response_body_chunk()
			if chunk.is_empty():break
			received.append_array(chunk)
			if received.size()>65536:
				complete(HTTPRequest.RESULT_BODY_SIZE_LIMIT_EXCEEDED)
				return
		if received.size()==expected_bytes:complete(HTTPRequest.RESULT_SUCCESS)
	elif status in [HTTPClient.STATUS_DISCONNECTED,HTTPClient.STATUS_CANT_RESOLVE,HTTPClient.STATUS_CANT_CONNECT,HTTPClient.STATUS_CONNECTION_ERROR]:
		complete(HTTPRequest.RESULT_CONNECTION_ERROR)
