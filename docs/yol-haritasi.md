# Afet Mesh Ağı — Yol Haritası

Projeyi baştan sona **numaralı adımlara** böler. Her adım küçüktür: bir kavram + birkaç kod bloğu + çalıştırıp doğrulama. Bir adım bitince kutusu işaretlenir (`[x]`).
Konum: `docs/yol-haritasi.md`. Takvim 13 hafta içindir; donanım gecikirse Faz 0–2 radyosuz ilerler.

**Donanım sütunu:** ✅ şu an elimizde var · 🛒 sipariş gerekir

---

## Faz 0 — Hazırlık ve Python simülasyonu (Hafta 1–3)
Amaç: protokolü donanımsız tasarlayıp doğrulamak, ilk grafikleri üretmek.

| # | Adım | Ne yapılır / çıktı | Donanım |
|---|------|--------------------|---------|
| 00 | [x] Ortam kurulumu | Repo klonu, Python venv, VS Code, git kimliği, `.gitignore` kontrolü, README, ilk commit | ✅ |
| 01 | [x] Düğümler ve radyo menzili | `Node` sınıfı, 2D yerleşim, log-mesafe kayıp modeli ile RSSI, "kim kimi duyar" komşuluk | ✅ |
| 02 | [x] Olay tabanlı simülasyon motoru | Zaman, olay kuyruğu, LoRa airtime formülü (SF, BW, CR, payload), duty cycle sayacı | ✅ |
| 03 | [x] Paket yapısı, HELLO, komşu tablosu | Paket alanları, periyodik HELLO, komşu tablosu (ID, RSSI, son görülme) | ✅ |
| 04 | [ ] Distance-vector yönlendirme | Gateway'e mesafe, sıra numarası, en iyi komşu seçimi, döngü önleme | ✅ |
| 05 | [ ] Veri iletimi | DATA paketi, TTL, çift paket bastırma, hop-hop ACK, sınırlı yeniden deneme | ✅ |
| 06 | [ ] Kanal erişimi | Çarpışma modeli, dinle-sonra-konuş, rastgele backoff | ✅ |
| 07 | [ ] Self-healing | Düğüm arızası, HELLO zaman aşımı, RERR, alternatif rota, **iyileşme süresi** ölçümü | ✅ |
| 08 | [ ] Deney altyapısı | PDR, gecikme, iyileşme süresi; çoklu tekrar, CSV çıktı, Matplotlib grafikleri | ✅ |
| 09 | [ ] GPS'siz konum prototipi | RSSI→mesafe, multilateration, IMU ölü hesap, Kalman filtresi, hata (m) analizi | ✅ |
| 10 | [ ] Güvenlik prototipi | AES-CCM (Python), nonce/sayaç, replay reddi, klon/sayaç anomali tespiti | ✅ |

**Faz 0 çıktısı:** çalışan simülasyon + iyileşme süresi ve PDR grafikleri (README için).

---

## Faz 1 — Raspberry Pi gateway, sahte radyo ile (Hafta 4–5)
Amaç: gerçek radyo olmadan gateway yazılımını tamamlamak.

| # | Adım | Ne yapılır / çıktı | Donanım |
|---|------|--------------------|---------|
| 11 | [ ] Pi hazırlığı | İşletim sistemi, SSH, Python ortamı, repo klonu | ✅ (microSD, 5 V/3 A güç doğrulanacak) |
| 12 | [ ] Paket çözücü ve SQLite | Paket doğrulama/çözme, veritabanı şeması, kayıt | ✅ |
| 13 | [ ] Sahte radyo ile besleme | Simülasyon çıktısını alıcı servise akıtan mock radyo | ✅ |
| 14 | [ ] Dashboard sunucusu | FastAPI uç noktaları, canlı veri (WebSocket/SSE) | ✅ |
| 15 | [ ] Dashboard arayüzü | Harita (Leaflet, çevrimdışı altlık), düğüm listesi, ağ sağlığı, mesajlar | ✅ |
| 16 | [ ] Fırsatçı köprü | Kalıcı kuyruk, bağlantı izleyici, uzak sunucu (FastAPI), benzersiz ID ile çift kayıt önleme, kes/aç demosu | ✅ |

**Faz 1 çıktısı:** dashboard + köprü demosu (internet kapat/aç).

---

## Faz 2 — STM32 protokol çekirdeği (Hafta 5–7)
Amaç: protokolü C'ye taşıyıp STM32'de radyosuz (UART ile) çalıştırmak.

