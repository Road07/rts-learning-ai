"""Bounded arena rollouts -> survival reward -> policy gradient -> paired evaluation.

Trains tactical and legal build/train/wait scorers in the isolated test arena.
All artifacts/checkpoints are separate from the model used in normal matches.
"""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
import argparse
from datetime import datetime
import hashlib
import json
import msvcrt
from pathlib import Path
import shutil
import subprocess
import sys
import numpy as np
from decision_net import DecisionNet, features, FACTIONS, load_tactical_model

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent / "service"))
from episode_policy import probabilities
from spend_policy import spend_features, load_spend_model, ENCODING
from reward_policy import calculate_episode
from action_credit import calculate as calculate_credit, key as credit_key, credit_version
from economy_evaluation import evaluate as evaluate_economy, compare as compare_economy
from feedback_audit import build as audit_feedback


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path=Path(path)
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False),encoding="utf-8")
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def survival_reward(report):
    data = report["training"]
    if data["reward_version"] not in ("initial-own-assets-v1","survival-income-army-v2") or not data["truncated"]:
        raise ValueError("Unexpected reward schema")
    final = {(int(o["player"]), int(o["id"])): float(o["health"]) for o in data["final"]}
    denominator = 0.0
    delta = 0.0
    for obj in data["initial"]:
        cost = float(obj["cost"])
        health = float(obj["health"])
        if not np.isfinite(cost) or cost < 0 or not 0 <= health <= 1:
            raise ValueError("Invalid initial asset")
        after = final.get((int(obj["player"]), int(obj["id"])), 0.0)
        if not np.isfinite(after) or not 0 <= after <= 1: raise ValueError("Invalid final asset")
        denominator += cost
        delta += cost * (after - health)
    if denominator <= 0: raise ValueError("No priced initial assets")
    reward=delta / denominator
    if data["reward_version"]=="survival-income-army-v2":
        before,after=data["initial_finance"],data["final_finance"]
        for state in (before,after):
            if any(not np.isfinite(float(state[k])) or float(state[k])<0 for k in ("earned","military_value")):
                raise ValueError("Invalid financial measurement")
        if after["earned"]<before["earned"]: raise ValueError("Earned counter decreased")
        reward+=.25*((after["earned"]-before["earned"])+(after["military_value"]-before["military_value"]))/denominator
    return reward


