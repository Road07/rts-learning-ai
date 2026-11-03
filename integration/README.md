# OpenBFME integration / OpenBFME entegrasyonu

Upstream: https://github.com/Open-BFME/openbfme-godot

Base commit: `1a09e5f` (the full revision is recorded in `UPSTREAM.json`).

`openbfme-ai.patch` contains tracked engine changes plus the new integration
sources. It is supplied instead of redistributing the full game engine,
retail data or local build products. Apply it to a clean checkout of the
recorded upstream revision and follow that project's build documentation.
The game bridge and packaging helpers still need local configuration and
external inputs; applying the patch is not a playable installation procedure.

OpenBFME and its contributors retain authorship of the upstream engine.
This project's original work is the experimental AI/model/training integration.
GPL-3.0 and existing attribution notices are retained. No retail game
assets, installers, executable bundles or personal recordings are included.

---

`openbfme-ai.patch`, belirtilen OpenBFME sürümüne göre motor değişikliklerini
ve yeni entegrasyon kaynaklarını içerir. Tam motor, oyun verisi veya yerel
derleme çıktıları dağıtılmaz. Yamayı kaydedilen upstream sürümünün temiz
kopyasına uygulayıp upstream derleme yönergelerini izlemek gerekir.
Bu işlem tek başına oynanabilir kurulum oluşturmaz.

OpenBFME motorunun geliştiricileri upstream katkıcılarıdır. Bu deponun amacı
kendi deneysel RTS karar modelimizi ve eğitim bağlantısını geliştirmektir.
