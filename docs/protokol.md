# Protokol tanımı

Paket formatı ve yönlendirme kuralları. Simülasyondaki (`sim/`) uygulamanın özeti; STM32 C kodu aynı biçimi kullanacaktır.

## Paket formatı
Sabit başlık 8 bayt, ardından yük, ardından 4 bayt doğrulama etiketi. Toplam boyut = 8 + yük + 4.

| Alan | Boyut | Anlamı |
|---|---|---|
| src | 1 bayt | Paketi ilk üreten düğüm (röle yeniden yayınlasa da değişmez) |
| dst | 1 bayt | Nihai hedef (çoğunlukla gateway); 255 = yayın |
| next_hop | 1 bayt | Bu hop'ta paketi kimin ileteceği; 255 = herkes |
| ptype | 1 bayt | 1 HELLO, 2 DATA, 3 ACK, 4 RERR |
| seq | 2 bayt | Kaynağın artan sıra numarası; (src, seq) paketi benzersiz tanımlar |
| ttl | 1 bayt | Her aktarmada 1 azalır, 0 olunca paket atılır |
| last_hop | 1 bayt | Paketi bu hop'ta yayınlayan düğüm (ACK'in kime gideceğini belirler) |
| payload | n bayt | Yük |
| tag | 4 bayt | Doğrulama etiketi (AES-CCM ile doldurulacak; şimdilik yer ayrılmış) |

## Paket türleri
- **HELLO** (yayın, TTL 1): periyodik "ben buradayım". Yük 4 bayt, büyük uçlu (`>HBB`): gateway sıra numarası (2 bayt), gateway'e toplam maliyet (1 bayt), ilan edenin sonraki hop'u (1 bayt). Yolu olmayan düğüm yüksüz HELLO yollar.
- **DATA**: kaynaktan gateway'e, hop hop. Yalnızca `next_hop` kendisi olan düğüm işler.
- **ACK**: DATA'yı alan düğüm, `last_hop`'a 1 hop'luk ACK yollar; yük 1 bayt (DATA'nın `src` değeri), `seq` = DATA'nın `seq` değeri.
- **RERR**: yolu kaybeden düğümün komşularına yayını (TTL 1): "benim gateway'e yolum kalmadı".

## Yönlendirme (distance-vector, DSDV tabanlı)
- Gateway her HELLO'da sıra numarasını artırır, maliyet 0 ilan eder.
- Düğüm duyduğu ilana bağlantı maliyetini ekler. Bağlantı maliyeti RSSI'dan: >= -110 dBm: 1; -110 ile -118: 2; altı: 3. 255 = ulaşılamaz.
- Her komşunun son ilanı aday olarak tutulur; 15 sn (3 HELLO periyodu) ses vermeyen aday silinir.
- En ucuz aday seçilir; mevcut yoldan yalnızca kesin olarak daha ucuz aday varsa vazgeçilir (histerezis).
- İlan edenin sonraki hop'u bizsek aday sayılmaz (poison reverse).
- Sıra numarası dairesel karşılaştırılır: `0 < (a - b) mod 65536 < 32768` ise a daha yenidir.

## Veri iletimi
- Çift paket bastırma: (src, seq) çifti 256 kayıtlık listede görülmüşse paket iletilmez; yine de ACK yollanır.
- Hop-hop ACK: DATA 1 sn içinde ACK almazsa en fazla 3 kez yeniden gönderilir (yeniden gönderimde güncel yol kullanılır).
- Yeniden denemeler tükenirse sonraki hop ölü sayılır, yol değişir; yol kalmazsa RERR yayınlanır.
- Kanal erişimi: göndermeden önce dinle; doluysa rastgele bekle, pencere her denemede ikiye katlanır (en fazla 6 deneme).

## Havadaki bayt dizisi (kablo biçimi)
`sim/wire.py`: 8 bayt başlık + yük + 4 bayt etiket. Başlık biçimi `>BBBBHBB` (büyük uçlu): `src`, `dst`, `next_hop`, `ptype`, `seq` (2 bayt), `ttl`, `last_hop`. STM32 C kodu aynı biçimi kullanacak ve Python ile uyum testi yapılacak.

## Uygulama yükü (DATA içi, şifreli gider)
`gateway/receiver/report.py`: `>BhhBB` + metin. Alanlar: tür (1 durum, 2 SOS, 3 sensör), x ve y (işaretli 16 bit, gateway'e göre metre), pil yüzdesi (0-100), kod, ardından en çok 24 baytlık UTF-8 metin.

## Gateway kayıt kimliği
Her mesajın kimliği `kaynak:sayaç` (sayaç, güvenlik katmanının 32 bit çerçeve sayacı). Veritabanı, köprü kuyruğu ve uzak sunucu bu kimlikle çift kaydı önler (uzak sunucuda `(gateway, uid)` benzersizdir).

## Güvenli protokolün C uygulaması (`firmware/core/`)
- Tüm kareler (HELLO, DATA, ACK, RERR) AES-128-CCM ile mühürlenir; `seq` alanı düğümün 32 bit çerçeve sayacının alt 16 bitidir.
- **ACK yükü 3 bayt:** onaylanan paketin kaynağı (1 bayt) ve sıra numarası (2 bayt). ACK'in kendi `seq` değeri kendi çerçeve sayacıdır.
- Boyutlar: HELLO 16 bayt (8 + 4 + 4), ACK 15 bayt (8 + 3 + 4), RERR 12 bayt, DATA 12 + yük.
- Hop alanları (`next_hop`, `ttl`, `last_hop`) mühürlenmez; röle yalnızca bu baytları değiştirip kareyi aynen iletir, şifreyi çözmeden etiketi doğrular.
- Geç kabul penceresi: sayacı son kabul edilenden en çok 32 geride ve daha önce görülmemiş kare kabul edilir (sıra dışı gelen paketler).
- Zaman 32 bit milisaniye tamsayısıdır; radyo, rastgelelik ve teslim `afet_radio_if_t` ile verilir.
