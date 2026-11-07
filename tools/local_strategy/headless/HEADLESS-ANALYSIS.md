# Inspection before changes — 2026-11-06

1. **Normal entry:** `godot/project.godot` main_scene is
   `godot/scenes/game.tscn`, running `godot/scripts/game.gd`. The launcher has
   a separate `launcher/project.godot` and `launcher/scripts/core/game_start.gd`.
   Existing AI-Yeni-Model.exe invokes Python `service/decision_host.py`, which
   starts a local model server and an installed exported OpenBFME game. Config
   is external runtime.json; checkpoints/catalogues are pinned by SHA.
2. **Godot confirmed:** project features 4.7, GDExtension GameWorld with C++
   GameClient/LiveGame + GameLogic. The installed binary reports 4.7.2. The native
   engine exports set_auto_advance, set_logic_thread, advance, get_state_hash,
   prepare_new_game/start_new_game and get_victory_report. It runs five native
   logic frames per simulation second. Godot physics FPS is a different clock.
   Existing arena multiplies wall delta and supports a frame budget; larger dt
   can hit LiveGame.maxFramesPerAdvance/drop protection. Engine.time_scale and
   fixed-fps are therefore not used as the authoritative training clock.
3. **Coupling:** normal game _ready calls display setup/AppIcon/Release; _boot
   builds camera/environment, GameAudio and menu/HUD; _process includes input,
   audio listener, viewport/UI and native presentation work. game.gd has some
   headless guards, but these are not a full removal of client code. Screenshot
   capture cannot assume a viewport texture; DisplayServer screen/window calls,
   modal crash dialogs, watermark/Controls, audio-device initialization and
   original input loops are hazards or unnecessary overhead. Native
   GameWorld.advance also performs heldClientWork, refresh_shroud, refresh_views,
   tree and texture animation work after logic. Our new scene bypasses the game
   shell; those native presentation costs remain and are explicitly reported.
4. **Existing match knobs:** arena/scenarios.json selects map, seed, roster,
   stage cash/assets and phase durations. arena/run.py writes a patched PCK and
   mod into shared AI-Test-Sahasi, copies the engine and passes --arena-stage,
   --arena-case, --arena-seconds, --arena-speed, --arena-sim-frames. Stage wall
   timeout and logic-frame budget are distinct. Retail folders were hardcoded
   in arena.gd. New CLI keeps its own config/output/install arguments.
5. **Controller path:** decision_host.py -> arena/run.py -> arena.gd loads
   general_strategy.gd, replaced by decision_trial.patch_entries with
   model_only_controller.gd. It takes fog-filtered native observations, builds
   bounded legal candidates, requests HTTP inference, applies accepted commands.
   Arena and host use shared files/locks, and async response application depends
   on elapsed render/logic frames. Just running them in parallel or multiplying
   delta is not a determinism guarantee. The new runner reuses options/response
   mapping but waits at fixed logic-frame boundaries; it never calls the normal
   tick/setup, which would create the HUD and wall-clock transport lifecycle.

No source changes were made until the above inspection was completed and the
findings shared. Implementation is opt-in new files, no installed asset or
checkpoint edits. Long 180-second comparisons are specifically authorized by
the user's current request; the usual six-second default remains unchanged.
