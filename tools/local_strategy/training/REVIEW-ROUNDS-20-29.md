# Eğitim verisi incelemesi: turlar 20–29

İnceleme, komuta puanı düzeltmesinden sonraki yeni raporlara aittir.
Yeni maç/test/eğitim başlatılmadı; model veya eğitim ayarları değiştirilmedi.

## Doğrulanan ilerleme

- 20–29 arası 10 tur tamamlanmış, her biri 180 saniye.
- 3.137 taktik ve 3.137 harcama örneği kaydedilmiş. Bunların tamamı
  çok seçenekli veya sıfırdan farklı krediye sahip örnek demek değildir.
- Yedi fraksiyonun iki bankası da güncelleme almış. 19. turun checkpointiyle
  etkin 29. tur çifti doğrudan karşılaştırıldı; her bankada gerçek parametre
  farkı var. Kaynak oyun bilgilerine ait giriş ağırlıkları da sıfır değil.
- Tamamlanan yeni turlar etkin oyuna aktarılmış; incelenen runtime 29. turu
  işaret ediyor. 30. turun eğitim adımı raporda var, ancak tamamlanmış
  karşılaştırma/aktivasyon sonucu yok; başarılı turlar arasına katılmadı.
- Yeni kayıtların sunucu loglarında request/reward/host hatası bulunmadı.
  Önceki negatif CP hatası bu kayıtlarda tekrarlamamış.
- Angmar üretim bankasının 26 ve 27. tur güncellemeleri KL denetimiyle
  geri alınmış (0.535 / 0.342). Bunlar tüm turun çökmesi değil, aşırı
  politika değişimini engelleyen korumanın çalışmasıdır.

## Davranış sorunları

20. turun başlangıç karşılaştırmasında eski ve yeni takımın hiç asker
üretim emri yok. Yaklaşık 40'ar farm emri veriliyor. Yeni takımın süre
ağırlıklı farm payları yaklaşık %22.2 / %22.1 / %26.6. İki modelin ödülü
de yaklaşık 1.0 ve yalnız ekonomi getirisi. Ödül tavanı hâlâ zayıf
ekonomik tek davranışı ayırt etmiyor; galibiyet kanıtı değil.

25. turun hazır orta oyun karşılaştırmasında üretim iptal döngüsü var:
yeni model tarafındaki Mordor 21 asker üretim emrine karşı 20 okçu üretim
iptal emri vermiş. Goblin tarafında 28 Goblin King üretim iptal emri var.
Bunlar doğrulanmış gönderim kayıtlarıdır; her emrin tamamlanan birim veya
kesin aynı siparişin iptali olduğu varsayılmadı. Hazır başlangıç ordusunun
sonradan kaybı, sıfırdan ordu kurmayı öğrendiği şeklinde yorumlanmadı.

## Karşılaştırma sınırlamaları

Karşılaştırma ödülleri 20. turda 1.0 → 1.0, 25. turda 0.517 → -0.241.
İkinci sonucu tek başına genel gerileme kanıtı saymıyoruz:

- 25. turda ölçüm pencereleri eşleşmemiş: frame 7–3384 ve 7–3418.
  Rapor zaten `matched_roster_and_window=false` olarak işaretliyor.
- Faction rotasyonu yeni değerlendirme tohumu `seed+100000` üzerinden
  yeniden hesaplanıyor. 100000, 7'nin katı olmadığı için eğitim ve
  değerlendirme öğrenci rosterları farklı oluyor. Örneğin 20. tur eğitim
  Angmar–Men–Elf, değerlendirme Mordor–Isengard–Angmar. 25. tur eğitim
  Mordor–Isengard–Angmar, değerlendirme Cüce–Goblin–Mordor. İki değerlendirme
  kendi aralarında aynı rosterı kullanıyor, ama o tur eğitilen üç bankadan
  yalnız birini öğrenci tarafında test ediyor. Diğer banka gelişimleri
  bu karşılaştırmayla sınanmamış kalıyor.
- Her durumda yalnız bir çift var; aşamalar/rakipler değiştiği için
  farklı turların ham ödüllerini gelişim eğrisi gibi karşılaştırmıyoruz.

## Sonuç ve önerilen sıra

Öğrenme ve otomatik aktarım çalışmış; yeni veriler ağırlıklara ulaşmış.
Oynanışta güvenilir ve genel güçlenme henüz kanıtlanmıyor. Öncelikler:
eğitim/değerlendirme rosterını sabitlemek ve simülasyon pencerelerini
eşlemek; üretim/iptal davranışının sonuçlarını ölçmek; yalnız gelirden
doyan geri bildirimi askeri ve terminal sonuçlarla daha iyi ilişkilendirmek.

Ham özet: `ai-mod-source/latest-training-review.json`. Kaynaklar ilgili
koşuların `report.json`, `experience.json`, `economy-evaluation.json` ve
model checkpointleridir. Bu incelemede bulgular kaydedildi; devam eden
eğitimin kodu/ilerlemesi değiştirilmedi.
