# Sabit yerleşik AI karşısında checkpoint ölçümü

`fixed-native-benchmark-v1` — 2026-11-05.

## Hazır durum

`AI-Egitim/benchmark-v4` her checkpoint için 200 maçlık, sabit bir plan içerir.
Henüz uzun maç başlatılmadı. Güncel oynanan NumPy checkpointi ilk kayıt olarak
alındı; yeni ortak PyTorch modelinin canlı servis/RL geçişi henüz bitmediği için
ona sahte sonuç verilmez. Normal maçtaki değişken rakipler bu sete katılmaz.

`runtime.json.benchmark_suite` üzerinden otomatik eğitimde her tur sonunda
kaydedilen taktik/üretim checkpoint çifti değişmez kopyayla sıraya eklenir.
Aynı içerik tekrar eklenmez. Bu işlem maç başlatmaz, ödül veya etkin ağırlık
seçimini değiştirmez. Hata varsa turun `benchmark_registration_error` alanına
kaydedilir; hata sessizce değerlendirilmiş sayılmaz.

## Sabit koşullar ve çalıştırma

- Lostriand, normal 1000 başlangıç parası, 3v3 Brutal, ring/custom hero kapalı.
- Bir takım yalnız model, diğer takım yalnız motorun yerleşik AI'ı. Sonraki
  maçta modelin tarafı değişir. Yedi faction için roster/tohum planı önceden
  sabittir; aynı checkpointler aynı maç indeksini aynı koşullarda oynar.
- Retail `skirmishaidata.ini` kullanılır; geliştirilmiş native strateji,
  ClassicOpening, ek %25 gelişmiş gelir/üretim çarpanı ve kısaltılmış faz
  süreleri benchmark moduna eklenmez. Modellerin normal maç ayarları değişmez.
- Hazır nesne/para yok; fixture CP düzeltmesi kapalı. Başlangıç/oyun kuralları,
  motor paketi, karar kaynak hashleri, katalog ve checkpointler sabitlenir.
  Kod/motor/katalog değişirse aynı koşullar altında sayılmaz, yeni set gerekir.
- Native köprüde yerel model yetkisi EnhancedCounterProduction bayrağından
  ayrıldı. Yalnız kontrollü oyuncunun model seçeneklerine izin verir; diğer
  takımın native ayarını açmaz. Ağlı/replay/kayıttan yükleme sınırları korunur.
- Her maç en fazla 9000 simülasyon karesi (30 oyun dakikası) sürer. Sonuç
  oluşursa erken biter; süre dolarsa `truncated`. Duvar saati güvenlik sınırı
  aşılırsa hata kanıtı saklanır. Başarısız maç kazanma oranına gizlice katılmaz.
- Değerlendirme verisi eğitime/ödüle geri beslenmez. Bağlı otomatik eğitim
  CLI'sı bu planın tohumlarıyla eğitim başlatmayı reddeder. Bu koruma önceki
  verilerin geçmişte bu tohumları hiç içermediğini kanıtlamaz.

Uzun koşular yalnız kullanıcı istediğinde açıkça başlatılır. Varsayılan `run`
en fazla bir maç çalıştırır; yarıda kalmış bölüm sonraki çağrıda arşivlenir,
tamamlanmış sonuç atlanır. Kayıtlı hata otomatik tekrar edilmez. Eğitim ile
aynı test sahası kilidi kullanılır, aynı anda sahayı değiştiremezler.

```powershell
# Bir sonraki tek değerlendirme maçını çalıştırır; hızlı kontrol değildir.
python ai-mod-source/tools/local_strategy/training/benchmark.py run --suite AI-Egitim/benchmark-v4 --max-games 1
# Daha sonra açıkça seçilen sayıda maç:
python ai-mod-source/tools/local_strategy/training/benchmark.py run --suite AI-Egitim/benchmark-v4 --max-games 200
# Yalnız raporu yenile; oyun açmaz.
python ai-mod-source/tools/local_strategy/training/benchmark.py summary --suite AI-Egitim/benchmark-v4
```

Projede kullanılan Python ile çalıştırılmalı. İlk komut bile tam maç açar;
kurulum sırasında bu komutların uzun sürümü çalıştırılmadı.

