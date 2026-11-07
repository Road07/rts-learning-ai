# OpenBFME motorunu otomatik takip etme

Model başlatıcısı aynı konumdaki AI-Yeni-Model.exe olarak kalır. Model
ağırlıklarının eğitimi ve OpenBFME motorunun güncellenmesi ayrı işlemlerdir.

## İşleyiş

`engine_update.py`, resmî başlatıcının AppData/Roaming/OpenBFMELauncher
versions dizinindeki kurulmuş sürümleri izler. Başlatıcıdaki açık sürüm
seçimini, yoksa en yeni kurulu sürümü okur. Kendisi oyun güncellemesi
indirmez; kurulu sürümün manifest/VERSION kimliğini ve dosya boyutu/hashlerini
doğrular. Manifest imza doğrulamasını yapan resmî kurucunun yerine geçmez.

Oyun veya sürekli eğitim başlatıldığında düşük öncelikli bir işçi, ayrı
yerel AI motor fork'una kurulu sürümün tam kaynak revizyonunu getirir.
Yerel AI değişikliklerini son alınan içerikle üç yönlü birleştirir;
upstream değişikliklerini fork'a birleştirip derler. Normal arka plan
derlemesi iki iş parçacığı kullanır; geliştirme derlemesi varsayılanı altıdır.
Yeni Godot binding revizyonu veya çözülemeyen kaynak çakışması otomatik
olarak uyumlu sayılmaz.

Yeni oyun paketi, resmî sürümün paketidir. İki bilinen ek AI game.gd
kancası doğrulanmış çapalara eklenir; upstream oyun script'i eski kopyayla
değiştirilmez. Modelin ilave kaynakları ayrı eklenir. Standart DLL hiçbir
zaman özel AI DLL'i yerine kullanılmaz.

Her yeni paket için ayrı config ile tek 6 saniyelik orta/mechanics
kontrolü yapılır. Aynı anda eğitim açıksa kontrol ertelenir. Başarıdan sonra
engine-state.json işaretçisi atomik değişir. Önceden çalışan oyun etkilenmez;
ilk açılış hazırlanma sırasında mevcut motoru kullanabilir, hazır sürüm
sonraki açılışa geçer. Başarısız iş mevcut işaretçiyi değiştirmez. Aynı
başarısız sürüm/girdi, değişiklik olmadan tekrar tekrar derlenmez.

Paketler AI-Motor-Guncellemeleri/packages altında sürüm/içerik kimlikli
ayrı dizinlerdir. Model runtime'ındaki weights/spend_weights, hashler,
fraksiyon bankaları ve model_activation değiştirilmez. İnsan ve bot
logları kalıcı AI-Yeni-Model dizininde kalır. Her eğitim/değerlendirme çifti
başlangıçta tek bir motor paketine sabitlenir; karşılaştırma ortasında yeni
motor seçilmez. Doğrulama config'leri auto-sync başlatmaz.

Otomatik geriye sürüm düşürme yoktur. Daha eski bir sürüm seçilirse çalışan
AI paketi korunur; update-status kaydı bunun nedenini belirtir.

## Yerel durum

- AI-Motor-Guncellemeleri/source: ayrı AI entegrasyon Git fork'u, upstream'e push yapılmaz.
- ai-source-baseline.json: kanonik AI motor dosyalarının son alınan içeriği.
- engine-state.json: etkin, doğrulanmış paketin sürümü ve dosya hashleri.
- update-status.json / auto-update.log / build.log: hazırlama sonucu ve ayrıntılar.
- checks/: ayrı config ve kısa kontrol kanıtları; model eğitimi değildir.

Motor C++ değişikliklerini geliştirirken bu yolun import/build işlemi
kullanılmalıdır; etkin cache varken yalnız eski kanonik DLL'i derlemek
oyunda yeni motor değişikliğinin kullanıldığını göstermez. Otomasyonun
kısa mechanics kontrolü başarılı olursa başka bütün testleri çalıştırma.

## İlk doğrulama — 2026-11-05

Upstream v0.4.12-nightly.261105100 / aa3e25842bf2ebc3473e33ee38a86cbd82a97a28.
İlk taşımadaki dört motor çakışması incelenerek çözüldü; upstream ekleri ve
AI özellikleri birlikte korundu. Yeni native motor derlendi. Resmî 12
dosyanın bütünlüğü doğrulandı. 23 ilgili Python kontrolü geçti.

Tek 6 saniye mechanics kontrolü: 120 kare, 12 model kararı, 0 istek/ödül/
script hatası; gerçek farm yapım emri ve bağlı duvar parçaları gözlendi.
Başlatıcı --check güncel paketi seçti; aynı sürüm için tekrar sync derleme
ve saha kontrolü başlatmadı. Ağırlıklar korundu. Bu genel oynanış, bütün
mekanikler veya multiplayer uyumu sertifikası değildir.
