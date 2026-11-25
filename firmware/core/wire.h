#ifndef AFET_WIRE_H
#define AFET_WIRE_H

#include "afet_config.h"

typedef struct {
    uint8_t src, dst, next_hop, ptype;
    uint16_t seq;
    uint8_t ttl, last_hop;
    uint8_t payload_len;
    uint8_t payload[AFET_MAX_PAYLOAD];
    uint8_t tag[AFET_TAG_BYTES];
} afet_packet_t;

/* Başarıda bayt sayısı, hatada negatif döner. */
int afet_wire_encode(const afet_packet_t *p, uint8_t *out, size_t cap);
/* Başarıda 0, hatada negatif döner. */
int afet_wire_decode(const uint8_t *in, size_t len, afet_packet_t *p);

#endif
