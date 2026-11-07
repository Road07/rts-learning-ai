# OpenBFME Gymnasium arayüzü

`gym_env.OpenBFMEEnv` gerçek başsız simülasyonu bir Gymnasium ortamına sarar.
`reset(seed=...) -> (observation, info)` ve
`step(action) -> (observation, reward, terminated, truncated, info)` kullanılır.
Her ortam tek oyuncuyu kontrol eder. Varsayılan Lostriand 3v3 düzeninde ilk
Cüce oyuncu ajandır; diğer beş oyuncu yerleşik Brutal AI olarak kalır. İki
oyunculu harita/roster da mevcut runner ile desteklenir. PettingZoo veya bir
`step` ile bütün takımı kontrol eden çok ajanlı bir arayüz değildir.

## Kurulum ve kullanım

Bağımlılık ayrı `AI-PyTorch/venv` ortamına kuruldu: Gymnasium1.2.2. Kaynaktan
kurulum için bu ortamın Python'u ile `pip install -r
ai-mod-source/tools/local_strategy/requirements-gymnasium.txt` çalıştırılır.
Kurulu oyun dosyaları, AI motor paketi ve public oyun kataloğu gereklidir;
repo bunları içermez. Mevcut model ağırlıkları bu ortamda yüklenmez.

Kök klasörden, `AI-PyTorch/venv/Scripts/python.exe` ile:

```python
import sys
sys.path.insert(0, "ai-mod-source/tools/local_strategy")
import gymnasium as gym
import gym_env  # OpenBFME-v0 kaydı

env = gym.make("OpenBFME-v0", duration=180, time_scale=10)
try:
    observation, info = env.reset(seed=271026)
    while True:
        # Örnek politika: yalnız mevcut yasal adaylardan rastgele seçim.
        action = env.unwrapped.sample_action()
        observation, reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            break
finally:
    env.close()
