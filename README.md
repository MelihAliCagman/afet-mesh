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
| 0 | Python simülasyonu (adım 00-10) | **devam ediyor** (adım 04 tamam) |
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

**Adım 03: Paket yapısı, HELLO ve komşu tablosu** (`sim/packet.py`, `sim/neighbor.py`, `sim/radio.py`, `sim/node.py`). Paket formatı (7 bayt başlık + yük + 4 bayt doğrulama etiketi) tanımlandı ve airtime hesabına bağlandı. Radyo ortamı, yayını menzildeki düğümlere airtime kadar sonra ve ölçülen RSSI ile ulaştırıyor. Her düğüm periyodik HELLO yayıp komşu tablosunu kendi kuruyor; sessiz kalan komşular zaman aşımıyla siliniyor.

Çalıştırma (proje kökünden): `python -m sim.node`

| Test | Sonuç |
|---|---|
| HELLO paketi, 2 bayt yük | 13 bayt, SF7'de 46,3 ms |
| Komşu tablosu, timeout 15 sn: sessizlik 13 sn / 16 sn | 13 sn'de kalır, 16 sn'de silinir |
| Timeout 5 sn | Sağlam komşu da yanlışlıkla silinir (yanlış alarm) |
| Radyo: 3 düğüm (0, 700, 1400 m), düğüm 1 yayın yapar | Yalnızca 700 m'deki düğüm alır (t = 1,041216 sn, -116,8 dBm) |
| Radyo: aynı paket SF12 | Alma zamanı 2,155072 sn (airtime 1155 ms, SF7'nin yaklaşık 28 katı) |
| Röle yeniden yayını | Paketin kaynak alanı değişmez; üretici kendi paketini geri duyar (yankı) |
| HELLO ile komşu keşfi, 4 düğüm, 700 m, 30 sn | `1 [2]`, `2 [1, 3]`, `3 [2, 4]`, `4 [3]`: haritasız, Adım 01'deki hesapla aynı |
| Aynı, 400 m arayla | Ağ sıklaşır: `1 [2, 3]`, `2 [1, 3, 4]`, `3 [1, 2, 4]`, `4 [2, 3]` |
| Aynı, yalnızca 3 sn | Keşif tamamlanmaz (ilk HELLO'lar rastgele), tablolar eksik |

Bulgular: (1) 5 sn'lik HELLO periyodu SF7'de bile %1 duty cycle bütçesinin yaklaşık %82'sini tüketiyor, bu yüzden periyot SF'ye göre seçilmeli. (2) Hassasiyet eşiği şimdilik SF'den bağımsız; SF12'nin menzil kazancı henüz modelde yok.

**Adım 04: Distance-vector yönlendirme** (`sim/routing.py`, `sim/node.py`). Gateway, HELLO paketlerinde kendi sıra numarasını ve maliyetini (0) ilan eder. Diğer düğümler duydukları ilanlara kendi bağlantı maliyetlerini ekleyip gateway'e giden en iyi komşuyu seçer ve kendi maliyetlerini ilan eder; bilgi her HELLO periyodunda bir hop ilerler. Bağlantı maliyeti RSSI'ya göre 1-3 arasındadır (zayıf bağlantı pahalı). Daha yeni sıra numaralı bilgi eskiye üstündür, eski numaralı bilgi kabul edilmez (döngü ve bayat yol önlemi); sıra numarası 65535'ten sonra 0'a döner.

Çalıştırma (proje kökünden): `python -m sim.node` (deneyler), `python -m sim.routing` (karar kuralları)

| Test | Sonuç |
|---|---|
| HELLO yükü (sıra numarası 2 bayt + maliyet 1 bayt) | Kodla-çöz gidiş-dönüş doğru; HELLO 14 bayt, SF7'de 46,3 ms (yük ek airtime getirmedi) |
| Sıra numarası taşması | 0, 65535'ten yeni sayılır (dairesel karşılaştırma) |
| Karar kuralları | Daha yeni numara kazanır; aynı numarada daha ucuz yol kazanır; eski numara reddedilir; yolu sağlayan komşu "ulaşılamıyor" derse yol silinir |
| 700 m aralıklı 4 düğüm zinciri | Yollar `2→1`, `3→2→1`, `4→3→2→1`; maliyetler 2, 4, 6 |
| 400 m aralıklı zincir | Düğüm 3, zayıf doğrudan bağlantı (maliyet 3) yerine iki sağlam hop'u (maliyet 2) seçer |
| Gateway'e 200 ve 400 m'de iki düğüm | 400 m'deki düğüm sağlam doğrudan bağlantıyı iki hop'a tercih eder |
| 3x3 ızgara (500 m aralık) | 8 düğümün tümü gateway'e ulaşır (en uzaklar 2 hop) |
| Döngü taraması | 12 farklı HELLO zamanlaması x 8 düğüm = 96 yol: döngü ve kopukluk yok |

Bulgular: (1) Gateway bilgisi zincirde her HELLO periyodunda bir hop yürür; uçtaki düğümün bilgisi gateway'in bir sıra numarası gerisinde kalır. (2) **Yol kararsızlığı:** iki seçenek arasında kalan düğümlerde (400 m zincirde düğüm 3: 60 sn'de 23 sonraki hop değişimi; ızgarada 2 düğüm: 80 sn'de 31'er) yol, her yeni sıra numarasında zayıf doğrudan bağlantı ile iki sağlam hop arasında gidip gelir. Döngü yoktur, hedefe ulaşılır; ama yol kararlı değildir. Çözümü, yol zaman aşımı ve hata bildirimiyle birlikte self-healing adımında (Adım 07) yapılacak; iyileşme süresi ölçümünden önce kararlı bir taban çizgisi gerekir.

**Sıradaki:** Adım 05, veri iletimi (DATA paketi, TTL, çift paket bastırma, hop-hop ACK).

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
