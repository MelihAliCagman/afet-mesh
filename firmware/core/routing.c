#include "routing.h"

#include <string.h>

void afet_routing_init(afet_routing_t *t, uint8_t me, uint32_t timeout_ms)
{
    memset(t, 0, sizeof(*t));
    t->me = me;
    t->timeout_ms = timeout_ms;
}

int afet_seq_newer(uint16_t a, uint16_t b)
{
    uint16_t d = (uint16_t)(a - b);
    return d > 0 && d < AFET_SEQ_MOD / 2;
}

uint8_t afet_link_cost(float rssi_dbm)
{
    if (rssi_dbm >= -110.0f) {
        return 1;
    }
    if (rssi_dbm >= -118.0f) {
        return 2;
    }
    return 3;
}

static afet_cand_t *find_cand(afet_routing_t *t, uint8_t neighbor)
{
    for (int i = 0; i < AFET_MAX_CANDS; i++) {
        if (t->cands[i].used && t->cands[i].neighbor == neighbor) {
            return &t->cands[i];
        }
    }
    return NULL;
}

static void drop_cand(afet_routing_t *t, uint8_t neighbor)
{
    afet_cand_t *c = find_cand(t, neighbor);
    if (c) {
        c->used = 0;
    }
}

int afet_routing_update(afet_routing_t *t, uint8_t neighbor, uint16_t adv_seq, uint8_t adv_metric, uint8_t adv_next_hop,
                        float rssi_dbm, uint32_t now_ms)
{
    uint16_t metric = (uint16_t)(adv_metric + afet_link_cost(rssi_dbm));
    if (adv_next_hop == t->me || metric >= AFET_INFINITY) {
        drop_cand(t, neighbor);
    } else {
        afet_cand_t *old = find_cand(t, neighbor);
        if (!old || !afet_seq_newer(old->gw_seq, adv_seq)) {
            afet_cand_t *slot = old;
            if (!slot) {
                for (int i = 0; i < AFET_MAX_CANDS; i++) {
                    if (!t->cands[i].used) {
                        slot = &t->cands[i];
                        break;
                    }
                }
            }
            if (slot) { /* tablo doluysa yeni komşu eklenmez (yer ayrılmış komşular korunur) */
                slot->used = 1;
                slot->neighbor = neighbor;
                slot->gw_seq = adv_seq;
                slot->metric = metric;
                slot->updated_ms = now_ms;
            }
        }
    }
    return afet_routing_select(t, now_ms);
}

int afet_routing_remove_neighbor(afet_routing_t *t, uint8_t neighbor, uint32_t now_ms)
{
    drop_cand(t, neighbor);
    return afet_routing_select(t, now_ms);
}

int afet_routing_select(afet_routing_t *t, uint32_t now_ms)
{
    afet_cand_t *best = NULL;
    afet_cand_t *cur = NULL;
    int had = t->route.valid;
    afet_route_t old = t->route;

    for (int i = 0; i < AFET_MAX_CANDS; i++) {
        afet_cand_t *c = &t->cands[i];
        if (c->used && now_ms - c->updated_ms > t->timeout_ms) {
            c->used = 0;
        }
    }
    for (int i = 0; i < AFET_MAX_CANDS; i++) {
        afet_cand_t *c = &t->cands[i];
        if (!c->used) {
            continue;
        }
        if (!best || c->metric < best->metric || (c->metric == best->metric && c->neighbor < best->neighbor)) {
            best = c;
        }
        if (had && c->neighbor == old.next_hop) {
            cur = c;
        }
    }
    if (!best) {
        t->route.valid = 0;
        return had;
    }
    if (cur && best->metric >= cur->metric) {
        best = cur; /* histerezis: yalnızca kesin daha ucuz aday varsa değiştir */
    }
    int changed = !had || old.next_hop != best->neighbor || old.metric != best->metric;
    if (had && old.next_hop != best->neighbor) {
        t->switches++;
    }
    t->route.valid = 1;
    t->route.next_hop = best->neighbor;
    t->route.metric = best->metric;
    t->route.gw_seq = best->gw_seq;
    t->route.updated_ms = best->updated_ms;
    return changed;
}
