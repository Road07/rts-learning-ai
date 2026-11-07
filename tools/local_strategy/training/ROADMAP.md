# RTS öğrenen AI yol haritası

Güncelleme: 2026-11-05. Kullanıcı bu plana göre ilerlemek istiyor;
"devam" sıradaki tamamlanmamış işe devam edilmesi demektir.

## Amaç ve çalışma düzeni

Yerel çalışan, oyun gözlemlerinden kendi stratejisini seçen ve deneyimlerinden
öğrenen RTS karar modeli. İlk ortam OpenBFME + RotWK 2.01, öncelik 3v3.
Başarı, ağırlık değişmesi veya saha PASS sonucu değil; eğitim dışında kalan
koşullarda ölçülebilir oyun başarısıdır. Metaya uyum uzun vadeli hedeftir.

- Her devam turunda önce güncel kayıt/durum okunur, aşağıdaki ilk açık iş ele alınır.
- Her aşamanın sonunda yapılan değişiklik, kanıt, sınırlar ve sıradaki iş bu
  dosyanın ilerleme bölümüne eklenir. Başarısız ölçümde aşama tamamlanmış sayılmaz.
- Kod doğrulaması için ilgili tek 6 saniyelik saha kullanılır; uzun maç veya
  toplu test kendiliğinden başlatılmaz. Kullanıcının mevcut eğitim çıktıları
  önce incelenir. Gerekli uzun deneyin süresi/kapsamı önceden açıkça belirtilir.
- Sabit build order, zorunlu asker/hero sayısı veya iptal yasağıyla başarı
  taklit edilmez. Oyun kuralları ve yasal eylem sınırları kodda korunur.
- Sisle gizlenen düşman bilgisi karar veya ödül etiketine aktarılmaz.
- Eski ağırlıklar, yedi faction bankası ve eğitim geçmişi korunur. Şema
  genişlemeleri uyumlu taşınır. Deneyler özel config/--no-activate kullanır.
- Normal maç offline verisi, on-policy arena verisi ve fixture emirleri
  ayrı tutulur. Tamamlanan geçerli eğitimlerin otomatik aktarımı korunur;
  performans karşılaştırması sonucu ayrıca raporlanır.
- Oyun başlatıcısı AI-Yeni-Model.exe, eğitim başlatıcısı AI-Otomatik-Egitim.exe
  olarak kalır. GitHub yayını yalnız kullanıcı istediğinde yapılır.

## 1. Eğitim ve değerlendirme zincirini kapat — TAMAMLANDI

İş: Bekleyen 30. turun durumunu doğrula. Eğitimin tekrar uygulanmaması,
tamamlanan baseline karşılaştırmasının korunması, aday karşılaştırmasının
bitmesi, rapor/başlatıcı durumu/otomatik aktarımın aynı modeli göstermesini
kontrol et. İptal, kesinti ve hata durumlarını açık ayır.

Çıkış kanıtı: Tamamlanmış karşılaştırma çifti; eş roster/rakip/tohum/kare
bütçesi; checkpoint hashleri ve runtime aktarımı tutarlı. Tek çift güçlenme
kanıtı sayılmaz. Bu aşama yalnız güvenilir işlem zincirini kanıtlar.

## 2. Önce taklit öğrenme, sonra RL ile gerçek öğrenmeyi göster — AKTİF

Kullanıcının güncel önceliği: Önce gerçek insan veya seçilmiş yerleşik AI
örneklerinden behavior cloning; ardından mevcut RL ile ince ayar. Sabit bir
build order kodlamak değildir. Önceki RL geri bildirim işleri korunur,
fakat temel oyunu sıfırdan RL ile keşfetmek ana başlangıç yöntemi değildir.

### 2A. Gösterim verisini mevcut politikayla eşleştir — altyapı uygulandı; gerçek veri kapsamı bekleniyor

Karar öncesi FOW uyumlu gözlem, actor/target/koordinat, mevcut yasal aday
kümesi ve gösterilen seçimi aynı sürümlü şemada topla. Kaynak tipi insan /
yerleşik-AI / model / fixture ayrıdır. Model ve fixture emirlerine uzman
etiketi verme. Yerleşik AI'nın ayrıcalıklı bilgisini gözleme kopyalama;
yasal adayda temsil edilemeyen emri yakın başka hamleye uydurma.

Farm konumu için gerçek koordinat/verim, duvar için başlangıç ağı ile
bağlı genişletme hedefi gerekir. Yalnız 'construct' etiketi bunları öğretmez.
Seçilen aday kapsamı yetersizse önce eylem arayüzünü düzelt. Emir kabulü,
uygulanması ve stratejik kalitesi ayrı alanlardır; success_verified=false
tek başına başarısız eylem demek değildir. Kaynak/nesne/olay kanıtlarını
ayrıca eşleştir; eksik sonuç etiketini uydurma.

