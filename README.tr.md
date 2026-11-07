# RTS Learning AI — Türkçe

## Amaç

RTS oyunlarına yalnızca ezberlenmiş stratejiler uygulayan bir bot yerine,
gözlemlerinden karar veren ve deneyimlerinden öğrenen bir yapay zekâ modeli
eklemek istiyoruz. Karar ağını ve eğitim altyapısını kendimiz geliştiriyoruz.

İlk uygulama alanımız **OpenBFME + Rise of the Witch-king**. Uzun vadede
ortak bir karar altyapısı ile oyuna özel gözlem/emir bağlantılarını ayırarak
başka RTS oyunlarına uyarlanabilen bir sistem hedefliyoruz. Diğer oyunlara
aktarım henüz uygulanmış veya doğrulanmış bir yetenek değildir; yeni oyunlar
için bağlantı, temsil ve eğitim çalışması gerekecektir.

## Mevcut durum: çok erken prototip

**Bu proje şu anda oynanabilir olmaktan çok uzaktır.** Güvenilir bir BFME
oyuncusu, tamamlanmış mod veya indirip güçlü botlarla oynanacak bir ürün
olarak sunulmamalıdır. Farm verimini, duvar genişletmeyi ve uzun vadeli
stratejileri yeterince öğrenmiş değildir. Yan yana kaynak binası yapabilir,
wall hub'ları yanlış kullanabilir ve kötü savaş/ekonomi kararları verebilir.

Çalışan deneysel parçalar:

- Python/NumPy ile küçük yerel karar ağları ve eğitim kodu.
- Gözlemden sunulan eylemler arasından taktik ve üretim/komut seçimi.
- Yedi fraksiyon için bağımsız ağırlıklar; mevcut bilgiyle ortak başlangıç.
- Hazırlanmış 3v3 senaryolarında otomatik eğitim ve checkpoint kaydı.
- Gerçek sonuçlarla ilişkilendirilen, zaman pencereli karar geri bildirimi.
- Uygun yeni normal maç kayıtlarından sınırlı offline öğrenme.
- Doğrulanmış tamamlanan eğitim çiftinin sonraki oyun açılışına aktarılması.

Bunların varlığı iyi oynanış veya sürekli gelişme kanıtı değildir. Eylem
seçenekleri ve konumlar hâlâ kod tarafından sınırlandırılır. Modelin büyüye
erişebilmesi onu doğru kullanmayı öğrendiği anlamına gelmez. Ödülün
aktör/hedef/zaman ilişkisi kesin nedensellik değildir.

## Öncelikler

1. Oyunun mekaniklerini daha doğru gözlem ve eylemlerle temsil etmek.
2. Kaynak yerleşimi, üretim, savaş ve takım desteğini ayrı ölçmek.
3. Tekrarlanabilir eski/yeni model karşılaştırmaları kurmak.
4. Tam maç stratejisi ve uzun vadeli sonuçlardan öğrenmeyi geliştirmek.
5. Ortak RTS çekirdeğini oyuna özel bağlantılardan ayırmak.

## Son altyapı güncellemeleri

- Mekanik gözlem/eylem arayüzü ve kurulu oyunun kamuya açık sayısal kurallarını kullanan girdiler.
- Ekonomi/üretim ölçümleri; eş fraksiyon, rakip ve oyun karesiyle önceki/yeni checkpoint karşılaştırması.
- Gerçek birim ve araştırma kuyruğu başlama/iptal olayları; gözlenen üretim ilerlemesiyle sınırlı karar geri bildirimi.
- Sürümlenmiş `action-credit-v3` ödülü; eski politikalar ve yedi fraksiyonun ağırlıkları korunur.
- Kesilen karşılaştırmadan devam, aşama bildirimi ve atomik checkpoint aktarımı.

Bunlar öğrenmeyi ölçmek için altyapıdır. Meta bilgisi, güçlü strateji, rekabetçilik veya sürekli gelişme henüz doğrulanmış değildir. Oyun tanımlarını girdiye eklemek, modelin bunları öğrendiği anlamına gelmez. Kısa saha kontrolleri gerçek maç başarısının yerine geçmez.

[İlerleme planı / Roadmap](docs/ROADMAP.md) · [Güncel ödül kapsamı](tools/local_strategy/training/LEARNING-FEEDBACK-V3.md)

## 8 Kasım 2026: eğitim altyapısı

- Gerçek OpenBFME simülasyonunu saran `OpenBFME-v0` Gymnasium ortamı ve yasal eylem maskeleri.
- Terminal zafer/yenilgi ödülünü koruyan potansiyel tabanlı yoğun ödül; gizli rakip bilgisi yalnız ödül hesabında, gözlemde değil.
- Mevcut oyun modelinden ayrı, standart MaskablePPO ile 180 saniyelik ekonomi görevi; sabit değerlendirme seedleri, CSV ve TensorBoard.
- Daha hafif ortam işçileri, hash doğrulamalı paket önbelleği, bellek koruması ve bölüm/ödül bileşeni logları.
- Kalıcı oyun süreci reseti ve ortak attention/GRU modeli ayrı deneysel yollardır; varsayılan oyun modeline aktarılmış sayılmaz.

Kısa kontroller akışın çalıştığını gösterir. Tam eğitim, oyun becerisi, uzun süreli kararlılık ve başka bilgisayarlarda kurulum henüz doğrulanmış değildir.
[Ayrıntılar ve ölçüm sınırları](docs/EXPERIMENTS.md).

### Kurulum kapsamı

Bu bir araştırma kaynak anlık görüntüsüdür. Yerel klasör varsayımları,
paketleme yardımcıları ve eski iç bağımlılıklar vardır; başka bilgisayarda
doğrudan çalışacak taşınabilir bir kurulum henüz yoktur. Kaynaklar ve
sınırlar [mimari notlarında](docs/ARCHITECTURE.md) açıklanır.

Motor OpenBFME projesine aittir; bu depoda onun üzerine AI entegrasyon
yaması bulunur. [Entegrasyon notlarına](integration/README.md) bakınız.
Oyun varlıkları, özel replay/loglar, çalıştırılabilir oyun paketleri ve
yerel model ağırlıkları bu depoda bulunmaz. Kaynak kod GPL-3.0 kapsamındadır;
upstream ve üçüncü taraf bildirimleri korunur.
