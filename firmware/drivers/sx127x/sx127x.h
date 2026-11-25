#ifndef SX127X_H
#define SX127X_H

#include <stddef.h>
#include <stdint.h>

/* SX1278 (Ra-02, 433 MHz) LoRa sürücüsü. Donanımdan bağımsız: SPI ve RESET dışarıdan verilir.
 *
 * Yasal sınırlar (BTK Tablo-1, madde 15a): 433,05-434,79 MHz, 10 mW e.r.p., görev çevrimi <= %10.
 * Sürücü bu sınırları aşan ayarı reddeder/kırpar:
 *   - çıkış gücü en fazla SX127X_MAX_DBM
 *   - taşıyıcı +- bant genişliği/2, 433,05-434,79 MHz aralığının dışına çıkamaz */

#define SX127X_MAX_DBM 10
#define SX127X_FREQ_MIN_HZ 433050000u
#define SX127X_FREQ_MAX_HZ 434790000u
#define SX127X_MAX_PAYLOAD 255

#define SX127X_OK 0
#define SX127X_ERR_CHIP -1   /* sürüm yazmacı 0x12 değil: kablo/besleme/pin hatası */
#define SX127X_ERR_PARAM -2  /* parametre sınır dışı */
#define SX127X_ERR_BUSY -3   /* yayın sürerken yeni yayın istendi */
#define SX127X_ERR_CRC -4    /* alınan paketin CRC'si bozuk */

typedef struct {
    /* NSS'yi içeride aşağı çekip bırakır; n bayt gönderir ve aynı anda alır (tx ve rx aynı uzunlukta). */
    void (*spi_xfer)(void *ctx, const uint8_t *tx, uint8_t *rx, size_t n);
    void (*reset)(void *ctx); /* RESET pinini düşük-yüksek yapar, çip hazır olana kadar bekler (>= 10 ms) */
    void *ctx;
} sx127x_hal_t;

typedef struct {
    uint32_t freq_hz;     /* taşıyıcı frekansı, ör. 433175000 */
    uint8_t sf;           /* 6..12 (SF6 desteklenmez: 7..12) */
    uint32_t bw_hz;       /* 125000, 250000 veya 500000; yasal bant için 125000 */
    uint8_t cr;           /* 5..8 (4/5 ... 4/8) */
    int8_t power_dbm;     /* istenen çıkış gücü; SX127X_MAX_DBM'e kırpılır, en az 2 */
    uint8_t sync_word;    /* 0x12 özel ağ */
    uint16_t preamble;    /* sembol sayısı, ör. 8 */
} sx127x_cfg_t;

typedef struct {
    sx127x_hal_t hal;
    sx127x_cfg_t cfg;
    uint8_t tx_busy;
} sx127x_t;

void sx127x_default_cfg(sx127x_cfg_t *cfg);
/* Sıfırlar, çipi doğrular, LoRa moduna alır ve ayarları yazar. */
int sx127x_init(sx127x_t *d, const sx127x_hal_t *hal, const sx127x_cfg_t *cfg);
/* Çıkış gücünü kırpılmış değere ayarlar, uygulanan dBm'i döndürür. */
int sx127x_set_power(sx127x_t *d, int dbm);
/* Yayını başlatır (bekleme yok). Bitince sx127x_poll() SX127X_EV_TX_DONE döndürür. */
int sx127x_send(sx127x_t *d, const uint8_t *data, size_t len);
/* Sürekli alım moduna girer. */
int sx127x_start_rx(sx127x_t *d);

#define SX127X_EV_NONE 0
#define SX127X_EV_TX_DONE 1
#define SX127X_EV_RX_DONE 2
#define SX127X_EV_RX_CRC_ERR 3

/* IRQ bayraklarına bakar (DIO0 pinini okumak yerine yazmaç yoklaması; her iki yolla da çalışır).
 * RX_DONE ise paketi buf'a okur (cap bayta kadar), uzunluğu *len'e, RSSI'yı (dBm) *rssi'ye yazar. Yayın bitince
 * çipi otomatik alım moduna döndürür. */
int sx127x_poll(sx127x_t *d, uint8_t *buf, size_t cap, size_t *len, float *rssi_dbm);
/* Kanal şu an meşgul mü (CSMA için): modem sinyal algıladıysa 1. */
int sx127x_channel_busy(sx127x_t *d);
/* Havada kalma süresi (mikrosaniye), lora_time.c ile aynı formül. */
uint32_t sx127x_airtime_us(const sx127x_t *d, size_t len);

#endif
