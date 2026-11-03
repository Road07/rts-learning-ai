extends RefCounted

const C = preload("res://scripts/team_ai/contracts.gd")
var teams: Dictionary = {}
var half_life = 150.0
var minimum_confidence = 0.35
var logbook: RefCounted

func update(team: int, observer: int, obs: Dictionary, frame: int) -> bool:
	if not teams.has(team): teams[team] = {}
	var changed = false
	var friendly: Array = C.objects(obs,"self")+C.objects(obs,"ally")
	var friendly_bases: Array = friendly.filter(func(o): return o.base)
	for player in obs.get("players", []):
		if player.relation != "enemy": continue
		var old: Dictionary = teams[team].get(player.index, {"faction": player.faction, "contacts": {}, "build_order_observed": [], "powers": [], "heroes": {}, "style": "unknown", "confidence": 0.0, "frame": frame, "revision": 0})
		var previous_count = old.contacts.size()
		# Contact records are replaced, not mutated; a shallow map preserves the
		# previous observations without cloning every nested record again.
		var before_contacts: Dictionary = old.contacts.duplicate(false)
		var visible_army = 0
		var static_army = 0
		var exposed_farms = 0
		var visible_base: Dictionary = {}
		for object in player.objects:
			if object.base: visible_base = object
		for object in player.objects:
			var id = int(object.id)
			var before: Dictionary = old.contacts.get(id, {})
			if not object.structure:
				visible_army += 1
				if not before.is_empty() and frame - int(before.frame) > 0 and Vector2(object.x, object.y).distance_to(Vector2(before.value.x, before.value.y)) < 30: static_army += 1
			if object.get("economy", false):
				var nearby_guards = player.objects.filter(func(u): return not u.structure and Vector2(u.x, u.y).distance_to(Vector2(object.x, object.y)) < 500).size()
				if nearby_guards == 0: exposed_farms += 1
			var activity: Array = object.get("visible_activity", [])
			if not activity.is_empty() and (before.is_empty() or activity != before.value.get("visible_activity", [])):
				old.powers.append(C.record({"unit": id, "visible_conditions": activity}, frame, observer, 0.6))
				while old.powers.size() > 16: old.powers.pop_front()
			if not old.contacts.has(id) and object.structure:
				old.build_order_observed.append({"template": object.template, "first_seen": frame, "confidence": 1.0, "source": observer})
				if old.build_order_observed.size() > 40: old.build_order_observed.pop_front()
			old.contacts[id] = {"value": object.duplicate(true), "frame": frame, "confidence": 1.0, "source": observer}
			if object.get("hero", false):
				var preserving = false
				if not before.is_empty() and float(object.get("health_ratio", 1)) < 0.35:
					for ally in friendly:
						if not ally.structure and Vector2(object.x, object.y).distance_to(Vector2(ally.x, ally.y)) > Vector2(before.value.x, before.value.y).distance_to(Vector2(ally.x, ally.y)) + 30: preserving = true
				old.heroes[id] = C.record({"template": object.template, "health_ratio": object.get("health_ratio", 1), "preserving": preserving, "visible_ability": object.get("visible_activity", [])}, frame, observer)
		var counts = [0.0, 0.0, 0.0, 0.0]
		var confidence_sum = 0.0
		for id in old.contacts.keys():
			var contact: Dictionary = old.contacts[id]
			var confidence = pow(0.5, float(frame - int(contact.frame)) / maxf(1, half_life))
			if confidence < 0.05:
				old.contacts.erase(id)
				continue
			var role = int(contact.value.get("category", -1))
			if role >= 0 and role < 4: counts[role] += confidence
			confidence_sum += confidence
		var total = maxf(1.0, counts.reduce(func(a, b): return a + b, 0.0))
		old.composition = counts.map(func(n): return n / total)
		old.weaknesses = {"anti_cavalry_gap": C.record(clampf(1.0 - counts[2] / maxf(1, total * 0.25), 0, 1), frame, observer, minf(1, total / 6)), "anti_infantry_gap": C.record(clampf(1.0 - counts[1] / maxf(1, total * 0.25), 0, 1), frame, observer, minf(1, total / 6))}
		# Economy, reaction speed, tech and power dependence remain unknown until evidence exists.
		for key in ["economy", "harass_defence", "reaction_speed", "single_front", "over_aggression", "turtle", "power_dependence", "slow_tech"]:
			old.weaknesses[key] = C.record(0.0, frame, observer, 0.0)
		derive_observed_patterns(old, player.objects, before_contacts, friendly, visible_base, frame, observer)
		if exposed_farms > 0:
			old.weaknesses.harass_defence = C.record(minf(1, exposed_farms / 3.0), frame, observer, 0.6)
		if visible_army >= 3 and not visible_base.is_empty() and static_army >= visible_army * 0.75:
			var near_base = player.objects.filter(func(u): return not u.structure and Vector2(u.x, u.y).distance_to(Vector2(visible_base.x, visible_base.y)) < 700).size()
			if not old.has("hold_since"): old.hold_since = frame
			if near_base >= 3 and frame - int(old.hold_since) >= 150:
				old.style = "turtle"
				old.weaknesses.turtle = C.record(0.6, frame, observer, 0.4)
		else: old.erase("hold_since")
		var pressure = 0
		for object in player.objects:
			if object.structure: continue
			for building in friendly_bases:
				if Vector2(object.x, object.y).distance_to(Vector2(building.x, building.y)) < 700: pressure += 1
		if pressure > 0:
			old.style = "aggressive" if pressure >= 3 else "harass"
			old.weaknesses.over_aggression = C.record(minf(1, pressure / 6.0), frame, observer, 0.6)
		old.confidence = confidence_sum / maxf(1, old.contacts.size())
		old.frame = frame
		var signature = JSON.stringify([old.composition.map(func(r): return int(r * 5)), old.style, old.heroes.keys()])
		if old.contacts.size() != previous_count or signature != old.get("signature", ""):
			old.revision += 1
			old.signature = signature
			changed = true
			logbook.write("enemy_model_update", {"team": team, "enemy": player.index, "frame": frame, "revision": old.revision, "style": old.style, "confidence": old.confidence})
		teams[team][player.index] = old
	return changed

