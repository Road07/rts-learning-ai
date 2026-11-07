# RTS Learning AI — English

## Purpose

We are developing our own neural decision model and training infrastructure
to bring learning AI to RTS games. The goal is an agent that makes decisions
from observations and improves through experience, rather than following
one prescribed strategy.

Our first environment is **OpenBFME + Rise of the Witch-king**. Eventually
we want to separate a common RTS decision system from game-specific
observation/action adapters. Transfer to other RTS games is a research goal,
not an implemented or demonstrated capability. It will require new
integration, representations and training.

## Current status: very early prototype

**The project is still far from playable.** It should not be presented as
a reliable BFME player, finished mod or competitive AI release. The model
has not learned important mechanics such as efficient resource-building
placement, connected wall construction and long-term strategy. It may place
farms next to each other, misuse wall hubs and make poor economic or combat
decisions.

Experimental components currently include:

- Small local neural scorers and training code in Python/NumPy.
- Tactical and production/command selection from offered observations/actions.
- Independent weights for seven factions, initialized from existing knowledge.
- Automatic training and checkpoints in prepared 3v3 scenarios.
- Outcome feedback associated with actors, targets and decision time windows.
- Limited offline learning from eligible newly recorded normal matches.
- Publication of validated completed checkpoint pairs for the next game launch.

These components do not establish strong play or consistent improvement.
Code still defines the available actions and candidate locations. Access to
a spell does not mean the model knows how to use it. Outcome association is
not exact causal credit assignment.

## Priorities

1. Represent the game's mechanics through better observations and actions.
2. Measure economy placement, production, combat and team support separately.
3. Establish reproducible comparisons against earlier model versions.
4. Develop full-match strategy and learning from longer-term consequences.
5. Separate reusable RTS learning components from individual game adapters.

## Recent infrastructure updates

- A mechanics observation/action interface and inputs derived from the installed game's public numerical rules.
- Economy/production measurements and checkpoint comparisons with matching factions, opponents and simulation-frame budgets.
- Native unit and research queue start/cancellation receipts; bounded decision feedback for observed discarded production work.
- Versioned `action-credit-v3` rewards, preserving earlier policies and all seven faction banks.
- Interrupted-evaluation recovery, phase reporting and atomic checkpoint activation.

These are tools for measuring learning. Meta adaptation, strong strategy, competitive play and consistent improvement remain unverified. Adding game definitions to inputs does not mean the model has learned them. Short runtime checks are not evidence of full-match playing strength.

[Roadmap / İlerleme planı](docs/ROADMAP.md) · [Current reward scope](tools/local_strategy/training/LEARNING-FEEDBACK-V3.md)

## November 8, 2026: training infrastructure

- The `OpenBFME-v0` Gymnasium adapter controls the real native simulator through legal action masks.
- Potential-based dense rewards retain terminal victory/defeat rewards; privileged opponent statistics stay out of policy observations.
- A separate stock MaskablePPO economy task uses 180-second episodes, held-out evaluation seeds, CSV and TensorBoard. It does not replace the gameplay model.
- Lightweight environment workers, hash-verified package caching, memory guards and episode/reward-component logging support local experiments.
- Persistent native-process resets and the shared attention/GRU architecture remain separate experimental paths, not automatically deployed gameplay features.

Short checks establish execution and bounded regression coverage, not successful full training, stronger play, long-term stability or portable installation.
[Experiment details and measurement limits](docs/EXPERIMENTS.md).

### Installation scope

This is a research source snapshot. Packaging helpers still contain local
directory assumptions and legacy internal dependencies. A portable,
ready-to-run setup for other machines is not available yet. See the
[architecture notes](docs/ARCHITECTURE.md) for scope and limitations.

The game engine belongs to the independent OpenBFME upstream project; this
repository supplies an AI integration patch on top of it. See
[integration notes](integration/README.md). Retail assets, private replays
and logs, game executables and local trained checkpoints are excluded.
Source code is published under GPL-3.0, retaining upstream and third-party
notices.
