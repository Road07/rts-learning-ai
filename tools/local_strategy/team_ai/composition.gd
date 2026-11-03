extends RefCounted

func desired(own: Array, enemies: Array, allied: Array) -> Dictionary:
	var current = [0, 0, 0, 0]
	var seen = [0, 0, 0, 0]
	var team = [0, 0, 0, 0]
	for pair in [[own, current], [enemies, seen], [allied, team]]:
		for unit in pair[0]:
			var role = int(unit.get("category", -1))
			if not unit.structure and role >= 0 and role < 4: pair[1][role] += 1
	var weights = [1.0, 1.0, 1.0, 1.0]
	var needed_pikes = int(ceil(float(seen[3])*0.9+float(current[1])*0.3))
	var pike_deficit = maxi(0,needed_pikes-current[2])
	if seen[3] > 0: weights[2] = clampf(1.2+float(pike_deficit)*0.8,1.2,4)
	if seen[2] > 0:
		weights[1] = 2.0
		weights[3] = 0.4
	elif seen[1] + seen[0] > 0: weights[3] = clampf(1.0+float(maxi(0,int(ceil(seen[1]*0.6))-current[3]))*0.7,1.0,3.5)
	for i in range(4):
		if current[i] == 0 and i < 3: weights[i] *= 1.4
		if team[i] == 0 and i < 3: weights[i] *= 1.15
	return {"weights": weights, "own": current, "enemy": seen, "team": team,"pike_deficit":pike_deficit}

# Apply after faction, opening and exploitation multipliers. Visible counters
# keep their urgency; they do not override unit caps or factory prerequisites.
func protect_counters(comp: Dictionary) -> void:
	if int(comp.pike_deficit)>0 and int(comp.enemy[3])>0:
		comp.weights[2]=maxf(float(comp.weights[2]),minf(4.0,2.4+float(comp.pike_deficit)*0.4))
	if int(comp.enemy[2])>0:
		comp.weights[3]=minf(float(comp.weights[3]),0.4)
	if int(comp.own[1])>=3: comp.weights[1]=0.25
	if int(comp.own[3])>=2: comp.weights[3]=0.25