def episode_data(folder, stage, arena_logs):
    report = read_json(folder / "arena" / (stage + ".json"))
    if not report.get("ok") or report.get("script_errors") or report.get("exit_code"):
        raise RuntimeError("Arena failed; episode cannot enter training")
    records = [json.loads(s) for s in (folder / "service.jsonl").read_text(encoding="utf-8").splitlines() if s.strip()]
    if any(r["event"] in ("host_error", "request_error","reward_error") for r in records):
        raise RuntimeError("Inference failed; episode cannot enter training")
    actions = [r for r in records if r["event"] == "episode_action"]
    spend_actions=[r for r in records if r["event"]=="episode_spend_action"]
    purchases=[]
    commands=[]
    responses=set()
    accepted = set()
    orders = 0
    credit_events=[]
    arena_logs=Path(report.get("telemetry_directory",arena_logs))
    paths = sorted(arena_logs.glob(report["diagnostic_session"] + "-*.jsonl"))
    if not paths: raise RuntimeError("Missing exact game session telemetry")
    telemetry = folder / "telemetry"
    telemetry.mkdir(exist_ok=True)
    for path in paths:
        shutil.copy2(path, telemetry / path.name)
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            data = row.get("data", {})
            if row["event"] == "decision_credit_action": credit_events.append(data)
            if row["event"] == "model_decision" and data.get("training_action_id"):
                accepted.add(data["training_action_id"])
            if row["event"]=="training_spend_response": responses.add(data["action_id"])
            if row["event"]=="model_production" and data.get("action_id"): purchases.append(data)
            if row["event"]=="model_command" and data.get("action_id"): commands.append(data)
            if row["event"] in ("general_order", "cohort_order") and data.get("result", {}).get("ok"):
                orders += 1
    # Preserve no-op/rejected samples too: selecting only accepted actions would bias
    # the sampled policy gradient. Acceptance is an audit gate, not a success label.
    purchase_ids=[p["action_id"] for p in purchases+commands]
    if len(purchase_ids)!=len(set(purchase_ids)): raise RuntimeError("Duplicate purchase dispatch; episode excluded")
    for action in actions:
        action["intent_accepted"] = action["action_id"] in accepted
    for action in spend_actions: action["response_received"]=action["action_id"] in responses
    breakdown=None
    feedback_report=None
    economy_report={"schema":"economy-production-eval-v1","status":"missing_telemetry","players":[]}
    if report["training"]["reward_version"]=="bfme-outcome-reward-v3":
        config_record=next(r for r in records if r["event"]=="reward_config_loaded")
        reward_path=folder / "reward-tuning.json"
        if sha(reward_path)!=config_record["sha256"]: raise ValueError("Episode reward tuning changed")
        rows=[r["sample"] for r in records if r["event"]=="reward_observation"]+report.get("reward_final_samples",[])
        economy_report=evaluate_economy(rows,credit_events)
        economy_report.update(fixture=True,stage=stage)
        learners=[int(p["player"]) for p in report["initial"][:3]]
        breakdown=calculate_episode(read_json(reward_path),rows,learners)
        reward=breakdown["total"]
        credit,credit_metrics=calculate_credit(read_json(reward_path),rows,credit_events)
        feedback_report=audit_feedback(learners,{'tactical':actions,'spend':spend_actions},credit,credit_events)
        policy_version=credit_version(read_json(reward_path))
        for head,traces in [("tactical",actions),("spend",spend_actions)]:
            for action in traces:
                obs=action["observation"]
                action["decision_credit"]=credit.get(credit_key(obs["player_index"],obs.get("decision_frame",-1),head),
                    {"version":policy_version,"reward":0.,"components":{},"matured":False,"reason":"no_confirmed_dispatch"})
        local=[v for (player,_,_),v in credit.items() if player in learners]
        components={}
        for value in local:
            for name,amount in value["components"].items(): components[name]=components.get(name,0.)+amount
        terminal=sum(v["terminal_share"] for v in local)
        shaping=sum(components.values())
        breakdown={"version":"bfme-outcome-reward-v3","credit_version":policy_version,
            "team":breakdown["team"],"components":components,"terminal":terminal,"shaping":shaping,
            "outcome":breakdown["outcome"],"total":terminal+shaping,"samples":breakdown["samples"],
            "legacy_team_summary":breakdown,"decision_credit":{"version":policy_version,"decisions":len(credit),"metrics":credit_metrics,
            "attribution":"observed actor/target/time association; not counterfactual causality"}}
        reward=breakdown["total"]
    else: reward=survival_reward(report)
    write_json(folder / "economy-evaluation.json",economy_report)
    write_json(folder / "feedback-audit.json",feedback_report)
    write_json(folder / "experience.json", {"schema": 1, "fixture": True,
        "reward_version": report["training"]["reward_version"], "reward": reward,"reward_breakdown":breakdown,"economy_evaluation":economy_report,
        "feedback_audit":feedback_report,"spend_actions":spend_actions,"purchase_submissions":purchases,
        "command_submissions":commands,
        "purchase_receipts":report.get("training_purchase_receipts",[]),
        "purchase_pending":report.get("training_purchase_pending",0),
        "actions": actions, "accepted_intents": len(accepted), "real_orders_all_bots": orders,
        "truncated": breakdown is None or breakdown["outcome"]=="ongoing", "win_label":breakdown["outcome"] if breakdown and breakdown["outcome"]!="ongoing" else None})
    return reward, actions, len(accepted), spend_actions


