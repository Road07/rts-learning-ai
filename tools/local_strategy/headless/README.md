# Unattended OpenBFME matches / Gözetimsiz maçlar

This is a separate opt-in CLI path. With no arguments, `run_match.py` delegates
to the installed engine's unchanged normal game. It does not replace the normal
game launcher, activate checkpoints, train a model, or modify retail assets.

## Requirements / Gerekenler

Python 3.10+ standard library for native-vs-native matches, a locally installed
OpenBFME AI integration package (EXE/PCK/native DLL), BFME2 + RotWK 2.01 retail
installs. None of these binaries/assets/checkpoints belong in git. Optional
NumPy model inference also needs the existing NumPy environment and a valid
runtime.json with matching checkpoints/public catalogue; no weights are invented.
The shared PyTorch/PPO runtime is not connected to this runner yet.

Run from the checkout root (`ai-mod-source` locally):

```powershell
# Headless 180 simulation seconds, target 10x wall-clock pace, 1v1 Brutal.
python tools/local_strategy/run_match.py --headless --time-scale 10 --duration 180 --faction1 FactionDwarves --faction2 FactionWild --seed 42 --map "maps/map wor lostriand/map wor lostriand.map" --out runs/match-001/result.json --engine-package "C:/path/to/integration-package" --bfme2 "D:/Games/BFME2" --rotwk "D:/Games/RotWK"

# Independent workers. --out is a batch directory here; seeds are 42,43,...
python tools/local_strategy/run_matches.py --matches 20 --parallel 2 --headless --time-scale 10 --duration 180 --seed 42 --out runs/batch-001 --engine-package "C:/path/to/integration-package" --bfme2 "D:/Games/BFME2" --rotwk "D:/Games/RotWK"

# Windowed 1x measurement of the same automatic scene (no game HUD/audio/input).
python tools/local_strategy/run_match.py --duration 180 --time-scale 1 --seed 42 --out runs/windowed/result.json

# Original 3v3 roster / contiguous team start slots on Lostriand.
python tools/local_strategy/run_match.py --headless --time-scale 10 --duration 180 --factions FactionDwarves,FactionWild,FactionDwarves,FactionElves,FactionIsengard,FactionMordor --out runs/3v3/result.json

# Existing model (first player), explicit greedy inference; no training update.
python tools/local_strategy/run_match.py --headless --duration 30 --time-scale 10 --controllers model,native --model-config "C:/path/to/runtime.json" --out runs/model/result.json

# Same-seed parallel reproducibility check, not varied-seed strength evaluation.
python tools/local_strategy/run_matches.py --matches 2 --parallel 2 --same-seed --headless --duration 6 --time-scale 10 --seed 42 --out runs/parallel-check
```

Locally the validated package can be discovered from
`AI-Motor-Guncellemeleri/engine-state.json`. Else set `OPENBFME_ENGINE_PACKAGE`
or pass `--engine-package`. Retail roots can be set with `BFME2_INSTALL` and
`ROTWK_INSTALL`; the checked Windows defaults are D:/Games/BFME2 and D:/Games/RotWK.
Missing packages/install paths are errors; a clean source checkout cannot run
without its external dependencies. Only Windows package names are implemented.

## Arguments and outputs / Argümanlar ve çıktılar

`--headless` passes Godot's native `--headless --disable-render-loop`; audio uses
Dummy even for a windowed automated match. Game UI and input are never created
in the automatic scene. `--time-scale` changes ONLY pacing, not native tick size.
`--duration` is simulation time, a positive multiple of 0.2 s. `--faction1` and
`--faction2` configure 1v1; `--factions` accepts six names for 3v3. `--positions`
optionally chooses distinct map start indices. Maps/start slots must exist in
retail; invalid setup fails rather than fabricating a map. `--seed` is explicit.
`--timeout` is an optional real-time process-tree safety timeout.

Canonical faction names: FactionMen, FactionElves, FactionDwarves, FactionWild
(Goblins), FactionMordor, FactionIsengard, FactionAngmar. Default map is Lostriand.
Defaults: 1v1, 1000 starting cash, native Brutal AI, ring/custom hero disabled;
no fixture armies/buildings/cash or compressed AI phase durations. All 3v3 team
members use contiguous start indices. No flags on the original EXE are changed.

