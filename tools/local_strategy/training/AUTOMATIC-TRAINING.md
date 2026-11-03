# Otomatik eğitim döngüsü — bina ve üretim dahil

Çift tıklamayla **sürekli** eğitim için oyun klasöründeki
`AI-Otomatik-Egitim.exe` kullanılır. Tur süresi 3, 5, 15 veya 30 dakika
seçilip Başlat'a basılır; tamamlanmış son kayıttan devam eder ve pencereden
durdurulur. Seçim her koşunun gerçek süresidir; yükleme ek süre alır. Ayrıntılar:
[TRAINING-LAUNCHER.md](TRAINING-LAUNCHER.md).
Alttaki `.cmd` kullanımı tek/belirli sayıda tur isteyen kısa komut satırı yoludur.

`AI-Otomatik-Egitim.cmd` ayrı test sahasında oyun çalıştırır, deneyim kaydeder,
yerel sinir ağını günceller ve aday checkpoint üretir. Başarıyla tamamlanan
koşunun taktik/komut çifti oyun paketinde otomatik etkinleştirilir; sonraki
`AI-Yeni-Model.exe` açılışı bu çifti kullanır. Açık maç ve kurulu oyun INI'leri değişmez.
`--no-activate` yalnız doğrulama çıktısını ayrı tutar; EXE'nin `--verify` kipi bunu kullanır.
Güncel paket model karar yetkisi kipindedir; ayrıntılar [MODEL-ONLY.md](../MODEL-ONLY.md).

## Kullanım

Çift tıklama: tek orta aşama / baskı durumu, 6 saniye, ardından bir eğitim adımı.
Bu varsayılan hızlı bağlantı kontrolüdür; rekabet gücü değerlendirmesi değildir.

PowerShell'de kullanıcı istediğinde daha fazla tekrar:

```powershell
.\AI-Otomatik-Egitim.cmd --cycles 10 --seconds 30 --evaluate
```

Bu komut 10 eğitim koşusu ve aynı yeni tohumla iki karşılaştırma koşusu yapar.
Şu ana kadar bu uzun komut çalıştırılmadı. Aşamalar `opening/middle/late`,
durumlar `pressure/counters/baseline/team`; aynı deneyde tek aşama/durum seçilir.
Her koşu en fazla 1800 saniyedir; bu bir tam maç eğitim sistemi değildir.
Ctrl+C kendi başlattığı süreç ağacını sonlandırır. Başka eğitim döngüsü aynı
anda başlatılamaz; normal test sahasını eğitim devam ederken ayrıca açmayın.

Önceki adaydan devam etmek için:

```powershell
.\AI-Otomatik-Egitim.cmd --resume "C:\tam\yol\candidate.npz" --seed 2000
```

Yeni tohum kullanın; varsayılan tohum tekrar çalıştırıldığında başlangıç aynıdır.
Devamda hareketli ödül ortalaması sıfırlanır. Aday kendiliğinden normal oyuna alınmaz.
Aynı klasörde `spend-candidate.npz` varsa bina/üretim ağı da devam eder;
başka bir dosya için `--resume-spend "C:\tam\yol\spend-checkpoint-000.npz"`
verilebilir. Yanında `spend-metadata.json` bulunmalıdır. Eski taktik-only
koşulardan devam edilirse üretim ağı yeni başlatılır.

## Ne öğreniyor?

Taktik ve komut ağları yedi fraksiyon için bağımsız ağırlıklar taşır.
Sürekli eğitimde kadro öğrenci fraksiyonlarını dönüşümlü seçer. Ayrıntılar:
[FACTION-LEARNING.md](FACTION-LEARNING.md).

Normal oyun kayıtları da koşu başında ayrı bir offline işaretli sonuç adımıyla
işlenir. Gerçek sonucu ve yerel karar etkisi doğrulanmış bot seçimleri kullanılır;
eski eksik kayıtlar ve yarım maçlar kullanılmaz. Ayrıntılar:
[NORMAL-MATCH-LEARNING.md](NORMAL-MATCH-LEARNING.md).
Yeni ödül yolu: [DECISION-REWARDS.md](DECISION-REWARDS.md). Arena da ortak
takım toplamını her hamleye kopyalamak yerine karar kredilerini kullanır.

Mevcut DecisionNet'in sunulan saldırı/savunma/keşif/yardım adayları arasındaki
puanları güncellenir. İlk üç yuvadaki takım aynı eğitim ağını kullanır;
rakip takım koşu başındaki sabit taktik ve üretim ağlarını kullanır.
Öğrenci, yasal seçeneklerin sinir ağı skorlarından softmax ile örnekler.
Her iki takımda da yerleşik bot ve script karar katmanları kapalıdır.
Hedef geçerliliği ve emir uygulama motor tarafından denetlenir; otomatik
mikro, destek veya taahhüt modeli geçersiz kılamaz.

İkinci küçük ağ (`spend-v2`) aynı karar isteğinde **bekle / bina / birlik /
kahraman / araştırma / bilim / büyü / tünel / formasyon / duruş / iptal**
seçeneklerinden birini seçer. Girdi: mevcut durum,
maliyet/para oranı, birim sınıfı, bina tipi, eldeki nesne sayısı, kaynak verimi
ve şablon için sabit hash özellikleri. Güncel paketteki üretim ağı başlangıç
alınır; önceki checkpoint ile devam edilebilir. Üretim gözlem ağının sınırlı
insan tercihleriyle eğitilmiş ağırlıkları kullanılmaz.
Başlangıçtaki seçimler öğrenilmiş iyi bir strateji olarak yorumlanmamalıdır.

