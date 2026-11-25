/* SX1278 yazmaç düzeyinde sahte çip: sürücüyü kart ve modül olmadan sınamak için. Yalnızca testlerde derlenir. */
#include <stdint.h>
#include <string.h>

#include "sx127x.h"

static uint8_t regs[128];
static uint8_t fifo[256];
static uint8_t tx_copy[256];
static int tx_len, tx_count, reset_count, version_override = -1;

static void mock_reset_state(void)
{
    memset(regs, 0, sizeof(regs));
    memset(fifo, 0, sizeof(fifo));
    regs[0x42] = (uint8_t)(version_override >= 0 ? version_override : 0x12);
    tx_len = 0;
    tx_count = 0;
}

static void spi(void *ctx, const uint8_t *tx, uint8_t *rx, size_t n)
{
    (void)ctx;
    uint8_t reg = tx[0] & 0x7F, wr = tx[0] & 0x80;
    rx[0] = 0;
    for (size_t i = 1; i < n; i++) {
        if (reg == 0x00) { /* FIFO: adres işaretçisi otomatik artar */
            uint8_t p = regs[0x0D]++;
            if (wr) {
                fifo[p] = tx[i];
            } else {
                rx[i] = fifo[p];
            }
        } else if (wr) {
            if (reg == 0x12) {
                regs[0x12] &= (uint8_t)~tx[i]; /* IRQ bayrakları 1 yazılarak temizlenir */
            } else {
                regs[reg] = tx[i];
                if (reg == 0x01 && (tx[i] & 0x07) == 3) { /* TX moduna geçildi: yayın anında biter */
                    tx_len = regs[0x22];
                    memcpy(tx_copy, fifo + regs[0x0E], (size_t)tx_len);
                    tx_count++;
                    regs[0x12] |= 0x08;
                }
            }
        } else {
            rx[i] = regs[reg];
        }
    }
}

static void do_reset(void *ctx)
{
    (void)ctx;
    reset_count++;
    mock_reset_state();
}

static sx127x_t dev;

void mock_set_version(int v) { version_override = v; }
int mock_reset_count(void) { return reset_count; }
int mock_reg(int r) { return regs[r & 0x7F]; }
int mock_tx_count(void) { return tx_count; }
int mock_tx_len(void) { return tx_len; }
int mock_tx_byte(int i) { return tx_copy[i]; }

void mock_inject_rx(const uint8_t *data, int len, int pkt_rssi, int snr_raw, int crc_ok)
{
    memcpy(fifo, data, (size_t)len);
    regs[0x10] = 0;
    regs[0x13] = (uint8_t)len;
    regs[0x1A] = (uint8_t)pkt_rssi;
    regs[0x19] = (uint8_t)snr_raw;
    regs[0x12] |= (uint8_t)(0x40 | (crc_ok ? 0 : 0x20));
}

int t_init(uint32_t freq, int sf, uint32_t bw, int cr, int power)
{
    sx127x_hal_t hal = {spi, do_reset, 0};
    sx127x_cfg_t cfg;
    sx127x_default_cfg(&cfg);
    cfg.freq_hz = freq;
    cfg.sf = (uint8_t)sf;
    cfg.bw_hz = bw;
    cfg.cr = (uint8_t)cr;
    cfg.power_dbm = (int8_t)power;
    return sx127x_init(&dev, &hal, &cfg);
}

int t_send(const uint8_t *d, int n) { return sx127x_send(&dev, d, (size_t)n); }
int t_rx(void) { return sx127x_start_rx(&dev); }
int t_power(int dbm) { return sx127x_set_power(&dev, dbm); }
int t_busy(void) { return sx127x_channel_busy(&dev); }
unsigned t_airtime(int n) { return sx127x_airtime_us(&dev, (size_t)n); }

int t_poll(uint8_t *buf, int cap, int *len, float *rssi)
{
    size_t l = 0;
    int ev = sx127x_poll(&dev, buf, (size_t)cap, &l, rssi);
    *len = (int)l;
    return ev;
}
