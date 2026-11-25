#include "framing.h"

size_t afet_frame_encode(const uint8_t *in, size_t len, uint8_t *out, size_t cap)
{
    size_t n = 0;
    if (cap < 2) {
        return 0;
    }
    out[n++] = AFET_SLIP_END;
    for (size_t i = 0; i < len; i++) {
        uint8_t b = in[i];
        if (b == AFET_SLIP_END || b == AFET_SLIP_ESC) {
            if (n + 2 > cap) {
                return 0;
            }
            out[n++] = AFET_SLIP_ESC;
            out[n++] = b == AFET_SLIP_END ? AFET_SLIP_ESC_END : AFET_SLIP_ESC_ESC;
        } else {
            if (n + 1 > cap) {
                return 0;
            }
            out[n++] = b;
        }
    }
    if (n + 1 > cap) {
        return 0;
    }
    out[n++] = AFET_SLIP_END;
    return n;
}

void afet_deframer_init(afet_deframer_t *d)
{
    d->n = 0;
    d->esc = 0;
    d->overflow = 0;
}

int afet_deframer_push(afet_deframer_t *d, uint8_t byte, const uint8_t **frame, size_t *len)
{
    if (byte == AFET_SLIP_END) {
        int complete = d->n > 0 && !d->overflow && !d->esc;
        if (complete) {
            *frame = d->buf;
            *len = d->n;
        }
        d->n = 0;
        d->esc = 0;
        d->overflow = 0;
        return complete;
    }
    if (d->overflow) {
        return 0;
    }
    if (d->esc) {
        d->esc = 0;
        if (byte == AFET_SLIP_ESC_END) {
            byte = AFET_SLIP_END;
        } else if (byte == AFET_SLIP_ESC_ESC) {
            byte = AFET_SLIP_ESC;
        } else {
            d->overflow = 1; /* geçersiz kaçış: bu kare bozuk, sonraki END'e kadar atla */
            return 0;
        }
    } else if (byte == AFET_SLIP_ESC) {
        d->esc = 1;
        return 0;
    }
    if (d->n >= sizeof(d->buf)) {
        d->overflow = 1;
        return 0;
    }
    d->buf[d->n++] = byte;
    return 0;
}
