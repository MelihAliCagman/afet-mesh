#include <math.h>
#include <string.h>

#include "board.h"
#include "lora_time.h"
#include "node.h"

/* Tek kartın içinde 6 düğümlü LoRa ağı: protokol çekirdeği (afet_node_t) gerçek işlemcide koşar, radyo yazılımla taklit edilir
 * (menzil ve gecikme gerçek airtime formülüyle). Faz 1: sanal zamanda hızlı deney ve ölçüm. Faz 2: gerçek zamanda LED demosu;
 * USER düğmesi düğüm 6'nın yolundaki düğümü kapatır/açar. Çıktı RAM'deki log_buf tamponunda (scripts/flash.py --log). */

#define N 6
#define QSIZE 48
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

/* ---------------- ağ: elmas topolojisi, iki ayrık yol (1-2-4-6 ve 1-3-5-6) ---------------- */
static const float pos[N][2] = {{0, 0}, {400, 250}, {400, -250}, {800, 250}, {800, -250}, {1200, 0}};
static const uint8_t KEY[16] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}; /* yalnızca deneme anahtarı */

typedef struct {
    uint32_t due;
    uint8_t used, dst, len;
    float rssi;
    uint8_t frame[AFET_MAX_FRAME];
} delivery_t;

static afet_node_t nodes[N];
static delivery_t q[QSIZE];
static float rssi_m[N][N];
static uint32_t rng[N], stored_ctr[N], now_ms, dropped_q;
static uint32_t tx_frames;

#define HEARD_DBM (-123.0f)

static void build_links(void)
{
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            float dx = pos[i][0] - pos[j][0], dy = pos[i][1] - pos[j][1];
            float d = sqrtf(dx * dx + dy * dy);
            rssi_m[i][j] = d < 1.0f ? 99.0f : 14.0f - 31.2f - 35.0f * log10f(d);
        }
    }
}