Each `--out result.json` owns a unique private `result-runtime-<id>/` containing
its engine copies, private patched PCK, config and optional model logs. There
is no global arena folder, latest-result file, runtime lock or inference port.
A per-output reservation refuses concurrent writes to the same result; existing
results are never overwritten. A batch has its own per-directory reservation.
Release autoload UI/watermark/update/log startup is bypassed only while this
private package has `--simulation-config`; no shared user:// log pruning occurs.

`result.json` contains winner (team number or null), end_reason, simulation
seconds, requested seed, map/factions, native ScoreKeeper kills/losses, current
observed building/unit counts, actual native income payment totals, state hash,
per-frame hash-chain, actual wall times and input/package/checkpoint fingerprints.
Income excludes starting cash, refunds and cash-delta inference. Building counts
are objects the native observer marks STRUCTURE (may include fortress parts);
unit counts are mobile non-structure controller objects, not a sum of individual
soldiers in every horde. Kills/losses follow native ScoreKeeper semantics and
can therefore count differently from the live controller count.

A result ending by duration has winner=null, not a fabricated draw/win. Process
exit code is 0 only for a produced valid result without script/engine errors.
A start/inference/script/time-out failure yields nonzero and an error result/log.
The process and its children are stopped on interruption/timeout. Private files
are intentionally kept for inspection, never published. Deleting them is an
explicit user housekeeping action, not a runner side effect.

`result.json.hashes.jsonl` stores the native state hash at EVERY logic frame.
`summary.json` reports attempts/errors/completed outcomes, win rate only among
completed games, mean simulation duration and mean actual match wall seconds
(including loading/scheduling). `--parallel` results are throughput measurements;
compare speeds sequentially for clean single-match timings.

## Determinism and limits / Determinizm ve sınırlar

Native LiveGame uses 5 logic frames/s, not Godot physics ticks. Both 1x and 10x
execute exactly `GameWorld.advance(0.2)` once per frame, logic worker/auto advance
disabled. Frame skipping or larger dt is not used. Engine.time_scale remains 1;
Godot physics tick settings and `--fixed-fps` are left alone. At different speeds
only the wall deadline differs. If compute is slower than the requested pace,
the match finishes late without dropping simulation steps.

Optional existing-model inference is an instance-local server bound to port 0.
It uses deterministic greedy selection, the same current model_only_controller
observation/options/action mapper, and the pinned public-rule encoders. At fixed
25-frame decision intervals, players are visited in stable slot order and the
simulation WAITS for each response before its next native step. No model HUD,
wall-clock replanning/fallback or normal offline learning ingestion is run.
This deliberately differs from the ordinary asynchronous gameplay controller.
A timeout is an error; the engine does not proceed with a timing-dependent guess.

Render/UI/native logic are only partly separated: Godot headless disables actual
rendering/audio and our scene omits camera/UI/input, but native start/advance
still prepares visual resources and runs view/effect synchronization. This is
not a stripped C++ simulation-only build. Windowed measurements use the same
automatic scene with a camera, not a full interactive HUD session. Cross-platform,
other Godot/compiler builds, all maps/factions and long-run determinism are not
proven by a single matching pair. Use hashes, not only equal scoreboard totals.

Comparison helper (same seed/map/roster/positions/controller/checkpoint inputs):

```python
from run_matches import compare_results
print(compare_results("runs/windowed/result.json", "runs/headless/result.json"))
```

`HEADLESS-ANALYSIS.md` records the inspected entry points and coupling. Measured
validation/timing evidence is recorded separately in local test artifacts; never
replace missing measurements with the theoretical 180/10=18 seconds.

