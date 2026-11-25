#include "node.h"

#include <string.h>

#define OFF_NEXT_HOP 2
#define OFF_TTL 6
#define OFF_LAST_HOP 7

static void mac_send(afet_node_t *n, const uint8_t *frame, uint8_t len, uint8_t attempt, uint32_t now_ms);

void afet_node_default_cfg(afet_node_cfg_t *c)
{
    memset(c, 0, sizeof(*c));
    c->gateway_id = 1;
    c->hello_period_ms = 5000;
    c->timeout_ms = 15000;
    c->ack_timeout_ms = 1000;
    c->max_retry = 3;
    c->csma = 1;
    c->fast_detect = 1;
    c->rerr_on = 1;
    c->data_ttl = 8;
    c->backoff_slot_ms = 50;
    c->max_backoff = 6;
    c->counter_block = 64;
}

void afet_node_init(afet_node_t *n, uint8_t id, uint8_t is_gateway, const afet_node_cfg_t *cfg,
                    const afet_radio_if_t *radio, const uint8_t key[16], uint32_t stored_counter,
                    afet_persist_fn persist, void *persist_ctx, uint32_t now_ms)
{
    memset(n, 0, sizeof(*n));
    n->id = id;
    n->is_gateway = is_gateway;
    n->alive = 1;
    n->cfg = *cfg;
    n->radio = *radio;
    afet_sender_init(&n->sender, key, id, stored_counter, cfg->counter_block, persist, persist_ctx);
    afet_receiver_init(&n->receiver, key);
    afet_routing_init(&n->routing, id, cfg->timeout_ms);
    n->next_hello_ms = now_ms + n->radio.rand32(n->radio.ctx) % (cfg->hello_period_ms + 1);
}

void afet_node_set_deliver(afet_node_t *n, afet_deliver_fn fn, void *ctx)
{
    n->deliver = fn;
    n->deliver_ctx = ctx;
}

void afet_node_kill(afet_node_t *n)
{
    n->alive = 0;
}

/* ---------------- gönderim ---------------- */

static void mac_send(afet_node_t *n, const uint8_t *frame, uint8_t len, uint8_t attempt, uint32_t now_ms)
{
    if (n->cfg.csma && n->radio.channel_busy && attempt < n->cfg.max_backoff && n->radio.channel_busy(n->radio.ctx)) {
        for (int i = 0; i < AFET_MAX_TXQ; i++) {
            if (!n->txq[i].used) {
                uint32_t shift = (uint32_t)attempt + 1 > 5 ? 5 : (uint32_t)attempt + 1;
                uint32_t window = n->cfg.backoff_slot_ms << shift;
                n->txq[i].used = 1;
                memcpy(n->txq[i].frame, frame, len);
                n->txq[i].len = len;
                n->txq[i].attempt = (uint8_t)(attempt + 1);
                n->txq[i].due_ms = now_ms + n->radio.rand32(n->radio.ctx) % (window + 1);
                n->stats.backoffs++;
                return;
            }
        }
    }
    n->radio.tx(n->radio.ctx, frame, len);
    n->stats.tx_frames++;
}

static void emit(afet_node_t *n, afet_packet_t *p, uint32_t now_ms)
{
    uint8_t raw[AFET_MAX_FRAME];
    int len = afet_wire_encode(p, raw, sizeof(raw));
    if (len > 0) {
        mac_send(n, raw, (uint8_t)len, 0, now_ms);
    }
}

static void route_lost(afet_node_t *n, int had_route, uint32_t now_ms)
{
    if (had_route && !n->routing.route.valid && n->cfg.rerr_on) {
        afet_packet_t p;
        memset(&p, 0, sizeof(p));
        p.dst = AFET_BROADCAST;
        p.next_hop = AFET_BROADCAST;
        p.ptype = AFET_RERR;
        p.ttl = 1;
        afet_sender_seal(&n->sender, &p, NULL);
        emit(n, &p, now_ms);
    }
}

