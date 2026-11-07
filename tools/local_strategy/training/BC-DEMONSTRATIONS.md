# BC gösterim kaydı ve birebir eylem eşleştirmesi

Şema: `bc-demonstration-v1`. Bu aşama veri toplar; BC veya RL eğitimi yapmaz.
İnsan gösterimi, yerleşik AI öğretmeni, model kararı ve fixture birbirinin
yerine etiketlenmez. Bu sürümün çalışan kayıt kaynağı gerçek yerel insan
oyuncudur; scripted-AI öğretmen kaydı henüz bağlı değildir.

## Emir öncesi kayıt

Opt-in insan kaydı açıkken dispatcher, desteklenen komutu uygulamadan hemen
önce `human_policy_snapshot` yazar. Aynı oyuncu/frame/command_id, native
human_state / human_command / human_command_result kayıtlarını bağlar.
Gözlem ve standart sınırlı üretim/komut adayları, botun kullandığı native
sorgularla alınır. İnsan için yalnız bu gözlem çağrısında geçerli thread-local
okuma izni vardır; model kontrolü veya oyuncu tipi değiştirilmez. Logic
worker içinde yeniden drainFrames beklenmez; disk ve GDScript işlemleri
orada çalışmaz. Tampon 8 MiB ile sınırlıdır, taşma capture_gap üretir.

İnsan gözlemi kendi ve yaşayan müttefiklerin görüşüyle sınırlıdır. Gizli
hedef parametreleri mevcut native redaction kurallarıyla korunur. Ağ,
replay veya yüklenen save'den yeni insan gösterimi oluşturulmaz.

GDScript, kayıt okunurken mevcut dünyadan birim/ekonomi/büyü durumu yeniden
toplamaz. `model_only_controller.options(obs, true)` aynı kodlayıcı ve
taktik aday üreticisini yalnız kaydedilmiş gözlemden çalıştırır. Harita
boyutu ve spell_points de native emir-öncesi gözlemde sabittir. Public
kuralların hash'i kayıt anında pinlenir. Hareket/saldırı kaydında pahalı
üretim adayları hesaplanmaz; ilgili taktik adayları yine kaydedilir.

## Eşleştirme ve kapsam

`service/demonstrations.py`, template, actor, target, koordinat, kuyruk ve
bağlı duvar başlangıç/bitiş/opsiyonlarını karşılaştırır. Koordinatlar yalnız
JSON float yuvarlama toleransıyla (0.01 dünya birimi) eşleşir; en yakın
aday seçilmez. Aynı düşük seviye hareketi birden fazla stratejik aday
temsil ediyorsa insanın niyeti tahmin edilmez, ambiguity raporlanır.

İlk kapsam: tek üreticiden normal birim/araştırma üretimi ve tekil iptal,
modelde temsil edilen konum/rotation'da bina ve bağlı duvar, tekil giriş,
toplu tahliye, aynı actor grubu/hedefi temsil eden hareket ve saldırı.
Hero by-index, batch/secondary queue, çoklu üretici, bireysel çıkış,
foundation, power ve diğer henüz dönüştürülmeyen emirler eğitim etiketi
uydurulmadan kapsam dışında kalır. Ham kayıtlar silinmez.

Farmın insan tarafından seçilen konumu mevcut sınırlı adaylarda olmayabilir.
Duvar uzantısının uzunluğu/yönü de kapsanmayabilir. Böyle bir emir
`outside_candidate_space` olur; aday kapsamı ayrıca geliştirilecektir.
Bu kayıt katmanı tek başına farm/duvar stratejisi öğrenildiği anlamına gelmez.

## Dışa aktarım

`training/export_demonstrations.py --logs <human-logs> --output <yeni-dizin>
--config <runtime.json>` değişmez JSONL veri seti ve kapsam raporu üretir.
Eski dosyalardan güncel aday kümesi yeniden üretilmez. Eksik/çakışan kimlik,
frame, katalog hash'i, native pre-state, sonraki duruma ait spell_points,
capture gap ve fixture kaydı dışlanır. `--include-fixtures` yalnız kontrol
içindir; bütün fixture satırlarında training_eligible=false ve split=
fixture_validation kalır.

Gerçek bir kuyruğa ekleme veya kuyruktan çıkarma, before/after kuyruk
kimlikleriyle kanıtlanır. success_verified=false tek başına başarısızlık
değildir; dispatcher hatası olmaması da başarı değildir. İlk eğitim
uygunluğu yalnız doğrulanmış normal kuyruk örneklerine verilir. Bina,
duvar ve hareket eşleşmeleri saklanır fakat uygulama sonucu henüz ayrıca
kanıtlanmadığından training_eligible=false kalır. Stratejik kalite/good-play
etiketi veya RL ödülü üretilmez.

Veri, mevcut public-game-rules zenginleştiricisi ve gerçek 385/383 girişli
kodlayıcılarla doğrulanır. Yeni ağ veya girdi genişletmesi yoktur. Train /
validation / test ataması oturum+maç anahtarıyla deterministiktir; komşu
kareler bölünmez. Yeterli ayrı oturum yoksa ayrılmış değerlendirme hazır
sayılmaz. Sonraki BC eğitici yalnız uygun train satırlarını kullanmalı;
validation/test/fixture verisini gradient güncellemesine almamalıdır.

## Doğrulama — 2026-11-05

16 ilgili Python kontrolü geçti. İnsan-log sahası için insanı model kontrolüne
almaya çalışan eski fixture varsayımı düzeltildi. İlgili kısa koşu yeni hata
ve son pre-state düzeltmeleri nedeniyle tekrarlandı; uzun maç yapılmadı.
Son 6 saniyelik koşuda 3 native pre-dispatch görüntüsü ve 2 birebir üretim/
iptal eşleşmesi doğrulandı. Gerçek kuyruk ekleme/çıkarma, para/CP/seçim/frame
tutarlılığı ve emir öncesi büyü puanları kontrol edildi. Görünen düşman
kayıttaydı, gizli fixture düşmanı yoktu. İnsan kontrolü değişmedi. Bütün
fixture örnekleri eğitimden dışlandı; aktif ağırlıklar korundu.

Eski gerçek insan kayıtları için AI-Egitim/bc-demonstrations-v1 raporu:
5 oturumdaki 2852 komutta yeni pre-dispatch politika görüntüsü yok; bunlar
kullanılabilir BC örneği değildir ve bir kısmı zaten UI/seçim emridir.
Yeni gerçek maçlar bu şemayı biriktirecek. Henüz gerçek BC ön eğitimi veya
oyun başarısı ölçümü yapılmadı.

Kanıt: `ai-mod-source/bc-demonstrations-verification.json`.
