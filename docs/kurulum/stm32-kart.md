# STM32F4DISCOVERY kartı: derleme, yükleme, log ve iki kart arası UART

Yalnızca Windows ve STM32CubeIDE kurulu olmalı (derleyici ve programlayıcı CubeIDE ile gelir). Başka kurulum gerekmez.

## 1. Hazırlık
- Kartı bilgisayara **mini-USB** (ST-LINK portu, "USB ST-LINK" yazan) ile bağlayın. Her kart ayrı kabloyla bağlanır.
- Kartlar ödünçse **yazmadan önce sahibinden izin alın** ve özgün yazılımı yedekleyin:
  `STM32_Programmer_CLI -c port=SWD -r 0x08000000 0x100000 C:\afet-yedek\stm32\yedek.bin` (1 MB flash'ı okur, hiçbir şey yazmaz).
- Özgün yazılımı geri yüklemek için: `python scripts/flash.py --restore C:\afet-yedek\stm32\yedek.bin`.
- Bağlı kartları listelemek için: `python scripts/flash.py --list` (her ST-LINK'in seri numarası görünür).

## 2. Derle, yükle, log oku (proje kökünden)
```
python scripts/build_firmware.py blink                     # LED denemesi
python scripts/flash.py blink

python scripts/build_firmware.py selftest --core           # C çekirdeğinin kartta öz-sınaması
python scripts/flash.py selftest --log

python scripts/build_firmware.py meshsim --core -DAFET_MAX_SRC=6   # tek kartta 6 düğümlü ağ
python scripts/flash.py meshsim --log
```
- Program çıktısı kartın RAM'indeki bir tampona yazılır; `--log` yüklemeden sonra bu tamponu okur (ek donanım gerekmez).
- Birden çok kart bağlıyken `--sn <seri no>` verin, yoksa ilk bulunan karta yazılır.
- Program uzun sürüyorsa `--wait <sn>` ile okumadan önce bekleme süresini artırın. Yalnızca logu okumak için `--log-only`.
- Her bağlantı kartı yeniden başlatabilir; program çıktısı bitmeden okunursa eksik görünür. `--log-only` tekrar çalıştırmak yeter.

## 3. UART ile iki kart arası sahte radyo
Protokol düğümü karelerini **USART2** üzerinden (PA2 = TX, PA3 = RX, 115200 bayt/sn) SLIP çerçevelemesiyle yollar.

**Önce tek kartta sürücü testi (kablo gerekmez):**
```
python scripts/build_firmware.py uartnode --core -DUART_LOOPBACK=1
python scripts/flash.py uartnode --log --wait 14
```
Beklenen: "geçerli çerçeve" sayısı yayınlanan kareye (bir eksiğine kadar) eşit, "taşma 0", düğüm 2'nin yolu `1 maliyet 1`, düğüm 2'nin 9 raporu "teslim" sayılır.

**İki kartla:**
1. Kablolama (hepsi **3,3 V**, **TX çapraz RX'e**, **ortak GND**):

| Kart A | Kart B |
|---|---|
| PA2 (TX) | PA3 (RX) |
| PA3 (RX) | PA2 (TX) |
| GND | GND |

   Uyarılar: Kartlar kapalıyken bağlayın. 5 V'luk bir hatta (Arduino, 5 V pini) **bağlamayın**. TX'i TX'e bağlarsanız hiçbir şey olmaz ama haberleşme de olmaz, kontrol edin. Her iki kartın GND'si birleşmeli.
2. Kart A gateway olsun (düğüm 1), kart B rapor yollayan düğüm (düğüm 2):
```
python scripts/build_firmware.py uartnode --core -DNODE_ID=1
python scripts/flash.py uartnode --sn <A kartının seri no> --log --wait 14
python scripts/build_firmware.py uartnode --core -DNODE_ID=2
python scripts/flash.py uartnode --sn <B kartının seri no> --log --wait 14
```
3. Kart A'nın logunda `düğüm 1: ... teslim N`, kart B'nin logunda `düğüm 2: ... ack N`, `yol: 1 maliyet 1` görülmelidir. Yeşil LED gateway'e rapor ulaştığında, mavi LED çerçeve alındığında yanar; kırmızı LED UART taşması olursa yanar.

## 4. Sık karşılaşılan sorunlar
- **"Unable to get core ID":** İşlemci uyuyorken hata ayıklayıcı bağlanamıyor. Yazılımlarımız bunu önlüyor (`DBGMCU` ayarı). Olursa karta "sıfırlama sırasında bağlanma" ile erişilir: `STM32_Programmer_CLI -c port=SWD mode=UR reset=HWrst`.
- **Log boş çıkıyor:** Program henüz bitmemiş olabilir, `--wait` artırın ya da `--log-only` ile tekrar okuyun.
- **Derleme "bulunamadı" diyor:** STM32CubeIDE `C:\ST\` altında kurulu olmalı.
- **İki kartta aynı seri numarası görünmüyor:** Her karta ayrı USB kablosu ve portu verin.