### 2B. Ayrı BC ön eğitimi

Kullanıcının yeni mimari tercihi: ortak gövde + faction embedding + entity
attention + GRU, PyTorch/CUDA. Eski yedi bankayı geri dönüş olarak koru.
Yeni ağda gösterilen yasal aday dağılımına supervised loss uygula. Eğitim/validasyon/testi
maç/oturum bazında ayır; komşu kareleri iki tarafa dağıtma. Kaynak ve
fraksiyon kapsamasını, adayda temsil edilemeyen gösterimleri ve reddedilen
kayıtları raporla. Eski 16 komut ailesi shadow sınıflandırıcısını mevcut
385/383 girişli karar ağlarının BC ön eğitimi diye sunma. Deneysel BC çifti
ayrı kaydedilir; ağırlıkları sıfırlama, otomatik eğitim akışına rastgele
eski veri ithal etme.

### 2C. Önce BC'yi değerlendir, sonra RL

Ayrılmış gösterimlerde seçim/parametre kapsamı ve aynı koşullu oyun
karşılaştırmalarını birlikte değerlendir. Taklit doğruluğu güçlü oyun
kanıtı değildir. Bu temelden sonra RL ile sonuç ödülüne göre ince ayar yap;
öğretmenin kötü alışkanlıklarını, dağılım kaymasını ve unutmayı izle.
Mevcut otomatik RL başlatıcısı bu plan değişikliğinde sessizce BC eğitilmiş
bir sistemmiş gibi yeniden etiketlenmez; geçiş ayrıca uygulanıp doğrulanır.


İş: Üretim–iptal–yeniden başlatma davranışını ilk öğrenme hedefi seç.
Mevcut yasal seçenekleri, native kuyruk olaylarını ve karar kredilerini
incele. Ceza gerçekten ilgili öğrenen faction/head'e ulaşıyor mu doğrula;
rakip sabit model davranışını öğrenci başarısızlığıyla karıştırma.
Tamamlanan üretim olaylarının eksikliği varsa önce ölçümü tamamla;
onaylanan emirleri tamamlanmış birlik gibi sayma.

Ölçüm: İptaller/gerçek yeniden başlatmalar, kaybedilen üretim ilerlemesi,
tamamlanan üretimin maliyeti, sahadaki ordu ve savaş kayıpları ayrı gösterilir.
Önce/sonra değerlendirmede aynı koşullar ve eğitimde kullanılmamış birden
fazla tohum gerekir. Tohum sayısı, bütçe ve karar ölçütü deneyden önce kaydedilir.

Çıkış kanıtı: İyileşme tekrar eder; yalnız iptal sayısını düşürüp üretimi
tamamen durdurma veya kötü ordu üretme gibi ödül sömürüsü görülmez.
Kanıt yoksa ödül/eylem/gözlem/öğrenme sorununu ayırıp bu aşamada kal.

## 3. Ekonomi ve üretimi birlikte öğren

İş: Farm adayları ve gerçek gelir verileri; yatırım maliyeti, geri dönüş
penceresi, inşaatçı hareketi, üretim seçenekleri ve teknoloji önkoşullarının
modelce erişimini denetle. Yapı yerleşiminde yasal aday kapsamını ölç.
Sadece farm kurarak ödül toplama ve savunmayı ihmal etme durumlarını incele.

Çıkış kanıtı: Başlangıçtan oynanan koşullarda yatırım/ordu kararları bağlama
göre değişir; saldırı altında ekonomik toparlanma ve askeri sonuçlar beraber
iyileşir. Para tutmak veya boş fabrika tek başına hata etiketi değildir.

## 4. Savaş ve özel mekanikleri öğren

İş: Sınıf karşılaşmaları, erişilebilir yükseltmeler, hedef/konum/geri çekilme,
kahraman ve spellbook sonuçlarının gözlem–eylem–ödül bağını tamamla.
Tünel çıkışı, bağlı duvar genişletmesi gibi motorun destek sınırlarını ayır.
Tek bir durumu seçip ilerle; bütün birlik matrisi çalıştırma.

Çıkış kanıtı: Eğitim dışında kalan küçük savaş durumlarında maliyet
verimliliği, kahramanın tekrar savaşa katılması ve büyünün gerçek etkisi
iyileşir; emir kabulü tek başına başarı değildir.

## 5. Zaman içinde strateji kurma

İş: Modelin mevcut belleğini ve gözlem geçmişini denetle. Gerekliyse
gözlenen düşman kompozisyonu, eskime/güven, kendi önceki planı ve sonuçları
için zamansal temsil ekle. Plan devamlılığı ile gerekli strateji değişimini
ayır; model genişlemesini eski bankaları koruyarak yap.

