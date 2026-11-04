"""Versioned numeric game facts; no preferred strategy or hidden enemy state."""
import math

ENCODING="rts-mechanics-v1"
STATE_KEYS=("economy_count","economy_mean_share","income_base_per_second","factories","idle_factories",
 "queued_items","builders","unfinished_buildings","army_value","hero_value","hero_lowest_health",
 "base_health","cp_used_fraction","wall_hubs","wall_segments","own_swords","own_ranged","own_pikes",
 "own_cavalry","enemy_swords","enemy_ranged","enemy_pikes","enemy_cavalry","home_threat_value",
 "army_home_fraction","ally_threat_value","game_seconds","spell_points")
SCALES={"army_value":10000.,"hero_value":10000.,"home_threat_value":10000.,"ally_threat_value":10000.,
 "income_base_per_second":25.,"economy_mean_share":1.,"base_health":1.,"hero_lowest_health":1.,
 "cp_used_fraction":1.,"army_home_fraction":1.,"game_seconds":1800.,"spell_points":25.}
ACTION_KEYS=("farm_share","base_income_per_second","builder_distance","home_distance","nearest_farm_distance",
 "pending_farm_overlap","visible_threat_value","build_seconds","cp_cost","wall_length","wall_tiles",
 "wall_seed","connected_wall","selected_value","selected_health","target_health","target_value",
 "target_economy","target_pikes","selected_cavalry_fraction","target_distance","own_local_value",
 "enemy_local_value","group_fraction")
ACTION_SCALES={"base_income_per_second":25.,"builder_distance":2000.,"home_distance":4000.,
 "nearest_farm_distance":2000.,"visible_threat_value":10000.,"build_seconds":180.,"cp_cost":100.,
 "wall_length":1000.,"wall_tiles":20.,"selected_value":10000.,"target_value":5000.,"target_distance":4000.,
 "own_local_value":10000.,"enemy_local_value":10000.,"pending_farm_overlap":5.}


def scaled(value, scale, field="unknown"):
    value=float(value or 0)
    if not math.isfinite(value) or value<0: raise ValueError("Invalid mechanics feature: %s=%s" % (field,value))
    return min(3.,value/scale)


def state_features(observation):
    data=observation.get("mechanics",{})
    return [float(data.get("schema")==ENCODING)]+[scaled(data.get(k,0),SCALES.get(k,10.),k) for k in STATE_KEYS]


def action_features(candidate):
    data=candidate.get("mechanics",candidate)
    return [scaled(data.get(k,0),ACTION_SCALES.get(k,1.),k) for k in ACTION_KEYS]
