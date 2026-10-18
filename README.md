# Afet Mesh Ağı

LoRa tabanlı, kendini onaran afet iletişim ağı. Bilgisayar Mühendisliği bitirme projesi.

Baz istasyonu ve elektrik altyapısı çöktüğünde; STM32 saha/röle düğümleri çok hoplu mesh kurar, Raspberry Pi gateway verileri toplar ve dashboard'da gösterir. İnternet bulunduğunda veriler uzak sunucuya kayıpsız aktarılır.

## Özellikler (hedef)
- Çok hoplu, self-healing distance-vector yönlendirme (HELLO, ACK, RERR)
- AES-128 CCM ile şifreleme/doğrulama, replay koruması
- GPS'siz konum tahmini (RSSI + IMU + Kalman)
- Raspberry Pi gateway, SQLite, yerel dashboard
- Fırsatçı internet köprüsü (kalıcı kuyruk, çift kayıt önleme)

## Durum
Faz 0: Python simülasyonu devam ediyor. Adım listesi ve ilerleme: [docs/yol-haritasi.md](docs/yol-haritasi.md)

| Adım | Konu | Durum |
|---|---|---|
| 00 | Ortam kurulumu (repo, venv, `.gitignore`) | tamam |
| 01 | Düğümler, radyo menzili, komşuluk | tamam |
| 02 | Olay tabanlı simülasyon motoru, LoRa airtime | sırada |

## Simülasyon: düğümler ve radyo menzili
`sim/mesh_sim.py` ağın temelini tanımlar.

- **`Node`**: kimlik, 2D konum (metre) ve gateway olup olmadığını tutar.
- **`distance(a, b)`**: iki düğüm arası Öklid mesafesi.
- **`rssi(a, b)`**: log-mesafe yol kaybı modeliyle alıcıdaki sinyal gücü (dBm):

  `RSSI(d) = P_tx − PL(d0) − 10·n·log10(d / d0)`

  | Parametre | Değer | Anlamı |
  |---|---|---|
  | `P_tx` | 14 dBm | 868 MHz için tipik verici gücü |
  | `PL(d0)` | 31.2 dB | 1 m'deki serbest uzay kaybı |
  | `n` | 3.5 | yol kaybı üssü (şehir/enkaz varsayımı, ölçümle kalibre edilecek) |
  | hassasiyet | −123 dBm | bu değerin altındaki sinyal duyulmaz |

- **`can_hear(tx, rx)`** ve **`neighbors(node, nodes)`**: RSSI hassasiyet eşiğinin üstündeyse düğümler birbirinin komşusudur. Bu komşuluk ilişkisi ağın grafını oluşturur; yönlendirme bunun üzerinde çalışacak.

Bu modelde yol kaybı yalnızca mesafeye bağlıdır, bu yüzden bağlantılar simetriktir. Gerçek bağlantılardaki asimetri ve gölgeleme ileriki adımlarda eklenecek.

### Örnek
700 m arayla dizilmiş dört düğüm, her düğümün yalnızca yanındakini duyduğu bir zincir oluşturur:

```python
from sim.mesh_sim import Node, neighbors

nodes = [
    Node(1, 0.0, 0.0, is_gateway=True),
    Node(2, 700.0, 0.0),
    Node(3, 1400.0, 0.0),
    Node(4, 2100.0, 0.0),
]
for n in nodes:
    print(n.node_id, [m.node_id for m in neighbors(n, nodes)])
```

```
1 [2]
2 [1, 3]
3 [2, 4]
4 [3]
```

Düğüm 4'ün mesajı gateway'e 4 → 3 → 2 → 1 yoluyla, üç hopta ulaşır.

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