func summary(team: int) -> Dictionary:
	var out: Dictionary = {}
	for id in teams.get(team, {}):
		var p: Dictionary = teams[team][id]
		var known: Dictionary = {}
		var scored: Array = []
		for key in p.get("weaknesses", {}):
			var item: Dictionary = p.weaknesses[key]
			if float(item.confidence) >= minimum_confidence: scored.append({"key": key, "item": item, "score": float(item.value) * float(item.confidence)})
		scored.sort_custom(func(a, b): return a.score > b.score)
		for entry in scored.slice(0, 3):
			var item: Dictionary = entry.item.duplicate(true)
			item.value = snappedf(float(item.value), 0.01)
			item.confidence = snappedf(float(item.confidence), 0.01)
			known[entry.key] = item
		out[str(id)] = {"faction": p.faction, "style": p.style, "composition": p.get("composition", []).map(func(r): return snappedf(float(r), 0.01)), "weaknesses": known, "confidence": snappedf(float(p.confidence), 0.01), "frame": p.frame, "revision": p.revision}
		if not p.build_order_observed.is_empty(): out[str(id)]["observed_build_order"] = p.build_order_observed.slice(maxi(0, p.build_order_observed.size() - 4))
		if not p.powers.is_empty(): out[str(id)]["visible_power_activity"] = p.powers.slice(maxi(0, p.powers.size() - 2))
		var hero_ids: Array = p.heroes.keys()
		if not hero_ids.is_empty(): out[str(id)]["hero_usage"] = hero_ids.slice(0, 3).map(func(hero_id): return p.heroes[hero_id])
	return out

func derive_observed_patterns(profile: Dictionary, objects: Array, before: Dictionary, friendly: Array, base: Dictionary, frame: int, observer: int) -> void:
	var measurements: Dictionary = profile.get("measurements", {})
	var army = objects.filter(func(o): return not o.structure)
	if army.any(func(o): return int(o.get("category", -1)) == 7): profile.style = "tech"
	var farms = objects.filter(func(o): return o.get("economy", false))
	if not farms.is_empty():
		var damage = farms.reduce(func(total, o): return total + 1.0 - float(o.get("health_ratio", 1)), 0.0) / farms.size()
		measurements.economy = C.record(damage, frame, observer, 0.5)
	# Response is a local, observed movement estimate, not access to enemy orders.
	var probe: Dictionary = profile.get("response_probe", {})
	for farm in farms:
		var old: Dictionary = before.get(int(farm.id), {})
		if old.is_empty() or float(old.value.get("health_ratio", 1)) - float(farm.get("health_ratio", 1)) < 0.02: continue
		if friendly.any(func(o): return not o.structure and Vector2(o.x, o.y).distance_to(Vector2(farm.x, farm.y)) < 600) and probe.is_empty():
			probe = {"x": farm.x, "y": farm.y, "frame": frame}
	if not probe.is_empty():
		var at = Vector2(probe.x, probe.y)
		for unit in army:
			var previous: Dictionary = before.get(int(unit.id), {})
			if previous.is_empty(): continue
			var now_distance = Vector2(unit.x, unit.y).distance_to(at)
			if now_distance < 300 or Vector2(previous.value.x, previous.value.y).distance_to(at) - now_distance > 40:
				measurements.reaction_speed = C.record(clampf(float(frame - int(probe.frame)) / 75, 0, 1), frame, observer, 0.45)
				probe = {}
				break
		if not probe.is_empty() and frame - int(probe.frame) > 150: probe = {}
	profile.response_probe = probe
	if army.size() >= 6:
		var concentration = 0
		for unit in army:
			concentration = maxi(concentration, army.filter(func(o): return Vector2(o.x, o.y).distance_to(Vector2(unit.x, unit.y)) < 700).size())
		measurements.single_front = C.record(float(concentration) / army.size(), frame, observer, 0.4)
	var casts = profile.powers.filter(func(event): return frame - int(event.frame) < 300).size()
	if casts >= 2: measurements.power_dependence = C.record(minf(1, casts / 5.0), frame, observer, 0.35)
	# A long continuously observed base with no observed siege is weak evidence only.
	# This low-confidence proxy cannot drive exploitation at the default threshold.
	if base.is_empty(): profile.base_watch_start = frame
	elif not profile.has("base_watch_start"): profile.base_watch_start = frame
	elif frame > 1500 and frame - int(profile.base_watch_start) > 600 and not army.any(func(o): return int(o.get("category", -1)) == 7):
		measurements.slow_tech = C.record(0.4, frame, observer, 0.2)
	for key in measurements:
		var record: Dictionary = measurements[key].duplicate(true)
		record.confidence = float(record.confidence) * pow(0.5, float(frame - int(record.frame)) / maxf(1, half_life))
		profile.weaknesses[key] = record
	profile.measurements = measurements

func observed_power(team: int, enemy: int, power: String, frame: int, evidence: Dictionary) -> void:
	# Only verified visible events may enter here; never poll the enemy spellbook.
	if not evidence.get("visible", false) or int(evidence.get("frame", -1)) != frame or not teams.get(team, {}).has(enemy): return
	var profile: Dictionary = teams[team][enemy]
	profile.powers.append(C.record(power, frame, int(evidence.get("observer", -1))))
	while profile.powers.size() > 16: profile.powers.pop_front()
