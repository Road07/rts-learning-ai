# Sonuca dayalı takım ödülü

Güncel öğrenme yolu [DECISION-REWARDS.md](DECISION-REWARDS.md) içinde açıklanır:
`action-credit-v1` her kararın aktör/hedef/zaman ile ilişkilendirilen sonucunu
kullanır. Aşağıdaki v3 takım toplamı tanı/uyumluluk raporudur; yeni eylemlere
aynı avantaj olarak topluca verilmez. Terminal +10/-10 korunur.

Sürüm: `bfme-outcome-reward-v3`. Kaynak ayarlar
[reward_v3.json](../knowledge/reward_v3.json); paket kopyası
oyun `runtime.json` içindeki `reward_config` dosyasıdır. Ayarlar hash ile sabitlenir ve
her eğitim koşusuna ayrıca kopyalanır. Kaynak ayarı değiştirdikten sonra
`decision_trial.py` ile paket yeniden hazırlanır.

| Ölçülen sonuç | Ham puan | Bileşen sınırı |
|---|---:|---:|
| Gerçek takım galibiyeti / yenilgisi | +10 / −10 | Tek sonuç |
| Gerçek ekonomi ödeme kayıtları | 1000 kaynak için +0.10 | +0.25 |
| Kendi skorunda düşman birimi öldürme | +0.002 | +0.50 |
| Kendi skorunda düşman binası yıkma | +0.15 | +0.50 |
| Kendi birimini kaybetme | −0.0025 | −0.75 |
| Kendi binasını kaybetme | −0.20 | −0.75 |
| Yeni ölü kahraman kaydı | −0.40 | −1.00 |
| Takım üslerinin sağlık değişimi | +/−0.50 × sağlık oranı farkı | +/−0.50 |
| Mevcut kahramanların sağlık değişimi | +/−0.15 × sağlık oranı farkı | +/−0.30 |
| Kesintisiz gözlemde yeni düşman hasarı | +0.15 × fiyat × sağlık düşüşü / 1000 | +0.25 |
| İlk kez görülen düşman nesnesi | +0.002 | +0.05 |

Galibiyet dışındaki toplam, **−1 ile +1** arasında tutulur. Kısa sahada maç
bitmezse terminal puan **0**, sonuç `ongoing`, `win_label=null` kalır.
Üç müttefik bot ortak takım ödülü alır. Destek emrine puan verilmez; müttefik
üslerinin/ordularının sonucu ortak ödüle girer. Bu, yardımın sonucu kesin
olarak değiştirdiğini veya belirli bir komutun doğru olduğunu kanıtlamaz.

Öldürme/kayıp sayıları motorun skor sayaçlarıdır; her kayıt bir tabur anlamına
gelmez. Ucuz kalabalık ırkların kayıplarını aşırı cezalandırmamak için birim
sayısı ağırlığı küçük tutulmuştur. Bu ayarlar öğrenilmiş oyun dengesi değildir.

## Puan biriktirme açıklarına karşı sınırlar

- Harcama, birlik basma, farm sayısı, upgrade alma, büyü veya yardım emri
  vermek doğrudan puan kazandırmaz. Bunların değeri sonuçlarından gelir.
- Üretim iptalinin para iadesi gelir sayılmaz. Eski `moneyEarned` sayacı
  yerine `Economy::noteIncome` olayları, benzersiz sıra numarasıyla okunur.
- Düşmanın sisten kaybolması ölüm değildir. Sis aralığında kaybettiği sağlık
  hasar puanı sayılmaz. Aynı düşman sağlık kaybı takımda iki kez yazılmaz;
  iyileşen düşmana aynı hasarı tekrar vermek puan üretmez.
- Kendi hasar/iyileşme farkı işaretli toplanır. Yeni kahramanı tam canla
  çıkarmaya sağlık bonusu verilmez. İlk gözlem yalnız başlangıçtır.
- Skor/gelir zamanı geriye giderse veya sınırlı gelir günlüğünde olay
  atlanırsa eğitim koşusu reddedilir; eksik veri başarı gibi doldurulmaz.

Ödül için görünmeyen düşman nesneleri sorgulanmaz. Kendi skor geri bildirimi,
kendi kahraman/üs sağlığı ve normal sisle filtrelenen düşman görüntüsü kullanılır.
Gözlenen hasar bütün takımın gözlem sonucudur; hasarı seçilen model emrine
nedensel olarak bağlamaz. Çağırma/dönüşüm ve oyunun eksik mekaniklerinin
skor sayaçlarına etkisi izlenmelidir; bu bir kusursuz değer fonksiyonu değildir.

## Çalışma ve kayıtlar

Normal maçta sunucu `reward_observation` ve bileşenleriyle `reward_update`
kaydeder; **ağırlıklar maç sırasında otomatik değiştirilmez**. Maç sonu
gözlemleri oyun logunda `reward_final_observation` olarak kalır.

`AI-Otomatik-Egitim.cmd` gerçek örnekleri başlangıç ve son kayıtlarıyla
birleştirir; yalnız öğrenci takımını hesaplar. `experience.json` ve
`report.json` içindeki `reward_breakdown` bileşenleri ayrı gösterir. İki
karar ağı bu ortak bölüm ödülüyle güncellenir. Hâlâ bütün bölüme tek ödül
atanır; her hamlenin nedensel katkısı öğrenilmiş değildir. Güncellemeler
aday checkpoint'tedir; normal maç modeline kendiliğinden aktarılmaz.
