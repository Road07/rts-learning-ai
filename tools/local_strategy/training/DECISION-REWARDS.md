# Kararların gözlenen sonuçlarından öğrenme

Etkin eylem geri bildirimi `action-credit-v1`; motorun gerçek maç sonucu
ve eski takım raporlaması `bfme-outcome-reward-v3` ile uyumlu tutulur.
Eski takım toplamı artık yeni kararların hepsine aynı avantaj olarak verilmez.
Kaynak ayar `knowledge/reward_v3.json` içindeki `decision_credit` bölümüdür.
Aktif oyun config'i SHA ile sabitlenmiş ödül dosyasına işaret eder.

| Alan | Öğrenmeye giren kanıt |
|---|---|
| Ekonomi | Gerçek gelir ödemesi, benzersiz sıra numarası, kaynak bina kimliği ve inşa kararı eşleşmesi. Gelir, yatırılan gerçek maliyetle normalize edilir; gerçekleşen ROI ayrıca raporlanır. Kaynak binası kaybından sonra yeniden inşa edilen binanın geliri ayrı bileşendir. |
| Üretim | Emirden sonra gerçekten oluşan birlik, üretici/şablon/konum eşleşmesi; o birliğin sonraki gözlenen savaş katkısı ve maliyet kaybı. Kuyruğa basmak tek başına puan değildir. |
| Savaş | Kendi birimlerinin maliyete göre sağlık/kayıp değeri; kesintisiz görülen düşman değer hasarı. Yakındaki gerçekten savaşan birliklerle ilişkilendirilir. |
| Baskın | Kaynak binasının gözlenen değer kaybı ve baskın birliklerinin maliyet kaybı. Üsse yürüyüp dönmek veya sağ kalmak tek başına puan değildir. |
| Savunma | Kendi binaları çevresindeki gerçek çatışma katkısı ve savunma sırasındaki varlık hasarı/kaybı. Gerçekte önlendiği bilinmeyen kayıp uydurulmaz. |
| Kahraman | Kahramanın doğrulanabilir çatışma katkısı ve maliyete göre can/kayıp etkisi; yetenekler ayrıca tetik sayacıyla denetlenir. Sırf kahraman almak, kaçmak veya kendiliğinden iyileşmek puan getirmez. |
| Büyü | Gerçek native tetik artışı ve hedef/konum/zaman bakımından uyuşan gözlenen hasar veya onarım. `submitted` tek başına etki kanıtı değildir. |
| Takım yardımı | Müttefik yapıları çevresinde kendi katılan birliklerinin gözlenen savaş katkısı; bu sırada kendi üssündeki zarar ayrıca maliyettir. Müttefik varlık hasarı ölçülür; kesin önlenen kayıp/hasar diye sunulmaz. |
| Keşif | İlk görülen hedefin ardından o bilgiyle ilişkilendirilebilen gerçek çatışma katkısı. Sırf yeni nesne görmek, boş haritada gezmek veya aynı alanı tekrar görmek eylem ödülü değildir. |
| Maç sonucu | Gerçek galibiyet +10, yenilgi -10; takımın kararları arasında paylaştırılır. Toplam mutlak yerel şekillendirme bütçesi takım başına en fazla 1'dir. |

## Zaman ve ilişkilendirme

Motor saniyede **5 logic frame** kullanır. Savaş ve büyü için varsayılan
pencere 12 saniye; yardım 18, keşif 30; üretim 90, bina/kahraman/araştırma
180 saniyedir. Bunlar oyun süresidir, duvar saati değildir. Pencere dolmadan
uzun vadeli yatırım başarı/başarısızlık diye etiketlenmez; gerçek terminal
maç sonucu varsa o son tarihe kadar gerçekleşen sonuç kullanılır.

Üretim/inşa emri, önceki nesne kimlikleri ve sonradan oluşan nesneyle
eşleştirilir. Bir birlik hem kendi üretim kararına hem o anki taktik emrine
bağlıysa gözlenen etki 30/70 paylaştırılır; aynı etki tam puanla iki kez
yazılmaz. Birden fazla aktör/komut aynı toplam ödülü çoğaltamaz.

Bu, aktör/hedef/zaman yakınlığına dayalı **gözlenen sonuç ilişkilendirmesidir**.
Yakında iki ordu savaşırken belirli bir silahın veya büyünün verdiği tüm
hasarı kesin olarak ayrıştıran bir nedensellik sistemi değildir. Bir anda
görüşten kaybolan düşmanın kalan maliyeti, ölüm diye varsayılmaz; bu nedenle
bazı ani öldürmelerin tam değeri ölçülemeyebilir. Aura, upgrade ve önlenen
hasarın kesin bireysel katkısı mevcut API'de ayrışmıyorsa uydurulmaz.

## Sömürüye karşı koruma

- Para biriktirme, sırf boş kuyruk veya kasadaki miktar yüzünden cezalandırılmaz.
  Üretim fırsatı maliyeti ancak o kararda yasal asker seçeneği varken daha
  sonra görülen gerçek üs zararıyla ilişkilendirilebilir.
- İade, harcama, inşaat sayısı veya emir sayısı ödül değildir.
- Aynı gelir sıra numarası ve düşman sağlık düşüşü tekrar sayılmaz.
- Görüş kaybı ölüm değildir; yeniden görüşteki düşük HP yeni başlangıçtır.
- Kendi tünel içindeki birliği hâlâ kendi nesne listesinde bulunuyorsa
  kayıp sayılmaz. Tam nesne kaybı için kendi kayıp sayacında artış aranır.
- Onarım/iyileşme ödülü native tetik ve önceden görülen tehdit altındaki
  gerçek hasar gerektirir. Her nesnede önceden ölçülen en düşük sağlığın
  izin verdiği tek bütçe vardır; hasar/iyileşme döngüsüyle çoğalmaz.
- Yalnız kendi nesneleri, paylaşılmış müttefik gözlemi ve normal sisle
  filtrelenmiş düşman snapshot'ları kullanılır. Gizli düşman ekonomisi okunmaz.

## Eğitimde kullanımı

Arena REINFORCE adımı her seçimin kendi `decision_credit.reward` değerini
kullanır; eski sabit takım ödülü yeni eylemlere topluca kopyalanmaz. Tüm
fraksiyon ağırlıkları ayrı kalır. Gözlenmiş/matür etki yoksa sıfır kredi
ve güncelleme atlama geçerlidir; kısa kontrolde uzun yatırım öğrenilmiş sayılmaz.

Normal maçlarda deterministik kararlar ayrı **işaretli offline sonuç
karşılaştırması** ile işlenir: olumlu yerel kararın olasılığı artırılır,
olumsuz olanın azaltılır. Böylece kaybedilen maçtaki iyi ve kazanılan maçtaki
kötü hamleler ayrılabilir. Bu on-policy örnek veya insan uzman etiketi değildir;
sınırlı, KL kontrollü bir offline öğrenme adımıdır. Yeni sonuç/aktör kaydı
bulunmayan eski loglara geriye dönük doğru/yanlış etiketi uydurulmaz.

`decision_credit_action` olayları oyun logundadır. `experience.json` içindeki
her iki başlığın seçimleri `decision_credit` taşır; takım raporundaki
`reward_breakdown.decision_credit.metrics` ölçüm kapsamını gösterir. Normal
maç aktarım raporlarında da karar geri bildirimi yöntemi belirtilir.
