extends RefCounted

# Soft preferences: counters and personality still override them.
const PROFILES = {
	"FactionWild":{"weights":[1.45,1.05,1.0,1.15],"capacity":3,"edge":"multi_lane_tunnel_pressure"},
	"FactionMordor":{"weights":[1.35,1.25,1.1,0.9],"capacity":3,"edge":"mass_with_ranged_support"},
	"FactionDwarves":{"weights":[1.2,1.0,1.2,0.85],"capacity":2,"edge":"concentrated_mine_push"},
	"FactionElves":{"weights":[0.85,1.4,1.25,1.0],"capacity":2,"edge":"protected_archer_line"},
	"FactionMen":{"weights":[1.0,1.1,1.1,1.2],"capacity":2,"edge":"heroes_and_combined_arms"},
	"FactionIsengard":{"weights":[1.15,1.05,1.15,1.1],"capacity":2,"edge":"upgraded_combined_arms"},
	"FactionAngmar":{"weights":[1.0,1.25,1.2,1.0],"capacity":2,"edge":"adaptive_thralls_and_elites"}
}

static func apply(faction: String, composition: Dictionary) -> void:
	var profile: Dictionary = PROFILES.get(faction,PROFILES.FactionMen)
	for i in 4:
		# Never dilute an urgent counter deficit with faction flavour.
		if float(composition.weights[i])<2.5: composition.weights[i]=clampf(float(composition.weights[i])*float(profile.weights[i]),0.25,4)
	composition["identity"]=profile.edge
