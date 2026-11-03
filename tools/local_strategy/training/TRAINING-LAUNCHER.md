# Tek tıkla sürekli eğitim

Oyun klasöründeki **AI-Otomatik-Egitim.exe** açıldığında tur süresini
**3 / 5 / 15 / 30 dakika** olarak seçip **Başlat** düğmesine bas.
Son seçilen süre sonraki açılış için hatırlanır; ilk seçim 3 dakikadır.
Bu bilgisayardaki Python ve oyun dosyalarını kullanır; exe oyun klasöründe
kalmalıdır. Yeni bir kurulum gerekmez.

- Her tur seçilen gerçek süre kadar görüntüsüz bir 3v3 senaryodur; harita yüklemesi ek süre alır.
- Başlangıç, orta, geç oyun ve farklı baskı durumları sırayla kullanılır.
- Her turda yeni tohum; her beş turda bir iki ek kısa karşılaştırma koşusu vardır.
- Karşılaştırma koşuları da seçilen tur süresini kullanır; bu turlar toplamda üç koşu içerir.
- Taktik ve komut ağları, hesaplanan gerçek takım ödülüyle aday olarak güncellenir.
- Son tamamlanmış checkpoint çifti ve sonraki tohum otomatik kaydedilir.
- **Durdur** veya pencereyi kapatma yalnız bu başlatıcının süreç ağacını kapatır.
  O sıradaki eksik tur bırakılır; tamamlanmış turlar korunur. Sonraki açılışta
  kayıt üzerinden devam edilir. Tamamlanmış ama durum kaydına henüz yazılamamış
  son tur da yeniden açılışta doğrulanıp kurtarılır.

Başlatıcı durdurulana kadar çalışır. Yeni adayın mutlaka güçlendiği varsayılmaz;
tek eşleştirilmiş değerlendirme de rekabet gücü kanıtı değildir. **Tamamlanan
eğitimin doğrulanmış taktik/komut çifti otomatik olarak oyun paketine aktarılır.**
`AI-Yeni-Model.exe` sonraki açılışta bu sürümü kullanır; açık maç aynı modelle sürer.
Yarım/bozuk kayıt aktarılmaz; önceki ayar `ai-service/runtime.previous.json`
ve değişmez modeller `ai-service/trained-models/` altında korunur.
Bu hâlâ hazırlanmış kısa senaryolarda
eğitimdir; tam maç galibiyetine göre tamamlanmış bir eğitim sistemi değildir.

## Kayıtlar

- `AI-Egitim/otomatik-dongu/launcher-state.json`: devam noktası, tur, tohum, son ödül.
- Aynı klasörde `auto-.../`: her turun raporu, deneyimi ve iki aday ağırlığı.
- `launcher-session.log`: hata ayrıntıları ve eğitim çıktısı.
- Penceredeki **Kayıtları aç** bu klasörü açar.

Başlatıcı tek pencereyle sınırlıdır. Windows Job Object ve başlangıç kapısı,
sunucu/oyun alt süreçlerinin başlatıcıya ait olmasını sağlar. Durdurma işlemi
başka açık oyunlara veya Python süreçlerine dokunmaz.

## Derleme ve kısa doğrulama

Kaynak `TrainingLauncher.cs`, arka plan döngüsü `training_supervisor.py`.
`build_training_launcher.cmd` Windows'un mevcut .NET Framework derleyicisiyle
exe'yi üretir; indirme veya üçüncü taraf paketleme aracı kullanılmaz.

`AI-Otomatik-Egitim.exe --verify` arayüzü gizli doğrulama kipinde açar; tek
orta/baskı senaryosunu 6 saniye çalıştırır, aday checkpoint ve süreç durdurma
mekanizmasını denetler. Sonuçlar `AI-Test-Sahasi/launcher-check/` altındadır.
Normal devam kaydını değiştirmez. `--render-only` yalnız arayüz görseli üretir;
oyun veya eğitim çalıştırmaz.
`--verify` ayrıca oyun modeline aktarım yapmaz.
