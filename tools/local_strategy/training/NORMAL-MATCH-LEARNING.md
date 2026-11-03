# Normal maçlardan öğrenme

Güncel yöntem: [DECISION-REWARDS.md](DECISION-REWARDS.md). Artık yalnız
kazanan botlar seçilmez: kapanışı ve gerçek terminal sonucu doğrulanan
maçlardaki olumlu/olumsuz karar sonuçları ayrı işaretlerle öğrenilir.
Aktör/hedef/zaman ve `decision_credit_action` kaydı olmayan eski loglar
bu yeni yöntemde kullanılmaz. Fraksiyon ağırlıkları ayrı kalır.

`AI-Yeni-Model.exe` ile açılan yeni yerel maçlarda botun sisle filtrelenmiş
seçenekleri, yaptığı seçim ve takım sonuçları kaydedilir. Oynarken ağ
ağırlıkları değiştirilmez ve kararlar önceki gibi en yüksek skorla seçilir.
Ek eğitim kaydı oyuncu başına en fazla 150 logic frame'de bir alınır;
seçilen seçenek ve en fazla 16 alternatif özellik vektörü saklanır.

`AI-Otomatik-Egitim.exe` veya normal varsayılan `.cmd` eğitim döngüsü,
her koşu başında en fazla bir uygun normal maç kaydını işler. Maçın kapanış
işareti, gerçek galibiyet/yenilgi ölçümü ve oyunun aldığı karar kaydı
eşleşmelidir. Yarım maçlar, test sahası nesneleri, eksik/bozuk ödüller,
eski seçenek kaydı bulunmayan loglar ve cevabı oyuna ulaşmayan seçimler
öğrenilmiş doğru örnek sayılmaz. Aynı maçın kimliği tamamlanan eğitim
raporlarında tutulur; ikinci kez işlenmez. Başarısız eğitimde tüketilmez.

Normal maçlarda seçim deterministik olduğu için bu kayıtlar arena
REINFORCE adımına on-policy veri gibi verilmez. Ayrı, küçük bir offline
işaretli sonuç karşılaştırması kullanılır: olumlu yerel sonucun seçim
olasılığı artırılır, olumsuz olanın azaltılır. Kazanılan maçtaki kötü karar
ile kaybedilen maçtaki iyi karar ayrılabilir. Fraksiyon başına iki ağda
tur başına en fazla 128 kayıt, 0.001 öğrenme oranı, norm kırpma ve 0.005 KL
sınırı vardır. İnsanın hamleleri bot kararı veya uzman etiketi sayılmaz.

Takım galibiyeti her bireysel hamlenin iyi olduğunu kanıtlamaz; bu başlangıç
düzeyinde bir normal maç öğrenme bağlantısıdır. İnsan tarzını öğrenme veya
maç içindeki her hatanın nedenini çözme iddiası yoktur.

Sonra olağan kısa saha eğitimi sürer. İki aşama da tamamlanınca model çifti
otomatik yayımlanır ve sonraki oyun açılışında kullanılır. Ayrı config veya
`--no-activate` ile yapılan doğrulamalar gerçek maç havuzunu tüketmez.

Kayıt yerleri:

- `AI-Yeni-Model/ai-service/logs/`: `normal_match_start`, `normal_match_action`
  ve maç kimlikli ödül gözlemleri.
- `AI-Yeni-Model/logs/`: gerçek karar alımı ve `normal_match_closed` sonuçları.
- `AI-Egitim/otomatik-dongu/<koşu>/report.json`: `normal_matches` alanında
  kullanılan maç, takım sonuçları ve iki ağın güncelleme ölçümleri.

Mevcut eski loglarda tam seçenek/maç kimliği eşleşmesi yoksa geriye dönük
uydurulmaz. Bu bağlantı kurulduktan sonra açılan maçlar yeni kaydı üretir.
