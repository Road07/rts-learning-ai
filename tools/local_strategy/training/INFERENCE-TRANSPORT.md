# Model iletişimi ve paralel kapasite — 2026-11-07

## Kapsam

Gerçek automatic_training.run_episode/evaluate yolu, altı model botu, middle/pressure hazır sahası, Lostriand, seed 271026, 180 simülasyon saniyesi/900 native kare, hedef10x. Mevcut NumPy faction-bank taktik/üretim ağı kullanıldı. Karar sıklığı5 ve fast-poll kapalı kaldı. Eğitim, ağırlık güncelleme veya aktivasyon yapılmadı. Bu hazırlanan durum tam maç açılışı veya PPO eğitimi değildir.

## İnceleme ve aşamalı ölçüm

Eski GDScript HTTPRequest her POST için tekrar bağlantı kuruyordu; Python BaseHTTPRequestHandler varsayılan HTTP/1.0 idi. İstek JSON içindeki messages.content alanında ikinci bir JSON metni taşıyordu; cevapta da message.content tekrar JSON idi. Yeni HTTPClient ana sahne threadinde nonblocking poll edilir, HTTP/1.1 bağlantısını tekrar kullanır; sunucu TCP_NODELAY kullanır. Eski endpoint/mesaj biçimi uyumluluk için korunur. Belirsiz gönderilmiş POST otomatik tekrarlanmaz. İptal/çıkış soketi kapatır.

| Aşama | Simülasyon gerçek s | Toplam bölüm s | RPC bekleme s | Python s | Bağlantı |
|---|---:|---:|---:|---:|---:|
| Başlangıç | 32.91 | 48.97 | 8.09 | 4.64 | 180 |
| Kalıcı/polled HTTP + TCP_NODELAY | 29.08 | 42.37 | 5.22 | 4.01 | 1 |
| Tek katmanlı kompakt JSON | 29.66 | 42.20 | 5.24 | 4.02 | 1 |
| İstek ömürlü özellik önbelleği | 28.12 | 40.93 | 3.76 | 2.77 | 1 |
| Toplu endpoint (paket boyutu 1) | 28.27 | 40.94 | 3.93 | 2.74 | 1 |
| Oyun tarafı toplu dispatch (boyut 1) | 28.95 | 41.20 | 4.30 | 2.66 | 1 |
| Kullanılmayan JSON dönüşümlerini kaldırma | 26.36 | 38.20 | 3.54 | 2.58 | 1 |
| Etkin yeniden paketleme sonrası | 26.26 | 38.14 | 3.54 | 2.59 | 1 |

Her satır tek koşudur; küçük farklar kazanım kanıtı değildir. Kompakt biçim tek başına toplam süreyi düşürmedi; sonraki inceleme kullanılmayan eski zarfın da hesaplandığını buldu. Son satırda bu dönüşüm ve toplu yoldaki ikinci serileştirme kaldırıldı. Aynı gün başlangıç32.91→son26.36 s, yaklaşık%20 süre azalması/6.83x simülasyon hızı. Önceki günün38.64 s sonucunu sabit başlangıç kabul etmiyoruz.

## Karar başına süre ve veri boyutu

Aynı eski motor paketiyle son (clean) koşu180 karar: seçenek/gözlem/hazırlık6.834 s (37.97 ms/karar); bunun içindeki serileştirme0.568 s (3.16 ms). Üretim seçenekleri4.171 s, taktik seçenekler0.566 s. Hazırlık log yazımını da içerir. RPC3.539 s (19.66 ms, p95 23.13 ms); Python işlemleri2.584 s (14.35 ms) bunun içindedir. Cevabı parse etme, emri yeniden doğrulama ve uygulama4.154 s (23.08 ms). Native advance9.370 s. JSON parse/kurallar/özellik çıkarımı/policy+trace parçaları özel JSON raporundadır.

RPC−Python ≈0.955 s artık süre; yalnız ağ süresi değildir: localhost aktarımı, client poll, callback planlama ve toplu yanıt paketleme içerir. Python toplamını RPC üzerine yeniden eklemeyin. Saf sinir ağı matris hesabı ayrı izole edilmedi; policy_and_trace kodlama ve loglamayı içerir. Önceki15.62−5.16 s farkı da yalnız iletişim olarak kanıtlanmış değildi; yeni başlangıçta RPC8.09/Python4.64 s ölçüldü.

Eski ortalama istek111464 bayt/cevap403 bayt; kompakt istek99871 bayt/cevap329 bayt. Son tek öğeli batch isteği99874 bayt. Son cevap329 bayt model nesnesidir; batch zarfıyla gerçek cevap ortalaması369 bayttır (inference_batch.response_bytes). Baytlar UTF-8 gövde boyutlarıdır; HTTP/TCP başlıkları dahil değildir. JSON float gösterimi kayıpsız kaldı; ikili biçim/quantization veya neural girdi azaltımı yoktur.

## Aynı karede toplu karar ve hesap tekrarları

