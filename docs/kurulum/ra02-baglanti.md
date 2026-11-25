# Ra-02 (SX1278, 433 MHz) bağlantı planı

**Uyarılar (önce okuyun)**
- Modül **3,3 V** ile çalışır (veri sayfası 2,5-3,7 V). **5 V'a asla bağlamayın.** Satıcı sayfası "3V-5V" yazsa bile.
- Kartları ve modülü **kapalı** bağlayın; 3V3 ve GND'yi en son takın.
- **Anten takılı değilken yayın yapmayın.** Yazılım gücü zaten 10 dBm'e (BTK 10 mW e.r.p.) sınırlar.
- 3V3 ile GND arasına modüle yakın 100 µF ve 100 nF kondansatör takın (elektrolitikte uzun uç +).
- Pin aralığı 2,54 mm olmalı; çıplak Ra-02 2 mm'dir ve dupont takılmaz.

## Pin planı (STM32F407G-DISC1, SPI2; kartta doğrulanacak)
| Ra-02 pini | STM32 pini | Görev |
|---|---|---|
| 3.3V | 3V | Besleme |
| GND | GND | Ortak toprak |
| NSS | PB12 | SPI çip seçimi |
| SCK | PB13 | SPI saat |
| MISO | PB14 | SPI veri (çipten karta) |
| MOSI | PB15 | SPI veri (karttan çipe) |
| RESET | PE7 | Çip sıfırlama |
| DIO0 | PE8 | Yayın/alım bitti kesmesi (yazmaç yoklamasıyla da çalışır, zorunlu değil) |

SPI1 (PA5-PA7) kartın ivmeölçeriyle paylaşıldığı için kullanılmadı.

## Yazılım
Sürücü: `firmware/drivers/sx127x/sx127x.[ch]` (SPI ve RESET `sx127x_hal_t` ile verilir, test: `pytest firmware/tests/test_sx127x.py`).
Varsayılan ayar: 433,175 MHz, SF7, 125 kHz, CR 4/5, 10 dBm, eşzamanlama sözcüğü 0x12.

## Yasal çerçeve (BTK Tablo-1, madde 15a)
433,05-434,79 MHz, 10 mW e.r.p., görev çevrimi en fazla %10. Sürücü bandın dışına çıkan frekansı ve 10 dBm üstü gücü kabul etmez; protokol %1 görev çevrimi uygular.
