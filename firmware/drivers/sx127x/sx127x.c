#include "sx127x.h"

#include <string.h>

#include "lora_time.h"

/* SX1276/77/78/79 LoRa modu yazmaçları */
#define REG_FIFO 0x00
#define REG_OP_MODE 0x01
#define REG_FRF_MSB 0x06
#define REG_PA_CONFIG 0x09
#define REG_OCP 0x0B
#define REG_LNA 0x0C
#define REG_FIFO_ADDR_PTR 0x0D
#define REG_FIFO_TX_BASE 0x0E
#define REG_FIFO_RX_BASE 0x0F
#define REG_FIFO_RX_CURRENT 0x10
#define REG_IRQ_FLAGS 0x12
#define REG_RX_NB_BYTES 0x13
#define REG_PKT_SNR 0x19
#define REG_PKT_RSSI 0x1A
#define REG_MODEM_STAT 0x18
#define REG_MODEM_CONFIG1 0x1D
#define REG_MODEM_CONFIG2 0x1E
#define REG_PREAMBLE_MSB 0x20
#define REG_PAYLOAD_LENGTH 0x22
#define REG_MODEM_CONFIG3 0x26
#define REG_SYNC_WORD 0x39
#define REG_DIO_MAPPING1 0x40
#define REG_VERSION 0x42
#define REG_PA_DAC 0x4D

#define MODE_LORA 0x80
#define MODE_SLEEP 0x00
#define MODE_STDBY 0x01
#define MODE_TX 0x03
#define MODE_RX_CONT 0x05

#define IRQ_RX_DONE 0x40
#define IRQ_CRC_ERR 0x20
#define IRQ_TX_DONE 0x08

static uint8_t rd(sx127x_t *d, uint8_t reg)
{
    uint8_t tx[2] = {(uint8_t)(reg & 0x7F), 0}, rx[2];
    d->hal.spi_xfer(d->hal.ctx, tx, rx, 2);
    return rx[1];
}

static void wr(sx127x_t *d, uint8_t reg, uint8_t val)
{
    uint8_t tx[2] = {(uint8_t)(reg | 0x80), val}, rx[2];
    d->hal.spi_xfer(d->hal.ctx, tx, rx, 2);
}

static void set_mode(sx127x_t *d, uint8_t mode)
{
    wr(d, REG_OP_MODE, (uint8_t)(MODE_LORA | mode));
}

void sx127x_default_cfg(sx127x_cfg_t *cfg)
{
    cfg->freq_hz = 433175000u; /* 125 kHz bandın alt ucu 433,1125 MHz: 433,05 üstünde */
    cfg->sf = 7;
    cfg->bw_hz = 125000u;
    cfg->cr = 5;
    cfg->power_dbm = SX127X_MAX_DBM;
    cfg->sync_word = 0x12;
    cfg->preamble = 8;
}

static int bw_code(uint32_t bw)
{
    return bw == 125000u ? 7 : bw == 250000u ? 8 : bw == 500000u ? 9 : -1;
}

static int cfg_valid(const sx127x_cfg_t *c)
{
    if (c->sf < 7 || c->sf > 12 || c->cr < 5 || c->cr > 8 || bw_code(c->bw_hz) < 0) {
        return 0;
    }
    /* yasal bant: taşıyıcının iki yanındaki yarım bant genişliği dahil 433,05-434,79 MHz içinde kalmalı */
    uint32_t half = c->bw_hz / 2;
    if (c->freq_hz < SX127X_FREQ_MIN_HZ + half || c->freq_hz + half > SX127X_FREQ_MAX_HZ) {
        return 0;
    }
    return 1;
}

int sx127x_set_power(sx127x_t *d, int dbm)
{
    if (dbm > SX127X_MAX_DBM) {
        dbm = SX127X_MAX_DBM;
    }
    if (dbm < 2) {
        dbm = 2;
    }
    /* Ra-02 anteni PA_BOOST pinine bağlı: Pout = 2 + OutputPower (PaDac 0x84 varsayılanında, +17 dBm'e kadar) */
    wr(d, REG_PA_CONFIG, (uint8_t)(0x80 | (dbm - 2)));
    wr(d, REG_PA_DAC, 0x84);
    d->cfg.power_dbm = (int8_t)dbm;
    return dbm;
}