request_same_frame hazır botların kendi fog-filtered gözlemlerini taşır; sonuçlar giriş sırasında kendi epoch/player/frame/pending bağlamıyla uygulanır. Endpoint8 farklı oyuncuya kadar aynı maç/kareyi kabul eder; karışık kare/maç veya tekrar eden oyuncu reddedilir. Python sıralı mikro-toplu değerlendirme yapar: banka/RNG/token sırası korunur, farklı fraksiyon matrisleri tensor olarak birleştirilmez.

Mevcut zamanlayıcı beş karede bir yalnız bir botu seçer. Dolayısıyla toplu yolu kullanan gerçek koşularda batch boyutu1 idi; çok botlu paketle canlı oyun hız kazancı iddia edilmiyor. Aynı kareye bot çekmek veya sonraki kararları bekletmek davranış kısıtını bozardı. İki öğeli gerçek HTTP sunucu denetimi ayrı fixture gözlemlerini sentetik ortak karede kullandı; ayrı isteklerle yanıtlar/tokenlar birebir aynıydı. Oyun süreci bu protokol denetiminde mock edildi; native çok-botlu aynı-kare davranış testi değildir.

spend_features her aday için aynı legacy tabanı yeniden float32→liste dönüştürüyordu; mechanics state ve public-rule context de tekrar hesaplanıyordu. ContextVar ile yalnız bir karar isteği boyunca değişmez sonuçlar saklanır, çağırana ayrı liste verilir, finally ile temizlenir. Botlar/kareler arası cache, aday eleme, ağırlık değişimi yoktur. Gerçek180 fixture gözleminde16824 özellik satırı ve ağ skorları bit düzeyinde eşit; sabit tohumlu örnekleme seçimleri de eşit çıktı.

## Paralel kapasite — nihai aynı kod

| Paralel örnek | Tamamlanan bölüm | Grup gerçek s | Hesaplanan bölüm/saat |
|---|---:|---:|---:|
| 1 | 1 | 38.14 | 94.4 |
| 4 | 4 | 57.97 | 248.4 |
| 8 | 8 | 83.57 | 344.6 |

Süreye hazırlama/yükleme/raporlama dahildir. Başarısız örnek0; yalnız tamamlanan180 s bölümleri sayıldı. Bu bir saatlik dayanıklılık testi değildir; ölçülen tek grup üzerinden saatlik kapasite tahminidir. Gerçek galibiyetle biten tam maç/saat sayısı ölçülmedi. Her örneğin portu, servis kilidi, runtime/PCK, config ve çıktısı ayrıdır. Paralel sayıyı otomatik eğitimin varsayılanına çevirmedik; burada ölçüm aracının seçeneğidir.

Motor aktarımı güncelleyicinin tek6 s mechanics kontrolüyle yapıldı (23 model kararı,0 script/servis hatası). Güncelleyici DLL’i yeniden derlediği için binary hash değişti; kaynak entegrasyon commit’i aynı kaldı. Etkin yeni paket için ayrıca1/4/8 grupları tekrarlandı ve yukarıdaki kapasite tablosu bu son grupları kullanır. Eski/yeni bütün44 koşunun karar dizisi ve final hash eşittir.

## Eşitlik, kanıtlar ve kullanım

44 gerçek koşunun her birinde180 taktik+üretim seçim kimliği/oyuncu/kare dizisi ve final native hash3660350799 eşleşti. Her yeni koşuda yalnız final hash alındı; tüm ara karelerin eşitliğini yeniden ölçmüş gibi sunmuyoruz. Önceki1x/10x900-kare doğrulaması ayrı kalır. Diğer tohumlar/haritalar, stokastik canlı RL, uzun maç ve etkileşimli duvar saati determinismi bu ölçümle kanıtlanmaz. Ödüller/gösterim etiketi veya model gücü hakkında sonuç çıkarılmaz.

Özel kanıt: AI-Test-Sahasi/ipc-optimization-verification.json; her aşamanın summary.json, ham servis/model telemetrisi ve son hash dosyası. Özellik denetimi ipc-feature-audit.json, gerçek HTTP batch denetimi ipc-batch-host-audit/result.json. Özel loglar/fixture dosyaları eğitim veya yayına dahil edilmez.

```powershell
python ai-mod-source/tools/local_strategy/training/profile_model_speed.py --output AI-Test-Sahasi/new-ipc-measure --seconds 180 --speeds 10 --hash-stride 900 --persistent-http --compact-wire --feature-cache --batch-wire --parallel 4
```

--parallel1/4/8; yeni çıktı klasörü şarttır. Bu profil aracında aktarım bayraklarını vermemek eski yolu referans olarak zorlar; güncel ayarlar için dört bayrağı da ekleyin. Komut açıkça uzun ölçüm başlatır; sıradan geliştirme kontrolleri6 saniyedir. Oyun/eğitim başlatıcılarının adları korunur. runtime.json içindeki persistent_http/compact_wire/feature_cache/batch_wire ayarları geri dönüş için ayrı ayrı kapatılabilir; canlı maçın ağları değişmez.

Birincil kaynaklar: [Godot HTTPRequest kaynak kodu](https://raw.githubusercontent.com/godotengine/godot/4.7-stable/scene/main/http_request.cpp), [HTTPClient bağlantı tekrar kullanımı](https://docs.godotengine.org/en/stable/classes/class_httpclient.html). Bağlantı sayıları ayrıca gerçek peer portlarından doğrulandı.