```

Bu örnek180 simülasyon saniyesi başlatır; sıradan geliştirme kontrolü6 saniye
kalır. Tek kısa gerçek kontrol komutu:

```powershell
AI-PyTorch/venv/Scripts/python.exe ai-mod-source/tools/local_strategy/training/gym_smoke.py --output AI-Test-Sahasi/new-gym-check
```

Çıktı klasörü yeni olmalıdır. Ortam yeniden `reset` edildiğinde önceki maç
kapatılır. `close()` birden fazla kez çağrılabilir. Normal oyun/eğitim EXE'leri,
onların kadansı ve etkin model ağırlıkları bu adaptöre geçirilmedi.

## Gözlem ve eylem

Gözlem, mevcut `EntityCodec` üzerinden sabit boyutlu `spaces.Dict`'tir:

- `entities`: varsayılan256×95; `entity_valid`, template, ilişki, sahip fraksiyon
  ve sınıf dizileri; observer `faction` ve16 global özellik.
- `heads.tactical`:64 aday; `heads.spend`:65 aday (64 native seçenek + bekle).
  Her başta153 özellik, tür/şablon indisleri, aktör/hedef entity maskeleri ve
  `legal` maskesi vardır. Entity/action boyutları mevcut codec sabitlerinden gelir.
- Boş alanlar sıfırla doldurulur. Entity sınırında elenen sayı
  `info.dropped_entities` ile bildirilir; sınırsız dünya temsili değildir.

Ham nesne kimlikleri neural sayısal girdi değildir. Gözlem ve adaylar mevcut
fog/stealth filtreli native sorgudan gelir. `info.policy_observation` yalnız
kontrol edilen oyuncunun aynı sınırlı gözlemidir; rakiplerin gizli geliri/ordusu
buraya eklenmez. Sonuç dosyasındaki tam skor tablosu ajan `info`'suna verilmez.

Eylem `MultiDiscrete([64,65])`: `[taktik_indeksi, üretim_indeksi]`.
İndisler yalnız en son gözlemdeki adayları gösterir. `info.action_ids` hangi
indisin hangi aday olduğunu bildirir. Padding/yasa dışı indeks `InvalidAction`
üretir ve native emir göndermez; sessizce en yakın adaya veya başka stratejiye
çevrilmez. `sample_action()` maskeli örnekler; `action_masks()` iki başın
birleştirilmiş129 elemanlı maskesidir. Genel `action_space.sample()` padding
seçebilir: politika başların `legal` maskelerini kullanmalıdır.

Alan düzeni ortak entity/attention/GRU prototipinin `tensor_frame` girdisiyle
uyumludur; bu, yeni ağın eğitildiği veya PPO collector'ın bağlandığı anlamına
gelmez. GRU hafızası ortama gömülü değildir; politika her reset'te kendi
hafızasını sıfırlamalıdır. İç içe Dict ve iki baş için kullanılan RL
kütüphanesinde uygun özellik kodlayıcı ve maskeli dağılımlar gerekir.

## Zaman, ödül ve bitiş

Native logic adımı0.2 saniyedir. Bir Gym adımı mevcut standalone model
zamanlamasını korur: sonraki25 native kareye/5 simülasyon saniyesine kadar
ilerler; terminal/süre sınırında daha kısa olabilir. Python kararı beklerken
dünya ilerlemez. Bu, otomatik eğitim EXE'sinin staggered5-kare planlayıcısını
değiştirmez. `info.step_seconds` gerçek geçiş süresidir; zamana bağlı GAE
iskontosunda bu süre kullanılmalıdır. İki eylem başına tek geçiş/ödül vardır.

Gym ödülü `gym-potential-v1`: mevcut native zafer+1 / eliminasyon−1 üzerine
gelir, bina ve ordu farkından potansiyel şekillendirme; süre sınırında kırpılmış
skor sonucu eklenir. Formül, parametreler, ayrı bileşenler ve beş kısa maç:
[GYM-DENSE-REWARD.md](GYM-DENSE-REWARD.md). Bu, action-credit-v3 otomatik
eğiticisinin ödülünü değiştirmez. Ajan elendiğinde onun açısından terminaldir;
takımın daha sonra kazanacağı varsayılmaz.

- Native zafer/yenilgi: `terminated=True`.
- Süre dolması: `truncated=True`, galibiyet/beraberlik etiketi yok; ayrı skor ödülü var.
- Her iki durumda da dönen gözlem resetten **önceki gerçek final** native
  gözlemdir. Truncation bootstrap'ı yeni maçın ilk görüntüsünden alınmaz.
- Motor/iletişim hatası istisnadır; sahte yenilgi veya başarılı truncation değildir.

`timeout` karar bekleme/yükleme sınırı (varsayılan120 s), `episode_timeout`
toplam worker duvar saati sınırıdır (3600 s). Ekran çıktısı/render bu sürümde
sunulmaz. Varsayılan çalışma hızı10x hedef, ölçülmüş10x garantisi değildir.

## Süreçler ve doğrulama

Her reset benzersiz runtime/PCK, çıktı ve localhost portu açar; sabit port veya
ortak model servisi kullanmaz. İlk reset'te seçilen motor aynı ortamın sonraki
reset'lerine sabitlenir; public katalog ortam oluşturulurken hash ile sabitlenir.
Başka bir ortam ayrı süreçlerle çalışabilir; tek ortamı eşzamanlı iki `step`
çağrısıyla paylaşmayın. `close` yalnız bu ortamın süreç ağacını kapatır.
Çalışma dosyaları `AI-Test-Sahasi/gym-runs` altında özeldir, repoya eklenmez.

İlk adaptör doğrulaması (yoğun ödülden önce), 2026-11-07: altı kod kontrolü geçti; Gymnasium `check_env` sentetik tam-adaylı
transport ile API/seed/space sözleşmesini doğruladı. Bu checker gerçek oyunda
çok sayıda reset çalıştırılmış gibi sunulmaz; maskeli gerçek ortamda genel
rastgele örnekleme geçersiz padding seçebilir.

Tek gerçek başlangıç kontrolü:6 simülasyon saniyesi/30 native kare, gözlem
kareleri1→26→31, iki açık bekle/bekle eylemi, ödül0, terminated=false ve
truncated=true. Final gözlem31. kareydi, bütün gözlemler tanımlı space içindeydi,
script/motor hatası yoktu. Gerçek zafer/yenilgi bu kısa oyunda gerçekleşmedi;
bu dallar ayrı sentetik testlerde doğrulandı. Uzun rollout, çoklu Gym ortamı
ve bu arayüz üzerinden PPO öğrenmesi henüz ölçülmedi.

Kanıt: `AI-Test-Sahasi/gymnasium-opening-6s/verification.json` ve o koşunun
gerçek native sonuç/hash dosyaları. Eğitim/aktivasyon yapılmadı.

API referansı: [Gymnasium Env](https://gymnasium.farama.org/api/env/),
[ortam denetleyicisi](https://gymnasium.farama.org/api/utils/).
