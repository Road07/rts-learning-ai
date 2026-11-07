# Araştırma yeniden başlatma geri bildirimi

Politika: `action-credit-v3`. Temel: LEARNING-FEEDBACK-V2.md.

V1/v2 dosyaları ve hesapları korunur. V3, v2'nin ekonomi bütçesi, net nakit
geri dönüşü, birim/hero iptal hesabı ve terminal hedeflerini korur. Eklediği
tek ödül kapsamı, kanıtlanmış araştırma iptal–yeniden başlatma döngüsüdür.

## Kanıt ve eşleştirme

- Gerçek queued/cancelled kaydı; oyuncu, üretici, `queue_kind=research`,
  pozitif `queue_receipt_id` ve aynı araştırma şablonu eşleşmelidir.
- Motorun araştırma production_id=0 değeri tek başına eşleştirme değildir.
  Yeniden başlatma, aynı üreticide aynı şablon ve farklı pozitif gözlem
  kimliğiyle 30 saniye içinde gerçek bir queued olayı gerektirir.
- Gönderilmiş iptal kararı ve gözlenen iptal zamanı ilişkilendirilir;
  bitmemiş karar ufku, ücretsiz yatırım, sıfır ilerleme/iş, otomatik iptal,
  başlangıç/iptal kaydı eksikliği veya sıra geçmişi boşluğu etiket üretmez.
- Araştırma için iptal/yeniden başlatma arası mevcut gözlem dizisi de
  kontrol edilir. Görünür düşman kümesi değişimi, üreticiye yakın düşman,
  hasar/kayıp, 10 saniyeyi aşan örnekleme boşluğu veya olay çevresinde
  eskimiş gözlem durumunda ceza üretilmez. Fog ihlali yapılmaz.

`research_restart_delay = -ödenen_kuyruk_maliyeti * ilerleme_oranı / 1000`.
Bu değer mevcut %85 ekonomi dışı takım bütçesi içinde yumuşak sınırlanır.
İade edilen para kayıp sayılmaz. Bu, atılan üretim işinin nominal maliyetle
ölçeklenen göstergesidir; kesin stratejik hata veya nedensellik değildir.
İptal yasaklanmaz, asker üretimi zorlanmaz.

## Dağıtım ve veri sınırları

Değişmez politika dosyası runtime reward_config/reward_sha256 ile sabitlenir.
Normal maçlar ve otomatik eğitim aynı hesabı kullanır. Yeni normal maç
ithalatı politika sürümünü eşleştirir; eski v1/v2 hedefleri v3 hedefleriyle
sessizce karıştırılmaz. Eski ağırlıklar/bankalar korunur; yeni neural girdi
veya ağırlık sıfırlama yoktur. Eski loglara araştırma olayı uydurulmaz.
Katalog/ödül değişmişse bekleyen eski politika değerlendirmesi yeniden
kullanılmaz; bu kural mevcut sürüm kontrolüne aittir.

## Doğrulama ve sınırlar

32 ilgili kontrol geçti: sürüm uyumu, doğru gözlem kimliği, production_id=0
çakışması, eksik geçmiş, otomatik iptal, ücretsiz/olgunlaşmayan veri yolu,
tehdit/bilgi/hasar korumaları ve başlatıcı değerlendirme devamı.

Tek 6 saniyelik middle/learning-feedback değerlendirmesi: gerçek araştırma
başlama/iptal/yeniden başlama, %20 ilerleme ve 0.8 iş saniyesi; üç olay
sensöre ulaştı. 120 kare, 12 model kararı, 0 sunucu/istek/ödül hatası.
Gerçek native olaylar kontrollü bağlamla ayrı fixture kredi kontrolüne
verildi; -0.07727 sınırlanmış kredi doğru iptal kararına bağlandı. Bu
kontrollü bağlam gerçek maç strateji başarısı veya uzman eğitim verisi
değildir. Fixture/değerlendirme verisiyle gradient güncellemesi yapılmadı.

Kanıt: `ai-mod-source/research-credit-v3-verification.json`.
Sonraki aşama gerçek öğrenen oyuncuların yeni politikayla aldığı kredi ve
eğitim dışında tekrarlanan davranış değişimidir; henüz kanıtlanmadı.

## Öğrenen oyuncu geri bildirim kapsamı

`service/feedback_audit.py` salt okunur `decision-feedback-audit-v1` raporu
üretir. Her arena bölümü feedback-audit.json yazar; experience ve eğitim
turu raporu da aynı özeti taşır. Oyuncu/fraksiyon/head, seçilen/gönderilen
komutlar, çok seçenekli sample kararları, eşleşen kredi, olgunlaşma ve
sıfırdan farklı yerel/terminal geri bildirim ayrıdır. Bütün oyuncuların
kredi bileşenleri learner bayrağıyla gösterilir; rakipte ölçülen olay
öğrencinin öğrenme sinyali sayılmaz.

Sıfır kredi; gönderim yok, kredi eşleşmesi yok, zaman ufku dolmamış,
olgunlaşmış ama ölçülen yerel etki yok veya bileşenler birbirini götürüyor
olarak ayrılır. Sonuç bulunmaması stratejik doğru/yanlış etiketi değildir.
Bu rapor ödül, gradient, seçim olasılığı veya model ağırlığını değiştirmez.

17 ilgili kontrol ve tek 6 saniyelik middle/learning-feedback örnekleme
kontrolü geçti. 24 gerçek örneklenmiş model seçimi gönderim/kredi kaydıyla
eşleşti; 21 karar olgunlaşmamış, 3 kararda ölçülen yerel etki yok. Eğitim
güncellemesi/aktivasyon yapılmadı. Bu sonuç öğrenme başarısı değildir.
Kanıt: ai-mod-source/feedback-coverage-verification.json.
