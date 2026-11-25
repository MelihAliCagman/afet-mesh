#include "security.h"

#include <string.h>

static void nonce_for(uint8_t nonce[AFET_CCM_NONCE], uint8_t src, uint8_t ptype, uint32_t counter)
{
    nonce[0] = src;
    nonce[1] = ptype;
    nonce[2] = (uint8_t)(counter >> 24);
    nonce[3] = (uint8_t)(counter >> 16);
    nonce[4] = (uint8_t)(counter >> 8);
    nonce[5] = (uint8_t)counter;
    memset(nonce + 6, 0, 6);
}

/* Hop'ta değişen alanlar (next_hop, ttl, last_hop) hariç değişmeyen başlık alanları doğrulanır. */
static void aad_for(uint8_t aad[5], const afet_packet_t *p)
{
    aad[0] = p->src;
    aad[1] = p->dst;
    aad[2] = p->ptype;
    aad[3] = (uint8_t)(p->seq >> 8);
    aad[4] = (uint8_t)p->seq;
}

/* ---------------- Gönderen ---------------- */

void afet_sender_init(afet_sender_t *s, const uint8_t key[16], uint8_t node_id, uint32_t stored, uint32_t block,
                      afet_persist_fn fn, void *ctx)
{
    afet_ccm_init(&s->ccm, key);
    s->node_id = node_id;
    s->block = block;
    s->persist = fn;
    s->persist_ctx = ctx;
    s->value = stored;
    s->reserved = s->value + block;
    if (fn) {
        fn(ctx, s->reserved);
    }
    s->value = s->reserved;
    s->reserved = s->value + block;
    if (fn) {
        fn(ctx, s->reserved);
    }
}

int afet_sender_seal(afet_sender_t *s, afet_packet_t *p, uint32_t *counter_out)
{
    uint8_t nonce[AFET_CCM_NONCE], aad[5];
    s->value += 1;
    if (s->value >= s->reserved) {
        s->reserved += s->block;
        if (s->persist) {
            s->persist(s->persist_ctx, s->reserved);
        }
    }
    uint32_t c = s->value;
    p->src = s->node_id;
    p->last_hop = s->node_id;
    p->seq = (uint16_t)(c & 0xFFFF);
    nonce_for(nonce, p->src, p->ptype, c);
    aad_for(aad, p);
    if (counter_out) {
        *counter_out = c;
    }
    return afet_ccm_seal(&s->ccm, nonce, aad, sizeof(aad), p->payload, p->payload_len, p->payload, p->tag);
}

/* ---------------- Alıcı ---------------- */

void afet_receiver_init(afet_receiver_t *r, const uint8_t key[16])
{
    memset(r, 0, sizeof(*r));
    afet_ccm_init(&r->ccm, key);
}

static afet_peer_t *find_peer(afet_receiver_t *r, uint8_t src)
{
    for (int i = 0; i < AFET_MAX_SRC; i++) {
        if (r->peers[i].used && r->peers[i].src == src) {
            return &r->peers[i];
        }
    }
    return NULL;
}

static afet_peer_t *alloc_peer(afet_receiver_t *r, uint8_t src)
{
    for (int i = 0; i < AFET_MAX_SRC; i++) {
        if (!r->peers[i].used) {
            memset(&r->peers[i], 0, sizeof(afet_peer_t));
            r->peers[i].used = 1;
            r->peers[i].src = src;
            return &r->peers[i];
        }
    }
    return NULL;
}

static afet_hist_t *hist_find(afet_peer_t *p, uint32_t counter)
{
    for (int i = 0; i < AFET_HIST; i++) {
        if (p->hist[i].used && p->hist[i].counter == counter) {
            return &p->hist[i];
        }
    }
    return NULL;
}

