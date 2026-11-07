# Eğitim durması: negatif komuta puanı — 4 Kasım 2026

Başarılı tur `auto-20261104-204856-961571-19` korunuyor. Sonraki tur
`auto-20261104-205223-813783-20`, `Invalid mechanics feature` nedeniyle
45 istek reddedilince başarısız oldu. Saha/script kurulumu başarılıydı;
hata modelin veri doğrulamasındaydı.

Oyun istekleri kaynak kayıtlarıyla eşleştirildi: hatalı alan her seferinde
`cp_used_fraction`. Angmar oyuncusunda ilk bozulma frame 2381'de,
kullanılan CP -120, oran -0.192. Tekrarlanan düşüşler birikmiş. Negatif
oranlar gizlenmedi veya sıfıra kırpılarak eğitime sokulmadı.

## Kök neden ve düzeltme

`Object::addAttributeModifier`, özellik etkisini denemeden önce oyuncunun
CP hesabından birimi düşüyordu. `pool->add` reddederse geri eklemiyordu.
Ayrıca muhasebeye henüz girmemiş/çıkarılmış nesneler de yalnız şablondaki
CP'ye bakılarak bu yola girebiliyordu. Tekrarlanan retler sayacı azaltıyordu.

Artık yalnız gerçekten CP hesabına kayıtlı nesne geçici çıkarılıyor;
etki kabul edilse de reddedilse de hayatta kalan birim geri kaydediliyor.
Çıkarma/ekleme muhasebe bayrağını da güncelleyen Object yöntemlerinden
geçiyor. Modifier kaldırma yolu da aynı kayıt denetimini kullanıyor.
Geçersiz değer doğrulaması korunuyor; hatalar artık alan adı/değerini yazıyor.

## Kısa kanıt

`opening / cp-accounting`, aynı 1749 tohumu ve faction sıralaması,
6 saniye, ayrı config, `--no-activate`:

- AngmarThrallMaster: başlangıç CP 40.
- Sekiz reddedilmiş modifier eklemesi: CP hâlâ 40.
- Birim muhasebeden çıkarıldı: CP 0.
- Kayıt dışındayken sekiz ret ve kaldırma denemesi: CP hâlâ 0,
  birim kayıt dışı kalıyor.
- Tekrar kaydedildi: CP 40; öldüğünde CP 0.
- Saha PASS, sıfır script hatası ve gerçek ağ karar/ödül kayıtları.

Kanıt `AI-Egitim/otomatik-dongu/20261104-210434-17816/train-000/arena/opening.json`
içindeki `cp_validation`. İlk kontrol test erişim koşulunda durdu;
test_hooks koşulu düzeltildikten sonra aynı kısa durum tekrarlandı.
Beş ilgili Python kontrolü de geçti. Üç dakikalık maç yeniden oynatılmadı;
diğer olası uzun maç hataları bu kısa kanıtla dışlanamaz.

Probe yalnız `test_hooks` açık, ağ ve logic worker kapalı sahada çalışır;
normal model eylem uzayına eklenmedi. Normal oyun motor DLL'i ve eğitim
sahasının kullandığı DLL güncellendi. Öğrenilmiş çift sıfırlanmadı.

Başlatıcı durumunun kopyasıyla devam yolu kontrol edildi: başarısız
pending tur atlanıp 19. tamamlanan çift korunuyor; 20. tur tekrar deneniyor.
Canlı başlatıcı ilerleme dosyası elle değiştirilmedi.
