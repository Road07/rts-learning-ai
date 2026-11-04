"""Own CPU inference server + game lifecycle. Does not run/import/contact LocalModel."""
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import msvcrt
from pathlib import Path
import subprocess
import sys
import threading
import time
from decision_net import DecisionNet, load_tactical_model
from fandom_policy import FandomPolicy
from sequence_policy import SequencePolicy
from match_feedback import MatchFeedback
from human_state_policy import HumanStatePolicy
from mechanics_knowledge import MechanicsKnowledge
from production_policy import ProductionPolicy
from youtube_knowledge import YouTubeKnowledge
from episode_policy import EpisodePolicy
from spend_policy import spend_features, legal_spend_options, load_spend_model, ENCODING
from reward_policy import RewardLedger
from normal_match_capture import NormalMatchCapture
from economy_evaluation import EconomyEvaluation
from public_game_rules import PublicGameRules


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--arena", choices=["opening", "middle", "late"])
    parser.add_argument("--seconds", type=int, default=6)
    parser.add_argument("--arena-speed", type=float, default=4)
    parser.add_argument("--arena-case", choices=["baseline", "pressure", "counters", "team", "hero", "sequence", "production","access","mechanics","cp-accounting","learning-feedback"], default="baseline")
    parser.add_argument("--episode-dir", type=Path)
    parser.add_argument("--episode-seed", type=int, default=42)
    parser.add_argument("--episode-mode", choices=["sample", "evaluate"], default="sample")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.episode_dir and not args.arena: parser.error("Training is arena-only")
    if args.episode_dir: args.episode_dir.mkdir(parents=True, exist_ok=False)
    folder = args.config.resolve().parent
    logs = folder / "logs"; logs.mkdir(exist_ok=True)
    lock = (folder / "runtime.lock").open("a+b")
    lock.seek(0)
    if not lock.read(1): lock.write(b"0"); lock.flush()
    lock.seek(0)
    try: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        if not args.arena: ctypes.windll.user32.MessageBoxW(None, "Yeni model denemesi zaten açık.", "OpenBFME", 0x40)
        lock.close(); return 2
    logfile = logs / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + str(os.getpid()) + ".jsonl")
    state = {"backend": "decision_net_v0", "model": config["model"], "host_pid": os.getpid(), "served": 0, "errors": 0, "log": str(logfile)}
    server = None; thread = None; code = 1; failure = None
    normal_capture = NormalMatchCapture()
    normal_match = None
    economy = EconomyEvaluation()
    def status(phase, **fields):
        state.update(phase=phase, updated_utc=datetime.now(timezone.utc).isoformat(), **fields)
        temp = folder / "status.tmp"
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(folder / "status.json")
    with logfile.open("w", encoding="utf-8", buffering=1) as log:
        def record(event, **fields):
            log.write(json.dumps({"event": event, "backend": "decision_net_v0", **fields}, ensure_ascii=False) + "\n")
        def save_economy():
            if not normal_match or args.arena: return
            summary = economy.summary()
            summary.update(match_id=normal_match,tactic_sha256=digest,spend_sha256=config["spend_sha256"],
                           window_ends_at_last_request=True,fixture=False)
            target=logfile.with_name(logfile.stem+"-"+hashlib.sha256(normal_match.encode()).hexdigest()[:12]+".economy.json")
            target.write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
            latest=folder / "latest-economy-evaluation.json"
            temporary=latest.with_suffix(".tmp")
            temporary.write_text(target.read_text(encoding="utf-8"),encoding="utf-8")
            temporary.replace(latest)
            record("economy_evaluation_saved",path=str(target),match_id=normal_match)
        try:
            status("loading")
            weights = Path(config["weights"])
            digest = hashlib.sha256(weights.read_bytes()).hexdigest()
            if digest != config["sha256"]: raise ValueError("Model dosyası beklenen eğitim çıktısıyla eşleşmiyor")
            model = load_tactical_model(weights).ensure_factions()
            reward_path=Path(config["reward_config"])
            if hashlib.sha256(reward_path.read_bytes()).hexdigest()!=config["reward_sha256"]: raise ValueError("Reward configuration hash mismatch")
            rewards=RewardLedger.load(reward_path)
            record("reward_config_loaded",version=rewards.tuning["id"],credit_version=rewards.tuning.get("decision_credit",{}).get("version","action-credit-v1"),sha256=config["reward_sha256"],normal_match_updates_weights=False)
            if args.episode_dir:
                import shutil
                shutil.copy2(reward_path,args.episode_dir / "reward-tuning.json")
            episode = EpisodePolicy(args.episode_seed, args.episode_mode) if args.episode_dir else None
            opponent = load_tactical_model(config.get("opponent_weights", weights)).ensure_factions() if episode else None
            spend_model = None
            if config.get("spend_weights"):
                if config.get("spend_encoding")!=ENCODING or hashlib.sha256(Path(config["spend_weights"]).read_bytes()).hexdigest()!=config["spend_sha256"]:
                    raise ValueError("Spend checkpoint/encoding mismatch")
                spend_model=load_spend_model(config["spend_weights"]).ensure_factions()
            strict=bool(config.get("strict_model_only",False))
            if strict and spend_model is None: raise ValueError("Model-only mode needs a spending checkpoint")
            if strict and args.arena_case=="sequence": raise ValueError("Replay command override fixture is unavailable in model-only mode")
            opponent_spend=load_spend_model(config["opponent_spend_weights"]).ensure_factions() if episode and config.get("opponent_spend_weights") else spend_model
            if strict: record("model_only_loaded",native_brain=False,scripted_advice=False,fallback=False,spend_sha256=config["spend_sha256"],feature_encoding="rts-mechanics-v1+bfme-public-rules-v2+native-queue-v1",tactical_inputs=int(model.weights["w0"].shape[0]),spend_inputs=int(spend_model.weights["w0"].shape[0]))
            if episode:
                record("episode_start", seed=args.episode_seed, mode=args.episode_mode,
                       weights_sha256=digest, opponent_sha256=hashlib.sha256(Path(config.get("opponent_weights", weights)).read_bytes()).hexdigest())
            knowledge_path = Path(config["knowledge"])
            if hashlib.sha256(knowledge_path.read_bytes()).hexdigest() != config["knowledge_sha256"]:
                raise ValueError("Knowledge catalogue hash mismatch")
            knowledge = FandomPolicy(knowledge_path)
            feedback_path=Path(config["match_feedback"])
            if hashlib.sha256(feedback_path.read_bytes()).hexdigest()!=config["match_feedback_sha256"]:
                raise ValueError("Match feedback hash mismatch")
            feedback=MatchFeedback(feedback_path)
            record("match_feedback_loaded",id=feedback.data["id"],neural_weights_changed=False)
            sequence_path=Path(config["sequence_weights"])
            if hashlib.sha256(sequence_path.read_bytes()).hexdigest()!=config["sequence_sha256"]:
                raise ValueError("Replay sequence checkpoint hash mismatch")
            sequence=SequencePolicy(sequence_path,config["sequence_model"])
            human_path=Path(config["human_state_weights"])
            if config["human_state_mode"]!="shadow" or hashlib.sha256(human_path.read_bytes()).hexdigest()!=config["human_state_sha256"]:
                raise ValueError("Human shadow checkpoint/mode mismatch")
            human_state=HumanStatePolicy(human_path)
            record("human_state_loaded",model=human_state.model_name,mode="shadow",controls_game=False,sha256=config["human_state_sha256"])
            mechanics_path=Path(config["mechanics"])
            if hashlib.sha256(mechanics_path.read_bytes()).hexdigest()!=config["mechanics_sha256"]:
                raise ValueError("Mechanics source index hash mismatch")
            mechanics=MechanicsKnowledge(mechanics_path)
            public_rules=None
            if config.get("game_rules"):
                public_rules=PublicGameRules(config["game_rules"])
                if public_rules.sha256!=config["game_rules_sha256"]: raise ValueError("Public game rule hash mismatch")
                record("public_rules_loaded",encoding="bfme-public-rules-v2",sha256=public_rules.sha256,
                       objects=len(public_rules.data["cards"]),tables={k:len(v) for k,v in public_rules.data["tables"].items()},
                       numeric_inputs_enabled=True,base_values_not_live=True)
            youtube_path=Path(config["youtube_lessons"])
            if hashlib.sha256(youtube_path.read_bytes()).hexdigest()!=config["youtube_sha256"]: raise ValueError("YouTube evidence hash mismatch")
            youtube=YouTubeKnowledge(youtube_path)
            record("youtube_knowledge_loaded",catalogue=youtube.data["id"],lessons=len(youtube.data["lessons"]),neural_weights_changed=False)
            production_path=Path(config["production_weights"])
            if config["production_mode"]!="shadow" or hashlib.sha256(production_path.read_bytes()).hexdigest()!=config["production_sha256"]:
                raise ValueError("Production shadow checkpoint/mode mismatch")
            production_policy=ProductionPolicy(production_path,mechanics)
            record("production_loaded",model=production_policy.model_name,mode="shadow",controls_game=False,sha256=config["production_sha256"])
            record("mechanics_loaded",catalogue=mechanics.data["id"],objects=len(mechanics.data["objects"]),neural_weights_changed=False)
            record("sequence_loaded",model=config["sequence_model"],sha256=config["sequence_sha256"],scope="safe scout travel advisory")
            record("knowledge_loaded", catalogue=knowledge.data["id"], neural_weights_changed=False)
            record("model_loaded", sha256=digest, parameters=sum(w.size for w in model.weights.values()), device="CPU", training_run="model-v0", policy_factions=list(model.factions), learning_isolation="independent faction weights")
            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *unused): pass
                def reply(self, code, payload):
                    raw = json.dumps(payload).encode()
                    self.send_response(code); self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
                def do_GET(self):
                    if self.path != "/health": self.reply(404, {"error": "unknown route"}); return
                    self.reply(200, {"backend": "decision_net_v0", "model": config["model"], "sha256": digest})
                def do_POST(self):
                    nonlocal normal_match, rewards
                    if self.path != "/api/chat": self.reply(404, {"error": "unknown route"}); return
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        if not 0 < length <= 1024 * 1024: raise ValueError("Invalid request size")
                        body = json.loads(self.rfile.read(length))
                        if body.get("model") != config["model"]: raise ValueError("Unexpected model")
                        message = next(m for m in reversed(body["messages"]) if m["role"] == "user")
                        request = json.loads(message["content"])
                        observation, candidates = request["observation"], request["candidates"]
                        if not isinstance(observation, dict) or not isinstance(candidates, list) or not 1 <= len(candidates) <= 64: raise ValueError("Invalid state/candidates")
                        if any(not isinstance(c, dict) or not isinstance(c.get("id"), str) or not isinstance(c.get("description", ""), str) for c in candidates): raise ValueError("Invalid candidate")
                        if public_rules:
                            rule_inputs=public_rules.attach(observation,candidates,request.get("production_options",[]))
                            record("public_rule_inputs",player=observation.get("player_index"),**rule_inputs)
                        start = time.perf_counter()
                        match_id = str(observation.get("match_id", ""))
                        if strict and not args.arena and match_id and normal_match != match_id:
                            save_economy()
                            economy.players.clear()
                            rewards = RewardLedger.load(reward_path)
                            normal_match = match_id
                            record("normal_match_start", schema="normal-trajectory-v1", match_id=match_id,
                                   diagnostic_session=observation.get("diagnostic_session"),
                                   tactic_sha256=digest, spend_sha256=config["spend_sha256"],
                                   reward_tuning=rewards.tuning, fixture=False,game_rules_sha256=config.get("game_rules_sha256"))
                        for sample in observation.get("reward_observations",[]):
                            record("reward_observation",sample=sample,match_id=match_id)
                            if strict and not args.arena:
                                try: economy.observe(sample)
                                except (ValueError,KeyError,TypeError) as error: record("economy_evaluation_error",error=str(error))
                            try:
                                reward_update=rewards.observe(sample)
                                record("reward_update",player=sample["player"],frame=sample["frame"],**reward_update)
                            except (ValueError,KeyError,TypeError) as error:
                                record("reward_error",error=str(error))
                                state["reward_errors"]=int(state.get("reward_errors",0))+1
                        training_token = ""
                        spend_token = ""
                        spend_id = "none"
                        if episode and int(observation.get("training_slot", -1)) in (0, 1, 2):
                            selected, training_token, trajectory = episode.choose(model, observation, candidates)
                            record("episode_action", **trajectory)
                            if spend_model:
                                spend_options=legal_spend_options(request.get("production_options",[]),float(observation.get("money",0)))
                                spend_id,spend_token,spend_trace=episode.choose(spend_model,observation,spend_options,spend_features,"spend")
                                record("episode_spend_action",encoding=ENCODING,**spend_trace)
                            advice = {"selected": selected, "scope": "arena neural policy without advice offsets"}
                        elif strict:
                            if not observation.get("model_only"): raise ValueError("Expected model-only controller")
                            selected=(opponent if episode else model).predict(observation,candidates)
                            choices=legal_spend_options(request.get("production_options",[]),float(observation.get("money",0)))
                            encoder=spend_features
                            import numpy as np
                            scores,_=(opponent_spend if episode else spend_model).for_faction(observation.get("faction")).forward(np.stack([encoder(observation,c) for c in choices]))
                            spend_id=choices[int(np.argmax(scores))]["id"]
                            if not args.arena and match_id:
                                captured=normal_capture.action(observation,candidates,selected,choices,spend_id)
                                if captured: record("normal_match_action", **captured)
                            advice={"selected":selected,"scope":"model_only_no_scripted_advice"}
                        else:
                            selected, advice = knowledge.choose(opponent if episode else model, observation, candidates,feedback)
                        sequence_hint=sequence.hint(observation.get("command_history",{}))
                        mechanics_context=mechanics.context(observation.get("human_state_features"))
                        # Deliberately no path from this prediction to selected, answer,
                        # production_id or the game response. Diagnostics only.
                        try: human_shadow=human_state.shadow(observation.get("human_state_features"))
                        except (ValueError,KeyError,TypeError) as error:
                            human_shadow={"ready":False,"mode":"shadow","reason":"invalid_features","error":str(error),"controls_game":False}
                        try: production_shadow=production_policy.shadow(observation.get("human_state_features"),observation.get("production_shadow_options",[]))
                        except (ValueError,KeyError,TypeError) as error:
                            production_shadow={"ready":False,"mode":"shadow","reason":"invalid_features","error":str(error),"controls_game":False}
                        elapsed = (time.perf_counter() - start) * 1000
                        answer = {"candidate_id": selected, "production_id": spend_id, "messages": [], "reason": "model_only" if strict else "arena neural policy " + args.episode_mode if training_token else "local decision network v0 + fandom-v1 soft advice"}
                        self.reply(200, {"model": config["model"], "backend": "decision_net_v0", "done": True,
                                         "training_action_id": training_token,
                                         "training_spend_id": spend_token,
                                         "sequence_hint":sequence_hint,
                                         "message": {"role": "assistant", "content": json.dumps(answer)}})
                        state["served"] += 1
                        record("knowledge_advice", **advice)
                        record("sequence_inference",player=observation.get("player_index"),**sequence_hint)
                        record("human_state_shadow",player=observation.get("player_index"),current_candidate=selected,**human_shadow)
                        record("mechanics_context",player=observation.get("player_index"),**mechanics_context)
                        record("youtube_learning_notes",player=observation.get("player_index"),**youtube.context(observation.get("human_state_features")))
                        record("production_shadow",player=observation.get("player_index"),**production_shadow)
                        if production_shadow.get("ready"): state["production_predictions"]=int(state.get("production_predictions",0))+1
                        record("network_choice", candidate_id=selected, candidates=len(candidates), inference_ms=round(elapsed, 4), faction=observation.get("faction"), policy_faction=observation.get("faction"), separate_faction_policy=True, production_id=spend_id)
                    except (ValueError, KeyError, TypeError, StopIteration) as error:
                        state["errors"] += 1; record("request_error", error=str(error))
                        self.reply(400, {"error": str(error)})
            server = HTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
            thread.start()
            base = "http://127.0.0.1:" + str(server.server_port)
            status("ready", endpoint=base, sha256=digest)
            env = os.environ.copy()
            env.update(OPENBFME_AI_URL=base, OPENBFME_AI_MANAGED="1", OPENBFME_AI_BACKEND="decision_net_v0")
            if strict: env["OPENBFME_MODEL_ONLY"]="1"
            if episode: env["OPENBFME_AI_TRAINING"] = "1"
            if args.arena:
                command = [sys.executable, config["arena_script"], args.arena, "--seconds", str(args.seconds), "--model", "on"]
                command += ["--case", args.arena_case]
                command += ["--speed", str(args.arena_speed)]
                if config.get("arena_sim_frames"): command += ["--sim-frames",str(config["arena_sim_frames"])]
                if config.get("arena_factions"): command += ["--factions", ",".join(config["arena_factions"])]
                if episode:
                    command += ["--seed", str(args.episode_seed), "--output-dir", str(args.episode_dir / "arena")]
            else:
                command = [config["game_executable"], "--", "--no-update-check", "-mod", config["mod_directory"]]
            with (logs / (logfile.stem + "-game.log")).open("w", encoding="utf-8") as game_log:
                game = subprocess.Popen(command, cwd=config["game_directory"], env=env, stdout=game_log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
                status("running", game_pid=game.pid)
                code = game.wait()
            if args.arena and code and args.episode_dir:
                report_path = args.episode_dir / "arena" / (args.arena + ".json")
                if report_path.is_file():
                    arena_report = json.loads(report_path.read_text(encoding="utf-8"))
                    if arena_report.get("errors"):
                        raise RuntimeError("Saha kurulumu başarısız: " + "; ".join(map(str, arena_report["errors"][:3])))
            if args.arena and (not state["served"] or state["errors"] or state.get("reward_errors",0)): raise RuntimeError("Sahada gerçek ağ kararı/ödül kaydı doğrulanamadı")
            if args.arena_case=="production" and not strict and not state.get("production_predictions",0): raise RuntimeError("No genuine production shadow prediction observed")
            record("game_exit", exit_code=code, served=state["served"], errors=state["errors"])
        except Exception as error:
            failure = str(error); record("host_error", error=failure); code = 1
        finally:
            if server: server.shutdown(); server.server_close()
            if thread: thread.join(timeout=2)
            try: save_economy()
            except (OSError,ValueError,KeyError,TypeError) as error: record("economy_evaluation_error",error=str(error))
            status("stopped", game_pid=None, exit_code=code, error=failure)
            lock.close()
            if args.episode_dir:
                import shutil
                shutil.copy2(logfile, args.episode_dir / "service.jsonl")
    if failure and not args.arena: ctypes.windll.user32.MessageBoxW(None, failure + "\n\n" + str(logfile), "OpenBFME Decision Net", 0x10)
    return code


if __name__ == "__main__": sys.exit(main())