/* Geçmiş dolunca en küçük sayaç atılır (yeni kare en küçükse hiç eklenmez). */
static void hist_insert(afet_peer_t *p, uint32_t counter, const uint8_t tag[AFET_TAG_BYTES], uint32_t now_ms)
{
    afet_hist_t *slot = NULL, *min = NULL;
    for (int i = 0; i < AFET_HIST; i++) {
        if (!p->hist[i].used) {
            slot = &p->hist[i];
            break;
        }
        if (!min || p->hist[i].counter < min->counter) {
            min = &p->hist[i];
        }
    }
    if (!slot) {
        if (counter < min->counter) {
            return;
        }
        slot = min;
    }
    slot->used = 1;
    slot->counter = counter;
    memcpy(slot->tag, tag, AFET_TAG_BYTES);
    slot->t_ms = now_ms;
}

/* Anomali olayı (regression veya jump) kaydeder; yeni alarm üretildiyse 1 döner. */
static int note_event(afet_peer_t *p, uint32_t now_ms)
{
    uint8_t keep = 0;
    for (uint8_t i = 0; i < p->event_n; i++) {
        if (now_ms - p->events[i] <= AFET_ALARM_WINDOW_MS) {
            p->events[keep++] = p->events[i];
        }
    }
    p->event_n = keep;
    if (p->event_n == AFET_EVENTS) {
        memmove(p->events, p->events + 1, (AFET_EVENTS - 1) * sizeof(uint32_t));
        p->event_n--;
    }
    p->events[p->event_n++] = now_ms;
    if (p->event_n >= AFET_ALARM_COUNT && (!p->has_alarm || now_ms - p->last_alarm_ms >= AFET_ALARM_WINDOW_MS)) {
        p->has_alarm = 1;
        p->last_alarm_ms = now_ms;
        return 1;
    }
    return 0;
}

afet_sec_status_t afet_receiver_open(afet_receiver_t *r, afet_packet_t *pkt, uint32_t now_ms, uint8_t *alarm,
                                     uint32_t *counter_out)
{
    uint8_t nonce[AFET_CCM_NONCE], aad[5], plain[AFET_MAX_PAYLOAD];
    uint32_t cands[3];
    int ncand = 0;
    afet_peer_t *peer = find_peer(r, pkt->src);
    int has_last = peer && peer->has_last;
    uint32_t last = has_last ? peer->last : 0;
    uint32_t base = last & ~0xFFFFu;

    if (alarm) {
        *alarm = 0;
    }
    cands[ncand++] = base | pkt->seq;
    cands[ncand++] = (base | pkt->seq) + 0x10000u;
    if (base) {
        cands[ncand++] = (base | pkt->seq) - 0x10000u;
    }
    aad_for(aad, pkt);

    for (int k = 0; k < ncand; k++) {
        uint32_t c = cands[k];
        nonce_for(nonce, pkt->src, pkt->ptype, c);
        if (afet_ccm_open(&r->ccm, nonce, aad, sizeof(aad), pkt->payload, pkt->payload_len, pkt->tag, plain) != 0) {
            continue;
        }
        if (!peer) {
            peer = alloc_peer(r, pkt->src);
            if (!peer) {
                return AFET_SEC_NO_SPACE;
            }
        }
        if (counter_out) {
            *counter_out = c;
        }
        if (!has_last || c > last) {
            if (has_last && c - last > AFET_MAX_JUMP) {
                if (note_event(peer, now_ms) && alarm) {
                    *alarm = 1;
                }
                return AFET_SEC_JUMP;
            }
            peer->has_last = 1;
            peer->last = c;
            hist_insert(peer, c, pkt->tag, now_ms);
            memcpy(pkt->payload, plain, pkt->payload_len);
            return AFET_SEC_OK;
        }
        afet_hist_t *e = hist_find(peer, c);
        if (e && memcmp(e->tag, pkt->tag, AFET_TAG_BYTES) == 0) {
            return (c == last || now_ms - e->t_ms <= AFET_DUP_WINDOW_MS) ? AFET_SEC_DUP : AFET_SEC_REPLAY;
        }
        if (last - c <= AFET_LATE_WINDOW && !e) {
            hist_insert(peer, c, pkt->tag, now_ms);
            memcpy(pkt->payload, plain, pkt->payload_len);
            return AFET_SEC_OK;
        }
        if (note_event(peer, now_ms) && alarm) {
            *alarm = 1;
        }
        return AFET_SEC_REGRESSION;
    }
    return AFET_SEC_BAD_TAG;
}
