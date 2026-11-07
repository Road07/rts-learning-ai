# Training experiments / Eğitim deneyleri

## Türkçe

Bu proje kendi RTS karar modelimizi ve deneyimden öğrenme altyapısını geliştirmeyi
hedefler. İlk ortam OpenBFME + RotWK 2.01'dir. Proje çok erken aşamadadır;
oynanabilir ve rekabetçi bir AI sunduğumuz anlamına gelmez.

### Ayrı yollar

1. **Oyun modeli:** Mevcut NumPy taktik/üretim ağları ve yedi fraksiyon bankası.
   Önceki güncelleme kuralındaki clipping ve KL denetimleri onu PPO yapmaz;
   eski yolda critic/GAE yoktur.
2. **Yeni ortak model:** PyTorch faction embedding, entity attention ve GRU
   kodu/BC eğiticisi ayrı bir yoldur. Canlı oyun ve RL geçişi tamamlanmış değildir.
   Recurrent PPO/GAE API'si de canlı collector/aktivasyonla bütünleşmiş sayılmaz.
3. **Ekonomi deneyi:** Gymnasium üzerinde standart `sb3-contrib MaskablePPO`
   MLP politikası. Taktik/üretim kodlayıcıları 385/383, düz gözlem 49.920 giriş;
   64/65 yasal aday başı kullanılır. Bu deney ZIP checkpointlerini oyuna dağıtmaz.

### Ortam, ölçüm ve güvenlik

Ekonomi görevi Lostriand'da Dwarf vs Easy Men, 180 simülasyon saniyesidir.
Her adım 25 native mantık karesi/5 simülasyon saniyesi ilerler. Tam bölüm
36 adımdır. Her 20.000 geçişten sonra aynı beş ayrılmış seed ile değerlendirme
istenir; bunlar eğitim resetlerine alınmaz. Tam değerlendirme kampanyası
henüz tamamlanmadı. Varsayılan eğitim bütçesi 200.000 geçiştir; burada uzun
eğitimin başarılı olduğu iddia edilmez.

Yoğun ödül `gamma * Phi(new) - Phi(old)` biçimindedir; gelir/bina/ordu
farkları ve terminal ±1 korunur. Gerçek terminalde Phi sıfır, süre kesiminde
gerçek son potansiyel ve kırpılmış sonuç ödülü kullanılır. Gizli rakip
istatistikleri ödül/log içindir; policy gözlemine veya adaylara aktarılmaz.

Konsol/TensorBoard bölüm ödülü ve uzunluğu ile gelir, bina, ordu ve sonuç
ödül bileşenlerini ayrı gösterir. Bunlar ham gelir/ordu skoru değildir.
Yeni loglar ödülü yeniden tanımlamaz.

Yerel Windows ölçümünde beş hafif ortam için gözlenen native tepe private
bellek yaklaşık 1,04 GiB, tüm ortam süreçleri yaklaşık 1,23 GiB idi. Beşli
maç grubu en az 4,86 GiB serbest RAM bıraktı. Bu anlık senaryo ölçümüdür;
her harita/fraksiyon için evrensel bellek gereksinimi değildir. Hafif işçi
bütçesi RAM ve commit'i ayrı sınırlar, ana süreç için pay bırakır ve en fazla
beş ortam seçer. Çalışma sırasında RAM güvenlik sınırı düşerse eğitim durur.

180 saniyelik bölüm + auto-reset döngüsü için kısa yerel tahmin:

| Yol | Paralellik | Grup döngüsü | Tahmini bölüm/saat |
|---|---:|---:|---:|
| Hafif işçi, önbelleksiz | 3 | 37,86 s | 285 |
| Hafif işçi, paket önbelleği | 3 | 39,09 s | 276 |
| Hafif işçi, önbelleksiz | 5 | 41,70 s | 432 |
| Hafif işçi, paket önbelleği | 5 | 39,36 s | 457 |

Profiller rastgele yasal eylemler kullanır; ilk açılış, PPO güncellemesi ve
değerlendirme bu tablodaki döngü tahminine dahil değildir. Gerçek bir saat
veya galibiyet oranı ölçülmedi. Tek/az grup koşusundaki küçük farklar hız
kazancını kanıtlamaz. Asıl ölçülen kapasite artışı daha fazla güvenli ortamdır.