Çıkış kanıtı: Aynı başlangıçtan farklı gözlenen rakip stratejilerine
farklı ve işe yarayan tepkiler; görünmeyen ordulara bilgi sızıntısı yok.

## 6. 3v3 takım oyunu

İş: Sessiz otomatik koordinasyonda yardım, ortak hedef, rol/taahhüt ve
çakışma önleme arayüzlerini denetle. Yardımın yerel sonucu ile kendi
üssünde oluşan kaybı ayrı değerlendir. Sohbet ekranını geri getirme.

Çıkış kanıtı: Karşılaştırılabilir takım durumlarında yararlı destek ve
ortak saldırı; gereksiz toplu yürüyüş veya kendi üssünü boşaltma azalır.

## 7. Rakip ve harita çeşitliliği

İş: Başlangıç/orta/geç fixture'larına ek olarak gerçek maç akışı, farklı
haritalar, yedi faction, sabit geçmiş checkpoint rakipleri ve uygun farklı
oyun tarzlarından bir eğitim programı kur. Eğitim ve değerlendirme
havuzlarını ayır; replay sürüm farklarını ve veri kökenini kaydet.

Çıkış kanıtı: Tek rakibe karşı gelişirken diğerlerine çökmez. Görülmemiş
harita/strateji sonuçları faction ve takım eşleşmesine göre raporlanır.
Deneyim tekrarı eski verileri yanlışlıkla güncel on-policy veri yapmaz.

## 8. Metaya uyum ve sürdürülebilir geliştirme

İş: Yeni güçlü rakip tarzlarını veri havuzuna al; rakip havuzunu sürümle,
önceki yeteneklerin unutulmasını ve ödül sömürüsünü izle. Maç içi uyum ile
maçlar arasında yeniden eğitilmeyi ayrı ölç. Yerel bilgisayarın hız/bellek
bütçesini kaydet; başka RTS'ler için motor adaptörünü öğrenme çekirdeğinden ayır.

Çıkış kanıtı: Yeni stratejilere eğitim sonrası tekrarlanabilir uyum ve eski
eşleşmelerde kabul edilebilir performans. İnsan seviyesinde/metaya hâkim
olduğu ancak buna uygun dış değerlendirmeyle söylenebilir.

## İlerleme kaydı

- 2026-11-05: Yol haritası oluşturuldu. Aşama 1 aktif.
- Son bilinen durum: 29 tur tamamlanmış; 30. turun eğitim güncellemesi
  kaydedilmiş, baseline-retry-001 karşılaştırması 3600 kareyi tamamlamış;
  aday karşılaştırması kesilmiş. Bir sonraki devamda güncel dosyalardan
  yeniden doğrula; bu tarihsel satırı canlı durum sanma.
- Sıradaki somut iş: Bekleyen aday değerlendirmesi ve otomatik aktarım
  zincirini incele; veri yeterliyse aşama 1'i kanıtıyla kapat, ardından
  aşama 2 için üretim kararlarına gerçekten ulaşan krediyi denetle.

- 2026-11-05 / devam: Aşama 1 tamamlandı. 30. tur complete/activated;
  baseline-retry-001 ve candidate-retry-001 aynı 4→3604 (3600 kare)
  penceresini tamamladı. Eş roster/window doğrulaması true. Etkin iki NPZ
  dosyasının hashleri runtime ve 30. tur aktarım kaydıyla eşleşiyor.
  Başlatıcı completed=30; 31. tur ayrı pending. Uzun test başlatılmadı.
- Aşama 2 ilk denetim: Eski/yeni puan +0.09575 / -0.17102; tek çift
  güçlenme kanıtı değil. Üretim ağı eğitimde 294 karardan yalnız 22'sinde
  sıfırdan farklı geri bildirim almış. Eğitimde ölçülen 3 iptal-yeniden
  başlatma olayı öğrenen 3/4/5 oyuncularına değil, sabit rakip 7/8'e ait.
  Bu olayların öğrenci ağına aktarılmaması doğru izolasyondur.
- Aday değerlendirmesinde öğrenciler 57 iptal seçeneği seçmiş, ancak
  hiçbirinde production_restart_delay kredisi yok. Seçim gerçek iptal
  demek değildir; bağlam filtrelerini kaldırmadan, dispatch/receipt/tehdit/
  kayıt bütünlüğü koşullarıyla nedenleri sıradaki adımda ayrıştırılacak.
  Baseline/aday üretim seçimi 21→61; tamamlanan birlik veya güçlenme diye
  sunulamaz. Değerlendirme örnekleriyle eğitim yapılmadı.
