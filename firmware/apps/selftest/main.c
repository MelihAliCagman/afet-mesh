#include <string.h>

#include "board.h"
#include "lora_time.h"
#include "routing.h"
#include "security.h"
#include "vectors.h"
#include "wire.h"

/* Karttaki öz-sınama: Python'dan üretilen vektörlerle C çekirdeğini karşılaştırır, süreleri ölçer.
 * Çıktı RAM'deki log_buf tamponuna yazılır; bilgisayar SWD ile okur (scripts/flash.py --log). */

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

static int failures;

static void report(const char *name, int ok)
{
    log_s(ok ? "[GECTI] " : "[KALDI] ");
    log_s(name);
    log_c('\n');
    if (!ok) {
        failures++;
    }
}

static uint32_t to_us(uint32_t cycles)
{
    return (uint32_t)((uint64_t)cycles * 1000000u / board_cpu_hz());
}

static void timing(const char *name, uint32_t total_cycles, uint32_t n)
{
    uint32_t c = total_cycles / n;
    log_s("  ");
    log_s(name);
    log_s(": ");
    log_u(c);
    log_s(" çevrim = ");
    log_u(to_us(c));
    log_s(" us\n");
}

static void test_wire(void)
{
    afet_packet_t p;
    uint8_t out[AFET_MAX_FRAME];
    int ok = afet_wire_decode(wire_raw, sizeof(wire_raw), &p) == 0;
    ok = ok && p.src == wire_fields[0] && p.dst == wire_fields[1] && p.next_hop == wire_fields[2] && p.ptype == wire_fields[3];
    ok = ok && p.seq == (uint16_t)((wire_fields[4] << 8) | wire_fields[5]) && p.ttl == wire_fields[6] && p.last_hop == wire_fields[7];
    int n = afet_wire_encode(&p, out, sizeof(out));
    ok = ok && n == (int)sizeof(wire_raw) && memcmp(out, wire_raw, sizeof(wire_raw)) == 0;
    report("paket biçimi (çöz ve yeniden kodla)", ok);
}

static void test_ccm(void)
{
    afet_ccm_ctx c;
    int seal_ok = 1, open_ok = 1, bad_ok = 1;
    size_t pt_off = 0, ct_off = 0;
    for (int i = 0; i < CCM_N; i++) {
        uint8_t ct[AFET_MAX_PAYLOAD], tag[4], pt[AFET_MAX_PAYLOAD];
        size_t n = ccm_lens[i];
        afet_ccm_init(&c, &ccm_keys[16 * i]);
        afet_ccm_seal(&c, &ccm_nonces[12 * i], &ccm_aads[5 * i], 5, &ccm_pts[pt_off], n, ct, tag);
        seal_ok = seal_ok && memcmp(ct, &ccm_cts[ct_off], n) == 0 && memcmp(tag, &ccm_cts[ct_off + n], 4) == 0;
        open_ok = open_ok && afet_ccm_open(&c, &ccm_nonces[12 * i], &ccm_aads[5 * i], 5, &ccm_cts[ct_off], n, &ccm_cts[ct_off + n], pt) == 0 &&
                  memcmp(pt, &ccm_pts[pt_off], n) == 0;
        uint8_t bad[4];
        memcpy(bad, &ccm_cts[ct_off + n], 4);
        bad[3] ^= 1;
        bad_ok = bad_ok && afet_ccm_open(&c, &ccm_nonces[12 * i], &ccm_aads[5 * i], 5, &ccm_cts[ct_off], n, bad, pt) == -1;
        pt_off += n;
        ct_off += n + 4;
    }
    report("AES-128-CCM şifreleme = Python", seal_ok);
    report("AES-128-CCM çözme ve doğrulama", open_ok);
    report("AES-128-CCM bozuk etiketi reddeder", bad_ok);
}

static void test_routing(void)
{
    afet_routing_t t;
    afet_routing_init(&t, 1, 15000);
    int ok = 1;
    for (int i = 0; i < ROUTE_N && ok; i++) {
        const route_op_t *o = &route_ops[i];
        if (o->op == 0) {
            afet_routing_update(&t, o->nb, o->seq, o->metric, o->nh, (float)o->rssi_x100 / 100.0f, o->t_ms);
        } else if (o->op == 1) {
            afet_routing_remove_neighbor(&t, o->nb, o->t_ms);
        } else {
            afet_routing_select(&t, o->t_ms);
        }
        const route_exp_t *e = &route_exp[i];
        ok = t.route.valid == e->valid && t.switches == e->switches;
        if (ok && e->valid) {
            ok = t.route.next_hop == e->nh && t.route.metric == e->metric && t.route.gw_seq == e->gw_seq;
        }
    }
    report("yönlendirme tablosu (80 işlem) = Python", ok);
}

