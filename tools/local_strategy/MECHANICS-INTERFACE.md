# Mekanik gözlem ve eylem arayüzü

`rts-mechanics-v1`, normal maç ve otomatik eğitimde aynı sayısal girdileri
kullanır. Bu bir eğitim verisi/eylem arayüzüdür; mevcut modelin oyunu öğrendiği
veya daha iyi oynadığı anlamına gelmez.

## Gözlem

`team_ai/mechanics_observation.gd` yalnız kendi, takımın paylaştığı ve sisle
filtrelenmiş düşman nesnelerini kullanır. Ekonomi sayısı ve gerçek kaynak
alanı payı, temel gelir hızı, üretim kuyrukları, boş fabrikalar, inşaatçılar,
yarım binalar, komuta doluluğu, ordunun maliyet/can değeri, kahraman ve üs
sağlığı, görülen sınıf dağılımı, üs/müttefik çevresindeki tehdit, oyun zamanı
ve büyü puanları sayısal girdilerdir. İnşaatçılar saldırı ordusuna katılmaz.

Temel gelir göstergesi motorun gelir miktarı, üretim aralığı ve kaynak alanı
payından hesaplanır. Oyuncu bonusları ve bina sayısına bağlı gelir etkileri
dahil gerçekleşmiş gelir değildir; gerçekleşen ödemeler mevcut ödül
sensöründen ayrıca alınır. Görünmeyen düşman ekonomisi sorgulanmaz.

## Eylem

- Motor her bina/inşaatçı için sınırlı sayıda farklı konum sunar. Farm
  konumları oyuncunun yerleşim önizlemesindeki `claimableFraction` hesabını
  kullanır. Verim, temel gelir, yol mesafesi, komşu farm uzaklığı, devam eden
  farm inşaatıyla örtüşme, görülen tehdit, maliyet ve yapım süresi sunulur.
  Sabit yüzde 70 şartı veya ezber bir başlangıç sırası yoktur.
- İnşa eyleminin kimliği koordinatı içerir. Modelin seçtiği konum emir
  sırasında başka konumla değiştirilmez. Geçersizleşen seçenek reddedilir.
- Duvar arayüzü bir başlangıç hub'ı ve mevcut hub'dan bağlantılı uzatma
  olarak temsil edilir. Mevcut hub varken bağımsız yeni hub sunulmaz. Bu,
  bu sürümün tek duvar ağı kısıtıdır; oyunun genel bir yasağı değildir.
  Gerçek motor planı, maliyet, çarpışma, harita ve görünürlük kontrolleriyle
  8 yönde iki uzunluk denenir; uygulama normal duvar komutundan geçer.
  Kapı/yıkılan ağı yeniden bağlama gibi bütün duvar işlemleri kapsanmıyor.
- Karma ordu emirlerine ek olarak sınıf grubu saldırıları sunulur.
  Seçili ordunun değeri/canı, süvari oranı, hedefin sınıfı/canı/değeri,
  mesafe ve yerel kuvvet değerleri ağın girdileridir. Bunlar hangi hedefe
  saldırılacağını belirleyen sabit counter kuralları değildir.
- Üretim/komut seçenekleri maliyet, komuta ihtiyacı ve yapım süresini
  taşır. Eylemler sahiplik ve güncel motor koşullarıyla yeniden doğrulanır.

Konum araması ve seçenek bütçesi sınırlıdır; model haritadaki her noktayı
ve her olası birlik alt kümesini serbestçe seçmiyor. Mekanikler farklı
faction şablonlarından okunur; tüm faction eşleşmeleri bu kısa kontrolle
doğrulanmış sayılmaz.

## Öğrenme ve uyumluluk

`service/mechanics_features.py` sayısal şemayı tanımlar. Taktik ve harcama
ağlarına yeni kanallar sona eklenir. Eski giriş ağırlıkları ile yedi bağımsız
fraksiyon bankası korunur; yeni satırlar sıfırdan başlar. Bu geçiş modelin
yeni özelliklere henüz tepki vermediği anlamına gelir; anlamlı sonuçlarla
eğitim gerekir. Mevcut checkpoint dosyaları paket güncellemesinde ezilmez.

Arena aynı arayüzle seçenek ve sonuç kaydeder. Normal maçların yeni
seçenek kayıtları da `rts-mechanics-v1` olarak işaretlenir; tamamlanan
maçlar mevcut offline sonuç adımıyla eğitim döngüsüne girer. Eksik eski
özellik vektörleri yeni boyuta karşı eğitimde kullanılmaz. Oyun kapanınca
anında ağırlık güncellemesi yapılmaz; tamamlanan eğitim çifti bir sonraki
oyun açılışında etkinleşir.

Mevcut `action-credit-v1` gelir ve maliyet sonuçlarını ilişkilendirmeye
devam eder. Yeni duvar komutu için ayrı, kanıtlanmış bir savunma faydası
ölçümü eklenmedi; takım terminal sonucu kullanılabilir. Fixture emirleri
başarılı uzman kararı veya eğitim ödülü olarak etiketlenmez.

## Kısa doğrulama

Tek `middle / mechanics` durumu, 6 saniye, ayrı runtime ve `--no-activate`:

- Altı farklı farm konumu ve geçerli native kaynak payları.
- Başlangıç hub'ından 12 bağlı uzatma seçeneği.
- Gönderilen uzatmanın gerçekten beş yeni duvar nesnesi oluşturması.
- Farm seçeneğinin seçilen kimlik ve koordinatla gönderilmesi.
- Sıfır script hatası, 12 kabul edilmiş model kararı; iki ağın kayıt yolu.

Kanıt: `AI-Egitim/otomatik-dongu/20261104-031239-14008/train-000/arena/middle.json`.
23 ilgili Python kontrolü geçti. Altı saniyede yatırım sonuçları
olgunlaşmadığından bu koşu ağırlık geliştirmesi/rekabetçilik kanıtı değildir.