static void link_failed(afet_node_t *n, uint8_t neighbor, uint32_t now_ms)
{
    int had = n->routing.route.valid;
    afet_routing_remove_neighbor(&n->routing, neighbor, now_ms);
    route_lost(n, had, now_ms);
}

static void send_hello(afet_node_t *n, uint32_t now_ms)
{
    int had = n->routing.route.valid;
    afet_routing_select(&n->routing, now_ms);
    route_lost(n, had, now_ms);

    afet_packet_t p;
    memset(&p, 0, sizeof(p));
    p.dst = AFET_BROADCAST;
    p.next_hop = AFET_BROADCAST;
    p.ptype = AFET_HELLO;
    p.ttl = 1;
    if (n->is_gateway) {
        n->gw_seq++;
        p.payload[0] = (uint8_t)(n->gw_seq >> 8);
        p.payload[1] = (uint8_t)n->gw_seq;
        p.payload[2] = 0;
        p.payload[3] = 0;
        p.payload_len = 4;
    } else if (n->routing.route.valid) {
        const afet_route_t *r = &n->routing.route;
        p.payload[0] = (uint8_t)(r->gw_seq >> 8);
        p.payload[1] = (uint8_t)r->gw_seq;
        p.payload[2] = (uint8_t)r->metric;
        p.payload[3] = r->next_hop;
        p.payload_len = 4;
    }
    afet_sender_seal(&n->sender, &p, NULL);
    emit(n, &p, now_ms);
}

static void send_ack(afet_node_t *n, const afet_packet_t *data, uint32_t now_ms)
{
    afet_packet_t a;
    memset(&a, 0, sizeof(a));
    a.dst = data->last_hop;
    a.next_hop = data->last_hop;
    a.ptype = AFET_ACK;
    a.ttl = 1;
    a.payload[0] = data->src;
    a.payload[1] = (uint8_t)(data->seq >> 8);
    a.payload[2] = (uint8_t)data->seq;
    a.payload_len = 3;
    afet_sender_seal(&n->sender, &a, NULL);
    emit(n, &a, now_ms);
}

static afet_pending_t *pending_find(afet_node_t *n, uint8_t origin, uint16_t seq)
{
    for (int i = 0; i < AFET_MAX_PENDING; i++) {
        if (n->pending[i].used && n->pending[i].origin == origin && n->pending[i].seq == seq) {
            return &n->pending[i];
        }
    }
    return NULL;
}

/* Bir DATA karesini yollar ve ACK bekleme kaydı açar (kayıt doluysa yeniden denemesiz yollanır). */
static void send_tracked(afet_node_t *n, uint8_t origin, uint16_t seq, const uint8_t *frame, uint8_t len, uint32_t now_ms)
{
    for (int i = 0; i < AFET_MAX_PENDING; i++) {
        if (!n->pending[i].used) {
            afet_pending_t *p = &n->pending[i];
            p->used = 1;
            p->origin = origin;
            p->seq = seq;
            memcpy(p->frame, frame, len);
            p->len = len;
            p->tries = 0;
            p->deadline_ms = now_ms + n->cfg.ack_timeout_ms;
            mac_send(n, frame, len, 0, now_ms);
            return;
        }
    }
    n->stats.drop_pending_full++;
    mac_send(n, frame, len, 0, now_ms);
}

int afet_node_send_data(afet_node_t *n, const uint8_t *payload, size_t len, uint32_t now_ms)
{
    if (!n->alive || len > AFET_MAX_PAYLOAD) {
        return 0;
    }
    if (!n->routing.route.valid) {
        n->stats.drop_no_route++;
        return 0;
    }
    afet_packet_t p;
    memset(&p, 0, sizeof(p));
    p.dst = n->cfg.gateway_id;
    p.next_hop = n->routing.route.next_hop;
    p.ptype = AFET_DATA;
    p.ttl = n->cfg.data_ttl;
    memcpy(p.payload, payload, len);
    p.payload_len = (uint8_t)len;
    afet_sender_seal(&n->sender, &p, NULL);
    uint8_t raw[AFET_MAX_FRAME];
    int rl = afet_wire_encode(&p, raw, sizeof(raw));
    if (rl <= 0) {
        return 0;
    }
    send_tracked(n, n->id, p.seq, raw, (uint8_t)rl, now_ms);
    return 1;
}

