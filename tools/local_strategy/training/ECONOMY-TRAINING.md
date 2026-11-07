# Ayrı MaskablePPO ekonomi deneyi

Bu betikler mevcut oyun modelini, entity/attention/GRU mimarisini veya eski
otomatik eğitim EXE'sini değiştirmez. Kullanıcı ayrı standart MaskablePPO
deneyini seçti: stock `MlpPolicy`, mevcut385/383 sayısal kodlayıcıların
flatten/padding sargısı. Çıktı SB3 ZIP'tir; GRU/NPZ checkpoint değildir,
otomatik oyun aktivasyonu yapılmaz. MaskablePPO'nun recurrent politika desteği
yoktur; mevcut GRU'nun bu betikle eğitildiği iddia edilmez.

## Görev ve arayüz

Sabit `economy_task.json`:180 simülasyon saniyesi, Lostriand, Cüce ajan,
en kolay yerleşik Men AI, konumlar0/5. Difficulty native SLOT_EASY_AI=2'dir;
önceki genel Gym/runner varsayılanı Brutal=5 korunur. Rakip tamamen pasif
değildir; 180 saniye sonunda veya gerçek yenilgide bölüm biter.
Gym yoğun ödülü/±1 terminal ve maskeler korunur; ek build order veya
zorunlu üretim kuralı yoktur. Wrapper yalnız mevcut fog-filtered politika
gözlemi ve adayları49920 float32 sayıya çevirir. Özel reward_state/ödül
bileşenleri gözleme girmez. Meta verilerindeki kale parçaları dahil
STRUCTURE sayımı ve gelir tanımı önceki Gym ile aynıdır.

`action_masks()` doğrudan ortamda bulunur,129 bayrakla64/65 başı maskeler.
SB3'ün nested-Dict/şablon one-hot kısıtları bu codec sargısıyla aşılır;
oyundaki mimari veya adayların sırası değiştirilmez. SubprocVecEnv Windows
spawn kullanır; her örnek ayrı localhost portu/runtime/PCK/süreç ağacı açar.

## Komutlar — çalışma klasörünün kökünden

Bağımlılıklar AI-PyTorch/venv içine kuruldu; yeniden kurulum:

```powershell
& .\AI-PyTorch\venv\Scripts\python.exe -m pip install -r .\ai-mod-source\tools\local_strategy\training\requirements-economy.txt
```

Tam eğitim (kullanıcı başlatır):

```powershell
& .\AI-PyTorch\venv\Scripts\python.exe .\ai-mod-source\tools\local_strategy\training\train_economy.py --timesteps 200000 --parallel 8 --output .\AI-Egitim\economy-maskable-ppo
```

Aynı değerlendirmeyle rastgele maskeli ajan:

```powershell
& .\AI-PyTorch\venv\Scripts\python.exe .\ai-mod-source\tools\local_strategy\training\random_economy.py --output .\AI-Egitim\economy-random
```

Varsayılanlar:200000 toplam ortam geçişi (her örnek başına değil),8 örnek,
rollout100/örnek, minibatch200 (gerekirse ortak bölene düşer),4 PPO epoch,
gamma.99, lr3e-4, CPU. `--parallel`, `--device`, `--timesteps`, `--eval-every`
parametredir.8 örnekte800'lük rollout200000'i tam böler; farklı örnek
sayısında SB3 tamamlanan rollout boyutuna yukarı yuvarlayabilir.

Her20000 adımda, PPO güncellemesi sonrasında deterministic ve maskeli
tahminle aynı5 tohum değerlendirilir:831001..831005. Bu tohumlar ve mevcut
native benchmark tohumları eğitim resetlerinden dışlanır. Başka bir
değerlendirme kümesi uydurulmaz; rastgele ajan aynı görev ve tohumları kullanır.
Eğitim ortamlarının karar bekleme bütçesi değerlendirme arası duraklamaya
izin verir; simülasyon bu sırada ilerlemez.

