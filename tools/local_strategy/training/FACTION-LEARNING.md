# Fraksiyonlara ayrı öğrenme

Yedi fraksiyonun her birinde bağımsız taktik ve komut/üretim ağı vardır:
Men, Elves, Dwarves, Wild (Goblin), Mordor, Isengard ve Angmar.
Eski ortak ağırlıklar başlangıç bilgisi olarak birebir kopyalanır; bu taşıma
yeni fraksiyon becerisi öğrenildiği anlamına gelmez. Bu sürümde ortak başlangıç
ağı dondurulur, her fraksiyonun tam ağı ayrı güncellenir. Ortak bir gövdenin
eşzamanlı eğitildiği çok görevli bir mimari değildir.

Checkpoint biçimi `faction-bank-v1`: mevcut iki NPZ içinde yedişer ağ saklanır.
Dosyalar tek bir doğrulanmış çift olarak yayımlandığı için oyun yanlış taktik
ve üretim sürümlerini eşleştirmez. Eski checkpoint yüklenebilir; yedi ağın
başlangıcı eskisiyle aynı skorları üretir. Yeni checkpoint yedi ağı da korur.

Oyun, gözlemdeki kendi fraksiyonuna göre doğru ağı seçer. Eğitime giren
gözlem/kararlar da aynı fraksiyon etiketiyle ayrılır; Goblin verisi Elf ağını
güncellemez. Her fraksiyonun hareketli ödül baseline'ı ayrıdır. Takım sonucu
şimdilik ortak ödül sinyalidir; fraksiyona özel bireysel katkı ödülü eklenmiş
sayılmaz. Ayrı öğrenme, sabit agresif/savunmacı fraksiyon kuralları getirmez.

Sürekli eğitim başlatıcısı `--rotate-factions` ile altı eğitim yuvasını
döndürür. Yedi ardışık tohumda her fraksiyon üç kez öğrenci takımına gelir.
Bu yalnız otomatik eğitimin hazırlanan kadrosudur; oyuncunun normal maç
takımlarını veya varsayılan kısa test sahası kadrosunu değiştirmez.
Manuel komut satırında aynı davranış için `--rotate-factions` eklenebilir.

Normal maçların offline öğrenmesinde de yalnız etiketi bilinen ve yerel
karar sonucu ölçülen bot seçimleri kendi fraksiyon ağına işlenir. Kazanan
takım filtresi yerine işaretli karar kredisi kullanılır. Fraksiyon etiketi olmayan eski
kayıtlar tahminle bir fraksiyona atanmaz.

`report.json` içinde `faction_learning`, her turun `update.factions` ve
`spend_update.factions` alanları, normal maçlarda da fraksiyon bazlı güncelleme
ölçümleri bulunur. Güncelleme olması daha iyi oyun veya dengeli rekabet gücü
kanıtı değildir; her fraksiyonun ayrıca karşılaştırılması gerekir.
