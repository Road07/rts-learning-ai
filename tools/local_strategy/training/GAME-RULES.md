# Oyunun kaynak verilerini modele aktarma

`bfme-public-rules-v2` kurulu OpenBFME + RotWK 2.01 ortamının herkese açık
oyun tanımlarını saklar; ilgili birlik/hedef/üretim seçeneği için sayısal
özetleri taktik ve üretim ağlarına verir. Normal maç ve otomatik eğitim
aynı kataloğu ve aynı kodlayıcıları kullanır.

Bu bir strateji ezberi veya savaş sonucu tablosu değildir. Bilgiye erişim
sağlamak, bilgiyi doğru karar vermek için kullanmayı öğrenmekten ayrıdır.

## Kaynaklar ve içerik

`extract_mechanics.py --full --mod AI-Yeni-Model/ai-mod` gerçek kurulumun
RotWK 2.01/BFME2 arşiv öncelik politikasını ve modun dosya katmanını
kullanır. Dosya hashleri `AI-Egitim/game-rules-v2/inventory.json` içinde
saklanır. Kaynak satırları, makrolar, kalıtım ilişkileri ve koşullar korunur.
Oracle yapısal taraması sıfır hata verdi; bu, bütün motor semantiklerinin
bağımsız olarak doğrulandığı anlamına gelmez.

Katalog kapsamı:

| Tanım | Sayı |
|---|---:|
| Nesne: birlik, tabur, kahraman, bina, mermi ve diğer şablonlar | 4.319 |
| Silah | 741 |
| Zırh | 221 |
| Yükseltme | 1.052 |
| Komut seti / komut düğmesi | 674 / 1.286 |
| Spellbook bilimi / özel güç | 75 / 422 |
| Özellik değiştirici / deneyim seviyesi | 556 / 769 |
| Hareket tanımı / GameData | 120 / 1 |

Yedi fraksiyonun kaynakları dahildir. Sayılar yasal olarak üretilebilir
oyuncu birliği sayısı değildir; kampanya/dekor/yardımcı nesneler de vardır.
Ham `mechanics.json` kaynakları korur; yaklaşık 24 MB `game-rules.json`
grafik Draw blokları dışındaki mekanik nesne ve tablo tanımlarını taşır.

## Modelin sayısal olarak gördükleri

Maliyet, yapım süresi, komuta puanı, temel azami can, üye canı ve sayısı,
temel vuruş hasarı, menzil, atış gecikmesi, hız; 12 hasar türü için zırh
çarpanı; hasar türleri ve temel sınıf bayrakları kodlanır. Her sayısal
alanın bilinirlik maskesi vardır. Bilinmeyen değer sıfır istatistik değildir.

Kendi/görülen düşman şablonlarının özetleri, seçili birliklerin ve görülen
hedefin bilgileri taktik girdilerine; yasal satın alma seçeneğinin bilgileri
de üretim girdilerine eklenir. Özetler gözlenen şablon sayısına göre
ağırlıklı ortalamalardır; bilinmeyen şablonların kapsamı ayrıca belirtilir.
Gizli düşmanın varlığı, ordusu, konumu veya kaynakları katalogdan okunmaz.

Taburların kontrol nesnesindeki `ImmortalBody MaxHealth=1` asker canı
sayılmaz. Örneğin bu kurulumda GondorFighter 200 can/40 temel vuruş;
15 kişilik GondorFighterHorde 3.000 toplam temel can ve 250 maliyettir.
Taburun 600 nominal toplam vuruş değeri aynı anda vuruş veya DPS değildir.
Guardian temel hasarı 80'dir; yükseltme gerektiren ek hasar bileşenleri
yükseltmesiz karta katılmaz. Koşullu varyantlar ham silah tanımında kalır.

Can 3.578, temel hasar 547 ve menzil 588 nesne şablonunda çözülebildi.
Birçoğu saldırmayan/dekoratif nesneler olduğu için tüm 4.319 nesnede
hasar bulunması beklenmez. 24 kartta ayrıca açık çözümleme sorunu
işaretlidir. Çelişkili/eksik/karmaşık bilgiler uydurulmaz.

## Kesin sınırlar

- Kartlar kaynaklardan türetilen temel, yükseltmesiz değerlerdir. Seviye,
  duruş, aura, aktif yetenek, oyuncu indirimi ve hedef filtresinden sonraki
  canlı değeri iddia etmez. Motorun gerçek fiyat ve komut kontrolleri esas.
- Hasar parçaları DPS değildir. Animasyon, atış öncesi süre, hedef filtresi,
  alan hasarı ve diğer koşullar ham tabloda korunur; sabit vektör bunların
  tamamını çalıştıran bir savaş simülatörü değildir. Sıfır atış gecikmesi
  sonsuz saldırı hızı diye yorumlanmaz.
- Bütün ham tablolar `PublicGameRules.data`/`definitions()` üzerinden
  erişilebilirdir; **her ham alan ayrı bir sinir ağı girdisi değildir**.
  Kahraman güçleri, upgrade ve deneyim etkilerinin bütün koşullarını çözmek
  için daha ayrıntılı temsil gerekir. Araştırma seçeneğinin kaynak maliyeti
  ve süresi ayrıca kodlanır; bilim puanları para sayılmaz.
- Kaynak kalıtımı/RemoveModule/ReplaceModule ve eklemeli KindOf bayrakları
  muhafazakâr yorumlanır; karmaşık/çelişkili tanımlar bilinmiyor kalabilir.

## Model ve kayıt uyumluluğu

Taktik ağ 385, üretim ağı 378 giriş kullanır. Eski 88/141 taktik ve
109/125/141/195 üretim girdileri sona sıfır satırlar eklenerek genişletilir;
yedi fraksiyon bankasının öğrenilmiş ağırlıkları korunur. Yeni satırlar
sıfır başladığı için katalog aktarımı tek başına yeni bir oynayış üretmez.

Katalog içerik hash'iyle değişmez bir dosyada tutulur;
`runtime.json` içindeki `game_rules` ve `game_rules_sha256` alanları seçer.
Açık maçın kataloğu/ağırlıkları bellekte sabit kalır. Yeni eğitim kayıtları
sayısal kaynak özelliklerini ve katalog kimliğini taşır; normal maçların
yeni offline izleri de genişletilmiş vektörleri kaydeder. Eski eksik normal
izler yeni boyutla karıştırılmaz. Model ağırlıkları bu aktarımda sıfırlanmadı.

## Doğrulama

34 ilgili Python kontrolü geçti: gerçek kaynak örnekleri, tabur/asker
ayrımı, yükseltmeli hasarın ayrılması, zırh yüzdesi, kaynak bağlantıları,
fog ile gelen şablonlarla sınırlama ve tüm faction bankalarının taşınması.
Tek `middle / pressure` 6 saniyelik durum kullanıldı; sahada görülen
temel/yükseltmeli cüce hasarı eksikliği düzeltilince aynı durum tekrarlandı.
Emir ve özellik kayıtları kontrol edilir; bu test daha iyi oyun veya
öğrenilmiş savaş bilgisi kanıtı değildir.
