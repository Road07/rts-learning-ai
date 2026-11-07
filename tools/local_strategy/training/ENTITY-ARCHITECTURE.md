# Ortak nesne ve hafıza mimarisi

2026-11-05 — `shared-entity-gru-v1`, gözlem `rts-entities-v1`.

## Durum

Yeni PyTorch mimarisi, veri kaydı ve ayrı BC eğiticisi uygulandı. Henüz gerçek
veriyle eğitilmedi, oyun başlatıcısında veya otomatik RL döngüsünde etkin değil.
Eski 385/383 girişli yedi banka, etkin checkpointler ve başlatıcılar korunuyor.
Yeni kullanıcının ortak ağ tercihi, yeni sürümün yönüdür; eski bankaları silme
veya rastgele yeni ağı etkinleştirme talimatı değildir.

## Ağ

- Tek ortak gövde ve ortak skorlayıcı; yedi ayrı faction ağı yok.
- Gözlemci fraksiyonu ve görülen nesnenin sahibinin fraksiyonu için 16 boyutlu
  embedding. Bilinmeyen sahip fraksiyonu ayrı kategori.
- Görünen her birim/bina için 95 sayısal giriş: konum, sağlık oranı, bayraklar,
  bilinen kuyruk bilgisi ve kamuya açık temel oyun kartı. Eksik bilgi ayrı maskeli.
- Şablon embedding 24; ilişki 4; sınıf 8. Sabit kamu kataloğu sözlüğü: 10.209 ad.
- 96 genişlikte, dört başlı iki attention katmanı. Nesne kimlikleri neural
  sayı değildir; yalnız aktör/hedef bağlantısı için kullanılır. Liste sırası
  ağın anlamını değiştirmez; koordinatlar mekânsal bilgiyi taşır.
- 128 genişlikte GRU. Önce tek gözlemle hafıza güncellenir, sonra hem taktik hem
  harcama adayları aynı hafızayla puanlanır. Önceki görülen bilgi tutulabilir;
  görülmeyen düşman gerçeği kendiliğinden sağlanmaz.
- Yasal aday için 153 giriş, şablon/tür/baş embeddingi ve seçilen aktör/hedef
  nesnelerinin attention çıktısı. Tek ortak skorlayıcı, ayrıca RL için henüz
  eğitilmemiş değer başı. Üretim/nesne kimlikleri öğrenilen sayısal giriş değil.
- Toplam 587.314 parametre. Seçim mevcut yasal adaylardan yapılır; yeni serbest
  koordinat üretici, yol bulma veya sınırsız duvar planlayıcısı eklenmedi.

## Veri ve hafıza sınırı

`mechanics_observation.gd.entity_state` native gözlemde zaten fog/stealth ile
filtrelenmiş nesneleri dar alan listesiyle taşır. World census sorgulamaz.
`model_only_controller.options` aynı kaydı normal maç, arena ve insanın emir
öncesi BC görüntüsüne ekler. Eski NumPy kodlayıcı bu ek alanı kullanmaz.

Codec, kaynak/şema/kare, görünürlük, tekrar eden ID ve geçersiz değerleri
kontrol eder. Bayrağın doğruluğunun kaynağı native gözlemcidir. Kamu kataloğu
canlı gizli nesne oluşturmak için kullanılmaz. Varsayılan üst sınır 256 nesne:
önce adayların aktör/hedefleri, ardından hero/üs/ilişki sırası; kalan sayı
raporlanır. ID yeniden adlandırma invariansı sınırı aşmayan listede testlidir;
üst sınırda seçim sıralamasının ID bağımlılığı vardır. Bu sınırsız dünya temsili
veya bütün birimlerin mutlaka tutulduğu iddiası değildir.

`MemorySession` bir bot/maç içindir; anahtar `(session, match, player)` olmalı.
Yeni maçta veya geri giden karede sıfırlanır, sırası bozulan karar reddedilir.
Aynı karar tekrarında önbellek kullanılır; ikinci baş için GRU tekrar ilerlemez.
Aynı anahtar/adım farklı adaylarla tekrar kullanılmamalıdır. Canlı sunucu
adaptörü henüz bağlı değildir. Herhangi bir log/ödül etiketi hafızaya girmez.

## BC yolu

`training/train_entity_bc.py` açıkça verilen JSONL gösterim setini okur.
Yalnız gerçek insan, fixture olmayan, uygunluk verilmiş ve native kuyruk
sonucuyla doğrulanmış tam aday eşleşmeleri kabul edilir. Şema/katalog ve
seçili indeks doğrulanır. Eski toplulaştırılmış kayıtlardan entity uydurulmaz.
Seçili aktör/hedef gözleme veya üst sınıra takılmışsa örnek reddedilir.