- Kanıt: ai-mod-source/round30-credit-audit.json. Sıradaki somut iş:
  adayın 57 iptal seçiminin gerçek emir/olay/kredi zincirini nedenlere
  ayır; öğrenme sinyali eksikliği mi, meşru filtre mi olduğunu doğrula.

- 2026-11-05 / devam: 57 aday iptal seçimi emir/olay zincirine göre
  ayrıştırıldı: 33 görünür düşman kimlik/şablon kümesi değişimi; 12 araştırma
  iptali (native araştırma olay kaydı mevcut değil); 7 kısmen üretim çıkarmış
  kuyruk; 4 aynı üreticide 30 saniyede aynı şablon yeniden başlatılmamış;
  1 eşleşen gerçek iptal kaydı yok. Nedenler ilk dışlama koşuluna göredir;
  bir olay birden çok dışlama koşuluna uyabilir. Dışlama stratejik doğruluk
  etiketi değildir. Araştırma iptalleri veri yokluğudur, ceza uydurulmadı.
- Kanıt: ai-mod-source/cancellation-reasons-round30.json. Geri bildirim
  eşleştirmesinin bozuk olduğu kanıtlanmadı; v2 mevcut korumalarla bu
  57 öğrenci kararına yeniden başlatma cezası üretmiyor. Aşama 2 açık.
- Sıradaki somut iş: Araştırma kuyruğunun gerçek başlama/iptal olaylarını
  üretim olaylarıyla aynı sahip/üretici/sipariş kimliği ve iş ilerlemesi
  kanıtlarıyla kaydet; sayısal girdilerin birim/araştırma anlamını ayır.
  Önce gözlem kaydını doğrula, ödül kapsamını genişletmeyi sürümle ve
  meşru iptal korumalarını koru. Eski loglara eksik olay uydurma.

- Ek inceleme: Düşman kümesi değişimi nedeniyle dışlanan 33 olayın
  tamamında üretici çevresindeki 650 yarıçapta görünür düşman yok. Mevcut
  küresel kimlik değişimi filtresi yerel tehditten daha geniş; fakat uzaktaki
  stratejik yeni bilgi de iptali haklı çıkarabilir. Sıradaki uygulamada
  önce bilgi değişiminin anlamını (kimlik vs kompozisyon/tehdit) ayıran
  tanısal kayıt ekle; filtreyi körlemesine kaldırma. Ardından araştırma
  native olay kapsamını tamamla. Öğrenme başarısı henüz kanıtlanmadı.

- 2026-11-05 / devam: Düşman değişimi tanıları eklendi; 30. turdaki
  öğrenci dışlamaları yalnız kimlik değil şablon/sayı değişimi (cüce 4,
  goblin 29). Filtre körlemesine kaldırılmadı. Gerçek native araştırma
  queued/cancelled kayıtları, gözlem kimliği ve birim/araştırma ayrımı
  eklendi. ProductionID=0 korunuyor. V2 ödül kapsamı değişmedi.
- 18 kontrol ve tek 6 saniye middle/learning-feedback geçti: gerçek
  FortressBanners araştırması %20'de iptal/yeniden başlangıç; 3 olay
  sensöre ulaştı, 12 model kararı, 0 hata. Normal oyun motoru/sunucusu
  güncellendi; checkpointler/runtime değişmedi. Kanıt:
  ai-mod-source/research-receipts-verification.json.
- Aşama 2 hâlâ açık. Sonraki somut iş: Araştırma yeniden başlatma
  geri bildirimini yeni politika sürümünde tasarla/uygula; native gözlem
  kimliğiyle eşleştir, otomatik iptal/kayıp geçmiş/bağlam değişimi
  korumalarını ve eski ödül uyumunu test et. Düşman kompozisyonu
  değişimini gereksiz iptal kanıtı sayma. Ardından öğrenen fraksiyonların
  gerçekten kredi aldığı mevcut/izole veride doğrula; başarı iddiası için
  eğitim dışı birden fazla eş karşılaştırma gerekir.

- 2026-11-05 / devam: action-credit-v3 eklendi ve normal maç/otomatik
  eğitim varsayılanına dağıtıldı. Gerçek araştırma gözlem kimliğiyle
  iptal/yeniden başlatma kredisi; v1/v2 değişmedi. Eski checkpointler
  korundu, yeni neural girdi yok. 32 kontrol ve tek 6 saniye saha geçti.
  Gerçek native olaylarla kontrollü fixture kredi ilişkilendirmesi
  doğrulandı; eğitim örneği/strateji başarısı sayılmadı. Kanıt:
  ai-mod-source/research-credit-v3-verification.json.