Ayrı 120 s sınırlı PPO duman testi beş ortam/320 geçişle 84,91 s'de bitti;
iç eğitim süresi 79,75 s (~4,01 geçiş/s). Smoke 32 adım/1 epoch kullanır;
normal 100 adım/4 epoch eğitim hızını kanıtlamaz. Uzun eğitim çalıştırılmadı.

Kalıcı süreç reseti her maç için yeni GameWorld/kontrolcü kurarak uygulandı.
Üç ortamda belirgin kazanç vermedi ve daha fazla bellek tuttu; önerilen yol
değildir, varsayılan kapalı ve üç ortamla sınırlıdır. 20x de tutarlı kazanç
vermedi; varsayılan 10x kalır. Üç seed'lik 180 s karşılaştırmalarında bütün
900 native kare hashleri ve 72 emir kaydı eşleşti. Bu sınırlı regresyon
kapsamı bütün oyun durumları için determinism kanıtı değildir.

### Kaynaklar

- [Gymnasium arayüzü](../tools/local_strategy/GYMNASIUM.md)
- [Yoğun ödül](../tools/local_strategy/GYM-DENSE-REWARD.md)
- [Ekonomi deneyi ve yerel komutlar](../tools/local_strategy/training/ECONOMY-TRAINING.md)
- [Ortak entity/GRU mimarisi](../tools/local_strategy/training/ENTITY-ARCHITECTURE.md)
- [PPO/GAE kapsamı](../tools/local_strategy/training/PPO-GAE.md)
- [Sabit rakiple değerlendirme planı](../tools/local_strategy/training/BENCHMARK.md)

Yerel paket, kurulu oyun, public-rules kataloğu ve checkpoint yolları dış
girdilerdir. Kaynaklar henüz temiz clone'dan tek komutla kurulabilir değildir.
Oyun varlıkları, venv, EXE/DLL/PCK, ağırlıklar, özel replay/veri/loglar yayımlanmaz.

## English

We are building our own RTS decision model and learning infrastructure.
OpenBFME + RotWK 2.01 is the first adapter; playable, competitive AI and
successful general strategy learning remain unverified goals.

The gameplay path still uses the NumPy tactical/production faction banks.
Its older clipping/KL update is not PPO: it lacks a critic/GAE. The shared
PyTorch entity-attention/faction-embedding/GRU architecture, BC trainer and
recurrent PPO API are separate work; live collector/RL/activation integration
has not been established. The economy experiment is another separate path:
stock MaskablePPO MLP on the existing 385/383 codecs, flattened to 49,920
inputs with 64/65 legal-candidate heads. It never activates its ZIP in-game.

The economy task is a 180-second Dwarf vs Easy Men match on Lostriand.
Each transition advances 25 native frames/5 simulation seconds: 36 per full
episode. Five held-out evaluation seeds are scheduled every 20,000 training
transitions and excluded from training. The full evaluation campaign and
200,000-transition training run have not been completed.

Potential shaping preserves native terminal ±1 and uses income/building/army
differences. True terminal Phi is zero; truncation keeps final Phi and adds
a clipped outcome score. Privileged opponent statistics are reward-only,
never observation features or candidate inputs. Episode return/length and
four reward-component sums are logged to the console and TensorBoard.

The table above reports local masked-random native probes, including the next
auto-reset but excluding initial startup, PPO updates and evaluation. It is
an extrapolation from short groups, not an hour-long run or win-rate test.
Increasing safe concurrency was the main capacity gain; package caching alone
did not show a consistent gain at three environments. Small differences can
be noise. Five environments retained at least 4.86 GiB free RAM in the probe;
this is not a universal memory requirement for every map or faction.

A separate bounded smoke ran five environments/320 transitions in 84.91 s,
with 79.75 s inside training (~4.01 transitions/s). Smoke uses 32 rollout
steps/one epoch, not the normal 100 steps/four epochs. It does not establish
long-run speed, improved play or convergence. No full training was run.

Persistent native-process resets create a fresh GameWorld/controller each
episode. They passed limited equality checks but retained more memory without
a clear speed benefit, so remain optional, off by default and capped at three.
20x pacing also showed no consistent gain; 10x remains the default. Three
180-second fixed-seed cases matched all 900 native frame hashes and 72 command
records. This is bounded regression coverage, not universal determinism or
identical PPO weights across different environment counts.

Sources still expect external local engine/game/catalogue/checkpoint inputs;
this is not a turnkey installation. Retail assets, environments, executables,
trained weights and private recordings/datasets/logs are excluded. See the
linked interface, reward, architecture and experiment documents above.