CSV: `AI-Egitim/economy-maskable-ppo/evaluation.csv` ve
`AI-Egitim/economy-random/evaluation.csv`. Her değerlendirmede5 bölüm satırı
ve `kind=mean` satırı: toplam ödül/standart sapma, gelir, bina, ordu değeri,
terminal/truncated sayıları, simülasyon ve duvar saati süreleri. Eğitimde
`train_steps` gerçek geçiş sayısıdır. CSV başlığı başta yazılır; ilk sonuç
20000 geçişte gelir. Klasör mevcutsa üstüne yazılmaz, yeni --output gerekir.

TensorBoard `AI-Egitim/economy-maskable-ppo/tensorboard` altında PPO/rollout
ve eval/mean_reward, mean_income, mean_buildings, mean_army_value kaydeder.
Checkpointler her değerlendirmede, final_model.zip eğitim sonunda kaydedilir.

## EXE ile kullanım

### Güncel: 2026-11-08 ölçülen hız ve bölüm logları

Kaynak mimari, ödül hesabı ve 25 kare/5 s karar aralığı değişmedi. EXE'nin
eğitim işçisi artık `--light-workers --reuse-package` ile başlatır; normal
oyun ve eski otomatik eğitim başlatıcıları değişmez. CLI'da bu bayraklar açık
yazılır. Native paket aynı, model etkinleştirmesi yok.

Eski bütçe: `min(istenen, floor((free_commit-4 GiB)/3 GiB))`, bu makinede 3.
Yeni bütçe yalnız hafif işçi için 5 ile sınırlı:
`min(istenen,5,floor((free_RAM-3.75 GiB)/1.25 GiB),floor((free_commit-2.5 GiB)/1.5 GiB))`.
3 GiB fiziksel rezerv + .75 GiB parent/model RAM payı; commit için 1 GiB
rezerv + 1.5 GiB parent/model payı. Beş ortam native tepe private1.04 GiB,
tüm ortam süreçleri1.23 GiB; 1.5 GiB commit bütçesi bunun üstündedir. RSS
toplamları ortak image sayfalarını tekrar sayar; fiziksel bütçe gerçek 5-env
ölçümüne dayanır. Ek güvenlik: callback serbest RAM3.25 GiB altına düşerse
eğitimi açık hata ile sonlandırıp kendi süreçlerini temizler. Değişen sistem
yükünde 5 garanti edilmez; otomatik daha az ortam seçilebilir.

Beş native ortam ölçümü en az4.86 GiB boş RAM bıraktı. Gerçek 5-env PPO smoke
son bölümünde46.2 s boyunca451 örnekte en az4.54 GiB boş RAM görüldü. Smoke
256 hedef, rollout yuvarlamasıyla320 geçiş/2 smoke epoch, toplam84.906 s,
eğitim içi79.75 s (~4.01 geçiş/s); tam eğitim/20k eval yapılmadı. Smoke32
adım/1 epoch kullanır; normal100 adım/4 epoch hızını kanıtlamaz.

Kalıcı süreç `--persistent-games` ile uygulandı ve sınandı: aynı Godot
process/extension açık, her maçta temiz GameWorld/RetailFileSystem/controller
yaratılıyor. Native terminal sonuç süreç çıkışından ayrı teslim edilir;
`persistent_session=true`, `process_exit_code=null`, en son oturum çıkışı
ayrı `s-*/exit.json` içindedir. Sonuç dosyası cleanup sonrası yayımlanır;
bozuk oturum/timeout terminal ödülüne çevrilmez. Explicit reset yarım bölümü
bırakırsa güvenli soğuk başlatma yapılır. Eğitim auto-reset'i bitmiş bölümde
aynı process'i kullanır. Episode timeout ve kontrol yanıtı deadline'ları var.
Kalıcı süreç3 ortamda Native tepe1.31 GiB/tüm ortam1.49 GiB private tuttu;
bölüm döngüsü36.96 s ile cache yoluna göre belirgin hız kazanımı yoktu.
Bu yüzden önerilen/default yol değildir ve 3 ortamla sınırlıdır; 5-env
kalıcı süreç deneyi güvenlik hesabı nedeniyle çalıştırılmadı. Önerilen komut
kalıcı süreç bayrağı içermez.

