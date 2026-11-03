extends RefCounted

var samples: Array = []
var last_emit = -5000
var logbook: RefCounted

func summary() -> Dictionary:
	var output: Dictionary = {"samples":samples.size(),"fps":Engine.get_frames_per_second(),"headless":DisplayServer.get_name()=="headless"}
	for key in ["total_ms","snapshot_ms","decision_ms","orders_ms"]:
		var values: Array = samples.map(func(s): return float(s[key]))
		values.sort()
		if not values.is_empty():
			output[key]={"median":values[int(values.size()/2)],"p95":values[mini(values.size()-1,int(values.size()*0.95))],"max":values[-1]}
	return output

func record(frame: int, total_ms: float, snapshot_ms: float, decision_ms: float, orders_ms: float, world: Node):
	samples.append({"total_ms":total_ms,"snapshot_ms":snapshot_ms,"decision_ms":decision_ms,"orders_ms":orders_ms})
	if samples.size()>96: samples.pop_front()
	var now=Time.get_ticks_msec()
	if now-last_emit<5000: return
	last_emit=now
	var data=summary()
	data["frame"]=frame
	data["engine"]=world.get_frame_timings()
	logbook.write("ai_performance",data)