- Aşama 2 hâlâ açık: Sıradaki iş mevcut yeni eğitim/normal maç kayıtlarını
  kontrol etmek; v3 öğrenen oyuncu kredisi yoksa hangi yasal seçimlerin
  gerçek sonuç verebildiğini kısa izole gözlemle incelemek. Saatlerce
  kör eğitim veya fixture emirlerine uzman etiketi yok. Politika sürümü
  farklı eski değerlendirmeler v3 başarısı diye yeniden etiketlenmez.
  Gerekli eş değerlendirme bütçesi önceden kaydedilir; çoklu karşılaştırma
  olmadan öğrenme/güçlenme tamamlandı denmez.

- 2026-11-05 / devam: Güncel kayıtlar incelendi: tamamlanmış v3 tur
  henüz yok; son tamamlanan 30. tur v2, 31. tur eski yarım kayıt.
  `decision-feedback-audit-v1` episode/experience/tur raporuna bağlandı.
  Öğrenci/rakip, faction/head, seçim/gönderim/olgunlaşma ve sıfır kredi
  nedenleri ayrılıyor; gradient veya ödül değişmiyor. 17 kontrol geçti.
- Tek 6 saniyelik sample (gradient uygulanmayan) learning-feedback
  kontrolünde 24 model kararı gönderim ve krediyle eşleşti. 21 karar
  olgunlaşmamış, 3 kararda ölçülen yerel etki yok. Bu kadar kısa pencere
  ekonomi/araştırma öğrenmesi kanıtı değildir; aynı kısa koşuyu tekrarlama.
  Ağırlık/runtime korundu. Kanıt: ai-mod-source/feedback-coverage-verification.json.
- Aşama 2 açık. Sıradaki bağımlılık: Kullanıcının en az bir tamamlanmış
  v3 otomatik eğitim turu (başlangıç için arayüzde 3 dakika). Yeni veri
  gelince feedback-audit.json/round report ile öğrenci kredisi ve güncelleme
  eşleşmesini incele. Henüz yeni veri yoksa güçlenme iddiası veya uzun
  koşuyu kendiliğinden başlatma; mevcut kısa smoke'u tekrar etme.
  Güçlenme için bundan sonra eğitimden ayrı, önceden kapsamı belirlenmiş
  çoklu eş değerlendirme gerekiyor. GitHub bu adımda güncellenmedi.

- 2026-11-05 / kullanıcı isteği: OpenBFME sürümünü otomatik takip
  altyapısı eklendi. 5 Kasım motoru ayrı AI fork'unda derlenip doğrulandı;
  AI-Yeni-Model.exe güncel motoru seçiyor. Arka plan uyarlama, başarısızlıkta
  eski motoru koruma ve eğitim çiftine sabit motor seçimi var. Modeller ve
  ödül korunuyor. 23 kontrol + tek 6 saniye mechanics geçti. Kanıt:
  ai-mod-source/engine-update-verification.json. GitHub yayımlanmadı.
  Aşama 2 öğrenme doğrulaması hâlâ açık; bu motor güncellemesi güçlenme
  kanıtı değildir. Sonraki devamda yeni v3 eğitim kayıtlarını incele.

- 2026-11-05 / kullanıcı yönlendirmesi: Aşama 2'ye BC→değerlendirme→RL
  sırası eklendi. Mevcut shadow insan sınıflandırıcısında 863 örnek var;
  görev 16 komut ailesini tahmin etmek, mevcut karar skorlayıcılarının
  gösterim eğitimi değil. Son iki gerçek insan logunda sırasıyla 16 ve 30
  before-state/command/result çifti bulundu; güncel politika aday kümeleri
  yok. success_verified alanı pozitif değil; bu tek başına emirlerin
  başarısız olduğu anlamına gelmez, ek uygulama kanıtı gerekir.
- Kanıt: ai-mod-source/bc-readiness-audit.json. Bu adımda maç, eğitim veya
  ağırlık değişimi yapılmadı. Sıradaki iş 2A: mevcut politika ile uyumlu
  karar öncesi gösterim kayıt şemasını ve yasal eylem eşleştirmesini kur.

- 2026-11-05 / yap: bc-demonstration-v1 native pre-dispatch insan
  kaydı ve birebir aday eşleştiricisi kuruldu. Aynı normal encoderlar,
  pre-state map_extent/spell_points ve katalog hash'i kullanılır. Yasal
  adayda olmayan konum/actor/niyet yakın adaya çevrilmez. Native kuyruk
  ekleme/çıkarma kanıtı, stratejik kalite etiketinden ayrıdır.
- 16 kontrol; son middle/human-log 6 saniyede 3 görüntü, 2 doğru eşleşme,
  0 fixture eğitim örneği. FOW, insan kontrolü ve ağırlıklar korundu.
  Kanıt: ai-mod-source/bc-demonstrations-verification.json. Eski 5 gerçek
  oturumdaki 2852 komutta güncel aday kaydı yok; BC diye kullanılmadı.