20x3 ortam ölçümü aynı900-kare hash/72 emir kaydını verdi, fakat bölüm döngüsü
37.55 s ile10x'ten hızlı değildi. 20x uygulanmadı; varsayılan10x korunur,
5 ortam20x ek ölçümü kazanç görülmediği için yapılmadı.

Ölçümler `AI-Test-Sahasi/ef-thread3`, `ef-light5`, `ef-cache3-final`,
`ef-cache5`, `ef-session3`, `ef-20x3` altındadır. Bütün profiller masked-random
yasal eylem kontrolü, PPO/eval içermez. `rounds[].wall_seconds` bir tamamlanmış
bölüm grubu + sonraki auto-reset'i içerir; `wall_seconds` ayrıca ilk
process/factory/reset kurulumunu içerir. İlk açılışı hariç tutan saatlik
tahmin `parallel*3600/mean(rounds.wall_seconds)`; bunlar gerçek bir saatlik
dayanıklılık veya galibiyet maçları değildir.

Monitor eşdeğeri `info.episode`: r/l/t ve dört ayrı ödül toplamı üretir.
SB3 konsol/TensorBoard'da `rollout/ep_rew_mean`, `rollout/ep_len_mean` görünür;
callback `reward/ep_income`, `ep_buildings`, `ep_army`, `ep_result` yazar.
Sonuç bileşeni gerçek terminal + truncation sonucudur. Ekonomi/ordu/bina
potansiyel ödülleri loglanır; bunlar ham gelir veya ham ordu değeri değildir.
Ödül tekrar hesaplanmaz veya policy gözlemine eklenmez. Smoke event dosyasında
altı scalar step320'de doğrulandı, ep_len_mean36. Uzman veri/güçlenme kanıtı yok.

Determinizm: legacy/fast üç kısa seed615000,1320713198,615000 için gözlem,
maske, eylem, ödül, terminal ve her kare hash'i aynı (`ef-eq1`,
`ef-session-eq2`). Ayrıca615000..615002 üç TAM180 s bölümünde hafif/cached5,
kalıcı3 ve20x3 karşılaştırmalarının her birinde900 native hash zinciri ve72
emir kaydı eşit. Bu9 çift, öğrenilmiş PPO politikasının farklı paralellikler
ile aynı ağırlıklara eğitileceği iddiası değildir. 18 ilgili kod kontrolü geçti.
Özel birleşik kanıt: `AI-Test-Sahasi/economy-speed-logging-verification.json`.

