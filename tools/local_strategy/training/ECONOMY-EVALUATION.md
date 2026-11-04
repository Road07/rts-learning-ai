# Ekonomi ve üretim değerlendirmesi

`economy-production-eval-v1` yeni ödül veya build order değildir. Modelin
kararlarını değiştirmeden ölçer. Tüm fraksiyonlar oyuncu/fraksiyon kimliğiyle
ayrı raporlanır; farklı ırkların sayıları tek başarı puanına toplanmaz.

## Ölçümler

- **Farm verimi:** Tamamlanmış kendi kaynak binalarının gerçek alan payı,
  bina-saniye ile ağırlıklandırılır. Yeni bir farm yalnız son örnekte
  tamamlandıysa henüz süre ağırlıklı ortalamaya girmez. Onaylanan farm
  emirlerinin seçilen konum verimi ayrıca raporlanır; inşa tamamlanmasıyla
  karıştırılmaz.
- **Gelir:** Motorun seri numaralı gerçek gelir ödemeleri kullanılır.
  İlk örnek öncesindeki ödemeler, para iadeleri, başlangıç parası ve
  yinelenen örnek/ödeme gelir sayılmaz. Eksik gelir geçmişi sıfır başarı
  değil, `null` olur. Gelir her zaman bina geliri demek değildir; motorun
  gelir kayıtlarına giren diğer kaynakları da kapsayabilir.
- **Üretim:** Tamamlanmış ve etkin fabrikaların kuyrukta iş geçirdiği
  süre oranı ve toplam boş fabrika-saniyesi ölçülür. Kuyruk kahraman veya
  araştırma da içerebilir; bu oran yalnız asker üretimi oranı değildir.
  Onaylanan asker üretim emirlerinin sayısı ve nominal maliyeti ayrı
  yazılır. Onaylanan emir, tamamlanmış asker/gerçekleşmiş harcama değildir.
- **Ordu:** İnşaatçı hariç görülen kendi hareketli nesnelerinin maliyet/can
  değeri başlangıç ve sonda karşılaştırılır. Bu net değişim çatışma,
  iyileşme, garrison/tünel ve transferlerden etkilenebilir. Brüt üretim
  veya kesin yatırım getirisi diye yorumlanmaz.
- **Bağlam:** Zamana göre ortalama para ve komuta kapasitesinin dolu
  kaldığı süre eklenir. Kaynak tutmak ya da boş fabrika otomatik hata veya
  ceza sayılmaz; strateji ve baskı durumuyla birlikte incelenmelidir.

Örnekler 5 logic frame/saniye ile ölçülür. 10 saniyeden uzun örnek boşluğu
doldurulmaz; zaman kapsamı ayrıca gösterilir. En az 120 saniye, %90 zaman
kapsamı ve tam gelir geçmişi olmadığında `sufficient_window=false` olur.
Bu eşiğin geçilmesi de modelin daha güçlü olduğunun kanıtı değildir.

## Otomatik eğitim

Her bölümde `economy-evaluation.json` ve `experience.json` içindeki
`economy_evaluation` üretilir. Tur özeti `report.json` içine eklenir.
Mevcut ödül/gradient hesapları bu ölçümlerden değiştirilmez.

Mevcut `--evaluate` akışı eski ve yeni model için aynı aşama, durum,
tohum, roster, süre ve sabit rakip ağırlıklarıyla iki ayrı ölçüm yapar.
`economy-comparison.json` oyuncu bazlı yeni-eksi-eski farklarını ve
checkpoint hashlerini yazar. Farklı roster veya zaman pencereleri
eşleşmiş sayılmaz. Devam edilen eğitimde karşılaştırma başlangıcı,
o turdan önceki devam checkpointidir; etkin oyun modelinin farklı bir
sürümüyle yanlışlıkla karıştırılmaz.

Eğitim başlatıcısı zaten her beşinci turda bu değerlendirmeyi çalıştırır;
bu değişiklik fazladan uzun kontrol başlatmaz. Bir çift, genel galibiyet
üstünlüğünü kanıtlamaz; otomatik kazanan seçilmez ve model etkinleştirme
kurallarına yeni bir performans kapısı eklenmez. Tek bir metrik yükseldi
diye diğer alanların da düzeldiği varsayılmaz.

## Normal maçlar

Yeni sensör alanları normal maçlara da eklenmiştir. Oyun kapandığında veya
yeni maç başladığında sunucu `AI-Yeni-Model/ai-service/logs/` altında
maça özel `*.economy.json` ve kolay erişim için
`AI-Yeni-Model/ai-service/latest-economy-evaluation.json` yazar.
Bu canlı rapor son sunucu isteğine kadar olan gözlem penceresidir;
tam maç/galibiyet etiketi değildir. Kesintiyle sunucu öldürülürse rapor
yazılamayabilir, ham gözlem logu yine ayrı dosyadadır.

Tamamlanan normal maç eğitim döngüsünde işlenirken kapanış örnekleri
ve doğrulanmış gönderim kayıtlarıyla ekonomi raporu yeniden hesaplanır;
`report.json` içindeki `normal_matches[].economy_evaluation` alanına girer.
Eski kayıtlar yeni sensör verilerini içermiyorsa `missing_telemetry` olur;
geçmiş verim veya kuyruk ölçüsü uydurulmaz. Farklı harita/rakiplerle oynanan
normal maçlar otomatik olarak eşleştirilmiş karşılaştırma sayılmaz.

## Doğrulama

21 ilgili Python kontrolü geçti. Tek 6 saniyelik `opening / baseline`
kontrolü altı bot için gerçek gelir, konum seçimi ve gözlem kapsamı
raporu üretti. Hızlandırılmış sahada yaklaşık 24 saniye oyun süresi
gözlendi; üretimin çoğu henüz olgunlaşmadığından güçlenme sonucu çıkmaz.
Kanıt: `AI-Egitim/otomatik-dongu/20261104-171659-20996/`.
Bu kontrolde iki ek karşılaştırma maçı çalıştırılmadı; eşleştirme/fark
hesaplama yolu birim kontrolleriyle doğrulandı.
