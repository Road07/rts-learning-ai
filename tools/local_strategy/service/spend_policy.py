"""Shared model features for purchases and explicitly selected gameplay commands."""
import numpy as np
from decision_net import features, bag, magnitude

ENCODING = "spend-v2"
EXTRA_KINDS = ("hero","research","science","power","enter","exit","stance","formation","cancel","stop")
WAIT = {"id":"none", "kind":"wait", "cost":0}


def spend_features(observation, candidate):
    # Same fog-filtered context as the tactical scorer, with a separate action head.
    context = features(observation, {"id":"none"})[:-11].tolist()
    kind = candidate["kind"]
    cost = float(candidate.get("cost",0))
    money = max(1.0,float(observation.get("money",0)))
    template = candidate.get("template", "")
    own = observation.get("human_state_features",{}).get("own_templates",{})
    context += [float(kind==k) for k in ("wait","build","train")]
    context += [float(int(candidate.get("role",-1))==r) for r in range(8)]
    context += [float(candidate.get("economy",False)), magnitude(cost,5000),
        min(3.0,cost/money), float(candidate.get("farm_share",0)), magnitude(own.get(template,0),10)]
    context += bag({template:1}) if template else [0.0]*16
    context += [float(kind==k) for k in EXTRA_KINDS]
    context += [float(candidate.get("source_health",1)),float(candidate.get("target_health",1)),
        magnitude(observation.get("spell_points",0),25),magnitude(candidate.get("points_cost",0),25),
        float(candidate.get("needs_position",False)),float(candidate.get("reviving",False))]
    context += [float(kind=="stance" and int(candidate.get("variant",0))==v) for v in (1,2,3)]
    context += [magnitude(candidate.get("source_distance_home",0),5000),magnitude(candidate.get("target_distance",0),5000)]
    context += [float(candidate.get("target_relation")==r) for r in ("self","ally","enemy")]
    context += [float(candidate.get("source_hero",False)),float(candidate.get("target_hero",False))]
    context += [float(int(candidate.get("source_role",-1))==r) for r in range(4)]
    context += [float(candidate.get("source_contained",False)),float(candidate.get("target_structure",False))]
    return np.asarray(context,dtype=np.float32)


def load_spend_model(path):
    from decision_net import DecisionNet
    model=DecisionNet.load(path)
    inputs=len(spend_features({},WAIT))
    old=model.weights["w0"].shape[0]
    if old==inputs: return model
    if old not in (inputs-16,inputs-32): raise ValueError("Unknown spend checkpoint dimensions")
    # Add explicit command-kind/state channels. Zero rows preserve every old score;
    # this is a feature migration, not evidence that the new actions were learned.
    for bank in [model]+list(model.factions.values()):
        bank.weights["w0"]=np.vstack([bank.weights["w0"],np.zeros((inputs-old,64),dtype=np.float32)])
    return model


def legal_spend_options(options, money):
    result = [dict(WAIT)]
    seen = {"none"}
    if not isinstance(options,list): raise ValueError("Invalid spend choices")
    for option in options:
        if not isinstance(option,dict): raise ValueError("Invalid spend choice")
        identifier = option.get("id")
        kind = option.get("kind")
        cost = float(option.get("cost",-1))
        if not isinstance(identifier,str) or kind not in ("build","train")+EXTRA_KINDS or not identifier.startswith(kind+":"):
            raise ValueError("Unsupported spend choice")
        if not np.isfinite(cost) or cost<0: raise ValueError("Invalid purchase price")
        if identifier in seen or cost>money: continue
        result.append(option)
        seen.add(identifier)
    return result