20k eğitimi kullanıcı başlatır (tam eğitim burada başlatılmadı):
```powershell
.\AI-PyTorch\venv\Scripts\python.exe .\ai-mod-source\tools\local_strategy\training\train_economy.py --timesteps 20000 --parallel 8 --light-workers --reuse-package --output ".\AI-Egitim\economy-20k-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

Alttaki "henüz çalıştırılmamış" bölüm önceki yazım anının tarihsel kaydıdır;
güncel doğrulama ve varsayılanlar bu bölümde açıklanmıştır.

### 2026-11-08: henüz çalıştırılmamış hız seçenekleri

Kullanıcı bellek sınırındaki aktif eğitime dokunulmamasını ve oyun testi
yapılmamasını istedi. Aşağıdaki değişiklikler yalnız yazıldı; kod kontrolü,
oyun doğrulaması ve hız/RAM ölçümü ÇALIŞTIRILMADI. Varsayılanlar korunur;
aktif eğitim bu seçenekleri kullanmaz, EXE de kendiliğinden etkinleştirmez.

`--light-workers`: standart SB3'nin env işçisi, multiprocessing spawn ve
SB3 importları nedeniyle PyTorch'u her işçiye getiriyordu. Önceki canlı
görüntüde Python işçileri yaklaşık 660 MB, native oyunlar 897–914 MB working
set gösteriyordu. Bunlar anlık resident bellek; peak/private commit değildir.
Yeni işçi yalnız Gym/NumPy kodunu ayrı Python girişinden yükler; PyTorch
yüklenirse açık hata verir. SB3 vektör adaptörünün mevcut step/reset/mask
mesajları, terminal_observation, reset_info, seed sırası ve auto-reset korunur.
Policy/critic/PPO ve minibatchler aynı ana süreçte kalır. Gerçek RAM tasarrufu
henüz ölçülmedi; çalışma modelinin mimarisi değişmez.

Bellek koruması DEĞİŞMEDİ: Windows free_commit üzerinden
`min(requested, floor((free_commit - 4 GiB) / 3 GiB))`. 14,492,782,592 bayt
boş commit 3 ortam verir. 3 GiB native+Python ortamı için ihtiyatlı bütçedir,
oyunun ölçülmüş sabit/peak tüketimi değildir. Hafif işçi seçeneği bu eşiği
otomatik gevşetmez; yine 3 ortam seçilebilir.

`--reuse-package`: motor/controller/harness kaynak hashleriyle anahtarlanmış
özel worker önbelleği PCK'yi bir kez hazırlar; manifest ve dosya hashlerini
sonraki resetlerde doğrular. Değişmez EXE/DLL'ler ve PCK, bölümün özel runtime
klasörüne hard-link edilir; desteklenmezse aynı baytlar kopyalanır. Her maçın
portu, config, sonuç ve günlükleri ayrı kalır; native süreç taze açılır.
Bu paketleme/kopyalama maliyetini hedefler, map/asset yükleme süresini kaldırmaz.
Cache dizini private deney çıktısıdır; oyun paketi/checkpoint değildir.

Aynı GameWorld'de yeniden başlatma API olarak mümkün: `clear_game_data(false)`,
`prepare_new_game`, `start_new_game`. Ancak açık native GameWorld/RetailFileSystem
ve uzun ömürlü anahtar/template/FX depolarının taze süreçle aynı başlangıç
kimlikleri ve RNG/state hashlerini ürettiğine ilişkin sözleşme/kanıt yok.
Mevcut kapanış hatası da bu ömür ilişkilerini gösterdi. Dolayısıyla tam sıcak
süreç reseti bu değişiklikte uygulanmadı: doğrulanmamış state reuse ile
determinizm garantisi verilmez. Paket önbelleği bu API değişimini gerektirmez.

EĞİTİM DURDUKTAN SONRA PowerShell/proje kökü:
```powershell
$py = '.\AI-PyTorch\venv\Scripts\python.exe'
$tr = '.\ai-mod-source\tools\local_strategy\training'
& $py -m unittest discover -s $tr -p test_economy_fast.py
& $py "$tr\verify_economy_fast.py" --seconds 6 --seeds 615000,1320713198,615000 --output ".\AI-Test-Sahasi\fast-check-$(Get-Date -Format yyyyMMdd-HHmmss)"
& $py "$tr\train_economy.py" --timesteps 200 --parallel 2 --light-workers --reuse-package --output ".\AI-Egitim\fast-smoke-$(Get-Date -Format yyyyMMdd-HHmmss)"
```
İlk komut yalnız sentetik cache bütünlüğü; motor/PPO başlatmaz. İkinci komut
GERÇEK OYUN AÇAR: legacy ile hafif+cache yolunda aynı üç seed'i, aynı yerel
rastgele yasal eylemleri, gözlem/maskeleri/ödülleri ve her native kare hashini
karşılaştırır. Aynı seed'in araya başka seed girdikten sonra tekrar edilmesi
warm cache denetimidir. SB3 auto-reset nedeniyle kapanacak ek yarım maçlar
açılır; çalışma tek ortam/sıralı yürür. Bu denetim yeni politika eğitmez.
Başarı raporu `verification.json/passed=true`; farklılıkta legacy.json ve
fast.json karşılaştırılır. Doğrulama başarılı olmadan seçeneklerle uzun eğitim
başlatma. Üçüncü komut GERÇEK kısa PPO eğitimi: 200 geçiş hedefi/2 ortam,
rollout yuvarlaması olabilir. Uzun eğitim veya oyuna aktivasyon değildir.

Sonrasında manuel daha geniş kontrol gerekiyorsa `--seconds 180` aynı seed
dizisini tam bölümlerde karşılaştırır; burada bu uzun kontrol yetkisi verilmedi
ve çalıştırılmadı. Gerçek PPO bit eşitliği için aynı efektif paralellik, aynı
paket/katalog, aynı eğitim seedleri ve aynı toplam rollout bütçesiyle iki kısa
koşu karşılaştırılmalı; bu env regresyonu tek başına PPO eşitliğini kanıtlamaz.

Proje kökündeki `AI-Ekonomi-Deneyi.exe` iki işlemi de başlatır:
**Eğitimi başlat** (varsayılan 200000 adım, 8 paralel ortam) ve
**Rastgele ajanı ölç** (aynı 5 sabit değerlendirme tohumu).
EXE açıldığında eğitim başlamaz. Paralellik ve eğitim adımı pencereden seçilir.
Windows'ta istenen paralellik kullanılabilir commit belleğine göre sınırlandırılır
(4 GiB rezerv, ortam başına ihtiyatlı 3 GiB bütçe). Günlükte requested/effective,
run.json'da requested_parallel/parallel görünür. Bu bir kapasite tahminidir;
3 GiB ölçülmüş sabit ortam tüketimi değildir. Bu makinede 8 istek 2 ortamla
çalışabilir; önceki 10–16 saat tahmini daha az ortam için geçerli değildir.
Başlangıç 60 saniyeyle sınırlıdır; başlangıç hatasında aynı seed yalnız bir kez
yeniden denenir. Maç ortası hata yeni maçmış gibi rollout'a eklenmez.
Kapanış bozuk pipe üzerinde süresiz beklemez; yalnız kendi worker süreçlerini
ve onların çocuklarını kapatır. Her bölüm sonunda üretilmiş dört motor paketi
dosyası kaldırılır; gözlem/ödül/sonuç/config/günlükler korunur.
Geçici bölüm yolları Windows DLL yükleyicisi sınırı için kısadır; aşırı uzun
çıktı yolları oyun açılmadan açık hata verir.
Her çalışma `AI-Egitim/ekonomi-deneyleri/<tür>-<tarih>-<kimlik>` altında ayrı
sonuç üretir; `evaluation.csv`, eğitim için `tensorboard/` ve checkpointler
buradadır. Yanındaki `.log` dosyası işlem çıktısını tutar.
**Sonuçları aç** ilgili klasörü açar. **Durdur** veya pencereyi kapatma yalnız
bu pencereden başlatılmış süreç ağacını kapatır; kaydedilmemiş ilerleme kaybolur.
Bu ayrı deney oyun modeline otomatik aktarılmaz; diğer iki başlatıcı korunur.
Yeniden derleme: `training/build_economy_launcher.cmd`.
`AI-Ekonomi-Deneyi.exe --verify` yalnız arayüzü ve süreç sahipliği kapısını
kontrol eder, oyun/eğitim başlatmaz; kanıt `AI-Test-Sahasi/economy-launcher-check`.
`training/economy_recovery_smoke.py` en fazla 240 saniyede 200 geçiş ister;
tam 180 saniyelik maçların ardından otomatik reseti doğrular, tam eğitim değildir.

2026-11-07 hata kanıtı: `train-20261107-194639-2b329b` ikinci bölüm yüklemesinde
native `alloc_static: mem is null`, `cowdata: mem_new is null` ve çökme;
Gym pipe EOF bunun sonucudur. Kontrolde ayrıca Windows DLL yükleyicisinin uzun
yol sınırı görüldü ve bölüm adları kısaltıldı. Düzeltme sonrası kanıt
`AI-Test-Sahasi/eco-fix-195801/verification-reviewed.json`: 114.515 saniye,
200 geçiş, 4 tamamlanmış bölüm, eğitim bütçesinde kapatılmış 2 yarım bölüm,
0 gerçek bölüm hatası. İlk doğrulayıcının normal kapanıştaki 503'leri hata
saydığı `verification.json` korunur; gözden geçirilen rapor bunu ayrı sayar.
Önceden çöken 910173660 ve 278260303 tohumları tamamlandı. Süreç artığı yok.
Oyun modeli/ödül/eylem-gözlem yapısı değiştirilmedi; uzun eğitimin tamamı
ve 20k değerlendirmesi bu kısa kontrolle doğrulanmış sayılmaz.

## Duman testi ve sınır

2026-11-08 ikinci arıza: `train-20261107-205349-f31a4b` 900 geçişi
geçtikten sonra worker-02/e-c9de2719ca4c maçını kare 901'de bitirmiş,
`MATCH_RESULT ... exit=0` yazmış, fakat süreç kapanışta 0xC0000005 ile çökmüş.
Bu kayıtta bellek ayırma hatası yoktur. Etkin DLL SHA d85341ff... ile eşleşen
PDB çözümlemesi: RVA9855e8 LiveFX::~LiveFX, RVA986913 deleting destructor,
RVA2613af GameWorld::~GameWorld, RVA2666b3 deleting destructor, RVA1ac37
FXPlayer::free. SceneTree çocukları sildikten sonra LiveFX, FXPlayer'a
referansla kalıyordu. Normal oyunun quit yolu (`game.gd:4100`) önce
`clear_game_data(false)` çağırır; simülasyon harness'i bunu atlıyordu.
`simulation_match.gd/write_result` artık istatistik/hash/final gözlem alındıktan
sonra ve sonucu yayımlamadan önce aynı temizliği yapar. Temizlik hatası
başarı sayılmaz; runner'ın sıfır olmayan süreç çıkışını reddetmesi korunur.
Tek 6 s Gym ekonomi kontrolü: aynı sorunlu seed1320713198, iki adım,
teardown.ok=true, native exit0, 8.906 s. Kanıt
`AI-Test-Sahasi/eco-close-check/verification.json`. Bu bir 900+ adım veya uzun
eğitim doğrulaması değildir. EXE yerel harness'i her maçta yeniden paketler;
motor DLL'i ve model/ödül/eylem yapısı değiştirilmedi.

`economy_smoke.py --output <yeni-klasör> --parallel 8` sadece256 geçiş ve
tek PPO epoch ister; ayrı gözetici120 saniyede süreç ağacını kapatır.
Tam200000 adım veya5×180 s değerlendirme bu modda çalışmaz. İlk değerlendirme
20000'de olduğu için duman testinin evaluation.csv dosyası yalnız başlıktır.
CSV'nin5-tohum/mean/maskeli tahmin yolu oyun açmayan kod kontrolünde sınanır.
Ölçülmüş smoke sonucu ayrıca özel smoke-verification.json'da tutulur.
Kısa testin fps değeri uzun eğitim süresi için yalnız kaba tahmindir;
reset/yükleme, geç oyun karmaşıklığı ve50 değerlendirme bölümü ayrıca eklenir.

Birincil kaynaklar: [MaskablePPO/masking ve multiprocessing](https://sb3-contrib.readthedocs.io/en/master/modules/ppo_mask.html),
[SB3 politika ve ön işleme](https://stable-baselines3.readthedocs.io/en/master/guide/custom_policy.html).


2026-11-07 gerçek duman testi:8 native ortam,256 geçiş, bir PPO train turu
(1 epoch/4 minibatch), çıkış0, gözetici dahil53.92 s <120 s. TensorBoard
event dosyası ve final_model.zip oluştu.8 ayrı reward akışında256 gerçek
geçiş doğrulandı. İlk smoke rollout'u her ortamda160 s ilerledi;180 s görev
bütçesi değiştirilmedi, rollout kesildiğinde ortamlar close edildi. Bu bir
galibiyet/ekonomik başarı veya tam bölüm değerlendirmesi değildir.

4 oyun açmayan kontrol: görev/difficulty/konum,49920 boyutlu codec/maskeler/
privileged ödül izolasyonu, held-out tohum engeli, her iki ajan için5 sabit
tohum/12 CSV satırı/mean ve maskeli predict. Tam200000 eğitim,20k değerlendirme
ve gerçek uzun rastgele baseline ÇALIŞTIRILMADI. Kanıt
AI-Test-Sahasi/economy-training-verification.json.

Smokeda başlangıç dahil5.46 geçiş/s ölçüldü:200000 için doğrusal10.2 saat.
Resetler,4 epoch ve50 değerlendirme bölümüyle pratik kaba tahmin10–16 saat;
ölçülmüş tam eğitim süresi değildir. Oyun modeli/GRU ve etkin NPZ çifti aynı.
