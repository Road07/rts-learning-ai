extends RefCounted

static func run(arena: Node) -> Dictionary:
	var world: Node=arena._world
	var owner: Dictionary=arena.participants[0]
	var choices: Array=world.strategy_production_options(int(owner.index)).filter(func(o): return o.kind=="train" and int(o.get("role",-1)) in [0,1,2,3])
	var proof={"fixture":true,"scope":"native receipts and inputs only, not expert learning labels"}
	if not arena.require(not choices.is_empty(),"feedback probe needs a legal recruit"): return proof
	var recruit: Dictionary=choices[0]
	var producer: int=int(recruit.producer)
	proof["producer"]=producer
	proof["template"]=recruit.template
	var start: Dictionary=world.strategy_model_action(int(owner.index),{"id":recruit.id})
	world.advance(0.8)
	var queued: Dictionary=world.get_production(int(owner.index),producer)
	if not arena.require(start.get("ok",false) and not queued.get("queue",[]).is_empty(),"feedback queue did not start"):return proof
	var entry: Dictionary=queued.queue[0]
	var cancellations: Array=world.strategy_model_options(int(owner.index),true).filter(func(o): return o.kind=="cancel" and int(o.producer)==producer and int(o.variant)==int(entry.id))
	if not arena.require(not cancellations.is_empty(),"feedback cancel option missing"):return proof
	proof["cancel_option"]=cancellations[0]
	var cancel: Dictionary=world.strategy_model_action(int(owner.index),{"id":cancellations[0].id})
	world.advance(0.2)
	proof["cancel_result"]=cancel
	var restart_options: Array=world.strategy_production_options(int(owner.index)).filter(func(o):return o.kind=="train" and int(o.producer)==producer and o.template==recruit.template)
	if not arena.require(not restart_options.is_empty(),"feedback restart not available"):return proof
	var restart: Dictionary=world.strategy_model_action(int(owner.index),{"id":restart_options[0].id})
	world.advance(0.2)
	var after: Dictionary=world.get_production(int(owner.index),producer)
	proof["native_receipts"]=after.get("production_receipts",[])
	var cancelled: Array=proof.native_receipts.filter(func(e):return e.kind=="cancelled" and int(e.production_id)==int(entry.id))
	arena.require(cancel.get("ok",false) and restart.get("ok",false) and cancelled.size()==1,"feedback actual cancellation receipt missing")
	if not cancelled.is_empty():
		arena.require(float(cancelled[0].progress)>0 and float(cancelled[0].work_frames)>0,"feedback lost work was not measured")
	var starts: Array=proof.native_receipts.filter(func(e):return e.kind=="queued")
	arena.require(starts.size()==2 and int(starts[0].production_id)!=int(starts[1].production_id),"feedback restart identities invalid")
	arena.require(cancellations[0].get("queue_verified",false),"feedback queue inputs absent")
	probe_research(arena,proof,producer)
	return proof

static func probe_research(arena: Node, proof: Dictionary, reserved: int) -> void:
	var world: Node=arena._world
	var player: int=int(arena.participants[0].index)
	var choices: Array=world.strategy_model_options(player,true).filter(func(o):return o.kind=="research" and int(o.producer)!=reserved)
	if not arena.require(not choices.is_empty(),"research receipt probe needs legal research"):return
	var choice: Dictionary=choices[0]
	var producer: int=int(choice.producer)
	proof["research_producer"]=producer
	var start: Dictionary=world.strategy_model_action(player,{"id":choice.id})
	world.advance(0.8)
	var queue: Dictionary=world.get_production(player,producer)
	var entries: Array=queue.get("queue",[]).filter(func(e):return e.get("queue_kind","")=="research" and e.template==choice.template)
	if not arena.require(start.get("ok",false) and entries.size()==1,"research did not enter native queue"):return
	var token: int=int(entries[0].queue_receipt_id)
	var options: Array=world.strategy_model_options(player,true).filter(func(o):return o.kind=="cancel" and int(o.producer)==producer and o.template==choice.template and int(o.get("queue_receipt_id",0))==token)
	if not arena.require(options.size()==1 and token>0,"research cancel observation identity absent"):return
	var cancel: Dictionary=world.strategy_model_action(player,{"id":options[0].id})
	world.advance(0.2)
	var fresh: Array=world.strategy_model_options(player,true).filter(func(o):return o.kind=="research" and int(o.producer)==producer and o.template==choice.template)
	if not arena.require(not fresh.is_empty(),"research restart option absent"):return
	var restart: Dictionary=world.strategy_model_action(player,{"id":fresh[0].id})
	world.advance(0.2)
	var receipts: Array=world.get_production(player,producer).get("production_receipts",[]).filter(func(e):return e.get("queue_kind","")=="research")
	proof["research"]={"template":choice.template,"cancel_option":options[0],"native_receipts":receipts}
	var cancelled: Array=receipts.filter(func(e):return e.kind=="cancelled" and int(e.queue_receipt_id)==token)
	var starts: Array=receipts.filter(func(e):return e.kind=="queued")
	arena.require(cancel.get("ok",false) and restart.get("ok",false) and cancelled.size()==1,"research native cancellation absent")
	arena.require(starts.size()==2 and int(starts[0].production_id)==0 and int(starts[1].production_id)==0 and int(starts[0].queue_receipt_id)!=int(starts[1].queue_receipt_id),"research observation identities invalid")
	if not cancelled.is_empty():
		arena.require(float(cancelled[0].progress)>0 and float(cancelled[0].work_frames)>0 and not cancelled[0].automatic,"research work or explicit-cancel flag absent")
