# Gym yoğun ödülü — gym-potential-v1

`OpenBFMEEnv(a=1e-4, b=.01, c=1e-4, gamma=.99)`; katsayılar sonlu, gamma0..1.
`Phi = a*Δtotal_income + b*Δbuilding_count + c*Δarmy_value`.
Δ: kontrol edilen oyuncu eksi düşman oyuncuların aritmetik ortalaması;
müttefikler dahil değil. Böylece1 oyuncu3 düşmanın toplamıyla karşılaştırılmaz.
`shaping = gamma*Phi_new - Phi_old`; reset sadece başlangıç potansiyelini kurar.
Gerçek terminal absorbe durumunda `Phi_new=0`; truncated finalde gerçek Phi kalır.
Temel native zafer+1/eliminasyon−1 korunur. Truncated ek ödül `clip(Phi_final,-1,1)`.
Toplam `terminal + shaping + truncated_result`; shaping/total ayrıca kırpılmaz.
Gamma adım başınadır: öğrenici farklı/zaman bazlı iskonto kullanacaksa aynı
iskonto shaping'e de uygulanmalı. Ek truncated skor ödülü hedefi değiştirir;
bütün ödülün politika-değişmezliği iddia edilmez. [Temel potansiyel sonucu](https://ai.stanford.edu/~ang/papers/shaping-icml99.pdf).

Gelir: başlangıç parası/para bakiyesi/iade değil, episode boyunca gerçek native
kaynak ödemeleri. Bina: yaşayan STRUCTURE sayısı; mevcut sayaçtaki gibi inşaat ve
fortress bileşenleri dahildir. Ordu: yaşayan birlik/kahramanların temel şablon
BuildCost toplamı, canla çarpılmaz; taburlar tek sayılır, kurucu/mermi/tabur
üyeleri dışlanır, maden/garnizon içindeki birlikler kalır. Bilinmeyen maliyet hata.
Native `gym_reward_state()` sisten bağımsızdır ve yalnız taze yerel maçta çalışır.
Bu özel tablo RPC'de gözlemin kardeş alanıdır: gözlem/kodlayıcı/adaya girmez.

`info.reward_components`: terminal, potential_income, potential_buildings,
potential_army, shaping, truncated_result, total. Üç potential_* toplamı shaping;
bu alanları tekrar toplamayın. Özel bölüm klasöründe reward.jsonl ayar, başlangıç,
her adım, potansiyeller, gerçek oyuncu tablosu ve bileşenleri tutar. Info'ya ham
rakip tablosu verilmez; ayrıcalıklı ödül tanı bilgilerini politika girdisine katmayın.

14 kod kontrolü: cebir, kırpma, terminal/truncation, teleskoplama, kötü veri,
log, gizli metrik değişirken gözlem eşitliği, Gym API/sentetik checker geçti.
Beş6 s gerçek3v3 başlangıç testi (4 farklı tohum + ilk tohumun tekrarı):
271026:+.00336667; 271027:+.00340000; 271028:+.00336667;
271029:−.01640000; tekrar271026:+.00336667. Hepsi süre sınırında bitti.
Tekrarda eylem, ödül ve30 native kare hash'i birebir eşit. Bu pencerede gelirler
eşit/ordu0; fark bina bileşeniydi. Uzun maç ölçeği/oynanış gücü doğrulanmadı.
Kanıt: AI-Test-Sahasi/gym-dense-random-five/verification.json; her maç reward.jsonl.
Tekrar aracı: training/gym_dense_check.py --output <yeni-dizin> --seconds 6.