Maç/oturum train-validation-test kesişimi reddedilir. Üç gerçek veri bölümü
yoksa yalnız readiness raporu yazılır, ağırlık üretilmez. Sıralama bot/maç
bazlıdır; 16 olayda kesilen geri yayılım, gradient clipping ve AdamW kullanılır.
30 saniyeyi aşan gözlem boşluğunda hafıza sıfırlanır. Bu, insan emirlerinin
alındığı anlardan oluşan seyrek dizidir; aradaki tüm oyun karelerini içerdiği
iddia edilmez. Yalnız gösterilen başın seçimine loss uygulanır, diğer başa
uydurma 'wait' etiketi verilmez.

En iyi validation kaybı ayrı `candidate.pt` olarak kaydedilir; test yalnız
son seçimde kullanılır. Otomatik etkinleştirme yoktur. Dosyada mimari/gözlem
sürümü, katalog hash'i ve sözlük tutulur. Eski NPZ dosyaları bu farklı ağa
şekil değiştirerek aktarılamaz. Davranış aktarımı ayrıca doğrulanmış taklit
veya ayrı etiketli öğretmen distillation verisi gerektirir. BC doğruluğu
stratejik başarı veya insanın her hamlesinin iyi olduğu anlamına gelmez.

Örnek kullanım (yalnız uygun gerçek veri toplandıktan sonra):

```powershell
.\AI-PyTorch\venv\Scripts\python.exe ai-mod-source/tools/local_strategy/training/train_entity_bc.py --data <gosterimler.jsonl> --rules <sabit-katalog.json> --output <yeni-deney-klasoru> --device cuda --epochs 1
```

## Doğrulama

Ayrı ortam: PyTorch 2.11.0+cu128, NumPy 2.5.4; RTX 4070 Laptop 8 GB.
Kaynak bağımlılık listesi `training/requirements-entity-cuda.txt`.
Sekiz kısa kod kontrolü: ID/liste sırası, görünürlük/kare, boş nesne/aday,
yasal maske, GRU sıfırlama/bot ayrımı, ortak gradientler, checkpoint hash
kontrolü, CUDA ileri/geri ve BC split/fixture engelleri geçti. Sentetik
kontroller eğitim veri setine yazılmaz.

Tek oyun kontrolü: middle/human-log, 6 saniye. Native görünür düşman dahil,
gizli düşman hariç; sıfır script hatası. Üç emir öncesi görüntünün her birinde
62 nesne; yeni kodlayıcıya aktarım ve CUDA skorları sonradan bu fixture
kayıtları üzerinde kontrol edildi. Fixture kaydı yeni ağa oyun kumandası
verildiği veya oyun gücünün doğrulandığı anlamına gelmez.

Kanıt `ai-mod-source/entity-architecture-verification.json` içinde. Tek küçük
görüntüde 20 ısınmış ileri geçiş ortalaması GPU ~4,4 ms, CPU (iki thread)
~2,0 ms. Bu ölçümde GPU çıkarımda daha hızlı değildi; GPU özellikle toplu
eğitim için hazır. JSON/nesne kodlama/IPC dahil değil. Tepe tensor tahsisi
~11,7 MiB; CUDA bağlamı ve gerçek toplam ekran kartı tüketimi bu sayıya dahil
olmadığından toplam VRAM gereksinimi diye sunulmaz.

Mevcut BC veri setinde yeni gözlemle uygun gerçek örnek bulunmadı; readiness
raporu üretildi, eğitim/aktivasyon yapılmadı. Sonraki işler: güncel gerçek
veri kapsaması, BC değerlendirmesi; canlı recurrent sunucu ve arena sequence
rollout/RL-loss/aktivasyon adaptörleri. Mevcut otomatik eğitim henüz eski ağdır.

PyTorch referansları: [attention](https://docs.pytorch.org/docs/stable/generated/torch.nn.MultiheadAttention.html),
[GRU](https://docs.pytorch.org/docs/stable/generated/torch.nn.GRU.html).


## 2026-11-06 — Actor/critic algoritması

`service/recurrent_ppo.py` mevcut value başını kullanarak gerçek PPO clipped
surrogate, GAE, critic loss, joint entropy ve recurrent pencere eğitimi sağlar.
9 kısa CPU/CUDA kontrolü geçti; yalnız sentetik sayısal doğrulama. Detay ve
parametreler [PPO-GAE.md](PPO-GAE.md). Eski otomatik eğitim critic kazandı
anlamına gelmez; gerçek rollout ve aktivasyon bağlantısı hâlâ eksiktir.
