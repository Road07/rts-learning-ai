# PPO, GAE ve critic denetimi

2026-11-06 — `recurrent-ppo-gae-v1`.

## Denetim sonucu ve gerçek çalışma durumu

Çalışan `automatic_training.update` / `EpisodePolicy`, NumPy tabanlı tek adımlı
policy-gradient yoludur. Öğrenilen bir V(s) critic veya GAE yoktur. Hareketli
ödül ortalaması/yerel karar kredisi bir critic değildir. Buradaki clipping,
advantage/gradyan normu sınırıdır; PPO probability-ratio clipping değildir.
KL sonrası geri alma da tek başına PPO anlamına gelmez. Eski kayıt/bankalar
ve etkin oyun modeli bu denetimde değiştirilmedi.

Yeni `SharedEntityPolicy.value` zaten bir Linear(hidden,1) değer başı içeriyordu,
fakat BC loss'u onu eğitmiyordu. `service/recurrent_ppo.py` artık bu başı ve
ortak actor gövdesini PPO+GAE ile günceller. Bu ayrı bir algoritma API'sidir;
canlı recurrent servis, gerçek on-policy arena rollout bağlayıcısı ve güvenli
checkpoint/optimizer yayını henüz bağlı değildir. Mevcut otomatik başlatıcıyı
PPO olmuş gibi tanıtma. BC→değerlendirme→RL sırası değişmedi.

## Hesap

Her bot/maç dizisi GRU sıfırlamasından başlar. Her karar için aynı davranış
checkpointinden gözlem, tam yasal aday kümesi/maskesi, iki başın seçimi, tam
eski dağılımları, ortak seçimin log olasılığı ve eski V(s) saklanır. Fixture
etiketi varsayılan olarak üretim eğitimine kabul edilmez. Eski offline/greedy
loglar PPO deneyimi diye içeri alınmaz; checkpoint hash'i ve eski dağılım/
critic değerleri yeniden oynatılıp karşılaştırılır.

Aynı gözlemde taktik ve üretim için GRU yalnız bir kez güncellenir. Politika
ortak seçim için başların log olasılıklarını toplar. Bir geçiş/ödül ve tek
critic hedefi vardır; aynı takım ödülü iki başa ayrı ayrı eklenmez. Ödülün
oyundan doğru ve bir kez ölçülerek gelmesi collector'ın çağıranına aittir;
mevcut yerel action-credit kayıtlarını iki kez toplayıp GAE ödülü icat etmez.

```
gamma_t = gamma ** (gecen_saniye / discount_seconds)
lambda_t = lambda ** (gecen_saniye / discount_seconds)
delta_t = r_t + gamma_t * (1-terminal_t) * V_old(next_s) - V_old(s_t)
A_t = delta_t + gamma_t * lambda_t * continuation_t * A_next
return_t = A_t + V_old(s_t)
ratio_t = exp(logpi_new_joint - logpi_old_joint)
actor_loss = -mean(min(ratio*A, clip(ratio,1-eps,1+eps)*A))
```

Gerçek terminalde bootstrap sıfırdır. Süre sınırı veya rollout kesilmesinde
resetten önceki son gözlemin critic değeri kullanılır; sonraki maçın başlangıç
state'i kullanılmaz. Bir dizinin ortasında terminal/truncation veya sürekliliği
bozuk next-value reddedilir. GAE botlar/maçlar arasında devam etmez.

Advantage minibatch penceresinde tekrar tekrar değiştirilmez: rollout grubu
üzerinde aktör kararları için normalize edilir. Critic hedefi ham return kalır.
Tek örnekte normalizasyon yapılmaz. Critic loss'u eski değere göre clipping ve
kare hatanın maksimumudur. Joint entropy keşif için ayrı terimdir. Tek seçenekli
baş sıfır actor katkısı yapabilir; bu geçişin critic öğrenmesi dışlanmaz.

Varsayılanlar: gamma .99, lambda .95, referans süre 5 saniye, ratio clipping
.2, value clipping .2, value katsayısı .5 (critic loss'unda ayrıca .5 vardır),
entropy .01, Adam 3e-4, eps 1e-5, gradyan normu .5, hedef joint KL .02,
4 epoch, pencere 16 karar ve minibatch 4 pencere. Bunlar oyun başarısıyla
ayarlanmış hiperparametreler değildir. Parametreler PPOConfig ile değişir.

## Recurrent minibatch ve korumalar

Diziler zaman sırasını korur, pencereler minibatch için karıştırılabilir.
Her pencereden önce tüm geçmiş sıfır GRU'dan GÜNCEL ağırlıklarla no-grad olarak
yeniden hesaplanır. Rastgele pencere başında hafıza sıfırlanmaz; eski davranış
hidden-state'i optimizasyon güncellemelerinden sonra taşınmaz. Pencere içi
BPTT yapılır. Bu doğru fakat uzun dizilerde pahalı bir ilk sürümdür; henüz
büyük rolloutlar için verimli padding/burn-in minibatch motoru değildir.

Yeni adım sonrası tüm rollout üzerindeki tam kategorik old||new joint KL
kontrol edilir (yalnız seçilen eylemden yaklaşık KL değil). Eşik aşılırsa
parametreler VE Adam momentleri geri alınır, kalan epochlar durur. Sayısal hata
veya sonradan fırlayan dağılım hatasında da aynı işlem geri alınır. Daha önce
kabul edilmiş minibatch adımları korunur. Stale checkpoint, maske/eylem/old-logp
uyuşmazlığı ve tekrarlanan bot/maç dizisi reddedilir.

Value_loss, policy_loss, entropy, KL, clip_fraction, ham advantage dağılımı,
clipping öncesi norm, kabul/ret ve proposed explained_variance raporlanır.
Sabit return'de explained variance null olur; reddedilen adımın metriği kabul
edilmiş model iyileşmesi diye sunulmaz. Critic, actor ile aynı fog-filtered
entity/hafıza girişini görür; gizli rakip bilgisi eklenmedi.

## Doğrulama ve sınırlar

`training/test_recurrent_ppo.py`: 9 kısa sayısal kontrol geçti. Elle hesaplanan
GAE/return, terminal/truncation ve değişen süre, iki advantage işaretinde PPO
ratio clipping, ortak kararı tek sayma, actor ve critic ağırlıklarının ikisinin
de değişmesi, eski politika/illegal maske/fixture reddi, GRU prefix eşleşmesi,
KL sonrası model+Adam geri alma, sayısal hata sonrası geri alma ve CUDA adımı.

Kontroller, aynı mimarinin küçük width=32/hidden=32 örneğinde sentetik fixture
geçişleriyle yapılır; hiçbir gerçek eğitim veri setine veya checkpoint dosyasına
yazılmaz. Gerçek ödül sinyalinin varyansının azaldığını, critic'in değerleri
doğru tahmin ettiğini veya oyunun güçlendiğini kanıtlamaz. Oyun/native/GDScript
arayüzü değiştirilmediği için yeni oyun koşusu başlatılmadı; uzun eğitim yok.
Kanıt: `ai-mod-source/ppo-verification.json`.

Sonraki iş: BC başlangıcını doğrulamak, sonra gerçek on-policy collector'ı aynı
entity/hafıza akışıyla oyuna bağlamak; sonuç/ödül geçişlerini ve final bootstrap'ı
native olaylarla doğrulamak. PPO adayını ayrı checkpoint ve optimizer durumuyla
saklayıp sabit native benchmark'ta değerlendirmeden otomatik devreye alma.

Birincil kaynaklar: [PPO](https://arxiv.org/abs/1707.06347),
[GAE](https://arxiv.org/abs/1506.02438).