| # | Adım | Ne yapılır / çıktı | Donanım |
|---|------|--------------------|---------|
| 17 | [ ] CubeIDE/CubeMX projesi | HAL projesi, SWV `printf`, iki kart arası UART kablolaması (TX↔RX çapraz, ortak GND, 3.3 V) | ✅ + 🛒 USB-TTL (3.3 V) önerilir |
| 18 | [ ] Radyo soyutlaması | `radio_if.h` arayüzü + UART sahte radyo sürücüsü | ✅ |
| 19 | [ ] Paket serileştirme | Pakete çevirme/ayrıştırma, CRC; bilgisayarda birim test | ✅ |
| 20 | [ ] HELLO ve komşu tablosu (C) | Simülasyondaki mantığın C karşılığı | ✅ |
| 21 | [ ] Yönlendirme, iletme, ACK (C) | Distance-vector, çift paket bastırma, ACK | ✅ |
| 22 | [ ] Self-healing (C) | Zaman aşımı, RERR, alternatif rota; 3–4 kartta zincir ve arıza testi | ✅ |
| 23 | [ ] Güvenlik (C) | AES-128 CCM (tiny-AES-c/mbedTLS), donanım RNG, replay koruması | ✅ |
| 24 | [ ] Zamanlayıcılar ve duty cycle | Airtime sayacı, periyodik görevler, düşük güç hazırlığı | ✅ |

**Faz 2 çıktısı:** birden çok STM32 kartında çalışan self-healing protokol (radyosuz).

---

## Faz 3 — Gerçek LoRa (Hafta 7–8)
Amaç: sahte radyoyu gerçek radyoyla değiştirmek, ölçüm yapmak.

| # | Adım | Ne yapılır / çıktı | Donanım |
|---|------|--------------------|---------|
| 25 | [ ] SX126x sürücüsü | SPI, başlatma, gönder/al; iki düğüm arası ilk mesaj | 🛒 LoRa modül + anten (en az 4) |
| 26 | [ ] Radyo ölçümü ve kalibrasyon | Gerçek RSSI/SNR/airtime; simülasyon parametrelerini gerçekle eşleştirme | 🛒 |
| 27 | [ ] 3-hop zincir | Gerçek çok hoplu iletim, gerçek self-healing ölçümü | 🛒 |
| 28 | [ ] Gateway'e gerçek radyo | Pi'ye LoRa modülü bağlama, mock radyonun yerine geçirme | 🛒 |

---

## Faz 4 — Saha düğümü özellikleri (Hafta 9–11)

| # | Adım | Ne yapılır / çıktı | Donanım |
|---|------|--------------------|---------|
| 29 | [ ] GPS ve beacon | NMEA ayrıştırma, periyodik beacon, ekip takibi | 🛒 GPS |
| 30 | [ ] TFT radar ve tuş takımı | Göreli konum ekranı, menü, SOS türleri | 🛒 TFT, tuş takımı |
| 31 | [ ] PIN, duress PIN, check-in | Tuzlu hash, deneme sınırı, challenge-response, sessiz alarm | 🛒 tuş takımı |
| 32 | [ ] ESP8266 captive portal | Wi-Fi AP, hazır mesajlar, UART ile STM32'ye iletim | 🛒 ESP8266 |
| 33 | [ ] GPS'siz konum (donanım) | IMU + RSSI + Kalman'ı gerçek düğümlerde deneme | 🛒 IMU |
| 34 | [ ] Enerji yönetimi | Uyku modları, INA219 ile ölçüm, enerji modeli | 🛒 INA219 |
| 35 | [ ] Opsiyoneller | Tamper anahtarı, 3D baskı kasa, Android uygulaması (zaman kalırsa) | 🛒 |

---

## Faz 5 — Final (Hafta 12–13)

| # | Adım | Ne yapılır / çıktı |
|---|------|--------------------|
| 36 | [ ] Ölçüm kampanyası | PDR, gecikme, iyileşme süresi, duty cycle, enerji, konum hatası; tekrarlı deneyler ve grafikler |
| 37 | [ ] Saha testi | Açık alanda uçtan uca demo, menzil, GPS doğruluğu |
| 38 | [ ] Rapor, sunum, demo | Rapor son hali, README'nin tamamlanması, demo videosu/GIF |

---

## Her adımın akışı
1. Kavram ve amaç anlatılır (neden bu adım?).
2. Kod küçük bloklar halinde yazılır; her blok açıklanır.
3. Çalıştırılıp beklenen çıktı doğrulanır.
4. Adım PDF'i hazırlanır (`docs/adimlar/`, yerelde kalır).
5. Küçük, anlamlı bir commit atılır (`feature/...` dalı, mesajı biz yazarız).

## Öncelik ve kesinti kuralı
Çekirdek: Faz 0 + Faz 2 + Faz 3 (mesh ve self-healing). Zaman daralırsa ilk çıkarılacaklar: adım 35 (Android, güneş paneli, kasa), sonra 34 ve 32.