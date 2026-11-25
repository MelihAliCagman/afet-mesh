#include "lora_time.h"

#include <math.h>
#include <string.h>

static double symbol_time(int sf, int bw_hz)
{
    return (double)(1 << sf) / (double)bw_hz;
}

double afet_lora_airtime(int payload_bytes, int sf, int bw_hz, int cr, int n_preamble, int crc, int implicit_header)
{
    double ts = symbol_time(sf, bw_hz);
    int de = ts > 0.016 ? 1 : 0;
    int ih = implicit_header ? 1 : 0;
    int pay = 8 * payload_bytes - 4 * sf + 28 + 16 * (crc ? 1 : 0) - 20 * ih;
    int steps = (int)ceil((double)pay / (double)(4 * (sf - 2 * de)));
    int n = 8 + (steps * (cr + 4) > 0 ? steps * (cr + 4) : 0);
    return ((double)n_preamble + 4.25) * ts + (double)n * ts;
}

void afet_duty_init(afet_duty_t *d, uint32_t window_ms, uint32_t limit_ppm)
{
    memset(d, 0, sizeof(*d));
    d->window_ms = window_ms;
    d->limit_ppm = limit_ppm;
}

/* Pencere dışına çıkan kayıtları baştan siler (zaman artan sırada eklenir). */
static void prune(afet_duty_t *d, uint32_t now_ms)
{
    uint16_t drop = 0;
    while (drop < d->n && now_ms - d->t_ms[drop] >= d->window_ms) {
        drop++;
    }
    if (drop) {
        memmove(d->t_ms, d->t_ms + drop, (size_t)(d->n - drop) * sizeof(uint32_t));
        memmove(d->d_us, d->d_us + drop, (size_t)(d->n - drop) * sizeof(uint32_t));
        d->n = (uint16_t)(d->n - drop);
    }
}

uint64_t afet_duty_used_us(const afet_duty_t *d, uint32_t now_ms)
{
    uint64_t sum = 0;
    for (uint16_t i = 0; i < d->n; i++) {
        if (now_ms - d->t_ms[i] < d->window_ms) {
            sum += d->d_us[i];
        }
    }
    return sum;
}

int afet_duty_can_send(const afet_duty_t *d, uint32_t now_ms, uint32_t duration_us)
{
    uint64_t budget_us = (uint64_t)d->window_ms * 1000u * d->limit_ppm / 1000000u;
    return afet_duty_used_us(d, now_ms) + duration_us <= budget_us;
}

int afet_duty_record(afet_duty_t *d, uint32_t now_ms, uint32_t duration_us)
{
    prune(d, now_ms);
    if (d->n >= AFET_DUTY_LOG) {
        return 0;
    }
    d->t_ms[d->n] = now_ms;
    d->d_us[d->n] = duration_us;
    d->n++;
    return 1;
}