static void test_security(void)
{
    static afet_receiver_t rx;
    afet_receiver_init(&rx, sec_key);
    int ok = 1, alarms_ok = 1;
    for (int i = 0; i < SEC_N; i++) {
        afet_packet_t p;
        const sec_ev_t *e = &sec_ev[i];
        uint8_t alarm = 0;
        if (afet_wire_decode(&sec_blob[e->off], e->len, &p) != 0) {
            ok = 0;
            break;
        }
        afet_sec_status_t st = afet_receiver_open(&rx, &p, e->t_ms, &alarm, NULL);
        ok = ok && (int)st == e->status;
        alarms_ok = alarms_ok && alarm == e->alarm;
    }
    report("güvenlik alıcısı: durumlar (tekrar, geç, sahte, klon, atlama) = Python", ok);
    report("güvenlik alıcısı: klon alarmı = Python", alarms_ok);
}

static void test_timing(void)
{
    static afet_receiver_t rx;
    static afet_sender_t tx;
    afet_ccm_ctx c;
    uint8_t in[16] = {0}, out[16], data[20] = {1, 2, 3}, ct[20], tag[4];
    uint8_t nonce[12] = {0};
    uint32_t t0;
    const uint32_t N = 200;

    t0 = board_cycles();
    afet_ccm_init(&c, sec_key);
    uint32_t init_cycles = board_cycles() - t0;
    log_s("süre ölçümü (işlemci ");
    log_u(board_cpu_hz() / 1000000u);
    log_s(" MHz):\n");
    log_s("  anahtar kurulumu: ");
    log_u(init_cycles);
    log_s(" çevrim = ");
    log_u(to_us(init_cycles));
    log_s(" us\n");

    t0 = board_cycles();
    for (uint32_t i = 0; i < N; i++) {
        aes128_encrypt_block(&c.aes, in, out);
    }
    timing("AES blok şifreleme (16 bayt)", board_cycles() - t0, N);

    t0 = board_cycles();
    for (uint32_t i = 0; i < N; i++) {
        afet_ccm_seal(&c, nonce, in, 5, data, 20, ct, tag);
    }
    timing("CCM mühürleme (20 bayt yük, 5 bayt başlık)", board_cycles() - t0, N);

    t0 = board_cycles();
    for (uint32_t i = 0; i < N; i++) {
        afet_ccm_open(&c, nonce, in, 5, ct, 20, tag, data);
    }
    timing("CCM çözme ve doğrulama (aynı boyut)", board_cycles() - t0, N);

    afet_sender_init(&tx, sec_key, 5, 0, 64, 0, 0);
    afet_receiver_init(&rx, sec_key);
    afet_packet_t p;
    uint32_t seal_total = 0, open_total = 0;
    for (uint32_t i = 0; i < N; i++) {
        memset(&p, 0, sizeof(p));
        p.dst = 1;
        p.next_hop = 1;
        p.ptype = AFET_DATA;
        p.ttl = 8;
        p.payload_len = 20;
        t0 = board_cycles();
        afet_sender_seal(&tx, &p, 0);
        seal_total += board_cycles() - t0;
        uint8_t alarm;
        t0 = board_cycles();
        afet_receiver_open(&rx, &p, i * 1000, &alarm, 0);
        open_total += board_cycles() - t0;
    }
    timing("gönderen: kare mühürleme (sayaç dahil)", seal_total, N);
    timing("alıcı: kare doğrulama ve çözme (sayaç, geçmiş dahil)", open_total, N);

    afet_routing_t rt;
    afet_routing_init(&rt, 1, 15000);
    t0 = board_cycles();
    for (uint32_t i = 0; i < N; i++) {
        afet_routing_update(&rt, 2 + (i % 4), (uint16_t)i, 1, 0, -100.0f, i * 100);
    }
    timing("yönlendirme güncellemesi (HELLO ilanı)", board_cycles() - t0, N);

    log_s("  SF7 airtime (20 bayt yük + 12 bayt başlık/etiket): ");
    log_u((uint32_t)(afet_lora_airtime(32, 7, 125000, 1, 8, 1, 0) * 1000000.0));
    log_s(" us\n");
}

int main(void)
{
    board_init();
    board_cycles_start();
    log_s("== STM32F407 öz-sınama ==\n");
    log_s("çekirdek saati: ");
    log_u(board_cpu_hz());
    log_s(" Hz\n");
    test_wire();
    test_ccm();
    test_routing();
    test_security();
    test_timing();
    log_s(failures ? "SONUC: BASARISIZ (" : "SONUC: HEPSI GECTI (");
    log_u((uint32_t)failures);
    log_s(" hata)\n");
    log_s("<BITTI>\n");

    for (;;) {
        board_led(0, failures == 0); /* yeşil: hepsi geçti */
        board_led(2, failures != 0); /* kırmızı: hata var */
        __asm volatile("wfi");
    }
}
