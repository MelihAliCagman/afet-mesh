#include "wire.h"

#include <string.h>

int afet_wire_encode(const afet_packet_t *p, uint8_t *out, size_t cap)
{
    if (p->payload_len > AFET_MAX_PAYLOAD) {
        return -1;
    }
    size_t n = AFET_HEADER_BYTES + p->payload_len + AFET_TAG_BYTES;
    if (cap < n) {
        return -2;
    }
    out[0] = p->src;
    out[1] = p->dst;
    out[2] = p->next_hop;
    out[3] = p->ptype;
    out[4] = (uint8_t)(p->seq >> 8);
    out[5] = (uint8_t)(p->seq & 0xFF);
    out[6] = p->ttl;
    out[7] = p->last_hop;
    memcpy(out + AFET_HEADER_BYTES, p->payload, p->payload_len);
    memcpy(out + AFET_HEADER_BYTES + p->payload_len, p->tag, AFET_TAG_BYTES);
    return (int)n;
}

int afet_wire_decode(const uint8_t *in, size_t len, afet_packet_t *p)
{
    if (len < AFET_HEADER_BYTES + AFET_TAG_BYTES) {
        return -1;
    }
    size_t pl = len - AFET_HEADER_BYTES - AFET_TAG_BYTES;
    if (pl > AFET_MAX_PAYLOAD) {
        return -2;
    }
    if (in[3] < AFET_HELLO || in[3] > AFET_RERR) {
        return -3;
    }
    p->src = in[0];
    p->dst = in[1];
    p->next_hop = in[2];
    p->ptype = in[3];
    p->seq = (uint16_t)(((uint16_t)in[4] << 8) | in[5]);
    p->ttl = in[6];
    p->last_hop = in[7];
    p->payload_len = (uint8_t)pl;
    memcpy(p->payload, in + AFET_HEADER_BYTES, pl);
    memcpy(p->tag, in + AFET_HEADER_BYTES + pl, AFET_TAG_BYTES);
    return 0;
}
