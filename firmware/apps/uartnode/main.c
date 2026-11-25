#include <string.h>

#include "board.h"
#include "framing.h"
#include "node.h"
#include "uart.h"

/* UART üzerinden "sahte radyo": protokol düğümü kareleri SLIP çerçevelemesiyle seri hatta yollar.
 *
 * Derleme seçenekleri (scripts/build_firmware.py uartnode --core -D...):
 *   -DUART_LOOPBACK=1  tek kartta iki düğüm (1 = gateway, 2 = düğüm); USART kendi kendini dinler (kablo gerekmez)
 *   -DNODE_ID=n        iki kart arası: bu karttaki düğümün numarası (1 = gateway, diğerleri rapor yollar)
 * Kablolama (iki kart): A.PA2 -> B.PA3, A.PA3 -> B.PA2, GND-GND. Hepsi 3,3 V.
 * Çıktı RAM'deki log_buf tamponunda (scripts/flash.py uartnode --log). */

#ifndef UART_LOOPBACK
#define UART_LOOPBACK 0
#endif
#ifndef NODE_ID
#define NODE_ID 2
#endif
#define NN (UART_LOOPBACK ? 2 : 1)

#define LOG_SIZE 2048
volatile char log_buf[LOG_SIZE];
volatile uint32_t log_head;

static void log_c(char c)
{
    log_buf[log_head % LOG_SIZE] = c;
    log_head++;
}

static void log_s(const char *s)
{
    while (*s) {
        log_c(*s++);
    }
}

static void log_u(uint32_t v)
{
    char tmp[11];
    int n = 0;
    do {
        tmp[n++] = (char)('0' + v % 10);
        v /= 10;
    } while (v);
    while (n) {
        log_c(tmp[--n]);
    }
}

static const uint8_t KEY[16] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}; /* yalnızca deneme anahtarı */

static afet_node_t nodes[NN];
static afet_deframer_t deframer;
static uint32_t stored_ctr[NN], rng[NN];
static uint32_t frames_ok, frames_bad, tx_count, delivered, bytes_rx;
static volatile uint32_t pulse_green_until, pulse_blue_until;

static void radio_tx(void *ctx, const uint8_t *frame, size_t len)
{
    uint8_t out[2 * AFET_MAX_FRAME + 2];
    (void)ctx;
    size_t n = afet_frame_encode(frame, len, out, sizeof(out));
    if (n) {
        uart_write(out, n);
        tx_count++;
    }
}

static uint32_t radio_rand(void *ctx)
{
    uint32_t *s = &rng[(uintptr_t)ctx];
    uint32_t x = *s;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *s = x;
    return x;
}

static void persist(void *ctx, uint32_t reserved)
{
    stored_ctr[(uintptr_t)ctx] = reserved; /* gerçek cihazda flash'a yazılacak */
}

static void on_deliver(void *ctx, uint8_t src, const uint8_t *payload, size_t len, uint32_t counter, uint32_t t)
{
    (void)ctx;
    (void)src;
    (void)payload;
    (void)len;
    (void)counter;
    delivered++;
    pulse_green_until = t + 80;
}

static void start_nodes(void)
{
    for (unsigned i = 0; i < NN; i++) {
        afet_node_cfg_t cfg;
        afet_node_default_cfg(&cfg);
        cfg.csma = 0; /* UART tam çift yönlü: kanal dinleme yok */
        cfg.hello_period_ms = 1000; /* deneme için hızlı */
        cfg.timeout_ms = 3000;
        cfg.ack_timeout_ms = 500;
        afet_radio_if_t rif = {radio_tx, 0, radio_rand, (void *)(uintptr_t)i};
        uint8_t id = UART_LOOPBACK ? (uint8_t)(i + 1) : (uint8_t)NODE_ID;
        rng[i] = 2463534242u + 7919u * id;
        afet_node_init(&nodes[i], id, id == 1, &cfg, &rif, KEY, stored_ctr[i], persist, (void *)(uintptr_t)i, board_millis());
        if (id == 1) {
            afet_node_set_deliver(&nodes[i], on_deliver, 0);
        }
    }
}

static void print_summary(void)
{
    log_s("== UART sahte radyo, ");
    log_s(UART_LOOPBACK ? "tek kartta iç döngü (2 düğüm)" : "iki kart arası");
    log_s(" ==\nUART: ");
    log_u(UART_BAUD);
    log_s(" bayt/sn; alınan bayt ");
    log_u(bytes_rx);
    log_s(", geçerli çerçeve ");
    log_u(frames_ok);
    log_s(", bozuk çerçeve ");
    log_u(frames_bad);
    log_s(", yayınlanan kare ");
    log_u(tx_count);
    log_s(", taşma ");
    log_u(uart_overruns());
    log_c('\n');
    for (unsigned i = 0; i < NN; i++) {
        const afet_stats_t *st = &nodes[i].stats;
        log_s("  düğüm ");
        log_u(nodes[i].id);
        log_s(": rx ");
        log_u(st->rx_frames);
        log_s(" tx ");
        log_u(st->tx_frames);
        log_s(" ack ");
        log_u(st->acked);
        log_s(" yeniden ");
        log_u(st->retx);
        log_s(" vazgeç ");
        log_u(st->drop_retry);
        log_s(" güvenlik ");
        log_u(st->drop_security);
        log_s(" teslim ");
        log_u(st->delivered);
        log_s(" | yol: ");
        if (nodes[i].routing.route.valid) {
            log_u(nodes[i].routing.route.next_hop);
            log_s(" maliyet ");
            log_u(nodes[i].routing.route.metric);
        } else {
            log_s(nodes[i].is_gateway ? "gateway" : "yok");
        }
        log_c('\n');
    }
    log_s("<BITTI>\n");
}

int main(void)
{
    board_init();
    uart_init(UART_LOOPBACK);
    afet_deframer_init(&deframer);
    start_nodes();

    uint32_t next_report = 3000, k = 0, summary_at = 12000;
    int summarized = 0;
    for (;;) {
        uint32_t now = board_millis();
        int b;
        while ((b = uart_read_byte()) >= 0) {
            const uint8_t *f;
            size_t n;
            bytes_rx++;
            if (afet_deframer_push(&deframer, (uint8_t)b, &f, &n)) {
                frames_ok++;
                pulse_blue_until = now + 30;
                uint8_t copy[AFET_MAX_FRAME];
                memcpy(copy, f, n); /* düğümler yayın yaparken deframer tamponu değişmesin */
                for (unsigned i = 0; i < NN; i++) {
                    afet_node_on_rx(&nodes[i], copy, n, -100.0f, now);
                }
            }
        }
        for (unsigned i = 0; i < NN; i++) {
            if (afet_node_next_wakeup(&nodes[i]) <= now) {
                afet_node_tick(&nodes[i], now);
            }
        }
        if (now >= next_report) {
            next_report += 1000;
            for (unsigned i = 0; i < NN; i++) {
                if (!nodes[i].is_gateway) {
                    uint8_t id = (uint8_t)(k & 0xFF);
                    afet_node_send_data(&nodes[i], &id, 1, now);
                    k++;
                }
            }
        }
        if (!summarized && now >= summary_at) {
            summarized = 1;
            print_summary();
        }
        board_led(0, now < pulse_green_until);
        board_led(1, 0);
        board_led(2, uart_overruns() != 0);
        board_led(3, now < pulse_blue_until);
        __asm volatile("wfi");
    }
}
