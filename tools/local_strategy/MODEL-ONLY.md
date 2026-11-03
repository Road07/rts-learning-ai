# AI-Yeni-Model — model karar yetkisi

Ana oyun başlatıcısı kök klasördeki **`AI-Yeni-Model.exe`** dosyasıdır.
Gelecek oyun/model güncellemelerinde aynı ad ve konum korunur; başlatıcı
güncel `AI-Yeni-Model/ai-service/runtime.json` paketini kullanır.
LocalModel veya otomatik eğitim başlatmaz. Oyun kapanınca model sunucusu da kapanır.
EXE derlemesi: `build_game_launcher.cmd`; dosya/ayar kontrolü: `AI-Yeni-Model.exe --check`.
Bu kontrol oyunu açmaz ve maç davranışını doğrulamaz.

Bu başlatıcıyla yeni yerel Skirmish başlatılır. Tüm bilgisayar
oyuncularında karar yetkisi modele verilir. İnsan oyuncuya dokunulmaz.
ekranın üzerinde mod/chat paneli bulunmaz.

## Etkin karar yolu

Yedi fraksiyon kendi taktik ve üretim ağını kullanır; eğitimde yalnız
verinin ait olduğu fraksiyonun ağırlıkları değişir. Ortak eski bilgi
başlangıç olarak korunur. Ayrıntılar: [FACTION-LEARNING.md](training/FACTION-LEARNING.md).

Sisle filtrelenmiş gözlem → sınırlı yasal seçenek listesi → yerel sinir ağı
seçimi → taze sahiplik/hedef/para/yerleşim doğrulaması → normal oyun emri.
Taktik ve bina/üretim ağı normal maçta en yüksek skoru seçer; eğitimde öğrenci
takım örnekleme yapar. Her bot için en az 25 logic frame karar aralığı vardır;
her tick yeni karar/emir verilmez.

Model hareket, görünür hedefe saldırı, üsse çekilme, müttefiğe hareket,
keşif, bekleme, bina türü ve normal birlik/inşaatçı üretimini seçer. Ayrıca
kahraman alma/diriltme, upgrade ve bina seviyesi, bilim satın alma,
spellbook/kahraman büyüleri, Thrall çağırma, tünel giriş/çıkışı, duruş,
formasyon, durdurma ve üretim/araştırma iptali seçenekleri vardır. Konumlar/asker
grupları sunulan seçeneklerden gelir; serbest koordinat ve keyfi komut üretmez.
Oyun motoru para, önkoşul, komuta sınırı, sahiplik, görüş ve inşaatın
geçerliliğini denetler. Model kipinde eski %70 farm eşiği, 3 okçu / 2 süvari
kotası, zor durumdayken kuşatma yasağı ve duvar hub yasağı uygulanmaz.
Farm verimi gözlem özelliğidir, zorunlu tercih değildir. Duvar seçeneklerinin
açılması bağlantılı duvar kurmayı öğrenmiş olduğu anlamına gelmez.
Önceki zorunlu açılış, ucuz kahraman/350 CP şartı, can yüzdesine göre otomatik
kaçış ve destek yüzdeleri bu kipte çalışmaz. Eski kayıtlar ve öğrenilmiş ağ
ağırlıkları korunur; strateji filtrelerini kaldırmak geçmiş öğrenmeyi silmez.
Seçenek üretimi ve ödül hesabı kodla tanımlıdır; model kendi eylem uzayını
veya oyun mekaniklerini yeniden yazmaz.

## Kapatılan karar katmanları

- Yerleşik skirmish üretim/ekonomi/açılış, ordu/takım ve ortak beyin.
- Nesnelerin ayrı AISpecialPowerUpdate otomatik büyü kararları.
- Modun açılış, counter üretim ağırlıkları, otomatik destek/taahhüt,
  taktik seçici, makro, mikro, süvari kaçırma, kahraman kaçırma ve ileri
  tünel inşası.
- Fandom/maç geri bildiriminden elle eklenen karar puanları ve replay emir
  düzeltmesi. Bilgi/gözlem ağlarının logları emir üretmez.

Model servisi cevap vermezse yeni yedek plan/emir üretilmez. Önceden verilen
emirler, silahların normal otomatik ateşi ve başlamış inşaat/üretim devam eder.
Yerleşik bot geri açılmaz. Fizik, animasyon, yol bulma, hasar ve emirlerin
uygulanması motorun işi olarak kalır.

## Komut arayüzü ve öğrenme sınırı

