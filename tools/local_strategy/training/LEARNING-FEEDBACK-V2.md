# Karşılaştırma ve öğrenme geri bildirimi v2

## Eş koşullu değerlendirme

Fraksiyon rotasyonu artık değerlendirme tohumundan türetilmez. Eğitim
turunun rosterı korunur; yeni tohum yalnız maç rastgeleliğini değiştirir.
Çok döngülü bir çağrıda son eğitim turunun rosterı değerlendirilir.
Önceki ve yeni model yine aynı rakip checkpointine karşı oynar.

Değerlendirmede sabit `arena_sim_frames = seconds * 4 * 5` bütçesi vardır.
Saha ilk adımı bir logic frame olarak ilerletir, kalan ilerlemeyi son
kareye sınırlar. Sonuçta `simulation_window` başlangıç/bitiş/bütçe
alanları yazılır. Eğitim turlarının seçilen gerçek zaman süresi korunur;
değerlendirmeler aynı simülasyon süresini bitirir. Yavaş koşular için
zaman aşımı payı büyütülür; sınırsız bekleme yoktur. Bu, karar taşıma
gecikmelerini veya bütün maç davranışını deterministik yapmaz. Tek çift
hâlâ istatistiksel üstünlük kanıtı değildir.

## Gerçek üretim ve iptal verileri

Motor, birim/kahraman üretim kuyruğuna gerçekten girilen ve gerçekten
iptal edilen siparişler için üretici başına en fazla 64 kayıt tutar.
Kayıtlar seri numarası, sipariş kimliği, sahip, frame, şablon, ödenen
kuyruk maliyeti, ilerleme, üretim iş sayacı, üretilen miktar ve otomatik
iptal bayrağını içerir. Bunlar tanısal kayıtlardır; gameplay CRC/save
durumuna eklenmez. Eski save/replay için geçmiş olay uydurulmaz.

`get_production` yalnız kendi üreticisinin bilgilerini verir. Sensör
seri numaralarını takip eder; eksik halkalı geçmişle ceza üretilmez.
İptal seçenekleri de ilerleme, iş süresi, maliyet ve kalan miktarı taşır.
Beş yeni üretim girdisi ağın sonuna eklenir: taktik 385, üretim 383 giriş.
Eski 378 girişli model ve yedi faction bankası sıfır satırlarla korunur.

`action-credit-v2`, gerçek iptali aynı üretici ve sipariş kimliğiyle
gönderilen iptal kararına bağlar. 30 saniye içinde aynı şablonun gerçekten
yeniden kuyruğa girmesi halinde kaybedilen ilerleme, nominal maliyetiyle
ölçeklenerek `production_restart_delay` geri bildirimi olur. Bu para
kaybı değildir: tam iade edilmiş para ödül/ceza sayılmaz. İş saniyesi,
üretim hızı etkilerini içeren temel üretim-iş eşdeğeridir.

Otomatik iptal, kısmen birim çıkarmış sipariş, sıfır ilerleme, eksik kayıt,
görüşte değişen düşmanlar, yaralanan üretici veya yakında görülen tehdit
durumlarında bu ceza uygulanmaz. İptal yasaklanmaz; sayıya göre emir
engelleme veya zorunlu asker üretimi eklenmez. Bu yine gözlenen ilişkiyi
ölçer; kusursuz stratejik nedensellik veya her iptalin gereksizliği iddiası
değildir. Araştırma iptalleri bu ilk native kayıt kapsamına dahil değildir.

## Ekonomi getirisi

Yeni yapıların kendi motor verisindeki `paid_cost` kaydedilir. Kaynak
binanın gerçekten tamamlandığı gözlendikten sonra 180 saniyelik gelir
penceresi izlenir. Pencere olgunlaşırsa ekonomik geri bildirim
`(gerçek kaynak ödemeleri - ödenen yatırım) / (1000 + yatırım)` olur.
Eksik/ücretsiz ödeme kaydı, ilk harita binaları veya olgunlaşmamış yatırım
için tahminle ekonomik etiket üretilmez. Yapım emri ve para iadesi gelir
sayılmaz; arazi verimine sabit bir eşik dayatılmaz.

Bu nakit geri dönüş ölçüsüdür; binanın kalan sermaye değerini, gelecekteki
geliri veya bütün dolaylı askeri faydasını hesaplayan tam ekonomik kâr
değildir. Savaş kaybı ve gelir ayrı, sınırlı geri bildirim kanallarıdır.
Horizon kısalığı/atıf belirsizliği gelecekte ayrıca değerlendirilmelidir.

Ekonominin toplam yerel ödül bütçesi %15, diğer yerel sonuçların %85'tir.
İki kategori `bütçe * değer / (1 + toplam mutlak değer)` ile yumuşak
sınırlanır. Yalnız farm geliri toplayarak 1.0 yerel ödül tavanına ulaşılmaz;
farklı geri dönüşler birebir aynı sabit tavan skoruna çevrilmez.
Galibiyet/mağlubiyet ±10 ana hedef olarak korunur.

## Sürüm ve kullanım

Ölçüm satırları `action-credit-v1` gözlem şemasını korur; ödül politikasının
ayrı sürümü `action-credit-v2` olarak raporlanır. Eski v1 ayar dosyaları ve
hesabı korunur. Yeni politika hash ile sabitlenmiş `reward-policies/`
dosyasından yüklenir. Açık maçın bellekteki politikası değişmez.

Normal maçlar aynı sensör ve v2 politikayı kullanır. Eğitim döngüsüne
alınacak normal maçın kayıt politikası güncel politikayla eşleşmelidir;
eski v1 hedefleri sessizce yeni hedeflere karıştırılmaz. Model ağırlıkları
sıfırlanmadı; yeni kuyruk girdileri henüz eğitilmediği için otomatik bir
oynayış düzelmesi iddia edilmez. Tamamlanan eğitim çiftlerinin mevcut
otomatik aktarım davranışı korunur; yeni bir yayın/onay kapısı eklenmez.

