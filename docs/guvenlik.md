# Güvenlik

Simülasyondaki prototip: `sim/security.py`. STM32 uygulaması Adım 23'te aynı biçimle yapılacaktır.

## Tehdit modeli
- **Dinleyen saldırgan:** havadaki paketleri duyar. Karşı önlem: yük şifreli (AES-128).
- **Sahtecilik:** saldırgan kendi paketini ağa sokmak ister. Karşı önlem: 4 baytlık doğrulama etiketi (MAC); anahtarı bilmeyen geçerli etiket üretemez.
- **Tekrar oynatma (replay):** saldırgan geçerli bir paketi kaydedip sonra yeniden yollar. Karşı önlem: her kaynağın artan sayacı.
- **Klon / çalınmış anahtar:** saldırgan bir düğümün anahtarını ve kimliğini kopyalar. Karşı önlem: tam önleme yok; sayaç anomalisi tespit edilip alarm üretilir.
- **Kapsam dışı:** radyo karıştırma (jamming), fiziksel erişimle anahtar okuma, yan kanal saldırıları.

## Biçim
- **AES-128-CCM**, 4 baytlık etiket (mevcut paket formatındaki `tag` alanı). CCM: aynı anahtarla hem şifreler hem doğrular.
- **Nonce (12 bayt):** kaynak (1) + paket türü (1) + 32 bit sayaç (4) + 6 sıfır. Aynı anahtarla aynı nonce'un tekrar kullanılması CCM'i bozar; bu yüzden sayaç asla tekrar etmemeli.
- **Sayaç:** her düğümün 32 bit çerçeve sayacı. Pakette yalnızca alt 16 bit (`seq`) taşınır; alıcı üst 16 biti önceki sayaçtan çıkarır (taşmayı da kapsar). Ek bayt maliyeti yoktur.
- **Doğrulanan başlık (AAD):** `src`, `dst`, `ptype`, `seq`. Hop'ta değişen `next_hop`, `ttl`, `last_hop` doğrulanmaz.
- **Anahtar:** repoda tutulmaz. `AFET_KEY_HEX` ortam değişkeninden okunur (yoksa süreç için rastgele üretilir). Gerçek cihazda anahtar flash'ta, repoda yalnızca `.env.example`.

## Alıcı kuralları
| Durum | Anlamı | Davranış |
|---|---|---|
| `ok` | Etiket geçerli, sayaç ileri | Kabul, sayaç güncellenir |
| `dup` | Aynı kare, son kabul edilenle özdeş | Atılır (yeniden gönderim) |
| `replay` | Daha önce kabul edilmiş eski kare | Atılır |
| `regression` | Etiket geçerli ama sayaç geride ve kare yeni | Atılır, anomali olayı |
| `jump` | Sayaç son değerin 1024'ten fazla ilerisinde | Atılır, anomali olayı |
| `bad_tag` | Etiket geçersiz | Atılır |

60 sn içinde 3 anomali olayı (`regression` veya `jump`) aynı kaynaktan gelirse **klon / sıfırlanma şüphesi alarmı** verilir.

## Kalıcı sayaç
Düğüm yeniden başlayınca sayaç geri dönerse meşru düğüm de `regression` verir (klon gibi görünür). Çözüm: flash'a her 64 karede bir "rezerv sınır" yazılır, açılışta sayaç bu sınırdan başlar (en çok 64 numara atlanır, flash aşınması düşük kalır).

## Bilinen sınırlar
- **Tek ortak ağ anahtarı:** bir düğüm ele geçirilirse tüm ağ anahtarı gider. Düğüm başına anahtar türetme (ör. ağ anahtarı + düğüm kimliği) ileride değerlendirilecek.
- **Hop alanları doğrulanmaz:** saldırgan `ttl` veya `next_hop`'u değiştirip paketi düşürtebilir (hizmet engelleme).
- **Çalınmış anahtarla ileri sayaç:** klon, meşru düğümün sayacının biraz ilerisinde (1024'ten az) başlarsa kabul edilir ve meşru düğümün sonraki kareleri reddedilir.
- **4 baytlık etiket:** rastgele tahminle kabul olasılığı kare başına 2^-32. LoRa'nın düşük hızı ve duty cycle sınırı nedeniyle saldırganın deneme sayısı sınırlıdır (20000 denemede 0 kabul).
- **Replay penceresi:** yalnızca son 64 kare özdeş mi diye karşılaştırılır; daha eski tekrarlar `regression` olarak sınıflanır.