Altı bilgisayar oyuncusunda `modelOnlyControl` etkindir; yerleşik botun
üretim, takım, mikro/büyü kararları geri gelmez. Başlamış inşaat/üretim ve
normal savaş/yol bulma sürer. Eski süreli test üretim yetkisi buna eklenebilir,
ama süresinin bitmesi model-only bayrağını kaldıramaz. Bu eylemler otomatik
scriptlerle yürütülmez; modelin seçtiği komutlar
normal emir kuyruğundan geçer.

Model yalnız gerçek command set, uygun üretici, boş kuyruk, para ve önkoşul
kontrollerinden geçmiş seçenekleri görür. Uygulamada tekrar doğrulanır.
Eski farm verimi eşiği, okçu/süvari kotası ve kuşatma yasağı uygulanmaz.
Konumları motor arar; model henüz serbest
yerleşim koordinatı öğrenmez. Kahraman, upgrade, bina seviyesi, science ve
büyü seçimleri aynı komut ağına dahildir. Normal AI-Yeni-Model maçında da aynı model
otoritesi ve sinir ağı seçim yolu açıktır; öğrenme güncellemesi yalnız eğitimdedir.

REINFORCE ile tek güncelleme/koşu yapılır; ortak takım ödülü kullanılır.
Önceki koşulardan hareketli ödül ortalaması baseline olur. Tek seçenekli
kararlar öğrenilmez. Taktik ağı için en az bir kabul edilmiş niyet, üretim ağı
için en az bir oyuna ulaşmış seçim yanıtı aranır; bekleme de geçerli eylemdir.
Örneklenen ama reddedilen kararlar etkisiz eylem olarak deneyimde tutulur:
yalnız kabul edilenleri seçmek örnekleme dağılımını çarpıtır. Kabul edilmiş
niyet, gerçekten verilmiş emir veya iyi hamle anlamına gelmez.
Gradyan normu ve KL sınırı bozuk/aşırı güncellemeyi engeller; eski ağırlıkla
uyuşmayan deneyim reddedilir. Başarısız saha/HTTP koşusu eğitime alınmaz.

## Ödülün sınırı

Güncel sürüm `bfme-outcome-reward-v3`: gerçek gelir ödemeleri, kendi
öldürme/kayıp sayaçları, kahraman kaybı, üs/kahraman sağlığı, kesintisiz
gözlenen düşman hasarı ve ilk keşif için sınırlı takım sinyalleri kullanır.
Emir/harcama/üretim sayısına bonus verilmez. Para iadeleri gelir değildir.
Yardımın karşılığı takımın ortak sonucudur; yardım emrine bonus verilmez.
Gerçek takım galibiyeti +10, yenilgisi −10; diğer bileşenlerin toplamı
−1..+1 aralığındadır. Kısa sahada sonuç `ongoing` ve `win_label=null` kalır.
Formül, ayarlar, sınırlar ve kayıtlar: [REWARDS.md](REWARDS.md).
Eski v1/v2 raporları yalnız geçmiş analiz uyumluluğu için okunabilir.

## Çıktılar ve değerlendirme

`AI-Egitim/otomatik-dongu/<koşu>/`:

- `baseline.npz`: normal modelin değişmez kopyası; `candidate.npz`: son aday.
- `checkpoint-NNN.npz`: her tur sonunda ayrı kayıt.
- `spend-baseline.npz`, `spend-candidate.npz`, `spend-checkpoint-NNN.npz`:
  bina/üretim ağı; `spend-metadata.json`: özellik kodlaması.
- `train-NNN/experience.json`: gözlem, yasal seçenek, örnekleme olasılığı,
  kabul durumu, gerçek oyun ölçümünden türetilen ödül.
- Aynı deneyim dosyasında üretim seçimleri, gönderim sonucu ve gerçek sahip
  olunan yeni nesne/üretim kuyruğuyla doğrulanan `purchase_receipts` bulunur.
  İnşaata başlanması tamamlandığını, kuyruğa girmesi birliğin çıktığını kanıtlamaz.
  Aynı kararın iki kez gönderildiği koşu eğitime alınmaz.
- `command_submissions` yeni kahraman/araştırma/büyü/duruş/tünel emirlerini
  kaydeder; kabul edilen emir iyi strateji veya gerçekleşmiş etki etiketi değildir.
- `train-NNN/arena/middle.json`: başlangıç/sonuç, hatalar, ödül nesneleri,
  gerçek diagnostic session kimliği; `service.jsonl`: sunucu deneyimleri.
- `report.json`: hash'ler, öğrenme adımı, ödül, hata ve isteğe bağlı karşılaştırma.
- `reward-tuning.json`: koşudaki sabit ödül ayarları; `reward_breakdown`:
  gelir, savaş, kayıp, sağlık, keşif ve terminal puanın ayrı dökümü.

`--evaluate` öğrenmeye katılmayan yeni bir tohumda önce baseline sonra adayı,
aynı rakipler ve başlangıç düzeniyle çalıştırır; iki ağ birlikte karşılaştırılır.
Üretim baseline'ı koşunun başlangıçtaki üretim ağıdır, yerleşik üretim değildir.
Tek çift istatistiksel olarak
güçlenme kanıtı sayılmaz; eşzamansız çalışma tam determinizm sağlamaz.
Değerlendirme bilgi amaçlıdır; güçlenme kanıtı veya etkinleştirme eşiği değildir.
Kullanıcının tercihiyle tamamlanan her geçerli koşu otomatik etkinleştirilir;
bu seçim her güncellemenin daha iyi oynayacağını garanti etmez.
Tam strateji hedefi için gerçek maç bitişi/galibiyet, daha uzun ufuklar,
serbest yerleşim ve grup/komut zamanlaması öğrenimi ile farklı rakipler sonraki genişletmelerdir.