def update(model, actions, reward, baseline, learning_rate, encoder=features):
    if model.factions:
        by_faction = {}
        for faction, bank in model.factions.items():
            own = [a for a in actions if a["observation"].get("faction") == faction]
            if own: by_faction[faction] = update(bank,own,reward,baseline.get(faction,0.) if isinstance(baseline,dict) else baseline,learning_rate,encoder)
        if any(a["observation"].get("faction") not in model.factions for a in actions):
            raise ValueError("Unlabelled faction trajectory")
        return {"updated":any(r["updated"] for r in by_faction.values()), "factions":by_faction,
                "reward_scope":"actor/target/time decision credit; gradients isolated by faction" if any("decision_credit" in a for a in actions) else "legacy shared team outcome; gradients isolated by faction"}
    trainable = [a for a in actions if len(a["candidates"]) > 1]
    if not trainable: return {"updated": False, "reason": "no_multichoice_actions"}
    advantages=[float(np.clip(a["decision_credit"]["reward"] if "decision_credit" in a else reward-baseline,-1,1)) for a in trainable]
    if not any(abs(a)>1e-10 for a in advantages): return {"updated": False, "reason": "no_mature_observed_credit"}
    gradients = {k: np.zeros_like(v) for k, v in model.weights.items()}
    cached = []
    for action, advantage in zip(trainable,advantages):
        x = np.stack([encoder(action["observation"], c) for c in action["candidates"]])
        scores, cache = model.forward(x)
        p = probabilities(scores)
        logged = np.asarray(action["probabilities"])
        if not np.allclose(p, logged, rtol=1e-5, atol=1e-7):
            raise ValueError("Off-policy/stale trajectory rejected")
        chosen = int(action["selected_index"])
        if not 0 <= chosen < len(p): raise ValueError("Invalid sampled index")
        derivative = p.copy()
        derivative[chosen] -= 1
        # Sum log probabilities for the shared team return, then clip the norm.
        g = model.gradients(derivative * advantage, cache)
        for key in gradients: gradients[key] += g[key]
        cached.append((x, p))
    norm = float(np.sqrt(sum(float((g*g).sum()) for g in gradients.values())))
    old = {k: v.copy() for k, v in model.weights.items()}
    scale = min(1.0, 1.0 / max(norm, 1e-12))
    for key in gradients: model.weights[key] -= learning_rate * scale * gradients[key]
    kl = float(np.mean([np.sum(p * np.log(p / np.maximum(probabilities(model.forward(x)[0]), 1e-12))) for x,p in cached]))
    if not np.isfinite(kl) or kl > 0.02 or any(not np.isfinite(v).all() for v in model.weights.values()):
        model.weights = old
        return {"updated": False, "reason": "numerical_or_kl_guard", "kl": kl}
    return {"updated": True, "actions": len(trainable), "advantage":float(np.mean(advantages)), "gradient_norm": norm, "kl": kl,
            "credit":"decision_outcomes" if any("decision_credit" in a for a in trainable) else "legacy_team_return"}


def episode_environment(args, config, seed, mode, roster_seed=None):
    config=dict(config)
    for key in ('persistent_http','compact_wire','feature_cache','batch_wire'):
        if hasattr(args,key):config[key]=getattr(args,key)
    if hasattr(args,'engine_package'):config['arena_engine_directory']=args.engine_package
    if getattr(args,"inference_profile",False):
        config["inference_profile"]=True
        config["profile_hash_stride"]=getattr(args,"hash_stride",1)
    if args.rotate_factions:
        anchor=args.seed if roster_seed is None else roster_seed
        config["arena_factions"]=[FACTIONS[(anchor+i)%len(FACTIONS)] for i in range(6)]
    if getattr(args,"headless_training",False):
        config.update(arena_headless_training=True,arena_time_scale=args.time_scale,arena_sim_frames=int(round(args.seconds*5)),arena_decision_stride=getattr(args,"decision_stride",5),arena_fast_poll=getattr(args,"headless_fast_poll",False))
    elif mode=="evaluate": config["arena_sim_frames"]=int(round(args.seconds*20))
    else: config.pop("arena_sim_frames",None)
    return config