int sx127x_init(sx127x_t *d, const sx127x_hal_t *hal, const sx127x_cfg_t *cfg)
{
    memset(d, 0, sizeof(*d));
    d->hal = *hal;
    d->cfg = *cfg;
    if (!cfg_valid(cfg)) {
        return SX127X_ERR_PARAM;
    }
    d->hal.reset(d->hal.ctx);
    if (rd(d, REG_VERSION) != 0x12) {
        return SX127X_ERR_CHIP;
    }
    set_mode(d, MODE_SLEEP); /* LoRa moduna geçiş yalnızca uyku modunda yapılır */
    set_mode(d, MODE_STDBY);

    uint32_t frf = (uint32_t)(((uint64_t)cfg->freq_hz << 19) / 32000000u); /* Frf = f * 2^19 / Fxosc */
    wr(d, REG_FRF_MSB, (uint8_t)(frf >> 16));
    wr(d, (uint8_t)(REG_FRF_MSB + 1), (uint8_t)(frf >> 8));
    wr(d, (uint8_t)(REG_FRF_MSB + 2), (uint8_t)frf);

    /* ModemConfig1: BW [7:4], CR [3:1] (1 = 4/5), açık başlık (bit0 = 0) */
    wr(d, REG_MODEM_CONFIG1, (uint8_t)((bw_code(cfg->bw_hz) << 4) | ((cfg->cr - 4) << 1)));
    /* ModemConfig2: SF [7:4], yükün CRC'si açık (bit2) */
    wr(d, REG_MODEM_CONFIG2, (uint8_t)((cfg->sf << 4) | 0x04));
    /* ModemConfig3: sembol süresi 16 ms'yi aşarsa düşük veri hızı optimizasyonu (bit3), AGC otomatik (bit2) */
    uint32_t tsym_us = (uint32_t)(((uint64_t)(1u << cfg->sf) * 1000000u) / cfg->bw_hz);
    wr(d, REG_MODEM_CONFIG3, (uint8_t)((tsym_us > 16000u ? 0x08 : 0x00) | 0x04));
    wr(d, REG_PREAMBLE_MSB, (uint8_t)(cfg->preamble >> 8));
    wr(d, (uint8_t)(REG_PREAMBLE_MSB + 1), (uint8_t)cfg->preamble);
    wr(d, REG_SYNC_WORD, cfg->sync_word);
    wr(d, REG_OCP, 0x2B);   /* aşırı akım koruması 100 mA */
    wr(d, REG_LNA, 0x23);   /* en yüksek kazanç, LNA artırma */
    wr(d, REG_FIFO_TX_BASE, 0x00);
    wr(d, REG_FIFO_RX_BASE, 0x00);
    wr(d, REG_DIO_MAPPING1, 0x00); /* DIO0: RxDone (alım) ya da TxDone (yayın) */
    sx127x_set_power(d, cfg->power_dbm);
    return SX127X_OK;
}

int sx127x_start_rx(sx127x_t *d)
{
    wr(d, REG_IRQ_FLAGS, 0xFF);
    wr(d, REG_DIO_MAPPING1, 0x00);
    set_mode(d, MODE_RX_CONT);
    return SX127X_OK;
}

int sx127x_send(sx127x_t *d, const uint8_t *data, size_t len)
{
    if (len == 0 || len > SX127X_MAX_PAYLOAD) {
        return SX127X_ERR_PARAM;
    }
    if (d->tx_busy) {
        return SX127X_ERR_BUSY;
    }
    set_mode(d, MODE_STDBY);
    wr(d, REG_IRQ_FLAGS, 0xFF);
    wr(d, REG_FIFO_ADDR_PTR, 0x00);
    for (size_t i = 0; i < len; i++) {
        wr(d, REG_FIFO, data[i]);
    }
    wr(d, REG_PAYLOAD_LENGTH, (uint8_t)len);
    wr(d, REG_DIO_MAPPING1, 0x40); /* DIO0: TxDone */
    set_mode(d, MODE_TX);
    d->tx_busy = 1;
    return SX127X_OK;
}

int sx127x_poll(sx127x_t *d, uint8_t *buf, size_t cap, size_t *len, float *rssi_dbm)
{
    uint8_t irq = rd(d, REG_IRQ_FLAGS);
    if (irq & IRQ_TX_DONE) {
        wr(d, REG_IRQ_FLAGS, IRQ_TX_DONE);
        d->tx_busy = 0;
        sx127x_start_rx(d);
        return SX127X_EV_TX_DONE;
    }
    if (irq & IRQ_RX_DONE) {
        wr(d, REG_IRQ_FLAGS, 0xFF);
        if (irq & IRQ_CRC_ERR) {
            return SX127X_EV_RX_CRC_ERR;
        }
        uint8_t n = rd(d, REG_RX_NB_BYTES);
        wr(d, REG_FIFO_ADDR_PTR, rd(d, REG_FIFO_RX_CURRENT));
        size_t m = n < cap ? n : cap;
        for (size_t i = 0; i < n; i++) {
            uint8_t b = rd(d, REG_FIFO);
            if (i < m) {
                buf[i] = b;
            }
        }
        *len = m;
        /* LF portu (< 525 MHz): RSSI = -157 + PktRssi; SNR negatifse SNR/4 kadar düzeltilir (veri sayfası) */
        int8_t snr_raw = (int8_t)rd(d, REG_PKT_SNR);
        float snr = (float)snr_raw / 4.0f;
        float rssi = -157.0f + (float)rd(d, REG_PKT_RSSI);
        if (snr < 0) {
            rssi += snr;
        }
        *rssi_dbm = rssi;
        return SX127X_EV_RX_DONE;
    }
    return SX127X_EV_NONE;
}

int sx127x_channel_busy(sx127x_t *d)
{
    /* ModemStatus bit0: sinyal algılandı, bit1: sinyal senkronlandı */
    return (rd(d, REG_MODEM_STAT) & 0x03) != 0;
}

uint32_t sx127x_airtime_us(const sx127x_t *d, size_t len)
{
    double s = afet_lora_airtime((int)len, d->cfg.sf, (int)d->cfg.bw_hz, d->cfg.cr - 4, d->cfg.preamble, 1, 0);
    return (uint32_t)(s * 1e6);
}