- 2A normal maçta etkin; insan oynadıkça yeni kayıt toplanır. Scripted-AI
  öğretmen kaydı ve BC eğitici henüz bağlı değil. İlk exporter uygunluğu
  yalnız gerçek kuyruk etkisi kanıtlı örneklerdir; farm/duvar/movement
  eşleşmeleri uygulama kanıtı/kapsamı ayrıca geliştirilmeden uygun sayılmaz.
- Sıradaki iş: yeni gerçek kayıt varsa eylem kapsamını ve train/val/test
  oturumlarını denetle; ardından 2B'de ayrı BC eğiticisini kur. Veri yoksa
  fixture ile ön eğitim yapma veya otomatik RL'yi BC eğitilmiş diye sunma.
  Model ağırlıkları değiştirilmedi, GitHub yayımlanmadı.


### 2026-11-05 — Ortak entity/GRU mimarisi

`training/ENTITY-ARCHITECTURE.md`: ortak 587.314 parametreli PyTorch ağı,
faction embedding, iki attention katmanı, GRU, ortak taktik/harcama skorlayıcı.
Ayrı GPU ortamı ve BC dizi eğiticisi uygulandı. Eski ağlar dönüştürülmedi veya
etkin checkpointler üzerine yazılmadı. Normal maç/arena/insan pre-dispatch
özetlerinde artık sürümlü, fog-filtered entity listesi var.

Kanıt: `entity-architecture-verification.json`, 8 kısa kod kontrolü ve tek
middle/human-log 6 saniye PASS; 3 native görüntü x 62 nesne CUDA'da kodlandı.
Görünür/gizli düşman ayrımı korundu. Kısa ölçüm CPU ~2,0 ms, GPU ~4,4 ms;
GPU çıkarımı hızlandırdı denmez. BC veri hazırlığı kontrolünde uygun güncel
insan dizisi bulunmadı; eğitim, aktivasyon ve oyun gücü kanıtı yok.

Sıradaki iş: gerçek güncel entity gösterimleri toplamak/kapsamasını ölçmek,
ayrı BC adayını eğitip ayrılmış veriyle değerlendirmek. Ardından recurrent
canlı servis, arena dizi rollout/RL ve güvenli aktivasyon adaptörleri.
Otomatik eğitim ve oyun bu aşamada eski NumPy checkpointlerini kullanıyor.


### 2026-11-05 — Sabit native rakip ve checkpoint öğrenme eğrisi

`training/BENCHMARK.md`: her checkpoint için sabit 200 maç planı,
yerli Brutal AI, normal başlangıç, dönüşümlü takım/konum, yedi faction rosterı.
Katalog/motor/kaynak/NPZ SHA sabit; aynı koşullarda yeniden devam edilebilir.
Her eğitim checkpointi yalnız değerlendirme kuyruğuna kaydedilir; uzun
maç otomatik başlamaz. Gelir, gözlenen gerçek tamamlanma zamanları, terminal
kazanç/kayıp, yarım/hatalı maç ve yaklaşık Wilson aralığı CSV/JSON/HTML olur.

Kanıt: 4 kod kontrolü; ilgili 6 saniye opening/baseline kontrolünde yeni
hatalar düzeltilip tekrarlandı. Son smoke: benchmark-metrics-check-v3;
150 sensör satırı, %100 kısa pencere kapsamı, 3 model/3 native, gerçek gelir
ve farm tamamlanması; kazanma oranı null. Uzun ölçüm başlamadı, güçlenme
kanıtı yok. Etkin NPZ'ler değişmedi. Yeni PyTorch ağ henüz canlıya bağlı
değil; onun ölçümü, eğitilmiş canlı arayüz tamamlandıktan sonra alınmalı.

Sıradaki ölçüm: kullanıcı uzun deneyi başlatmak istediğinde benchmark-v1
planını seçilen sayıda çalıştır; önce tamamlanma/hata kapsamını, sonra
aynı tohum ve rosterdaki checkpoint sonuçlarını incele. BC veri/kapsama ve
canlı recurrent geçiş işleri açık kalıyor.


### 2026-11-06 — Critic denetimi ve recurrent PPO+GAE

Denetim: eski NumPy eğitiminde öğrenilen critic/GAE yok; norm clipping ve KL
koruması PPO ratio clipping değildir. Yeni value başı BC'de eğitilmiyordu.
`service/recurrent_ppo.py` ayrı on-policy collector, GAE, joint policy clipping,
value loss/clipping, entropy, recurrent minibatch prefix replay ve model+Adam
KL/sayısal geri almasını ekler. `training/PPO-GAE.md` varsayımları açıklar.