def run_episode(args, run, name, weights, opponent, seed, mode, spend_weights, opponent_spend_weights, roster_seed=None):
    print(json.dumps({"event":"episode_phase","phase":name,"seconds":args.seconds},ensure_ascii=False),flush=True)
    config = episode_environment(args,read_json(args.config),seed,mode,roster_seed)
    config.update(weights=str(weights), sha256=sha(weights), opponent_weights=str(opponent))
    config.update(spend_weights=str(spend_weights),spend_sha256=sha(spend_weights),spend_encoding=ENCODING)
    config["opponent_spend_weights"]=str(opponent_spend_weights)
    config_path = run / (name + "-runtime.json")
    write_json(config_path, config)
    folder = run / name
    command = [sys.executable, str(args.config.parent / "host.py"), "--config", str(config_path),
        "--arena", args.stage, "--arena-case", args.case, "--seconds", str(args.seconds),
        "--episode-dir", str(folder), "--episode-seed", str(seed), "--episode-mode", mode]
    with (run / (name + "-process.log")).open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try: code = process.wait(timeout=90 + args.seconds*(1.5 if config.get("arena_sim_frames") else 1))
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=log, stderr=subprocess.STDOUT)
            process.wait(timeout=10)
            raise RuntimeError("Episode timed out")
        except BaseException:
            if process.poll() is None:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=log, stderr=subprocess.STDOUT)
                process.wait(timeout=10)
            raise
    if code:
        detail = ""
        service_log = folder / "service.jsonl"
        if service_log.is_file():
            failures = [json.loads(line) for line in service_log.read_text(encoding="utf-8").splitlines() if line.strip()]
            failures = [row for row in failures if row.get("event") == "host_error"]
            if failures: detail = str(failures[-1].get("error", "")) + " "
        raise RuntimeError("Episode failed: " + detail + str(run / (name + "-process.log")))
    return episode_data(folder, args.stage, Path(config["arena_directory"]) / "logs")


def resumable_evaluation(run, config_path):
    """Only a committed training pair can resume; never train a partial rollout twice."""
    run=Path(run).resolve()
    report=read_json(run / "report.json")
    settings=report["settings"]
    if report.get("status")!="running" or not settings.get("evaluate") or len(report.get("rounds",[]))!=settings["cycles"]:
        raise ValueError("No committed training awaiting evaluation")
    last=report["rounds"][-1]
    for name, expected in [("candidate.npz",last["checkpoint_sha256"]),("spend-candidate.npz",last["spend_sha256"]),("baseline.npz",report["baseline_sha256"])]:
        if sha(run/name)!=expected: raise ValueError("Changed resume checkpoint: "+name)
    old=read_json(run/"train-000-runtime.json")
    current=read_json(config_path)
    for field in ["reward_sha256","game_rules_sha256"]:
        if old.get(field)!=current.get(field): raise ValueError("Resume environment changed: "+field)
    same_spend=sha(run/"spend-baseline.npz")==current["spend_sha256"]
    if not same_spend:
        # Loading may have appended zero feature rows before saving the baseline.
        # Compare every preserved bank, not container hashes across migration.
        left=load_spend_model(run/"spend-baseline.npz").ensure_factions()
        right=load_spend_model(current["spend_weights"]).ensure_factions()
        same_spend=all(np.array_equal(a.weights[k],b.weights[k]) for a,b in [(left,right)]+[(left.factions[f],right.factions[f]) for f in FACTIONS] for k in a.weights)
    if report["baseline_sha256"]!=current["sha256"] or not same_spend:
        raise ValueError("Active baseline changed; interrupted evaluation cannot resume")
    return report


