# Yol haritası / Roadmap

2026-11-08: Gymnasium ve ayrı MaskablePPO ekonomi göreviyle dar öğrenme
deneyinin altyapısı hazırlandı; kısa çalışma/log/eşitlik kontrolleri geçti.
Tam eğitim/değerlendirme ve öğrenme başarısı henüz doğrulanmadı.

Gymnasium and the separate MaskablePPO economy task provide infrastructure
for the narrow learning experiment. Short execution/log/equality checks
passed; full training/evaluation and successful learning remain unverified.

## Türkçe

Amaç, kendi yerel karar modelimizle deneyimlerinden öğrenen ve ileride başka RTS oyunlarına uyarlanabilen bir AI çekirdeği geliştirmek. İlk ortam OpenBFME + RotWK 2.01, öncelik 3v3.

1. **Güvenilir eğitim zinciri:** Karşılaştırma, kesintiden devam ve checkpoint aktarımı için işlem yolu uygulandı; güçlü oynanış anlamına gelmez.
2. **Dar bir problemde öğrenmeyi göster — aktif:** Üretim/araştırma iptallerini gerçek sonuçlarına bağlamak ve eğitim dışı koşullarda tekrarlanabilir davranış değişimi ölçmek.
3. **Ekonomi ve ordu:** Kaynak yerleşimi, yatırım, üretim ve savunmanın birlikte değerlendirilmesi.
4. **Savaş:** Birim karşılaşmaları, hedef/geri çekilme, kahraman, büyü ve özel mekanikler.
5. **Zamansal strateji:** Geçmiş gözlemlerden bilgi biriktirme ve rakibe göre plan değiştirme.
6. **3v3 koordinasyonu:** Yararlı destek, ortak hedefler ve kendi üssünü koruma.
7. **Genelleme:** Eğitimden ayrı haritalar/rakipler, fraksiyon eşleşmeleri ve tam maçlar.
8. **Metaya uyum ve başka RTS ortamları:** Yeni stratejilere uyum, eski yetenekleri koruma ve motor adaptörlerini ayırma; henüz doğrulanmamış hedefler.

Ölçüm: Ağırlık değişimi ve kısa test PASS sonucu güçlenme kanıtı değildir. Birden fazla ayrılmış değerlendirme gerekir. Fixture emirleri uzman etiketi değildir; normal maç offline verisi on-policy arena verisinden ayrılır. Sisle gizli bilgi kullanılmaz. Sabit stratejiyi zorunlu kılarak öğrenme başarısı taklit edilmez.

## English

We are building our own local decision model and an experience-driven RTS learning core. OpenBFME + RotWK 2.01 is the first environment, with 3v3 as the initial focus.

1. **Reliable training pipeline:** Checkpoint comparison, interruption recovery and activation paths are implemented; they do not establish playing strength.
2. **Demonstrate learning on a narrow task — active:** Associate production/research cancellation decisions with observed outcomes, then measure repeatable behavior changes outside training.
3. **Economy and army:** Evaluate placement, investment, production and defense together.
4. **Combat:** Matchups, targeting/retreat, heroes, powers and special mechanics.
5. **Temporal strategy:** Retain observations and change plans in response to opponents.
6. **3v3 coordination:** Useful support, shared targets and preserving the home base.
7. **Generalization:** Held-out maps/opponents, faction matchups and full matches.
8. **Meta adaptation and other RTS environments:** Adapt to new strategies, retain previous abilities and separate engine adapters; these remain unverified goals.

Measurement: Weight updates and short runtime checks do not demonstrate stronger play. Multiple held-out evaluations are necessary. Fixture commands are not expert labels; offline normal-match data remains separate from on-policy rollouts. Hidden enemy information is excluded. Prescribing a fixed strategy is not evidence of learning.
