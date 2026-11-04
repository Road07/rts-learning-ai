"""Package the trained v0 decision network as a separate, LocalModel-free trial."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from make_rescue_scenario import ROOT, HERE, pack, pck_entries

MODEL = "openbfme-decision-net-v0"
SEQUENCE_MODEL = "replay-sequence-v3"
HUMAN_STATE_MODEL = "human-state-v1"


def patch_entries(entries):
    source = entries["scripts/general_strategy.gd"].decode("utf-8")
    prompt_line = '\tvar prompt_candidates: Array = spec.candidates.map(func(c): return {"id": c.id, "description": c.description})'
    if source.count(prompt_line) != 1: raise RuntimeError("Candidate context adapter changed")
    source = source.replace(prompt_line, prompt_line + '\n\tprompt_candidates = preload("res://scripts/team_ai/fandom_context.gd").attach(obs,spec,prompt_candidates)')
    source = source.replace(prompt_line, '\t' + 'spec.summary["human_state_features"]=preload("res://scripts/team_ai/human_state_context.gd").collect(obs)\n' + prompt_line)
    source = source.replace(prompt_line, '\tif OS.get_environment("OPENBFME_AI_TRAINING")=="1" and game.has_method("training_slot"):\n\t\tspec.summary["training_slot"]=game.training_slot(int(bot.index))\n' + prompt_line)
    source = source.replace('"model_decision", {"request":', '"model_decision", {"training_action_id":outer.get("training_action_id",""), "request":')
    entries["data/fandom_knowledge.json"] = (HERE / "knowledge/fandom_v1.json").read_bytes()
    entries["data/replay_sequence.json"] = json.dumps({"schema":1,"model":SEQUENCE_MODEL}).encode()
    source = source.replace('var last_production_log: Dictionary = {}', 'var last_production_log: Dictionary = {}\nvar classic_log_frame: Dictionary = {}')
    source=source.replace('var classic_log_frame: Dictionary = {}','var classic_log_frame: Dictionary = {}\nvar training_pending_purchases: Array = []')
    source = source.replace('\t\tif not obs.get("ok", false): continue', '\t\tif not obs.get("ok", false): continue\n\t\tvar opening: Dictionary = obs.get("classic_opening", {})\n\t\tif not opening.is_empty() and int(opening.get("action_frame", -1)) != int(classic_log_frame.get(bot.index, -1)):\n\t\t\tdiagnostics.write("classic_opening", {"player": bot.index, "frame": frame, "opening": opening})\n\t\t\tclassic_log_frame[bot.index] = int(opening.action_frame)')
    old = 'var purchases: Array = game._world.strategy_production_options(int(bot.index))'
    if source.count(old) != 1: raise RuntimeError("Controller purchase adapter changed")
    source = source.replace(old, 'var purchases: Array = [] # normal trial retains its native production\n\tif obs.get("training_economy_control",false):\n\t\tpurchases=game._world.strategy_production_options(int(bot.index))\n\tspec.summary["production_shadow_options"]=game._world.strategy_production_options(int(bot.index),true)')
    source=source.replace('"production_options": prompt_purchases', '"production_options": purchases')
    purchase_dispatch='\t\t\tapply_model_production(answer, request, frame)'
    if source.count(purchase_dispatch)!=1: raise RuntimeError("Purchase dispatch adapter changed")
    source=source.replace(purchase_dispatch,'')
    source=source.replace('\tif not originally_offered: return', '\tif not originally_offered: return\n\trequest["training_spend_id"]=outer.get("training_spend_id","")\n\tif not str(request.training_spend_id).is_empty():\n\t\tdiagnostics.write("training_spend_response",{"action_id":request.training_spend_id,"player":request.player,"frame":frame,"selected":answer.get("production_id","none")})\n\tapply_model_production(answer,request,frame)')
    if source.count('apply_model_production(answer,')!=1: raise RuntimeError("Purchase must dispatch once per response")
    source=source.replace('"model_production", {"request":', '"model_production", {"action_id":request.get("training_spend_id",""), "request":')
    purchase_call='\t\tvar result: Dictionary = game._world.strategy_produce(int(request.player), operation)'
    if source.count(purchase_call)!=1: raise RuntimeError("Training purchase receipt adapter changed")
    source=source.replace(purchase_call, '\t\tvar before_ids: Array = []\n\t\tif not str(request.get("training_spend_id","")).is_empty():\n\t\t\tbefore_ids=preload("res://scripts/team_ai/contracts.gd").objects(game._world.strategy_observation(int(request.player)),"self").map(func(o): return int(o.id))\n'+purchase_call+'\n\t\tif result.get("ok",false) and not str(request.get("training_spend_id","")).is_empty():\n\t\t\ttraining_pending_purchases.append({"action_id":request.training_spend_id,"player":request.player,"frame":frame,"operation":result.get("operation",operation),"before_ids":before_ids})')
    source = source.replace('"model": "qwen3:4b-instruct"', '"model": "' + MODEL + '"')
    source = source.replace('"model_decision", {"request":', '"model_decision", {"backend": "decision_net_v0", "request":')
    source = source.replace('"model_transport", {"endpoint":', '"model_transport", {"backend": "decision_net_v0", "endpoint":')
    entries["scripts/general_strategy.gd"] = source.encode()
    tuning = json.loads(entries["scripts/team_ai/tuning.json"])
    tuning["decision"]["model"] = MODEL
    entries["scripts/team_ai/tuning.json"] = json.dumps(tuning).encode()
    client = entries["scripts/team_ai/model_client.gd"].decode("utf-8")
    client = client.replace('var chat_url := "http://127.0.0.1:11434/api/chat"', 'var chat_url := "" # trial requires its own launcher; never contact default LocalModel')
    entries["scripts/team_ai/model_client.gd"] = client.encode()
    hud = entries["scripts/team_ai/hud.gd"].decode("utf-8").replace('text("GENERAL AI",', 'text("DECISION NET",').replace('COMPETITIVE  /  v4', 'EXPERIMENTAL  /  v0')
    entries["scripts/team_ai/hud.gd"] = hud.encode()
    # Trial-only dispatch correction. The scorer's learned weights stay unchanged.
    battle = entries["scripts/team_ai/battle_director.gd"].decode("utf-8")
    old_minimum = '\tif plan.get("tactic_tag","") in ["feint_push","bait"]: minimum=1'
    if battle.count(old_minimum) != 1: raise RuntimeError("Battle cohort adapter changed")
    battle = battle.replace(old_minimum, old_minimum + '\n\tif plan.kind=="help": minimum=mini(minimum,army.size())')
    old_enough = '\t\tif enough and not recovering:'
    if battle.count(old_enough) != 1: raise RuntimeError("Battle release adapter changed")
    battle = battle.replace(old_enough, '\t\tif plan.kind=="help":\n\t\t\t# Dispatch to the ally instead of waiting for remote numerical superiority.\n\t\t\t# The unfavorable local fight/retreat guard above still applies.\n\t\t\tenough=at_rally.size()>=minimum or fighting.size()>=minimum\n\t\t\tif int(plan.get("priority",50))>=90: recovering=false\n' + old_enough)
    battle = battle.replace('\t\t\trecord.released=true', '\t\t\trecord.released=true\n\t\t\tif plan.kind=="help": result.reason="support_dispatch"')
    entries["scripts/team_ai/battle_director.gd"] = battle.encode()
    diag = entries["scripts/ai_diagnostics.gd"].decode("utf-8").replace('"general-ai-part2"', '"decision-net-v0-trial"').replace('"general_local_model"', '"local_decision_net_trial"').replace('"model_controls_game": true', '"model_controls_game": false')
    entries["scripts/ai_diagnostics.gd"] = diag.encode()
    entries["scripts/general_strategy_legacy.gd"]=entries["scripts/general_strategy.gd"]
    entries["scripts/general_strategy.gd"]=(HERE / "model_only_controller.gd").read_bytes()


def main():
    dest = ROOT / "AI-Yeni-Model"
    dest.mkdir(exist_ok=True)
    entries = dict(pck_entries((ROOT / "AI-Genel/OpenBFME.pck").read_bytes()))
    for name in ["general_strategy.gd", "human_training_log.gd", "strategic_support.gd", "combat_policy.gd", "rescue_order_policy.gd"]:
        entries["scripts/" + name] = (HERE / name).read_bytes()
    for p in (HERE / "team_ai").rglob("*"):
        if p.suffix in [".gd", ".json"]: entries["scripts/team_ai/" + p.relative_to(HERE / "team_ai").as_posix()] = p.read_bytes()
    patch_entries(entries)
    (dest / "OpenBFME.pck").write_bytes(pack(list(entries.items())))
    (dest / "README.md").write_text((HERE / "MODEL-ONLY.md").read_text(encoding="utf-8").replace("(training/REWARDS.md)","(REWARDS.md)").replace("(training/NORMAL-MATCH-LEARNING.md)","(NORMAL-MATCH-LEARNING.md)").replace("(training/FACTION-LEARNING.md)","(FACTION-LEARNING.md)").replace("(training/DECISION-REWARDS.md)","(DECISION-REWARDS.md)"),encoding="utf-8")
    (dest / "REWARDS.md").write_text((HERE / "training/REWARDS.md").read_text(encoding="utf-8").replace("(../knowledge/reward_v3.json)","(ai-service/reward-tuning.json)"),encoding="utf-8")
    shutil.copy2(HERE / "training/NORMAL-MATCH-LEARNING.md", dest / "NORMAL-MATCH-LEARNING.md")
    shutil.copy2(HERE / "training/FACTION-LEARNING.md", dest / "FACTION-LEARNING.md")
    shutil.copy2(HERE / "training/DECISION-REWARDS.md", dest / "DECISION-REWARDS.md")
    shutil.copy2(HERE / "training/ECONOMY-EVALUATION.md", dest / "ECONOMY-EVALUATION.md")
    shutil.copy2(HERE / "training/GAME-RULES.md", dest / "GAME-RULES.md")
    shutil.copy2(HERE / "training/LEARNING-FEEDBACK-V2.md", dest / "LEARNING-FEEDBACK-V2.md")
    shutil.copy2(HERE / "training/LEARNING-FEEDBACK-V3.md", dest / "LEARNING-FEEDBACK-V3.md")
    for name in ["OpenBFME.exe", "OpenBFME.console.exe"]:
        if not (dest / name).exists(): shutil.copy2(ROOT / name, dest / name)
    shutil.copy2(ROOT / "ai-mod-source/godot/bin/openbfme.windows.template_debug.x86_64.dll", dest / "openbfme.windows.template_debug.x86_64.dll")
    shutil.copytree(ROOT / "AI-Genel/ai-mod", dest / "ai-mod", dirs_exist_ok=True)
    ini = dest / "ai-mod/data/ini/default/skirmishaidata.ini"
    ini.write_bytes(ini.read_bytes().replace(b'EnhancedCounterProduction = Yes', b'EnhancedCounterProduction = Yes\n\tClassicOpening = Yes'))
    service = dest / "ai-service"
    service.mkdir(exist_ok=True)
    shutil.copy2(HERE / "service/decision_host.py", service / "host.py")
    shutil.copy2(HERE / "service/episode_policy.py", service / "episode_policy.py")
    shutil.copy2(HERE / "service/normal_match_capture.py", service / "normal_match_capture.py")
    shutil.copy2(HERE / "service/spend_policy.py", service / "spend_policy.py")
    shutil.copy2(HERE / "service/mechanics_features.py", service / "mechanics_features.py")
    shutil.copy2(HERE / "service/public_game_rules.py", service / "public_game_rules.py")
    game_rules=ROOT / "AI-Egitim/game-rules-v2/game-rules.json"
    rules_hash=hashlib.sha256(game_rules.read_bytes()).hexdigest()
    rules_file=service / "game-rules" / (rules_hash[:20]+".json")
    rules_file.parent.mkdir(exist_ok=True)
    shutil.copy2(game_rules,rules_file)
    shutil.copy2(HERE / "service/economy_evaluation.py", service / "economy_evaluation.py")
    shutil.copy2(HERE / "service/reward_policy.py",service / "reward_policy.py")
    shutil.copy2(HERE / "service/action_credit.py",service / "action_credit.py")
    reward=HERE / "knowledge/reward_action_credit_v3.json"
    reward_hash=hashlib.sha256(reward.read_bytes()).hexdigest()
    reward_file=service / "reward-policies" / (reward_hash[:20]+".json")
    reward_file.parent.mkdir(exist_ok=True)
    shutil.copy2(reward,reward_file)
    shutil.copy2(HERE / "service/fandom_policy.py", service / "fandom_policy.py")
    shutil.copy2(HERE / "service/sequence_policy.py", service / "sequence_policy.py")
    shutil.copy2(HERE / "service/match_feedback.py", service / "match_feedback.py")
    shutil.copy2(HERE / "service/human_state_policy.py", service / "human_state_policy.py")
    shutil.copy2(HERE / "service/mechanics_knowledge.py", service / "mechanics_knowledge.py")
    shutil.copy2(HERE / "service/youtube_knowledge.py",service / "youtube_knowledge.py")
    youtube=ROOT / "AI-Egitim/youtube-lessons-v1/lessons.json"
    shutil.copy2(youtube,service / "youtube-lessons.json")
    shutil.copy2(HERE / "service/production_policy.py", service / "production_policy.py")
    production=ROOT / "AI-Egitim/production-choice-roles-v3/production-network.npz"
    shutil.copy2(production,service / "production-network.npz")
    mechanics=ROOT / "AI-Egitim/rotwk-mechanics-v1/mechanics-runtime.json"
    production_report=json.loads(production.with_name("report.json").read_text(encoding="utf-8"))
    if production_report["mechanics_sha256"]!=hashlib.sha256(mechanics.read_bytes()).hexdigest(): raise ValueError("Production model mechanics features changed; retraining required")
    shutil.copy2(mechanics,service / "mechanics-runtime.json")
    human_weights=ROOT / "AI-Egitim" / HUMAN_STATE_MODEL / "human-state-network.npz"
    shutil.copy2(human_weights,service / "human-state-network.npz")
    feedback=HERE / "knowledge/match_feedback_v1.json"
    shutil.copy2(feedback,service / "match_feedback_v1.json")
    sequence_weights=ROOT / "AI-Egitim" / SEQUENCE_MODEL / "sequence-network.npz"
    shutil.copy2(sequence_weights, service / "sequence-network.npz")
    knowledge = HERE / "knowledge/fandom_v1.json"
    shutil.copy2(knowledge, service / "fandom_v1.json")
    shutil.copy2(HERE / "training/decision_net.py", service / "decision_net.py")
    weights = ROOT / "AI-Egitim/model-v0/network.npz"
    shutil.copy2(weights, service / "network.npz")
    spend=ROOT / "AI-Egitim/otomatik-dongu/20261103-204622-19124/spend-candidate.npz"
    spend_report=json.loads(spend.with_name("report.json").read_text(encoding="utf-8"))
    if spend_report.get("status")!="complete" or spend_report["rounds"][-1]["spend_sha256"]!=hashlib.sha256(spend.read_bytes()).hexdigest():
        raise ValueError("Model-only spending checkpoint is not a completed validated run")
    sys.path.insert(0,str(HERE / "training"))
    sys.path.insert(0,str(HERE / "service"))
    from spend_policy import load_spend_model, ENCODING
    load_spend_model(spend).save(service / "spend-network.npz")
    config = {"model": MODEL, "weights": str(service / "network.npz"), "sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
              "strict_model_only":True,"spend_encoding":ENCODING,"spend_weights":str(service / "spend-network.npz"),"spend_sha256":hashlib.sha256((service / "spend-network.npz").read_bytes()).hexdigest(),
              "reward_config":str(reward_file),"reward_sha256":reward_hash,
              "production_weights":str(service / "production-network.npz"),"production_sha256":hashlib.sha256(production.read_bytes()).hexdigest(),"production_mode":"shadow",
              "youtube_lessons":str(service / "youtube-lessons.json"),"youtube_sha256":hashlib.sha256(youtube.read_bytes()).hexdigest(),
              "mechanics":str(service / "mechanics-runtime.json"),"mechanics_sha256":hashlib.sha256(mechanics.read_bytes()).hexdigest(),
              "game_rules":str(rules_file),"game_rules_sha256":rules_hash,
              "human_state_weights":str(service / "human-state-network.npz"),"human_state_sha256":hashlib.sha256(human_weights.read_bytes()).hexdigest(),"human_state_mode":"shadow",
              "knowledge": str(service / "fandom_v1.json"), "knowledge_sha256": hashlib.sha256(knowledge.read_bytes()).hexdigest(),
              "sequence_weights":str(service / "sequence-network.npz"),"sequence_sha256":hashlib.sha256(sequence_weights.read_bytes()).hexdigest(),
              "sequence_model":SEQUENCE_MODEL,
              "match_feedback":str(service / "match_feedback_v1.json"),"match_feedback_sha256":hashlib.sha256(feedback.read_bytes()).hexdigest(),
              "game_directory": str(dest), "game_executable": str(dest / "OpenBFME.exe"), "mod_directory": str(dest / "ai-mod"),
              "arena_script": str(HERE / "arena/run.py"), "arena_directory": str(ROOT / "AI-Test-Sahasi")}
    from model_activation import publication_lock, read as read_runtime, atomic_json
    with publication_lock(service):
        runtime_path = service / "runtime.json"
        previous = read_runtime(runtime_path) if runtime_path.exists() else {}
        if previous.get("model_activation"):
            for path_key, hash_key in [("weights","sha256"),("spend_weights","spend_sha256")]:
                if hashlib.sha256(Path(previous[path_key]).read_bytes()).hexdigest() != previous[hash_key]:
                    raise ValueError("Active trained model is damaged; package update cannot replace it silently")
                config[path_key], config[hash_key] = previous[path_key], previous[hash_key]
            config["model_activation"] = previous["model_activation"]
        atomic_json(runtime_path, config)
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    launcher = '@echo off\nsetlocal\nset "AI_PYTHONW=' + str(pythonw) + '"\n'
    launcher += 'if not exist "%AI_PYTHONW%" (\n echo Python bulunamadi.\n pause\n exit /b 1\n)\n'
    launcher += 'start "OpenBFME Decision Net" "%AI_PYTHONW%" "%~dp0AI-Yeni-Model\\ai-service\\host.py" --config "%~dp0AI-Yeni-Model\\ai-service\\runtime.json"\n'
    launcher = launcher.replace(str(Path.home()), "%USERPROFILE%")
    (ROOT / "AI-Yeni-Model.cmd").write_bytes(launcher.replace("\n", "\r\n").encode("ascii"))
    print("Independent decision network trial:", dest)


if __name__ == "__main__": main()
