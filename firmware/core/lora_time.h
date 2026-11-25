#ifndef AFET_LORA_TIME_H
#define AFET_LORA_TIME_H

#include <stdint.h>

#define AFET_DUTY_LOG 1024

/* LoRa havada kalma süresi (saniye); sim/lora.py ile aynı formül. */
double afet_lora_airtime(int payload_bytes, int sf, int bw_hz, int cr, int n_preamble, int crc, int implicit_header);

/* %1 yayın süresi sayacı: kayan pencerede kullanılan yayın süresi (mikrosaniye). */
typedef struct {
    uint32_t window_ms;
    uint32_t limit_ppm; /* milyonda bir: %1 = 10000 */
    uint32_t t_ms[AFET_DUTY_LOG];
    uint32_t d_us[AFET_DUTY_LOG];
    uint16_t n;
} afet_duty_t;

void afet_duty_init(afet_duty_t *d, uint32_t window_ms, uint32_t limit_ppm);
uint64_t afet_duty_used_us(const afet_duty_t *d, uint32_t now_ms);
int afet_duty_can_send(const afet_duty_t *d, uint32_t now_ms, uint32_t duration_us);
/* Kayıt eklenemezse (kayıt dolu) 0 döner. */
int afet_duty_record(afet_duty_t *d, uint32_t now_ms, uint32_t duration_us);

#endif
