# Mevcut öğrenme denetimi — 4 Kasım 2026

Sonuç: geçmiş ağırlık güncellemeleri gerçek; etkin modelin yeni mekanik
kanallarını öğrendiği veya mevcut sürümün güçlendiği doğrulanmadı.

## Ağırlık kanıtı

Etkin çift `trained-models/043fbba5dbbcd14550a4/` içinden yüklendi.
Kaynak koşu `20261104-020740-13448`; bu koşu güncel karar bazlı kredi
sisteminden önceki takım ödülünü kullanmış.

Kendi başlangıç checkpointiyle karşılaştırıldığında hem taktik hem
harcama bankalarında Men, Elf ve Cüce parametreleri değişmiş (L2 farkı
bankabaşına yaklaşık 0.01). Diğer dört faction bankası bu son adımda
değişmemiş; bu, onların geçmişte hiç bilgi almadığı anlamına gelmez.

Yeni boyuta geçişte sona eklenen tüm mekanik giriş ağırlıkları iki ağın
yedi bankasında da sıfır. Eski girdiler sabitken yeni kanalların tamamını
değiştiren probda karar puanı farkı tüm bankalarda tam sıfır.
Dolayısıyla eklenen ayrıntıların doğrudan etkisi henüz öğrenilmemiş.
Örneğin farm verimi gibi bazı bilgiler eski kanallarda da bulunuyordu;
bu sonuç modelin bütün ekonomi bilgisinden yoksun olduğunu göstermez.

Sayısal kanıt: `ai-mod-source/learning-audit-weights.json`.

## Geçmiş deneyler

42 koşu raporu bulundu: 28 tamamlanmış, 9 başarısız, 1 geçersizleştirilmiş,
4 tamamlanma kaydı olmayan koşu. `running` kaydı süreç şu anda canlı
demek değildir. Güncelleme bayrağı taşıyan geçmiş turlar vardır.

Üç eski eşleştirilmiş karşılaştırmanın ödül farkları yaklaşık +0.772,
+0.495 ve +1.248. Bunlar önceki takım ödülü/arayüzüne aittir; yeni
mekanikler ve karar bazlı krediyle güçlenme kanıtı olarak kullanılamaz.
Galibiyet oranı veya genel rekabetçilik sonucu çıkarılmadı.

Yeni mekanik arayüzüyle tamamlanan son iki eğitim smoke koşusunda
güncelleme yok: `no_mature_observed_credit` veya tek seçenekli karar.
Kısa kontrolün tamamlanması yeni bilginin öğrenilmesi demek değil.

Normal kayıtlarda kapanış olayıyla eşleşen 50 eylemli bir tarihsel iz
bulundu; iki takımın da sonucu `ongoing`. Yeni ekonomi sensör alanları
yok. Yeni mekanikleri doğrulayan terminal normal maç örneği bulunamadı.

## Tek kısa saha kontrolü

`middle / pressure`, 6 saniye, `episode-mode=evaluate`, özel config:
12 öğrenci taktik kararı ve 12 harcama izi; 12 kabul edilen taktik karar;
sıfır script hatası. Sonuç kredisi sıfır olmayan bir karar kaydedildi.
Bu yalnız gözlem–emir–sonuç bağlantısının çalışabildiğinin kanıtıdır.
Deterministik değerlendirme izleri öğrenmeye verilmedi.

Kontrol model ağırlığı veya etkin runtime ayarını değiştirmedi; iki etkin
checkpoint hash'i doğrulandı. İlk başlatma özel config yol kodlamasında,
oyun başlamadan durdu; config düzeltilip aynı kısa durum çalıştırıldı.
Uzun maç veya ek karşılaştırma serisi çalıştırılmadı.

Kanıtlar: `AI-Test-Sahasi/learning-audit/validation.json`,
`AI-Test-Sahasi/learning-audit/episode-verified/experience.json`,
`AI-Test-Sahasi/learning-audit/episode-verified/arena/middle.json`.

## Sonraki anlamlı deney

Yeni arayüzle yeterince uzun, örneklemeli bir eğitim turu; sonra aynı
koşullarda eğitim öncesi/sonrası ayrı değerlendirme. Yeni kanalların
ağırlık ve çıktı etkisi, karar kredilerinin olgunlaşması, farm verimi,
gelir, üretim ve terminal sonuçlar birlikte incelenmeli. Tek bir pozitif
ödül/parametre değişimi başarı ilanı olmamalı. Bu denetimde eğitim
ödülü/eşikleri veya strateji kuralları değiştirilmedi.
