# Yeni geri bildirim sistemi: ilk veri kontrolü

Yeni politika: **action-credit-v2**. Kurulu ödül dosyasının hash doğrulaması başarılı.

Tamamlanmış v2 eğitim turu: **0**.

Son eğitim kaydı 30. turdur; eğitim bölümü mevcut, değerlendirme tamamlanmamıştır ve action-credit-v1 kullanılmıştır. Bu kayıt yeni politika sonrası sonuç olarak değerlendirilemez.

## Eski sistem başlangıç ölçümü — 30. tur

| Fraksiyon | Onaylanan üretim emri | İptal emri | Onaylanan farm emri | Ordu grubu başlangıç → son | Ortalama para |
|---|---:|---:|---:|---:|---:|
| FactionDwarves | 8 | 0 | 2 | 9 → 6 | 5088 |
| FactionWild | 8 | 0 | 1 | 9 → 8 | 9802 |
| FactionMordor | 10 | 0 | 7 | 9 → 12 | 3556 |
| FactionIsengard | 0 | 16 | 21 | 9 → 0 | 10219 |
| FactionAngmar | 27 | 19 | 11 | 9 → 5 | 13062 |
| FactionMen | 0 | 28 | 13 | 9 → 0 | 11566 |

Onaylanan emir, tamamlanan üretim değildir. İptal sayısı tek başına hatalı iptal kanıtı değildir. Ordu değişimi kayıplar ve diğer etkenleri de içerir. Bunlar farklı fraksiyon/başlangıç aşamalarını eşitlemeden güçlenme karşılaştırması yapılamaz.

## Sonraki veriyle karşılaştırma

- Önce action-credit-v2 kullanan tamamlanmış tur bulunmalı.
- Önceki/yeni checkpoint karşılaştırmasında aynı roster, rakip ve simülasyon karesi doğrulanmalı.
- Gerçek kuyruk kayıtlarından iptal–yeniden başlatma, kaybedilen üretim ilerlemesi ve kayıt bütünlüğü incelenmeli.
- Asker üretim emirleri, sahada görülen ordu ve olgunlaşan yatırım getirileri ayrı değerlendirilmeli.
- Kısa fixture koşusu strateji öğrenme veya güçlenme kanıtı sayılmamalı.

Eski kayıtlarda yeni native olaylar ve ödenmiş yatırım kanıtları eksik olduğundan v2 ödül etiketleri uydurulmadı. Bu incelemede eğitim başlatılmadı, model ağırlıkları değiştirilmedi.