Kanıt: 9 kısa CPU/CUDA sayısal kontrolü; actor/critic ikisi de fixture adımında
güncelleniyor, terminal/truncation bootstrap ve rollback kontrolü geçiyor.
Gerçek oynanış öğrenildi demek değildir. Eski ağ/başlatıcı/ödül korunur; yeni
oyun veya uzun eğitim başlatılmadı. Sıradaki iş hâlâ güncel gerçek BC verisini
ve değerlendirmeyi tamamlamak, ardından gerçek recurrent on-policy rollout,
ödül/terminal eşleştirmesi, ayrı PPO checkpoint/optimizer ve canlı bağlantıdır.

Yeni algoritma kaynakları sonrası ölçüm kaynak hashleri için bekleyen (henüz
çalıştırılmamış) plan benchmark-v2 olarak yenilendi; runtime işaretçisi ona
geçti. Önceki plan ve tüm smoke kanıtları korundu, uzun maç çalıştırılmadı.


### 2026-11-06 — İzole headless CLI ve paralel maçlar

Ön inceleme `headless/HEADLESS-ANALYSIS.md`, kullanım/ölçüm `headless/README.md`.
Yeni run_match.py + arena/simulation_match.gd aynı 0.2 saniyelik native adımı
korur; time-scale yalnız duvar zamanı beklemesini değiştirir. Özel PCK/runtime,
Release init/ready izolasyonu, native gelir/kayıp/öldürme, otomatik JSON ve
hata/timeout süreç temizliği vardır. run_matches.py ayrı Python/oyun süreçleriyle
N maçı çalıştırır. Normal oyun dosyaları/EXE/checkpointler değiştirilmedi.

Kullanıcı açıkça 180 saniyelik karşılaştırma istedi; varsayılan 6 saniye kuralının
bu işe özel istisnası olarak ölçüldü. Son 3v3 çift: pencereli 1x 190.46 s toplam
(180.05 s simülasyon çalışma zamanı), headless hedef10x 31.78 s toplam (24.51 s
simülasyon çalışma zamanı); 900 logic hash/istatistik eşit. Tek çift, tümplatform
ve uzun maç kanıtı değildir. İki paralel native + iki eşzamanlı model örneği,
modelde 1x/10x 30 kare eşitliği, geçersiz harita ve timeout exit1, 5 kod kontrolü
geçti. Gerçek victory ile erken çıkış oluşmadı, bu kısım canlı sonuçla doğrulanmadı.
Kanıt `AI-Test-Sahasi/headless-cli/verification.json`; özel çıktılar commit edilmedi.

CLI şu an native veya mevcut NumPy modelini sürer; yeni PyTorch/PPO canlı
collector ve eğitim/aktivasyon geçişi hâlâ açık. Bu altyapı kendiliğinden RL
veya BC eğitimi başlaması demek değildir. Yeni ölçüm kaynakları sonrası
bekleyen benchmark seti güncel hashlerle ayrıca yenilenmelidir.

Yeni headless kaynağı sonrasında muhafazakâr kod-hash sabitlemesi için
çalıştırılmamış ölçüm planı benchmark-v3 olarak yenilendi; eski planlar korunur.
Bu yalnız değerlendirme kuyruğunu günceller, 200 maç başlatmaz.


### 2026-11-06 — Başsız mod otomatik eğitim EXE'sine bağlandı

Aynı AI-Otomatik-Egitim.exe yeniden derlendi; supervisor her turda başsız sabit
adım ve 10x hedef hız seçer. Süre menüsü oyun dakikasıdır. Eğitim verisinin
şeması, örnekleme olasılıkları, native receipts, action-credit-v3 ve faction
bankaları korunur; bağımsız greedy CLI kaydı eğitim diye sunulmaz. Her bölümün
runtime/PCK/logu özeldir; HTTP yanıtı boyunca logic ilerlemez. Eski yarım
karşılaştırma özgün mod/süreyle devam eder; doğrulama bench kuyruğuna girmez.

Kanıt: 3 kod kontrolü ve aynı EXE --verify ile tek middle/pressure 6 oyun saniyesi
(30 kare), 3 kabul edilen öğrenci niyeti, taktik/üretim/ödül kayıtları, sıfır
script hatası ve Job temizliği. Etkin ağırlıklar değişmedi; olgunlaşmamış kısa
ödülden öğrenme başarısı çıkarılmaz. Yeni PyTorch/PPO hâlâ ayrıca bağlanmalı.

### 2026-11-07 — Model servis aktarımı ve kapasite

