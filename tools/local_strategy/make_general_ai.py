"""Package the first local model controller separately from the scripted test."""
import json
import os
from pathlib import Path
import re
import shutil
import sys
from make_rescue_scenario import ROOT, HERE, pack, pck_entries, Mount


def main():
    dest = ROOT / "AI-Genel"
    dest.mkdir(exist_ok=True)
    entries = dict(pck_entries((ROOT / "OpenBFME.pck").read_bytes()))
    source = entries["scripts/game.gd"].decode("utf-8")
    marker = "func _process(delta: float) -> void:\n"
    assert source.count(marker) == 1
    source = source.replace(marker, marker +
        '\tif not has_meta("general_ai_driver"):\n'
        '\t\tvar driver_script = load("res://scripts/general_strategy.gd")\n'
        '\t\tif driver_script == null or not driver_script.can_instantiate():\n'
        '\t\t\tpush_error("GENERAL_AI controller failed to compile")\n'
        '\t\t\tget_tree().quit(2)\n\t\t\treturn\n'
        '\t\tvar driver = driver_script.new()\n'
        '\t\tadd_child(driver)\n\t\tdriver.setup(self)\n'
        '\t\tset_meta("general_ai_driver", driver)\n'
        '\tget_meta("general_ai_driver").tick()\n')
    before = '\tvar spec := {\n\t\t"map": _map_key,\n\t\t"slots": slots,\n\t}'
    assert source.count(before) == 1
    source = source.replace(before,
        '\tif OS.get_cmdline_user_args().has("--general-matrix"):\n'
        '\t\tslots = [{"slot": 0, "faction": "FactionMen", "team": 0}]\n'
        '\t\tvar factions := ["FactionDwarves", "FactionWild", "FactionMordor", "FactionElves", "FactionMen", "FactionIsengard", "FactionAngmar"]\n'
        '\t\tfor index in range(factions.size()):\n'
        '\t\t\tslots.append({"slot": index + 1, "state": 4, "faction": factions[index], "team": 0 if index < 3 else 1})\n' + before)
    entries["scripts/game.gd"] = source.encode()
    for name in ("general_strategy.gd", "rescue_order_policy.gd", "ai_diagnostics.gd", "combat_policy.gd", "strategic_support.gd", "human_training_log.gd"):
        entries["scripts/" + name] = (HERE / name).read_bytes()
    for path in sorted((HERE / "team_ai").rglob("*")):
        if path.is_file() and path.suffix in (".gd", ".json"):
            entries["scripts/team_ai/" + path.relative_to(HERE / "team_ai").as_posix()] = path.read_bytes()
    entries["data/faction_profiles.json"] = (HERE / "faction_profiles.json").read_bytes()
    for path in sorted((HERE / "playbooks").glob("Faction*.json")):
        entries["data/playbooks/" + path.name] = path.read_bytes()
    # Identity is explicit in the session header as well as the HUD.
    entries["scripts/ai_diagnostics.gd"] = entries["scripts/ai_diagnostics.gd"].replace(b'"rescue-v4"', b'"general-ai-part2"').replace(b'"scripted_local_test"', b'"general_local_model"').replace(b'"model_controls_game": false', b'"model_controls_game": true')
    package = pack(list(entries.items()))
    assert dict(pck_entries(package)) == entries
    (dest / "OpenBFME.pck").write_bytes(package)
    shutil.copy2(HERE / "HUMAN-LOGGING.md", dest / "INSAN-KAYITLARI.md")
    for name in ("OpenBFME.exe", "OpenBFME.console.exe"):
        if not (dest / name).exists(): shutil.copy2(ROOT / name, dest / name)
    native = ROOT / "ai-mod-source/godot/bin/openbfme.windows.template_debug.x86_64.dll"
    use_native = native.exists() and "--parse-only" not in sys.argv
    shutil.copy2(native if use_native else ROOT / "openbfme.windows.template_debug.x86_64.dll", dest / "openbfme.windows.template_debug.x86_64.dll")
    mount = Mount("D:/Games/RotWK", "D:/Games/BFME2")
    data = mount.get(r"data\ini\default\skirmishaidata.ini").decode("latin1").replace("\r\n", "\n").replace("\r", "")
    for flag in ("DisableTacticalAI", "DisableTeamBuilding"):
        data, count = re.subn(rf"({flag}\s*=\s*)No", r"\g<1>Yes", data, flags=re.I)
        assert count == 1
    data, count = re.subn(r"(?m)^(\s*DisableTacticalAI\s*=\s*Yes[^\n]*\n)", r"\1\tEnhancedCounterProduction = Yes\n", data)
    assert count == 1
    tuning = json.loads((HERE / "team_ai/tuning.json").read_text())
    data = data.replace("EnhancedCounterProduction = Yes", "EnhancedCounterProduction = Yes\n\tEnhancedIncomeMultiplier = " + str(tuning["economy"]["income_multiplier"]) + "\n\tEnhancedProductionMultiplier = " + str(tuning["economy"]["production_multiplier"]))
    # Distinct production priorities, applied to AI ArmyDefinition only. Unit
    # stats, prices and human production remain retail in this first stage.
    profiles = json.loads((HERE / "faction_profiles.json").read_text())
    sides = {"Dwarves": "FactionDwarves", "Wild": "FactionWild", "Mordor": "FactionMordor", "Elves": "FactionElves", "Men": "FactionMen", "Isengard": "FactionIsengard", "Angmar": "FactionAngmar"}
    starts = list(re.finditer(r"(?m)^ArmyDefinition\b", data))
    for i in reversed(range(len(starts))):
        start = starts[i].start()
        end = starts[i + 1].start() if i + 1 < len(starts) else len(data)
        block = data[start:end]
        side = re.search(r"(?m)^\s*Side\s*=\s*(\w+)", block)
        faction = sides.get(side[1]) if side else None
        if not faction: continue
        role = profiles[faction]["production_weight"]
        if role == "swarm":
            block = re.sub(r"(MustUseCommandPointPercentage_Phase[123]\s*=\s*)\d+%", r"\g<1>95%", block)
        def adjust(match):
            member = match[0]
            unit = re.search(r"Unit\s*=\s*(\w+)", member)
            if not unit: return member
            low = unit[1].lower()
            cheap = ("fighterhorde" in low or "warriorhorde" in low) and "black" not in low
            elite = any(word in low for word in ("black", "hilltroll", "darkranger", "marauder", "phalanx", "guardian"))
            factor = 1.6 if role == "swarm" and cheap else 1.4 if role in ("elite", "durable") and elite else 1.0
            return re.sub(r"(PercentageOfArmyPhase[123]\s*=\s*)([0-9.]+)", lambda m: m[1] + f"{float(m[2]) * factor:.3f}", member)
        block = re.sub(r"(?ms)^\s*ArmyMemberDefinition\b[^\n]*\n.*?^\s*End\b[^\n]*", adjust, block)
        data = data[:start] + block + data[end:]
    folder = dest / "ai-mod/data/ini/default"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "skirmishaidata.ini").write_bytes(data.replace("\n", "\r\n").encode("latin1"))
    print("GENERAL_AI package:", dest, "native_observation=", use_native)
    service = dest / "ai-service"
    service.mkdir(exist_ok=True)
    shutil.copy2(HERE / "service/host.py", service / "host.py")
    shutil.copy2(HERE / "service/README.md", service / "README.md")
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    runtime = shutil.which("model")
    if not runtime or not pythonw.is_file():
        raise RuntimeError("Mod AI service requires the installed LocalModel engine and pythonw.exe")
    config = {"model": tuning["decision"]["model"], "num_ctx": tuning["decision"]["num_ctx"],
              "runtime_executable": runtime,
              "model_directory": os.environ.get("LOCAL_MODEL_MODELS", str(Path.home() / ".model/models")),
              "game_directory": str(dest), "game_executable": str(dest / "OpenBFME.exe"),
              "mod_directory": str(dest / "ai-mod"), "arena_script": str(HERE / "arena/run.py")}
    (service / "runtime.json").write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    launcher = ('@echo off\nsetlocal\nset "AI_PYTHONW=' + str(pythonw) + '"\n'
                'if not exist "%AI_PYTHONW%" (\n echo AI runtime bulunamadi.\n pause\n exit /b 1\n)\n'
                'start "OpenBFME AI" "%AI_PYTHONW%" "%~dp0AI-Genel\\ai-service\\host.py" --config "%~dp0AI-Genel\\ai-service\\runtime.json"\n')
    # ASCII command text; resolve the Unicode user path through USERPROFILE at runtime.
    launcher = launcher.replace(str(Path.home()), "%USERPROFILE%")
    (ROOT / "AI-Genel.cmd").write_bytes(launcher.replace("\n", "\r\n").encode("ascii"))
    print("GENERAL_AI managed local runtime:", service)


if __name__ == "__main__":
    main()