def evaluate_pair(args,run,report,baseline,candidate,spend_baseline,spend_candidate):
    seed=args.seed+100000
    roster_seed=args.seed+args.cycles-1
    episodes=[]
    for label,weights,spend in [("eval-baseline",baseline,spend_baseline),("eval-candidate",candidate,spend_candidate)]:
        progress=report.setdefault("evaluation_progress",{})
        saved=progress.get(label)
        if saved and saved.get("weights_sha256")==sha(weights) and saved.get("spend_sha256")==sha(spend):
            name=saved["name"]
            reward,_,_,_=episode_data(run/name,args.stage,Path(read_json(args.config)["arena_directory"])/"logs")
        else:
            name=label
            retry=0
            while (run/name).exists():
                retry+=1; name=label+"-retry-%03d"%retry
            reward,_,_,_=run_episode(args,run,name,weights,baseline,seed,"evaluate",spend,spend_baseline,roster_seed=roster_seed)
            progress[label]={"name":name,"weights_sha256":sha(weights),"spend_sha256":sha(spend)}
            write_json(run/"report.json",report)
        episodes.append((name,reward))
    report["evaluation"]={"baseline_reward":episodes[0][1],"candidate_reward":episodes[1][1],"difference":episodes[1][1]-episodes[0][1],"pairs":1,"sufficient_to_claim_strength":False}
    comparison=compare_economy(read_json(run/episodes[0][0]/"economy-evaluation.json"),read_json(run/episodes[1][0]/"economy-evaluation.json"))
    comparison.update(stage=args.stage,case=args.case,seed=seed,learner_slots=[0,1,2],roster_seed=roster_seed,simulation_frames=int(round(args.seconds*(5 if getattr(args,"headless_training",False) else 20))),baseline_sha256=sha(baseline),candidate_sha256=sha(candidate),baseline_spend_sha256=sha(spend_baseline),candidate_spend_sha256=sha(spend_candidate),opponent_sha256=sha(baseline),opponent_spend_sha256=sha(spend_baseline))
    report["evaluation"]["economy_production"]=comparison
    write_json(run/"economy-comparison.json",comparison)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "AI-Yeni-Model/ai-service/runtime.json")
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--seconds", type=int, default=6)
    parser.add_argument("--stage", choices=["opening", "middle", "late"], default="middle")
    parser.add_argument("--case", choices=["pressure", "counters", "baseline", "team","mechanics","cp-accounting","learning-feedback"], default="pressure")
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--evaluate", action="store_true", help="Two additional paired evaluation episodes on fresh seeds")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", type=Path, help="Continue an earlier candidate checkpoint, never change the live model")
    parser.add_argument("--resume-spend",type=Path,help="Matching spend checkpoint when continuing an earlier run")
    parser.add_argument("--no-activate", action="store_true", help="Keep this verification run separate from the playable model")
    parser.add_argument("--rotate-factions", action="store_true", help="Rotate all seven factions through learner slots")
    parser.add_argument("--resume-evaluation",action="store_true",help="Resume a committed training round without applying another gradient update")
    parser.add_argument("--engine-package",help="Pin one validated engine package for the whole training/evaluation pair")
    parser.add_argument("--headless-training",action="store_true",help="Private headless fixed-step rollout; --seconds is simulation time")
    parser.add_argument("--headless-fast-poll",action="store_true",help="Remove Godot headless idle frame delay; keep native logic step unchanged")
    parser.add_argument("--decision-stride",type=int,choices=[5,10,15,20],default=5,help="Global decision scheduler frames; default unchanged")
    parser.add_argument("--time-scale",type=float,default=10.,help="Headless target wall-clock speed")
    args = parser.parse_args()
    if not 1 <= args.cycles <= 100 or not 1 <= args.seconds <= 1800 or not 0 < args.learning_rate <= .05:
        parser.error("cycles 1..100, seconds 1..1800, learning-rate (0,.05]")
    if not np.isfinite(args.time_scale) or not .25<=args.time_scale<=100:parser.error("time-scale: 0.25..100")
    args.config = args.config.resolve()
    benchmark_suite=read_json(args.config).get("benchmark_suite")
    if benchmark_suite:
        heldout={int(g["seed"]) for g in read_json(Path(benchmark_suite)/"suite.json")["plan"]}
        used=set(range(args.seed,args.seed+args.cycles))
        if args.evaluate: used.add(args.seed+100000)
        if heldout & used: parser.error("Benchmark seeds are held out; choose a different training seed")

    if args.engine_package is None:
        sys.path.insert(0,str(HERE.parent))
        from engine_update import active
        engine=active()
        args.engine_package=engine['directory'] if engine else ''
    lock_path = ROOT / "AI-Test-Sahasi/training.lock"
    lock = lock_path.open("a+b")
    lock.seek(0)
    if not lock.read(1): lock.write(b"0"); lock.flush()
    lock.seek(0)
    try: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock.close()
        raise RuntimeError("Another training loop is already running")
    run = args.output or ROOT / "AI-Egitim/otomatik-dongu" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + str(os.getpid()))
    run = run.resolve()
    if args.resume_evaluation:
        try:
            report=resumable_evaluation(run,args.config)
            args.no_activate=args.no_activate or report["settings"].get("no_activate",False)
            args.headless_training=bool(report["settings"].get("headless_training",False))
            args.decision_stride=int(report["settings"].get("decision_stride",5))
            args.headless_fast_poll=bool(report["settings"].get("headless_fast_poll",False))
            args.time_scale=float(report["settings"].get("time_scale",10.))
            for field in ["cycles","seconds","stage","case","seed","rotate_factions","engine_package"]:
                setattr(args,field,report["settings"].get(field,getattr(args,field)))
            evaluate_pair(args,run,report,run/"baseline.npz",run/"candidate.npz",run/"spend-baseline.npz",run/"spend-candidate.npz")
            report.update(status="complete",candidate_sha256=sha(run/"candidate.npz"),live_model_unchanged=True)
            write_json(run/"report.json",report)
            if not args.no_activate:
                from model_activation import activate
                report["activation"]=activate(run,args.config)
                report["activated"]=bool(report["activation"].get("changed") or report["activation"].get("source_run")==str(run))
                report["live_model_unchanged"]=not report["activated"]
                write_json(run/"report.json",report)
        finally: lock.close()
        return
    run.mkdir(parents=True, exist_ok=False)
    initial = Path(read_json(args.config)["weights"])
    initial_sha=sha(initial)
    baseline = run / "baseline.npz"
    candidate = run / "candidate.npz"
    shutil.copy2(args.resume.resolve() if args.resume else initial, baseline)
    shutil.copy2(baseline, candidate)
    model = load_tactical_model(candidate).ensure_factions()
    model.save(candidate)
    spend_baseline=run / "spend-baseline.npz"
    spend_candidate=run / "spend-candidate.npz"
    spend_source=args.resume_spend
    if args.resume and not spend_source and args.resume.with_name("spend-candidate.npz").exists(): spend_source=args.resume.with_name("spend-candidate.npz")
    if spend_source:
        meta=read_json(spend_source.with_name("spend-metadata.json"))
        if meta.get("encoding") not in (ENCODING,"spend-v1"): raise ValueError("Spend resume encoding mismatch")
        spend_model=load_spend_model(spend_source)
    elif read_json(args.config).get("spend_weights"):
        spend_model=load_spend_model(read_json(args.config)["spend_weights"])
    else: spend_model=DecisionNet(len(spend_features({}, {"kind":"wait","id":"none"})),seed=args.seed)
    spend_model.ensure_factions()
    spend_model.save(spend_baseline)
    shutil.copy2(spend_baseline,spend_candidate)
    write_json(run / "spend-metadata.json",{"encoding":ENCODING,"features":len(spend_features({}, {"kind":"wait","id":"none"})),"mechanics_encoding":"rts-mechanics-v1","public_rules_encoding":"bfme-public-rules-v2","queue_encoding":"native-queue-v1","game_rules_sha256":read_json(args.config).get("game_rules_sha256"),"faction_encoding":"faction-bank-v1","factions":FACTIONS})
    report = {"schema": 3, "status": "running", "scope": "bounded versioned actor/target/time credit + terminal outcome v3; no command/refund bonus",
        "settings": {k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},
        "baseline_sha256": sha(baseline), "initial_candidate_sha256":sha(candidate), "rounds": [], "activated": False,
        "faction_learning":{"encoding":"faction-bank-v1","factions":FACTIONS,"shared_initial_knowledge":True,"shared_gradients":False}}
    write_json(run / "report.json", report)
    running_baseline = {f:0.0 for f in FACTIONS}
    try:
        if not args.no_activate and args.config == ROOT / "AI-Yeni-Model/ai-service/runtime.json":
            from normal_match_training import replay_one
            report["normal_matches"] = replay_one(model, spend_model, ROOT,expected_credit_version=credit_version(read_json(read_json(args.config)["reward_config"])))
            if report["normal_matches"]:
                model.save(candidate)
                spend_model.save(spend_candidate)
                write_json(run / "report.json", report)
                print("Normal maç kaydı eğitim ağına işlendi.", flush=True)
        for i in range(args.cycles):
            print("Rollout %d/%d" % (i+1, args.cycles), flush=True)
            reward, actions, accepted, spend_actions = run_episode(args, run, "train-%03d" % i, candidate, baseline, args.seed+i, "sample",spend_candidate,spend_baseline,roster_seed=args.seed+i)
            result = update(model, actions, reward, running_baseline, args.learning_rate) if accepted else {"updated":False,"reason":"no_accepted_intent"}
            if result["updated"]: model.save(candidate)
            spend_result=update(spend_model,spend_actions,reward,running_baseline,args.learning_rate,spend_features) if any(a["response_received"] for a in spend_actions) else {"updated":False,"reason":"no_spend_response"}
            if spend_result["updated"]: spend_model.save(spend_candidate)
            for faction in {a["observation"]["faction"] for a in actions}:
                running_baseline[faction] = .9 * running_baseline[faction] + .1 * reward
            checkpoint = run / ("checkpoint-%03d.npz" % i)
            shutil.copy2(candidate, checkpoint)
            shutil.copy2(spend_candidate,run / ("spend-checkpoint-%03d.npz" % i))
            reward_detail=read_json(run / ("train-%03d" % i) / "experience.json").get("reward_breakdown")
            report["rounds"].append({"reward":reward,"reward_breakdown":reward_detail,"accepted_intents":accepted,"samples":len(actions),"update":result,"checkpoint_sha256":sha(checkpoint),"spend_samples":len(spend_actions),"spend_update":spend_result,"spend_sha256":sha(spend_candidate)})
            report["rounds"][-1]["economy_evaluation"]=read_json(run / ("train-%03d" % i) / "economy-evaluation.json")
            report["rounds"][-1]["feedback_audit"]=read_json(run / ("train-%03d" % i) / "feedback-audit.json")
            # Queue immutable checkpoints for held-out evaluation; never start long
            # benchmark matches inside training, and never use these metrics as reward.
            benchmark_suite=read_json(args.config).get("benchmark_suite")
            if benchmark_suite and not args.no_activate:
                try:
                    from checkpoint_registry import add as register_benchmark
                    report["rounds"][-1]["benchmark_registration"]=register_benchmark(benchmark_suite,args.config,run.name+"/"+str(i),weights=checkpoint,spend=run/("spend-checkpoint-%03d.npz" % i))
                except (OSError,ValueError,KeyError,ImportError) as error:
                    report["rounds"][-1]["benchmark_registration_error"]=str(error)

            write_json(run / "report.json", report)
            print(json.dumps(report["rounds"][-1]), flush=True)
        if args.evaluate:
            evaluate_pair(args,run,report,baseline,candidate,spend_baseline,spend_candidate)
        report.update(status="complete", candidate_sha256=sha(candidate),
                      source_checkpoint_unchanged=sha(initial)==initial_sha, live_model_unchanged=True)
    except (Exception, KeyboardInterrupt) as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        write_json(run / "report.json", report)
        lock.close()
    print("Report: " + str(run / "report.json"), flush=True)
    if not args.no_activate:
        from model_activation import activate
        try:
            report["activation"] = activate(run, args.config)
            report["activated"] = bool(report["activation"].get("changed") or report["activation"].get("source_run") == str(run))
            report["live_model_unchanged"] = not report["activated"]
        except Exception as error:
            report["activation_error"] = str(error)
            raise
        finally:
            write_json(run / "report.json", report)


if __name__ == "__main__": main()
