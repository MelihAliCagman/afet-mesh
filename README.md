# Afet Mesh Ağı

LoRa tabanlı, kendini onaran afet iletişim ağı. Bilgisayar Mühendisliği bitirme projesi.

Baz istasyonu ve elektrik altyapısı çöktüğünde; STM32 saha/röle düğümleri çok hoplu mesh kurar, Raspberry Pi gateway verileri toplar ve dashboard'da gösterir. İnternet bulunduğunda veriler uzak sunucuya kayıpsız aktarılır.

## Özellikler (hedef)
- Çok hoplu, self-healing distance-vector yönlendirme (HELLO, ACK, RERR)
- AES-128 CCM ile şifreleme/doğrulama, replay koruması
- GPS'siz konum tahmini (RSSI + IMU + Kalman)
- Raspberry Pi gateway, SQLite, yerel dashboard
- Fırsatçı internet köprüsü (kalıcı kuyruk, çift kayıt önleme)

## Gerçekleme planı ve durum
Önce simülasyonda doğrulanır, sonra gerçek donanıma geçilir. Tam adım listesi: [docs/yol-haritasi.md](docs/yol-haritasi.md)

| Faz | İçerik | Durum |
|---|---|---|
| 0 | Python simülasyonu (adım 00-10) | **devam ediyor** (adım 02 tamam) |
| 1 | Raspberry Pi gateway, sahte radyo (adım 11-16) | bekliyor |
| 2 | STM32 protokol çekirdeği, UART sahte radyo (adım 17-24) | bekliyor |
| 3 | Gerçek LoRa (adım 25-28) | bekliyor (modül siparişi gerekli) |
| 4 | GPS, TFT, ESP8266, IMU, enerji (adım 29-35) | bekliyor |
| 5 | Ölçüm, saha testi, rapor (adım 36-38) | bekliyor |

### Tamamlanan adımlar ve test sonuçları

**Adım 00: Ortam kurulumu.** Repo, Python sanal ortamı, `.gitignore` ve ilk commit. Python 3.13 venv'inde `matplotlib` ve `pytest` kurulumu doğrulandı.

**Adım 01: Düğümler ve radyo menzili** (`sim/mesh_sim.py`). Düğümler 2D düzlemde konumlanır; log-mesafe yol kaybı modeliyle RSSI hesaplanır ve alıcı hassasiyet eşiğini (-123 dBm) aşan düğümler birbirinin komşusu sayılır.

| Test | Sonuç |
|---|---|
| 50 m'de mesafe ve RSSI | 50,0 m, -76,66 dBm (elle hesapla uyumlu) |
| 700 m arayla 4 düğüm | Her düğüm yalnızca yanındakini duyar: zincir, gateway'e 3 hop |
| 400 m arayla 4 düğüm | Ağ sıklaşır: düğümler 2'şer, 3'er komşu görür |
| 1100 m arayla düğümler | Hiçbir bağlantı kurulamaz: menzil sınırı ≈ 1050 m |
| Karışık yerleşim (3-4 arası 200 m) | Ağ üç ayrı parçaya bölünür: {1}, {2}, {3, 4} |

Bilinen sınır: model şimdilik yalnızca mesafeye bağlı olduğu için bağlantılar simetriktir. Gerçek ortamdaki asimetri ve gölgeleme ileriki adımlarda eklenecek. Yol kaybı üssü (3,5) bir varsayımdır; gerçek LoRa ölçümüyle (adım 26) kalibre edilecek.

**Adım 02: Olay motoru, LoRa airtime ve duty cycle** (`sim/engine.py`, `sim/lora.py`). Simülasyon zamanı olay kuyruğuyla yönetilir (saat olaydan olaya atlar). Bir LoRa paketinin havada kalma süresi resmi formülle hesaplanır; düğümün %1 duty cycle sınırı kayan 1 saatlik pencerede takip edilir.

| Test | Sonuç |
|---|---|
| Ters sırada eklenen olaylar | Zaman sırasıyla çalışır; aynı zamanlı olaylar ekleme sırasıyla |
| `run(until=1.5)` | 2,0 sn'deki olay çalışmaz, kuyrukta bekler |
| Periyodik HELLO, 2 düğüm, 30 sn | Düğüm 1: 7, düğüm 2: 6 HELLO, zamanlar beklenen gibi |
| Airtime, SF7, 20 bayt | 43 sembol, 56,576 ms (elle hesapla uyumlu) |
| Airtime, SF12, 20 bayt | 1,319 s (SF7'den ≈ 23 kat uzun) |
| Yük etkisi, SF7 | 10 bayt: 41,2 ms, 20 bayt: 56,6 ms, 51 bayt: 102,7 ms (basamaklı artış) |
| Duty cycle, SF12, 20 bayt | Saatte en fazla 27 paket (35,6 s); 28. paket reddedilir, 1 saat sonra bütçe yenilenir |

Bulgu: SF12 menzili artırır ama düğüm saatte yalnızca ~27 paket gönderebilir (ortalama 132 sn'de bir). HELLO ve SOS trafiği SF'ye göre tasarlanmalı.

**Sıradaki:** Adım 03, paket yapısı, HELLO ve komşu tablosu.

## Klasörler
| Klasör | İçerik |
|---|---|
| `sim/` | Python simülasyonu, konum prototipi, testler |
| `firmware/` | STM32 kodu; donanımdan bağımsız protokol çekirdeği |
| `gateway/` | Raspberry Pi: alıcı, dashboard, köprü |
| `remote-server/` | Uzak sunucu demosu |
| `hardware/` | Şemalar, malzeme listesi |
| `docs/` | Protokol, güvenlik, ölçümler, proje raporu |
| `scripts/` | Yardımcı betikler |

## Kurulum (simülasyon)
```
python -m venv venv
# Windows: venv\Scripts\activate    Linux: source venv/bin/activate
pip install -r requirements.txt
```

## Yazarlar
Ayşe, Melih Ali Çağman — Danışman: Prof. Fecir Duran