Kalıcı polled HTTP/1.1, tek katmanlı JSON, istek ömürlü ortak özellik önbelleği
ve sırası korunan aynı-kare toplu endpoint eklendi. Karar kadansı5 değişmedi;
mevcut zamanlayıcı bir bot seçtiğinden gerçek saha paketleri boyut1 kaldı.
44 gerçek180 s koşuda180 seçim çifti/kare ve son native hash eşit;180 kayıt/
16824 özellik satırı/skor ve seeded sample seçimleri cache açık/kapalı eşit.
İki öğeli gerçek HTTP denetimi ayrı protokol fixture'ıdır, native toplu oyun değildir.

Aynı gün başlangıç32.91 s → son26.36 s; toplam38.20 s. Son1/4/8 örnek
gruplarından94.4/248.4/344.6 bölüm/saat hesaplandı; tam maç veya1 saatlik
dayanıklılık kanıtı değil. Ağırlık güncellenmedi. Ayrıntı ve tekrar komutu:
INFERENCE-TRANSPORT.md; özel kanıt AI-Test-Sahasi/ipc-optimization-verification.json.
Sıradaki ölçüm iyileştirmesi native üretim adayı/uygulama maliyetidir; farklı
tohumlar ve stochastic PPO collector determinismi ayrıca doğrulanmalıdır.


### 2026-11-07 — Gerçek simülasyon için Gymnasium sınırı

OpenBFME-v0 reset/step/close arayüzü eklendi; bir ajanın native gözlem/yasal
adaylarından EntityCodec sabit Dict ve64/65 maskeli iki baş üretilir. Dünya
Python yanıtı boyunca sabit kalır,5 s native adım aralığı korunur. Gerçek
final gözlem, terminated ve süre sınırı truncation ayrıdır; yeni sparse
terminal ±1 ödül açıkça ayrı şemadır. Action-credit-v3 otomatik eğitimi veya
PyTorch/PPO collector/aktivasyon yolu bu arayüze geçirilmedi.

Tek gerçek6 s doğal başlangıç: kare1→26→31, iki bekle/bekle eylemi,
truncated=true, ödül0 ve gerçek son gözlem.6 kod kontrolü/sentetik Gym checker
ve5 mevcut runner kontrolü geçti. Çoklu Gym/gerçek victory/RL kazanımı
ölçülmedi. Ayrıntı ../GYMNASIUM.md; özel kanıt
AI-Test-Sahasi/gymnasium-interface-verification.json. Yeni harness hash'i için
çalıştırılmamış sabit benchmark planı v7 olarak yenilendi;200 maç başlatılmadı.
Sıradaki collector çalışması gerçek joint rollout/probability/value ve final
bootstrap kayıtlarını bağlamalı; bu adaptör tek başına PPO eğitimi değildir.


### 2026-11-07 — Gym potansiyel şekillendirme

Gym-native±1 korunarak ayrı gym-potential-v1 eklendi: gelir/STRUCTURE/temel
ordu maliyeti farkı, düşman kişi ortalaması; gamma*Phi_yeni−Phi_eski. Gerçek
terminal potansiyeli0; truncated ek clip(Phi_final,-1,1). Privileged native
sayaç sadece ödül/RPC yan alanı/log; EntityCodec/gözlem/adaya girmiyor.14 kod
kontrolü ve5×6 s gerçek3v3: toplam[-.0164,.0034], tekrar seedde30 native hash,
eylem ve ödül aynı. Erken pencerede asker yok/gelir farkı yok; uzun maç
ölçek testi yapılmadı. Action-credit-v3 otomatik eğitim/PPO aktarımı değil.
Ayrıntı ../GYM-DENSE-REWARD.md. Sabit benchmark-v8 yalnız200 maç planı olarak
yenilendi; maç başlatılmadı. Etkin ağırlıklar aynı.


### 2026-11-07 — Kullanıcı başlatmalı basit ekonomi PPO deneyi

Kullanıcı ayrı stock MaskablePPO deneyini seçti; oyundaki GRU/NPZ aynı.
180 s Easy Men karşısı, Dwarf ajan, konum0/5. train_economy.py varsayılan
200k/8env; random_economy.py aynı5 sabit eval tohumu/CSV kullanır.20k
aralıklarında güncelleme sonrası maskeli eval, TensorBoard ve checkpoint var.
Yalnız izinli120 s sınırlı smoke:53.92 s,256 native geçiş,1 PPO epoch.
4 kod kontrolü geçti; tam eğitim/gerçek uzun baseline/eval çalıştırılmadı.
Ayırt edilmiş deney ZIP’i otomatik aktive edilmez. Basit codec sargısı
mevcut385/383 girdilerini49920 float32’ye doldurur; ortak GRU eğitimi değildir.
Ayrıntı ECONOMY-TRAINING.md; benchmark-v9 sadece taze200 maç planıdır.