## Doğrulama

51 ilgili Python kontrolü geçti: roster sabitleme, v1 uyumluluğu, v2 net
geri dönüş, yumuşak bütçeler, gerçek iptal/yeniden başlatma eşleştirmesi,
meşru iptal istisnaları, bilinmeyen kayıtların dışlanması ve banka taşıma.

Tek `middle / learning-feedback` 6 saniyelik saha çalıştırıldı. Gerçek
Guardian üretimi, %3.33 ilerlemede iptali ve farklı sipariş kimliğiyle
yeniden kuyruğa girişi doğrulandı. 0.8 eşdeğer üretim-iş saniyesi kaydedildi.
Saha tam 120 logic frame ilerledi (10 → 130), 12 öğrenci kararı kaydedildi,
script/istek/ödül hatası yoktu. Bu manuel fixture eylemleri başarılı AI
kararı/uzman etiketi olarak kullanılmadı; deterministik değerlendirme
örnekleriyle gradient güncellemesi yapılmadı.

Kanıt `AI-Test-Sahasi/learning-feedback-check/episode/arena/middle.json`,
`episode/experience.json` ve `ai-mod-source/learning-feedback-v2-verification.json`.
İki uzun karşılaştırma maçı veya yeni uzun eğitim bu değişiklik sırasında
başlatılmadı; uzun vadeli davranış ve güçlenme henüz ölçülmedi.

## Kesilen değerlendirmeden devam

Başlatıcı, tamamlanmış eğitim adımı ve hash doğrulaması geçen aday çiftini
yeniden eğitmeden bekleyen karşılaştırmaya döner. Kesilen tek maç yeniden
başlar; rapora işlenmiş önceki/yeni model bölümü tekrar oynanmaz. Her bölüm
atomik raporla kaydedilir. Ödül/katalog veya etkin başlangıç ağırlıkları
değişmişse eski değerlendirme sessizce devam ettirilmez. Üretim girdilerinin
sıfır satırlarla genişlemesi tüm yedi bankanın sayısal eşitliğiyle tanınır.

Arayüz eğitim / önceki model 1/2 / yeni model 2/2 aşamalarını gösterir.
Seçilen süre her oyun bölümü için ayrıdır; her beşinci tur iki ek
karşılaştırma içerir. Başlatıcı kapatılınca süreçleri yine sonlandırır.
Başarıyla tamamlanan tur mevcut otomatik aktarım yolunu kullanır.

24 ilgili Python kontrolü geçti; gerçek başlatıcı durumunun kopyasında
29 tamamlanmış tur ve bekleyen 30. tur korunarak kurtarma doğrulandı.
Tek 6 saniyelik sabit 120-kare saha koşusunda gerçek model kararları ve
hatasız bitiş doğrulandı. Bu bir uzun değerlendirme veya güçlenme kanıtı
değildir. Aktif oyun ağırlıkları ve gerçek başlatıcı durumu değiştirilmedi.

## Araştırma olayları ve iptal tanıları — 2026-11-05

Native kuyruk kayıtlarına isteğe bağlı `queue_kind` (unit/research) ve
`queue_receipt_id` alanları eklendi. Araştırmanın native production_id değeri
0 olarak korunur; ayrı gözlem kimliği queued olay seri numarasından üretilir.
Queued/cancelled olayında aynı kalır, yeniden kuyruğa girişte değişir.
Kimlik motor emir kimliği, save/CRC veya yeni neural girdi değildir.
Yüklenen eski kayıtta başlangıcı gözlenmeyen kuyruk için kimlik 0 kalabilir.

Araştırmanın gerçek ücret/ilerleme/iş sayacı ve otomatik iptal bayrağı
kaydedilir. Cancel-all ve artık uygulanamayan object upgrade iptali
otomatik işaretlenir. 64 olaylık halka ve eksik geçmiş kontrolü korunur;
sensör yalnız kendi üreticisinin olaylarını toplar.

V2 araştırmaya yeni ceza uygulamaz; araştırma kayıtları diagnostics olarak
sayılır ve birim/hero iptal hesabından açıkça ayrılır. Ödül hash'i ve ağ
giriş sayıları değişmedi. Eski loglara araştırma olayı uydurulmaz.

Düşman değişimi filtresi artık toplam ve oyuncu bazında kimlik-değişimi /
şablon-sayı değişimi sayacı tutar; yerel çevrenin değişmediğini ve yakında
görünür düşman olmadığını ayrıca sayar. Bu tanılar ödül eklemez, filtreyi
gevşetmez, stratejik doğru/yanlış etiket değildir. 30. tur adayındaki
öğrencilerin önceki 33 dışlaması şablon/sayı değişimidir (cüce 4, goblin 29);
yalnız kimlik değişimi diye sunulamaz.

18 ilgili Python kontrolü geçti. Tek middle/learning-feedback 6 saniye
kontrolünde DwarvenFortressBanners araştırması gerçekten başladı, %20
ilerleme/0.8 iş saniyesinde iptal edildi ve farklı gözlem kimliğiyle yeniden
başladı. Üç araştırma olayı reward_observation'a ulaştı; 12 gerçek model
kararı, 0 script/istek/ödül hatası, 120 sabit kare (16→136). Fixture emirleri
uzman/başarılı model etiketi yapılmadı; gradient güncellemesi yapılmadı.
Normal oyun DLL'i ve sunucu tanıları güncellendi, runtime/ağırlıklar korundu.
Kanıt: ai-mod-source/research-receipts-verification.json.