/* ---------------- alım ---------------- */

static void handle_hello(afet_node_t *n, afet_packet_t *p, float rssi, uint32_t now_ms)
{
    uint8_t alarm = 0;
    afet_sec_status_t st = afet_receiver_open(&n->receiver, p, now_ms, &alarm, NULL);
    n->stats.sec_alarms += alarm;
    if (st != AFET_SEC_OK) {
        if (st != AFET_SEC_DUP) {
            n->stats.drop_security++;
        }
        return;
    }
    int slot = -1;
    for (int i = 0; i < AFET_MAX_NEIGH; i++) {
        if (n->neigh[i].used && n->neigh[i].id == p->src) {
            slot = i;
            break;
        }
        if (slot < 0 && !n->neigh[i].used) {
            slot = i;
        }
    }
    if (slot >= 0) {
        n->neigh[slot].used = 1;
        n->neigh[slot].id = p->src;
        n->neigh[slot].rssi = rssi;
        n->neigh[slot].last_seen_ms = now_ms;
    }
    if (!n->is_gateway && p->payload_len == 4) {
        uint16_t gw_seq = (uint16_t)(((uint16_t)p->payload[0] << 8) | p->payload[1]);
        int had = n->routing.route.valid;
        afet_routing_update(&n->routing, p->src, gw_seq, p->payload[2], p->payload[3], rssi, now_ms);
        route_lost(n, had, now_ms);
    }
}

static void handle_data(afet_node_t *n, afet_packet_t *p, const uint8_t *raw, size_t len, uint32_t now_ms)
{
    if (p->next_hop != n->id) {
        return;
    }
    uint8_t alarm = 0;
    uint32_t counter = 0;
    afet_sec_status_t st = afet_receiver_open(&n->receiver, p, now_ms, &alarm, &counter);
    n->stats.sec_alarms += alarm;
    if (st != AFET_SEC_OK && st != AFET_SEC_DUP) {
        n->stats.drop_security++;
        return;
    }
    send_ack(n, p, now_ms); /* kopya olsa da onay yollanır; yoksa gönderen vazgeçene kadar tekrar eder */
    if (st == AFET_SEC_DUP) {
        return;
    }
    if (n->is_gateway) {
        n->stats.delivered++;
        if (n->deliver) {
            n->deliver(n->deliver_ctx, p->src, p->payload, p->payload_len, counter, now_ms);
        }
        return;
    }
    if (p->ttl <= 1) {
        n->stats.drop_ttl++;
        return;
    }
    if (!n->routing.route.valid) {
        n->stats.drop_no_route++;
        return;
    }
    uint8_t fwd[AFET_MAX_FRAME];
    memcpy(fwd, raw, len); /* şifreli ve mühürlü özgün kare; yalnızca hop alanları değişir */
    fwd[OFF_NEXT_HOP] = n->routing.route.next_hop;
    fwd[OFF_TTL] = (uint8_t)(p->ttl - 1);
    fwd[OFF_LAST_HOP] = n->id;
    send_tracked(n, p->src, p->seq, fwd, (uint8_t)len, now_ms);
}

static void handle_ack(afet_node_t *n, afet_packet_t *p, uint32_t now_ms)
{
    if (p->next_hop != n->id) {
        return;
    }
    uint8_t alarm = 0;
    if (afet_receiver_open(&n->receiver, p, now_ms, &alarm, NULL) != AFET_SEC_OK) {
        return;
    }
    n->stats.sec_alarms += alarm;
    if (p->payload_len == 3) {
        afet_pending_t *e = pending_find(n, p->payload[0], (uint16_t)(((uint16_t)p->payload[1] << 8) | p->payload[2]));
        if (e) {
            e->used = 0;
            n->stats.acked++;
        }
    }
}

