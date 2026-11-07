# Local RTS learning AI tools

OpenBFME + RotWK 2.01 is the first integration environment. The shared PyTorch
entity/GRU actor-critic and PPO+GAE are experimental; the live game and existing
automatic trainer still use the preserved NumPy policy. No trained weights or
retail game assets are included here.

## Unattended matches

See [headless/README.md](headless/README.md) for installation paths, isolation,
determinism evidence and the full CLI. From the checkout root:

```powershell
python tools/local_strategy/run_match.py --headless --time-scale 10 --duration 180 --faction1 FactionDwarves --faction2 FactionWild --seed 42 --out runs/one/result.json
python tools/local_strategy/run_matches.py --matches 20 --parallel 2 --headless --time-scale 10 --duration 180 --seed 42 --out runs/batch
```

Supply --engine-package, --bfme2 and --rotwk when local discovery/default paths
are unavailable. No arguments to run_match.py delegate to the unchanged normal
game executable. The optional --controllers model,native --model-config path
uses explicit checkpoint hashes and synchronous fixed-frame greedy decisions.
It is not connected to the new recurrent PPO collector yet.

Measured native 3v3, 180 simulation seconds: windowed 1x **190.46 real seconds**;
headless requested 10x **31.78 real seconds**, including preparation/loading.
All 900 native logic-frame hashes matched. This is one measured pair, not a
universal determinism/performance guarantee or a strength claim.

Further status: [PPO/GAE](training/PPO-GAE.md),
[architecture](training/ENTITY-ARCHITECTURE.md),
[roadmap](training/ROADMAP.md). Existing arena smoke tests remain bounded and
separate from these explicitly requested full-duration CLI measurements.
