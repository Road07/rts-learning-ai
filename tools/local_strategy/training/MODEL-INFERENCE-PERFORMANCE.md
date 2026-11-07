# Model-controlled headless timing — 2026-11-06

Follow-up: [2026-11-07 transport/cache and 1/4/8-worker measurements](INFERENCE-TRANSPORT.md).
The historical timings below predate those changes.

The requested 10x pace is a ceiling, not measured throughput. The current model
does not sustain 10x in this prepared 3v3 scenario. Both Python communication and
game-side candidate generation/action application contribute to the limit.

## Conditions

Actual `automatic_training.run_episode`, evaluate mode, six model-controlled
bots, middle/pressure fixture, seed 271026, 180 simulation seconds / 900 native
frames. Current active NumPy faction-bank tactic/spend checkpoints were pinned;
the new shared recurrent PyTorch model and PPO are not live in this measurement.
Reward processing, traces and shadow paths remain enabled. No training, normal
match import or activation occurred. Prepared objects are not human expertise.

## Final low-overhead measurements

| Setting | Decisions | Simulation wall seconds | Total episode wall seconds | Effective pace |
|---|---:|---:|---:|---:|
| Target 10x, default stride 5 | 180 (30/bot) | 38.641632 | 51.367808 | 4.66x |
| Target 10x, optional stride 10 | 90 (15/bot) | 28.689789 | 39.776511 | 6.27x |

The slower decision cadence reduced simulation wall time by 25.8% in this pair.
It also doubles per-bot decision spacing here, approximately 6 to 12 simulation
seconds. The resulting match state changes: playing strength and reaction
quality are unmeasured. **Default stride remains 5.** Total episode wall time
also includes preparation/loading and post-match processing.

One final hash only was collected in each final run, costing 0.023 / 0.030 s.
Final evidence: `AI-Test-Sahasi/model-inference-profile-final-default/summary.json`
and `model-inference-profile-final-slower/summary.json`.

## Default-cadence budget

| Phase | Total seconds | Mean per decision |
|---|---:|---:|
| Game observation/options/serialization | 7.013 | 38.96 ms |
| HTTP request to callback entry | 15.624 | 86.80 ms |
| Callback parsing/revalidation/application | 4.418 | 24.55 ms |
| Native simulation advance | 9.472 | — |
| State hashing | 0.023 | — |

RPC p95 was 105.71 ms. Python server processing through reply was 5.162 s total
(28.68 ms/request), **included in** the RPC wait above, not additional time.
Policy encoding/evaluation/trace writing consumed 4.027 s of that server budget;
this is not an isolated neural matrix-inference measurement. Production option
generation alone consumed 4.253 s. The RPC gap includes transport and engine
callback scheduling; this profile cannot attribute all of it to Python compute.

Separate 36-hash runs measured 30.84 s at the same default cadence, with 42.63 ms
mean RPC wait. Opt-in fast polling measured 30.66 s in the corresponding pair:
this small single-pair difference is not evidence of a useful improvement.
Host/scheduling variability matters; the final 38.64 s is one measurement, not
a stable average. Fast polling remains off. No cross-player inference batching
has been implemented. Prioritize reducing the measured RPC/scheduling overhead
and production candidate/revalidation cost before assuming GPU inference alone
will reach 10x. Batching requires preserving each player's fog-filtered snapshot
and deterministic order. Cadence reduction is available explicitly, with the
reaction-time tradeoff above.

## Determinism and profiling cost

The separate 1x/10x model-controlled verification pair matched all 900 native
frame hashes and final hash `3660350799`. Its wall times were 179.84 / 60.50 s
(total episodes 192.98 / 72.72 s), but it hashed every native frame. That heavy
verification is absent from normal training and must not be presented as raw
production throughput. Subsequent measurements found roughly a second of hash
work for just 36 samples. The final low-overhead default run matched the same
final native hash; it did not collect another 900-frame trace.

Changing decision cadence intentionally changes actions: stride 10 ended at
hash `828348592`, also matching the earlier stride-10 experiment. This is not
a determinism comparison against stride 5. Native hashes do not prove that
every diagnostic field or wall-clock log is identical. Stochastic training,
other maps/seeds, long games and concurrent-worker scaling remain unmeasured.

## Reproduce (explicitly starts bounded matches)

From the workspace root, with the project's NumPy Python environment:

```powershell
python ai-mod-source/tools/local_strategy/training/profile_model_speed.py --output AI-Test-Sahasi/new-model-timing --seconds 180 --speeds 10 --hash-stride 900
```

Add `--decision-stride 10` for the optional lower-frequency comparison. Use
`--speeds 1,10 --hash-stride 1` for expensive full-frame determinism verification.
Always use a new output directory. The script holds the training lock, pins the
engine/checkpoints and evaluates through the real arena service. These private
measurement outputs are not training data, benchmark wins or published assets.
Ordinary development checks retain the six-second limit.