static void radio_tx(void *ctx, const uint8_t *frame, size_t len)
{
    unsigned from = (unsigned)(uintptr_t)ctx;
    uint32_t air = (uint32_t)(afet_lora_airtime((int)len, 7, 125000, 1, 8, 1, 0) * 1000.0 + 0.999);
    tx_frames++;
    for (unsigned to = 0; to < N; to++) {
        if (to == from || rssi_m[from][to] < HEARD_DBM) {
            continue;
        }
        int slot = -1;
        for (int k = 0; k < QSIZE; k++) {
            if (!q[k].used) {
                slot = k;
                break;
            }
        }
        if (slot < 0) {
            dropped_q++;
            continue;
        }
        q[slot].used = 1;
        q[slot].due = now_ms + air;
        q[slot].dst = (uint8_t)to;
        q[slot].len = (uint8_t)len;
        q[slot].rssi = rssi_m[from][to];
        memcpy(q[slot].frame, frame, len);
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
    stored_ctr[(uintptr_t)ctx] = reserved; /* kartta bu değer flash'a yazılacak */
}

/* ---------------- ölçüm kayıtları ---------------- */
#define MAX_REPORTS 64
static uint32_t sent_at[MAX_REPORTS], delivered_at[MAX_REPORTS];
static uint8_t is_sent[MAX_REPORTS], is_delivered[MAX_REPORTS];
static uint32_t gw_delivered;
static volatile uint32_t demo_delivered_flag;

static void on_deliver(void *ctx, uint8_t src, const uint8_t *payload, size_t len, uint32_t counter, uint32_t t)
{
    (void)ctx;
    (void)counter;
    (void)src;
    gw_delivered++;
    demo_delivered_flag = 1;
    if (len == 1 && payload[0] < MAX_REPORTS && !is_delivered[payload[0]]) {
        is_delivered[payload[0]] = 1;
        delivered_at[payload[0]] = t;
    }
}

static void node_start(unsigned i, uint32_t t, int fresh)
{
    afet_node_cfg_t cfg;
    afet_node_default_cfg(&cfg);
    cfg.csma = 0; /* kanal ideal: çarpışma modeli yok */
    afet_radio_if_t rif = {radio_tx, 0, radio_rand, (void *)(uintptr_t)i};
    if (fresh) {
        stored_ctr[i] = 0;
        rng[i] = 2463534242u + 7919u * i;
    }
    afet_node_init(&nodes[i], (uint8_t)(i + 1), i == 0, &cfg, &rif, KEY, stored_ctr[i], persist, (void *)(uintptr_t)i, t);
    if (i == 0) {
        afet_node_set_deliver(&nodes[0], on_deliver, 0);
    }
}

static void net_reset(void)
{
    memset(q, 0, sizeof(q));
    memset(is_sent, 0, sizeof(is_sent));
    memset(is_delivered, 0, sizeof(is_delivered));
    now_ms = 0;
    gw_delivered = 0;
    tx_frames = 0;
    dropped_q = 0;
    for (unsigned i = 0; i < N; i++) {
        node_start(i, 0, 1);
    }
}

/* Bir sonraki olayın zamanı: radyo teslimi veya bir düğümün zamanlayıcısı */
static uint32_t next_event(void)
{
    uint32_t t = AFET_NEVER;
    for (int k = 0; k < QSIZE; k++) {
        if (q[k].used && q[k].due < t) {
            t = q[k].due;
        }
    }
    for (unsigned i = 0; i < N; i++) {
        uint32_t w = afet_node_next_wakeup(&nodes[i]);
        if (w < t) {
            t = w;
        }
    }
    return t;
}

static void process_at(uint32_t t)
{
    now_ms = t;
    for (int k = 0; k < QSIZE; k++) {
        if (q[k].used && q[k].due <= t) {
            /* Kareyi yerel kopyaya al: düğüm yanıt yayınlayınca (ACK) kuyrukta aynı yuva yeniden kullanılabilir */
            uint8_t frame[AFET_MAX_FRAME];
            unsigned dst = q[k].dst, len = q[k].len;
            float rssi = q[k].rssi;
            memcpy(frame, q[k].frame, len);
            q[k].used = 0;
            afet_node_on_rx(&nodes[dst], frame, len, rssi, t);
        }
    }
    for (unsigned i = 0; i < N; i++) {
        if (afet_node_next_wakeup(&nodes[i]) <= t) {
            afet_node_tick(&nodes[i], t);
        }
    }
}

static void log_path(unsigned from)
{
    unsigned cur = from;
    for (int hops = 0; hops < N; hops++) {
        log_u(cur + 1);
        if (nodes[cur].is_gateway) {
            return;
        }
        if (!nodes[cur].routing.route.valid) {
            log_s(" (yol yok)");
            return;
        }
        log_s(" > ");
        cur = (unsigned)nodes[cur].routing.route.next_hop - 1;
    }
    log_s(" (döngü?)");
}

/* ---------------- faz 1: sanal zamanda hızlı deney ---------------- */
#define REPORTS 40
#define REPORT_PERIOD 2000u
#define T_FIRST_REPORT 60000u
#define T_KILL 110000u
#define T_END 200000u

static void experiment(void)
{
    net_reset();
    uint32_t t0 = board_cycles();
    uint32_t next_report = T_FIRST_REPORT, sent = 0, events = 0;
    int killed = 0, logged_converged = 0;

    for (;;) {
        uint32_t t = next_event();
        if (sent < REPORTS && next_report < t) {
            t = next_report;
        }
        if (!killed && T_KILL < t) {
            t = T_KILL;
        }
        if (t > T_END) {
            break;
        }
        process_at(t);
        events++;
        if (!logged_converged && nodes[N - 1].routing.route.valid && t > 10000) {
            logged_converged = 1;
            log_s("  yol öğrenildi t=");
            log_u(t / 1000);
            log_s(" sn: düğüm 6 yolu: ");
            log_path(N - 1);
            log_s(" (maliyet ");
            log_u(nodes[N - 1].routing.route.metric);
            log_s(")\n");
        }
        if (sent < REPORTS && t >= next_report) {
            uint8_t k = (uint8_t)sent;
            if (afet_node_send_data(&nodes[N - 1], &k, 1, t)) {
                is_sent[k] = 1;
                sent_at[k] = t;
            }
            sent++;
            next_report += REPORT_PERIOD;
        }
        if (!killed && t >= T_KILL) {
            killed = 1;
            unsigned victim = nodes[N - 1].routing.route.valid ? (unsigned)nodes[N - 1].routing.route.next_hop - 1 : 1;
            afet_node_kill(&nodes[victim]);
            log_s("  t=");
            log_u(t / 1000);
            log_s(" sn: düğüm ");
            log_u(victim + 1);
            log_s(" kapatıldı (düğüm 6'nın yolu üzerindeydi: ");
            log_path(N - 1);
            log_s(")\n");
        }
    }
    uint32_t cyc = board_cycles() - t0;

    uint32_t pre_sent = 0, pre_ok = 0, post_sent = 0, post_ok = 0, recovery = AFET_NEVER;
    for (unsigned k = 0; k < REPORTS; k++) {
        if (!is_sent[k]) {
            continue;
        }
        if (sent_at[k] < T_KILL) {
            pre_sent++;
            pre_ok += is_delivered[k];
        } else {
            post_sent++;
            post_ok += is_delivered[k];
            if (is_delivered[k] && delivered_at[k] - T_KILL < recovery) {
                recovery = delivered_at[k] - T_KILL;
            }
        }
    }
    uint32_t retx = 0, acked = 0, dr_retry = 0, dr_sec = 0;
    for (unsigned i = 0; i < N; i++) {
        retx += nodes[i].stats.retx;
        acked += nodes[i].stats.acked;
        dr_retry += nodes[i].stats.drop_retry;
        dr_sec += nodes[i].stats.drop_security;
    }
    log_s("sonuçlar (sanal süre ");
    log_u(T_END / 1000);
    log_s(" sn):\n  arızadan önce teslim: ");
    log_u(pre_ok);
    log_c('/');
    log_u(pre_sent);
    log_s("\n  arızadan sonra teslim: ");
    log_u(post_ok);
    log_c('/');
    log_u(post_sent);
    log_s("\n  iyileşme süresi (arızadan sonra gönderilen ilk paketin teslimi): ");
    if (recovery == AFET_NEVER) {
        log_s("iyileşmedi");
    } else {
        log_u(recovery);
        log_s(" ms");
    }
    log_s("\n  düğüm 6 son yolu: ");
    log_path(N - 1);
    log_s("\n  yayınlanan kare: ");
    log_u(tx_frames);
    log_s(", yeniden gönderim: ");
    log_u(retx);
    log_s(", ACK: ");
    log_u(acked);
    log_s(", vazgeçilen: ");
    log_u(dr_retry);
    log_s(", güvenlik reddi: ");
    log_u(dr_sec);
    log_s(", kuyruk taşması: ");
    log_u(dropped_q);
    log_s("\n  işlemci zamanı: ");
    log_u((uint32_t)((uint64_t)cyc * 1000u / board_cpu_hz()));
    log_s(" ms (");
    log_u(events);
    log_s(" olay; ");
    log_u((uint32_t)((uint64_t)T_END * board_cpu_hz() / ((uint64_t)cyc * 1000u > 0 ? (uint64_t)cyc : 1u) / 1000u));
    log_s(" kat gerçek zamandan hızlı)\n");
    log_s("düğüm istatistikleri (rx tx ack retx ttl yolyok vazgec guvenlik teslim):\n");
    for (unsigned i = 0; i < N; i++) {
        const afet_stats_t *st = &nodes[i].stats;
        log_s("  #");
        log_u(i + 1);
        uint32_t v[9] = {st->rx_frames, st->tx_frames, st->acked, st->retx, st->drop_ttl, st->drop_no_route, st->drop_retry, st->drop_security, st->delivered};
        for (int j = 0; j < 9; j++) {
            log_c(' ');
            log_u(v[j]);
        }
        log_s(" | yol: ");
        if (nodes[i].routing.route.valid) {
            log_u(nodes[i].routing.route.next_hop);
            log_s(" maliyet ");
            log_u(nodes[i].routing.route.metric);
        } else {
            log_s("yok");
        }
        log_c('\n');
    }
    log_s("<BITTI>\n");
}

/* ---------------- faz 2: gerçek zamanda LED demosu ----------------
 * yeşil: gateway'e veri ulaştı | turuncu: yeniden gönderim | kırmızı: bir düğüm kapalı | mavi: düğüm 6 yolu değişti
 * USER düğmesi: düğüm 6'nın yolundaki düğümü kapat / yeniden aç (sayaçlar korunarak) */
static void realtime_demo(void)
{
    net_reset();
    uint32_t base = board_millis();
    uint32_t next_report = 10000, retx_seen = 0, last_hop = 0, pulse_until[4] = {0, 0, 0, 0};
    int dead = 0, button_prev = 0;
    unsigned victim = 1;
    uint32_t k = 0;
    for (;;) {
        uint32_t real = board_millis() - base;
        uint32_t t = next_event();
        if (next_report < t) {
            t = next_report;
        }
        if (t <= real) {
            process_at(t);
            if (t >= next_report) {
                uint8_t id = (uint8_t)(k++ % MAX_REPORTS);
                afet_node_send_data(&nodes[N - 1], &id, 1, t);
                next_report += 3000;
            }
            if (demo_delivered_flag) {
                demo_delivered_flag = 0;
                pulse_until[0] = real + 80;
            }
            uint32_t rt = 0;
            for (unsigned i = 0; i < N; i++) {
                rt += nodes[i].stats.retx;
            }
            if (rt != retx_seen) {
                retx_seen = rt;
                pulse_until[1] = real + 150;
            }
            uint32_t hop = nodes[N - 1].routing.route.valid ? nodes[N - 1].routing.route.next_hop : 0;
            if (hop != last_hop) {
                if (last_hop != 0) {
                    pulse_until[3] = real + 600;
                    log_s("t=");
                    log_u(real / 1000);
                    log_s(" sn: düğüm 6 sonraki hop ");
                    log_u(last_hop);
                    log_s(" -> ");
                    log_u(hop);
                    log_c('\n');
                }
                last_hop = hop;
            }
        }
        int b = board_button();
        if (b && !button_prev) {
            if (!dead) {
                victim = nodes[N - 1].routing.route.valid ? (unsigned)nodes[N - 1].routing.route.next_hop - 1 : 1;
                afet_node_kill(&nodes[victim]);
                dead = 1;
                log_s("düğüm ");
                log_u(victim + 1);
                log_s(" kapatıldı\n");
            } else {
                node_start(victim, real, 0);
                dead = 0;
                log_s("düğüm ");
                log_u(victim + 1);
                log_s(" yeniden açıldı (sayaç ");
                log_u(stored_ctr[victim]);
                log_s("'dan devam)\n");
            }
        }
        button_prev = b;
        for (unsigned i = 0; i < 4; i++) {
            board_led(i, i == 2 ? dead : real < pulse_until[i]);
        }
        __asm volatile("wfi");
    }
}

int main(void)
{
    board_init();
    board_cycles_start();
    build_links();
    log_s("== 6 düğümlü ağ, tek STM32F407 kartında ==\n");
    log_s("topoloji: 1 (gateway) - 2,3 - 4,5 - 6; iki ayrık yol; çekirdek saati ");
    log_u(board_cpu_hz() / 1000000u);
    log_s(" MHz\n");
    experiment();
    realtime_demo();
    return 0;
}
