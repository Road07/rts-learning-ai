"""Offline reward-weighted imitation of completed normal matches, not on-policy RL."""
import hashlib
import copy
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "service"))
from episode_policy import probabilities
from reward_policy import calculate_episode
from action_credit import calculate as calculate_credit, key as credit_key


def records(path, events):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not any('"'+event+'"' in line for event in events): continue
            try: row = json.loads(line)
            except ValueError: continue  # An interrupted trailing line is not data.
            if row.get("event") in events: yield row


def read_matches(service_logs, game_logs):
    for source in sorted(service_logs.glob("*.jsonl"), key=lambda p:p.stat().st_mtime, reverse=True):
        matches = {}
        for row in records(source, ["normal_match_start","normal_match_action","reward_observation","request_error","reward_error","host_error"]):
            match_id = row.get("match_id")
            if row["event"] == "normal_match_start" and not row.get("fixture") and row.get("schema") == "normal-trajectory-v1":
                matches[match_id] = {"start":row, "actions":[], "rows":[], "credit_events":[], "source":str(source)}
            elif match_id in matches:
                match = matches[match_id]
                if row["event"] == "normal_match_action": match["actions"].append(row)
                elif row["event"] == "reward_observation": match["rows"].append(row["sample"])
            elif row["event"] in ("request_error","reward_error","host_error"):
                for match in matches.values(): match["invalid"] = True
        for match_id, match in matches.items():
            if match.get("invalid") or not match["actions"]: continue
            session = str(match["start"].get("diagnostic_session", ""))
            if not session or Path(session).name != session: continue
            accepted, closed = set(), None
            for segment in sorted(game_logs.glob(session + "-*.jsonl")):
                for row in records(segment, ["normal_match_closed","model_decision","decision_credit_action"]):
                    data = row.get("data", {})
                    if data.get("match_id") != match_id: continue
                    if row["event"] == "normal_match_closed" and not data.get("fixture"): closed = data
                    elif row["event"] == "decision_credit_action": match["credit_events"].append(data)
                    elif row["event"] == "model_decision": accepted.add((int(data["player"]), int(data["observed_frame"])))
            if closed is None: continue
            match["rows"] += closed.get("samples", [])
            match["actions"] = [a for a in match["actions"] if (int(a["player"]),int(a["frame"])) in accepted]
            match["id"] = hashlib.sha256(match_id.encode()).hexdigest()
            yield match


def imitation_update(model, traces, weight, learning_rate=.001):
    if not traces: return {"updated":False, "reason":"no_verified_winning_choices"}
    selected = [traces[i] for i in np.linspace(0,len(traces)-1,min(128,len(traces)),dtype=int)]
    gradients = {key:np.zeros_like(value) for key,value in model.weights.items()}
    cached = []
    for trace in selected:
        x = np.asarray(trace["features"], dtype=np.float32)
        index = int(trace["selected_index"])
        if x.ndim != 2 or x.shape[1] != model.weights["w0"].shape[0] or not 1 <= len(x) <= 17 or not np.isfinite(x).all() or not 0 <= index < len(x):
            raise ValueError("Invalid normal-match feature trace")
        if len(x) < 2: continue
        scores, cache = model.forward(x)
        p = probabilities(scores)
        derivative = p.copy(); derivative[index] -= 1
        signed=float(trace.get("credit_weight",weight))
        if not np.isfinite(signed): raise ValueError("Invalid normal decision credit")
        gradient = model.gradients(derivative * float(np.clip(signed,-1,1)) / len(selected), cache)
        for key in gradients: gradients[key] += gradient[key]
        cached.append((x,p))
    if not cached: return {"updated":False,"reason":"no_multichoice_actions"}
    norm = float(np.sqrt(sum(float((g*g).sum()) for g in gradients.values())))
    previous = {key:value.copy() for key,value in model.weights.items()}
    for key in gradients: model.weights[key] -= learning_rate * min(1.,1./max(norm,1e-12)) * gradients[key]
    kl = float(np.mean([np.sum(p*np.log(p/np.maximum(probabilities(model.forward(x)[0]),1e-12))) for x,p in cached]))
    if not np.isfinite(kl) or kl>.005 or any(not np.isfinite(v).all() for v in model.weights.values()):
        model.weights = previous
        return {"updated":False,"reason":"normal_match_kl_guard"}
    return {"updated":bool(norm>1e-12),"actions":len(cached),"kl":kl,"method":"offline_signed_outcome_contrast" if any("credit_weight" in t for t in selected) else "legacy_reward_weighted_imitation"}


def replay_one(model, spend_model, root):
    root = Path(root)
    runs = root / "AI-Egitim/otomatik-dongu"
    used = set()
    for path in runs.glob("*/report.json"):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get("status") == "complete": used.update(row["id"] for row in report.get("normal_matches", []))
        except (OSError,ValueError,KeyError): continue
    for match in read_matches(root / "AI-Yeni-Model/ai-service/logs", root / "AI-Yeni-Model/logs"):
        if match["id"] in used: continue
        players = {}
        for row in match["rows"]: players.setdefault(tuple(sorted(map(int,row["team_members"]))),set()).add(int(row["player"]))
        teams = []
        try:
            for members, learners in players.items():
                reward = calculate_episode(match["start"]["reward_tuning"],match["rows"],sorted(learners))
                teams.append((learners,reward))
        except (ValueError,KeyError,TypeError): continue
        # Closing the game is not a victory. Require observed terminal outcomes.
        if not teams or not any(r["outcome"] in ("win","loss") for _,r in teams): continue
        winners = set().union(*(p for p,r in teams if r["outcome"] == "win"))
        try:
            credit,credit_metrics=calculate_credit(match["start"]["reward_tuning"],match["rows"],match["credit_events"])
        except (ValueError,KeyError,TypeError): continue
        if not credit: continue
        if credit:
            actions=[]
            for action in match["actions"]:
                action=copy.deepcopy(action)
                for head in ("tactical","spend"):
                    value=credit.get(credit_key(action["player"],action["frame"],head),{})
                    action[head]["credit_weight"]=float(value.get("reward",0.))
                if any(abs(action[h]["credit_weight"])>1e-12 for h in ("tactical","spend")): actions.append(action)
        else:
            actions = [a for a in match["actions"] if int(a["player"]) in winners]
        if model.factions:
            actions = [a for a in actions if a.get("faction") in model.factions]
        if not actions: continue
        tactical_before = copy.deepcopy((model.weights,model.factions))
        spend_before = copy.deepcopy((spend_model.weights,spend_model.factions))
        try:
            tactic = faction_imitation(model,actions,"tactical")
            spend = faction_imitation(spend_model,actions,"spend")
        except (ValueError,KeyError,TypeError,IndexError):
            model.weights, model.factions = tactical_before
            spend_model.weights, spend_model.factions = spend_before
            continue
        return [{"id":match["id"],"match_id":match["start"]["match_id"],"source":match["source"],
                 "method":"offline signed local outcomes; not on-policy or human labels" if credit else "legacy winning-bot imitation",
                 "decision_credit_metrics":credit_metrics,"rewards":[r for _,r in teams],"update":tactic,"spend_update":spend}]
    return []


def faction_imitation(model, actions, head):
    if not model.factions: return imitation_update(model,[a[head] for a in actions],1.)
    results = {}
    for faction, bank in model.factions.items():
        traces = [a[head] for a in actions if a.get("faction") == faction]
        if traces: results[faction] = imitation_update(bank,traces,1.)
    return {"updated":any(r["updated"] for r in results.values()),"factions":results,
            "method":"faction-isolated reward-weighted imitation"}
