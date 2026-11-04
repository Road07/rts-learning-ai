# Architecture / Mimari

## English

The current implementation uses two small NumPy scoring networks: one for
tactical candidates and one for production/gameplay commands. Each stores
seven independent faction banks. They share their initial learned weights;
they do not currently train a shared multi-task backbone.

The controller receives fog-filtered game observations, generates bounded
candidate actions, requests a local model choice and submits a validated
engine command. Pathfinding, combat execution, costs and prerequisites remain
engine responsibilities. Candidate generation limits what the AI can learn.

Prepared-scenario training uses policy-gradient updates with probability
checks, clipping and KL guards. Normal-match feedback uses a separate bounded
offline signed-outcome step. Neither establishes strategic competence.
Reward association uses observed actors, targets, asset value and time
windows; it cannot prove exactly which decision prevented hypothetical damage.

### Source layout

- `tools/local_strategy/training/decision_net.py`: model and faction banks.
- `tools/local_strategy/training/automatic_training.py`: prepared rollouts and updates.
- `tools/local_strategy/training/normal_match_training.py`: offline match feedback.
- `tools/local_strategy/training/model_activation.py`: validated pair publication.
- `tools/local_strategy/service/`: inference, features, capture and reward calculations.
- `tools/local_strategy/model_only_controller.gd`: game/controller bridge.
- `tools/local_strategy/team_ai/`: observation/command helpers and legacy modules.
- `tools/local_strategy/arena/`: isolated prepared scenarios and API checks.
- `integration/`: source-only engine changes and upstream reference.

Legacy helper modules are retained for source dependencies and development
history; their presence does not mean every policy is active in model mode.
This snapshot omits local checkpoints, datasets, scraped catalogues, retail
files and packaged builds. Some integration helpers reference these external
inputs and local paths. There is no supported turnkey game setup yet.

Small Windows-side model/reward checks need Python and NumPy. From the
repository root:

```powershell
python -m pip install -r requirements.txt
cd tools/local_strategy/training
python -m unittest test_action_credit test_faction_learning test_model_activation
```

These are software checks, not full-match or portability validation.
The engine patch is supplied against a specific upstream commit; upstream
changes may require manual reconciliation.

## Türkçe

Model iki küçük NumPy puanlama ağından oluşur: taktik ve üretim/komut.
Her birinde yedi bağımsız fraksiyon ağırlık grubu vardır. Başlangıç bilgisi
ortaktır; şu an ortak bir çok görevli gövde birlikte eğitilmez.

Gözlem ve komut seçenekleri sınırlıdır. Motor maliyet, önkoşul, görüş ve
emir geçerliliğini denetler; hareket ve savaş uygulamasını yürütür. Bu sınırlar
modelin öğrenebileceği davranışları da sınırlar. Normal maç öğrenmesi arena
eğitiminden ayrı bir offline adımdır. Kısa kontroller güçlü oyun kanıtı değildir.

Kaynaklar yerel klasörlere ve bu depoya eklenmeyen veri/paket girdilerine
başvurabilir. Bu nedenle kaynak anlık görüntüsü hazır bir oyun paketi değildir.
İlk hedef taşınabilir, ölçülebilir ve güvenilir bir araştırma altyapısı kurmaktır.

## Current interfaces / Güncel arayüzler

The current feature widths are 385 for tactics and 383 for production/commands. Mechanics and public game-rule features are appended with zero-initialized rows when older checkpoints load, preserving all faction banks. Not every catalogue field is an independent neural input. Generated catalogues and learned checkpoints are not distributed.

`action-credit-v3` retains v2's bounded economy/other feedback split and adds verified research cancellation/restart association. Native research order IDs remain zero; a separate observation receipt identity distinguishes instances. Missing history, automatic cancellation and changed observed context do not produce invented labels. This is association, not a counterfactual proof of a strategic mistake. See the [v3 specification](../tools/local_strategy/training/LEARNING-FEEDBACK-V3.md).

Paired evaluations pin factions, opponents and simulation-frame budgets. Interrupted individual games restart; completed evaluation phases can be reused. Automatic activation verifies a completed model pair, not a demonstrated playing-strength improvement. The model continues to select from bounded legal candidates rather than unrestricted actions.

Güncel girdiler taktik için 385, üretim/komut için 383 genişliğindedir. Eski checkpointler sıfır satırlarla genişletilir; fraksiyon bankaları korunur. Katalogdaki her alan ayrı neural girdi değildir. Üretilmiş kataloglar ve ağırlıklar yayımlanmaz.

V3, gerçek araştırma iptal/yeniden başlatma olaylarını ayrı gözlem kimliğiyle eşleştirir. Eksik geçmiş, otomatik iptal veya değişen gözlenen bağlam için etiket uydurmaz. Bu ilişki, kararın kesin stratejik hata olduğu anlamına gelmez. Eş değerlendirme ve kesintiden devam uygulanmıştır; otomatik aktarım güçlü oynanış onayı değildir.
