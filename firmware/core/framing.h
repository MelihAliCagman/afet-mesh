#ifndef AFET_FRAMING_H
#define AFET_FRAMING_H

#include "afet_config.h"

/* UART gibi bayt akışlarında kare sınırlarını belirler (SLIP: RFC 1055). Kare: END + kaçışlı veri + END.
 * Veri içindeki END (0xC0) ve ESC (0xDB) baytları kaçışlanır. Bütünlük ve doğrulama pakettaki etikete bırakılır. */
#define AFET_SLIP_END 0xC0
#define AFET_SLIP_ESC 0xDB
#define AFET_SLIP_ESC_END 0xDC
#define AFET_SLIP_ESC_ESC 0xDD

/* En kötü durumda her bayt iki bayta çıkar: 2 * len + 2. Taşarsa 0 döner. */
size_t afet_frame_encode(const uint8_t *in, size_t len, uint8_t *out, size_t cap);

typedef struct {
    uint8_t buf[AFET_MAX_FRAME];
    size_t n;
    uint8_t esc;
    uint8_t overflow;
} afet_deframer_t;

void afet_deframer_init(afet_deframer_t *d);

/* Gelen her baytı verir. Tam kare tamamlanınca 1 döner; *frame ve *len kareyi gösterir (bir sonraki push'a kadar geçerli).
 * Boş kareler (art arda END), taşan veya bozuk kaçışlı kareler sessizce atılır. */
int afet_deframer_push(afet_deframer_t *d, uint8_t byte, const uint8_t **frame, size_t *len);

#endif
