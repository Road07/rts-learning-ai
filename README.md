# RTS Learning AI

[Türkçe açıklama](README.tr.md) · [English overview](README.en.md)

## Türkçe

RTS oyunlarına deneyimlerinden öğrenen gerçek bir yapay zekâ modeli eklemek
için **kendi karar modelimizi ve eğitim sistemimizi geliştiriyoruz**.
OpenBFME + Rise of the Witch-king ilk geliştirme ve deney ortamımızdır.
Uzun vadeli hedefimiz modeli farklı RTS oyunlarına uyarlayabilmektir.

**Proje çok erken bir araştırma prototipidir. Oynanabilir, güvenilir veya
rekabetçi bir oyun yapay zekâsı olmaktan henüz çok uzaktır.** Model oyunun
mekaniklerini yeterince öğrenmiş değildir: verimsiz farm yerleşimi ve
bağlantısız wall hub üretimi gibi temel hatalar yapabilir. Eğitim
ağırlıklarının değişmesi, oyun becerisinin geliştiğini tek başına kanıtlamaz.

Bu depo kaynak kodu ve motor entegrasyon yamasıdır; hazır mod, oynanabilir
sürüm veya eğitilmiş bir oyuncu değildir. Oyun dosyaları, özel maç kayıtları
ve yerel eğitim ağırlıkları dağıtılmaz.

## English

We are **building our own decision model and training system** to bring
experience-driven, learning AI to RTS games. OpenBFME + Rise of the
Witch-king is our first development and experimental environment.
The long-term goal is to adapt the AI to other RTS games.

**This is a very early research prototype, still far from a playable,
reliable or competitive game AI.** The model has not mastered the game
mechanics: it can make basic mistakes such as inefficient resource-building
placement and disconnected wall-hub construction. Changing network weights
does not, by itself, demonstrate improved gameplay.

This repository contains a source snapshot and an engine integration patch,
not a ready-to-play mod, release or trained player. Retail game files,
private match recordings and local trained checkpoints are not distributed.

## Repository

- [Architecture and source layout](docs/ARCHITECTURE.md)
- [OpenBFME integration and provenance](integration/README.md)
- [Decision outcome rewards](tools/local_strategy/training/DECISION-REWARDS.md)
- [Faction learning](tools/local_strategy/training/FACTION-LEARNING.md)
- [Normal-match learning](tools/local_strategy/training/NORMAL-MATCH-LEARNING.md)
- [GPL-3.0 license](LICENSE)

OpenBFME is an independent upstream project. Our AI work does not claim
authorship of its engine. This is an unofficial fan research project,
not affiliated with or endorsed by the original game publishers.