`strategy_model_options` yalnız kendi nesnelerini, görünen hedefleri ve gerçek
command set/hero/science kayıtlarını okur. Para, science puanı, seviye,
prerequisite, cooldown ve kapasite koşulları oyun kurallarından gelir. Komut
uygulanırken seçilen kimlik tekrar çözülür; model keyfi template/koordinat
göndererek eylem icat edemez. Yüzük ve custom hero kapsam dışındadır.

`spend-v2` aynı seçim ağına yeni komut türü, kaynak/hedef sağlığı, kaynak
sınıfı, duruş, mesafe, hedef ilişkisi, büyü puanı ve diriltme bilgisi ekler.
Eski ağırlıklara sıfır giriş satırları eklenir: bu bir uyumlu taşıma işlemidir;
yeni eylemlerin iyi kullanımını öğrenmiş olduğu anlamına gelmez. Bu eylemler
ayrı bir otomatik büyü veya counter scripti tarafından seçilmez.

Bir model yanıtındaki büyü, durdurma veya tünel giriş emrinin kaynak birliği
aynı yanıttaki toplu hareket emrinden çıkarılır; modelin iki emri birbirini
anında iptal etmez. Hedef listesi sınırlı ve dönüşümlüdür. Serbest harita
koordinatı, her olası hedef kombinasyonu veya her engine mekaniği kapsanmaz.
Motorun uygulamadığı bir özel güce/animasyona bu bağlantı yeni mekanik eklemez.

Komutun `submitted` olması başarı kanıtı değildir. Kuyruk, gerçek çağrılmış
birlik, power `triggers`, formasyon ve tünel sonuçları ayrı incelenir.

Küçük ağların tecrübesi sınırlıdır; bu kip önceki hibrit bottan zayıf olabilir.
Taktik başlangıcı mevcut `model-v0`, üretim başlangıcı doğrulanmış
`20261103-204622-19124/spend-candidate.npz` çıktısıdır. Eski Qwen etiketleriyle
başlatılmış taktik ağının geçmişi değişmedi; yeni bir genel oyun zekâsı
eğitilmiş gibi yorumlanmamalıdır.

## Kapsam ve kayıtlar

Yalnız yeni yerel modlu maçlar; online, replay ve kayıt yükleme kapsam dışında.
AI-Genel paketi ve kurulu perakende oyun dosyaları ayrı kalır.
Paketin `ai-service/runtime.json` dosyasında `strict_model_only=true` ve
iki ağın hash'i bulunur. `controller_start`, `model_only_authority`,
`model_request`, `model_decision`, `model_production`, `model_command`, `general_order`
kayıtlarından yetki ve gerçek emir izlenir. Normal maçta bu ağlar kendiliğinden
güncellenmez; eğitim ayrı `AI-Otomatik-Egitim.cmd` döngüsündedir.
Tamamlanan eğitim otomatik olarak bu oyun paketinin ayarına yayımlanır.
`AI-Yeni-Model.exe` bir sonraki açılışta son doğrulanmış eğitim çiftini yükler;
açık maçtaki ağlar değiştirilmez. Önceki ayar `ai-service/runtime.previous.json`,
ağırlıklar `ai-service/trained-models/` altında tutulur. Aktarım doğrulaması
modelin daha güçlü olduğunun kanıtı değildir.
Normal maçta da sonuç ödülleri `reward_update` olarak loglanır; gelir ve
savaş kayıtları dışında emir sayısına bonus verilmez. Açıklama:
[REWARDS.md](training/REWARDS.md).

Yeni normal maçların seçenek/karar/sonuç kayıtları da otomatik eğitim
açıldığında işlenir. Yerel olumlu/olumsuz karar sonuçları ayrı offline
işaretli sonuç adımında kullanılır; maç sırasında ağırlıklar değişmez. Eski eksik
loglar ve yarım maçlar başarı örneği değildir. Ayrıntılar:
[NORMAL-MATCH-LEARNING.md](training/NORMAL-MATCH-LEARNING.md).
Ödüller: [DECISION-REWARDS.md](training/DECISION-REWARDS.md).

`host.py --config runtime.json --arena middle --arena-case access --seconds 6`
tek erişim sahasıdır. Kahraman/Thrall/tünel nesneleri ve science puanı yalnız
ayrı fixture'da hazırlanır; API deneme emirleri `fixture=true` ile ayrıdır,
insan veya öğrenilmiş doğru strateji örneği sayılmaz. Normal mod verisine
test parası, hazır nesne veya puan aktarılmaz.