static void handle_rerr(afet_node_t *n, afet_packet_t *p, uint32_t now_ms)
{
    uint8_t alarm = 0;
    if (afet_receiver_open(&n->receiver, p, now_ms, &alarm, NULL) != AFET_SEC_OK) {
        return;
    }
    if (!n->is_gateway) {
        link_failed(n, p->src, now_ms);
    }
}

void afet_node_on_rx(afet_node_t *n, const uint8_t *raw, size_t len, float rssi_dbm, uint32_t now_ms)
{
    afet_packet_t p;
    if (!n->alive || len > AFET_MAX_FRAME || afet_wire_decode(raw, len, &p) != 0) {
        return;
    }
    n->stats.rx_frames++;
    if (p.src == n->id) {
        return;
    }
    switch (p.ptype) {
    case AFET_HELLO:
        handle_hello(n, &p, rssi_dbm, now_ms);
        break;
    case AFET_DATA:
        handle_data(n, &p, raw, len, now_ms);
        break;
    case AFET_ACK:
        handle_ack(n, &p, now_ms);
        break;
    case AFET_RERR:
        handle_rerr(n, &p, now_ms);
        break;
    default:
        break;
    }
}

/* ---------------- zamanlayıcılar ---------------- */

static void pending_timeout(afet_node_t *n, afet_pending_t *e, uint32_t now_ms)
{
    if (e->tries >= n->cfg.max_retry) {
        uint8_t neighbor = e->frame[OFF_NEXT_HOP];
        e->used = 0;
        n->stats.drop_retry++;
        if (n->cfg.fast_detect) {
            link_failed(n, neighbor, now_ms);
        }
        return;
    }
    if (!n->routing.route.valid) {
        e->used = 0;
        n->stats.drop_no_route++;
        return;
    }
    n->stats.retx++;
    e->frame[OFF_NEXT_HOP] = n->routing.route.next_hop;
    e->frame[OFF_LAST_HOP] = n->id;
    e->tries++;
    e->deadline_ms = now_ms + n->cfg.ack_timeout_ms;
    mac_send(n, e->frame, e->len, 0, now_ms);
}

void afet_node_tick(afet_node_t *n, uint32_t now_ms)
{
    if (!n->alive) {
        return;
    }
    for (int i = 0; i < AFET_MAX_TXQ; i++) {
        if (n->txq[i].used && n->txq[i].due_ms <= now_ms) {
            uint8_t frame[AFET_MAX_FRAME], len = n->txq[i].len, attempt = n->txq[i].attempt;
            memcpy(frame, n->txq[i].frame, len);
            n->txq[i].used = 0;
            mac_send(n, frame, len, attempt, now_ms);
        }
    }
    for (int i = 0; i < AFET_MAX_PENDING; i++) {
        if (n->pending[i].used && n->pending[i].deadline_ms <= now_ms) {
            pending_timeout(n, &n->pending[i], now_ms);
        }
    }
    if (now_ms >= n->next_hello_ms) {
        send_hello(n, now_ms);
        n->next_hello_ms = now_ms + n->cfg.hello_period_ms;
    }
}

uint32_t afet_node_next_wakeup(const afet_node_t *n)
{
    if (!n->alive) {
        return AFET_NEVER;
    }
    uint32_t t = n->next_hello_ms;
    for (int i = 0; i < AFET_MAX_TXQ; i++) {
        if (n->txq[i].used && n->txq[i].due_ms < t) {
            t = n->txq[i].due_ms;
        }
    }
    for (int i = 0; i < AFET_MAX_PENDING; i++) {
        if (n->pending[i].used && n->pending[i].deadline_ms < t) {
            t = n->pending[i].deadline_ms;
        }
    }
    return t;
}