Godot primary docs: [CLI](https://docs.godotengine.org/en/stable/tutorials/editor/command_line_tutorial.html),
[Engine](https://docs.godotengine.org/en/stable/classes/class_engine.html).


## Measured validation / Ölçülmüş doğrulama — 2026-11-06

Same final private package/native DLL, Lostriand 3v3, seed 271026, roster
Dwarves–Goblins–Dwarves vs Elves–Isengard–Mordor, 180 simulation seconds:

| Mode | Simulation execution wall time | Total wall time including preparation/loading |
|---|---:|---:|
| Windowed camera, 1x | 180.05 s | 190.46 s |
| Headless, requested 10x | 24.51 s | 31.78 s |

Measured total speedup: **5.99x**. Requested 10x is a pacing ceiling, not a claim
of a measured tenfold improvement. Native CPU/presentation work and startup
remain. This is one sequential pair on the user's Windows machine (RTX 4070
Laptop GPU, Godot 4.7.2); no average across multiple timing trials is claimed.
The windowed baseline uses the automatic camera scene, not the full interactive
HUD/audio path. Both runs used native AI, not a newly trained PPO model.

- Same final native hash and all **900 per-frame hashes** matched; scoreboard
  fields (income/buildings/units/kills/losses) matched as well. Both ended at the
  duration limit; winner remains null.
- `run_matches --matches 2 --parallel 2 --same-seed` succeeded for two independent
  six-second native matches; all 30 logic hashes matched. They also coexisted
  with two independent model workers without shared-file or port collisions.
- Optional old-model 1x/10x six-second pair: two logged decisions and two accepted
  native production commands per match; all 30 state hashes matched. Instance
  inference ports were different. This is not validation of recurrent PPO or
  stochastic sampling determinism.
- Invalid map produced error JSON and process exit 1. A one-second forced
  process timeout produced error JSON and exit 1; a read-only process inventory
  found no remaining processes under these private runtime directories.
- Five relevant Python checks passed: PCK integrity, CLI validation, no-argument
  delegation, completed-match denominators and first-divergent-frame reporting.
- Actual early victory did not occur in these bounded matches. The branch uses
  native alliance-victory and ScoreKeeper victory queries; a real victory-driven
  shutdown remains unobserved here. Other maps/factions/platforms and long-run
  memory scaling were not exhaustively tested.

Local evidence is under `AI-Test-Sahasi/headless-cli/verification.json`, with
per-run result JSON, hash traces and logs. Those private artifacts/binaries are
not committed. The preliminary windowed run was retained; the table above uses
the final pair after Release `_init` and `_ready` log/UI isolation was fixed.


## Automatic training launcher integration — 2026-11-06

AI-Otomatik-Egitim.exe now starts fixed-step headless training by default at a
10x target pace. The 3/5/15/30-minute selector means SIMULATION minutes, not wall
minutes. The visible training control window remains; game render/UI/audio are
disabled. The existing stage/fixture schedule is preserved in arena.gd, including
its stochastic EpisodePolicy logs, native receipts, final reward samples,
action-credit-v3 and all faction checkpoints. This is not the standalone greedy
run_match.py stream being relabelled into training data and not a PPO rollout.

The trainer forwards --headless-training --time-scale 10. Each rollout/evaluation
owns runtime/, PCK, mods and telemetry beside its episode output. The native
logic runs one 0.2 s step and holds while the current HTTP decision is pending.
Both sample and evaluation use seconds*5 native frames. Old interrupted
evaluations restore their original legacy mode/speed; no mixed-budget pair.
No-activate verification checkpoints are not added to the live benchmark queue.

Validation through the actual rebuilt, same-name EXE: --verify ran exactly one
6-simulation-second/30-frame middle-pressure rollout with separate checkpoints,
3 accepted learner intents and the action-credit-v3 records. Three relevant
configuration checks passed; UI process ownership/kill-on-close check passed;
zero script errors. The short credit window had no mature local reward, so
there was no neural improvement claim. Live weights were not replaced.
Evidence: AI-Test-Sahasi/headless-automatic-training-verification.json.

## Real model-controlled throughput

For external agent control through Gymnasium reset/step/close, see
[GYMNASIUM.md](../GYMNASIUM.md). This is a separate single-agent interface;
the existing automatic training launcher is not switched to Gym/PPO.

Updated [transport/cache and parallel capacity measurements](../training/INFERENCE-TRANSPORT.md):
same-day baseline 32.91 s → 26.36 s for 180 simulation seconds, unchanged 180
decision pairs; deployed package 26.26 s after repackaging. One/four/eight-worker end-to-end capacity extrapolated from
bounded groups: 94.4 / 248.4 / 344.6 duration-limited episodes/hour, not full
victories or an hour-long soak test. Persistent HTTP/compact JSON and request-local
feature reuse preserve the recorded choices; the staggered scheduler supplies
only one bot per same-frame batch. Earlier timings below are historical.

See [model inference measurements](../training/MODEL-INFERENCE-PERFORMANCE.md).
With six current-model bots and the real automatic-training service, a prepared
180-second scenario took 38.64 s of simulation execution / 51.37 s total at a
requested 10x (4.66x effective). Optional half-frequency decisions measured
28.69 / 39.78 s; defaults remain unchanged because reaction quality is untested.
Earlier per-frame-hashed timings include substantial verification overhead;
they are determinism evidence, not raw throughput. No weights were updated.