## Ölçümler ve yorum

`games/<checkpoint>/<maç>/` ham logları, ayrı runtime, maç raporu ve `metrics.json`
içerir. Checkpoint kimliği taktik+üretim SHA çiftidir; etiket ve varsa gerçek
training_step ayrıca saklanır. HTML yatay ekseni kayıt sırasıdır, bilinmeyen
öğrenme adımı uydurulmaz.

- Kazanma/kaybetme yalnız native alliance-victory olayından, takım başına tek
  sonuçtur. Bir 3v3 galibiyeti üç bağımsız örnek değildir. Süre dolması beraberlik
  değildir; belirsiz terminal ve motor/servis hatası ayrı sayılır.
- Biten maçlar için kazanma oranı ve yaklaşık %95 Wilson aralığı; ayrıca
  denenen/planlanan/bekleyen ve tamamlanma oranı. Yalnız biten maçları gösterip
  yarım kalanları saklamaz. Eksik oran `null`, sıfır değildir.
- `EconomyEvaluation` yeniden kullanılır: gerçek native gelir ödemeleri,
  ortalama dakika başı gelir ve oyun dakikası kovaları. İlk/son kısmi dakika
  açıkça işaretlenir. Para iadesi/net kasa farkı gelir değildir; eksik ödeme
  geçmişi `null`. 120 saniye ve %90 kapsam yoksa toplu yeterli gelir örneğine
  katılmaz. Fraksiyonlar ayrı; ortalamalar ve örnek sayıları birlikte yazılır.
- İlk üç farm/fabrika/ordu/hero için ilk tamamlanmış görülme zamanları; şablon,
  nesne ve gözlemler arasındaki zaman aralığı da saklanır. Emir kabulü bina veya
  asker tamamlandı sayılmaz. Başlangıç nesneleri çıkarılır. Ölçüm yaklaşık bir
  saniyelik aralıklıdır; görünüş/transfer/tünelden çıkış asker olayını etkileyebilir,
  bu yüzden asker görünüşü her durumda native üretim fişi diye sunulmaz.
- Olay görülmediyse sıfır saniyede yapılmış sayılmaz. Milestone özetleri yalnız
  görülen olayların dağılımıdır; farklı maç uzunluğu/eksik tamamlanma oranları
  doğrudan daha güçlü oyun kanıtı sayılmaz.

`learning-curve.json`, `learning-curve.csv`, `faction-metrics.csv` ve bağımsız
`learning-curve.html` her sonuçtan sonra yenilenir. HTML kazanma eğrisi ve sonuç
kapsamını gösterir; gelir ve build zamanlarının ayrıntıları CSV/JSON'dadır.
Checkpointler arasında aynı tamamlanan tohum kapsamı ve fraksiyon/konum
sonuçları ayrıca incelenmeden bir eğri yükselişi değişikliğin nedensel etkisi
sayılmaz. Otomatik kazanan/aktivasyon kapısı eklenmedi.

## Kısa doğrulama

4 ilgili kod kontrolü geçti: native sonuç/yarım maç, gerçek gelir ve tamamlanma
aralığı, maç başına payda, sabit roster/checkpoint ve boş rapor. İlgili tek
6 saniyelik opening/baseline durumu, görülen yeni hataları düzeltmek için
tekrarlandı. İlk native-yetki engeli ve sonraki kayıt/yerel bağlantı hataları
ayrı smoke klasörlerinde saklandı; gerçek 200 maçlık sete dahil edilmedi.

Son kanıt: `AI-Test-Sahasi/benchmark-metrics-check-v3`,
`ai-mod-source/benchmark-verification.json`. 150 kendi-oyuncu sensör satırı,
altı oyuncu için %100 örnek zaman kapsamı, üç model/üç native yetkisi, gerçek
gelir ve tamamlanmış ilk farmlar görüldü; sıfır script/servis hatası. Sonuç
truncated, bitmiş maç yok; kazanma oranı null. Simülasyon yaklaşık 24 saniye,
uzun maç veya güçlenme kanıtı değildir. Aktif checkpoint dosyaları değişmedi.
