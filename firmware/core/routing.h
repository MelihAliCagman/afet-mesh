#ifndef AFET_ROUTING_H
#define AFET_ROUTING_H

#include "afet_config.h"

typedef struct {
    uint8_t used;
    uint8_t neighbor;
    uint16_t gw_seq;
    uint16_t metric;
    uint32_t updated_ms;
} afet_cand_t;

typedef struct {
    uint8_t valid;
    uint8_t next_hop;
    uint16_t metric;
    uint16_t gw_seq;
    uint32_t updated_ms;
} afet_route_t;

typedef struct {
    uint8_t me;
    uint32_t timeout_ms;
    afet_cand_t cands[AFET_MAX_CANDS];
    afet_route_t route;
    uint32_t switches;
} afet_routing_t;

void afet_routing_init(afet_routing_t *t, uint8_t me, uint32_t timeout_ms);
int afet_seq_newer(uint16_t a, uint16_t b);
uint8_t afet_link_cost(float rssi_dbm);

/* HELLO ilanını işler. Dönüş: yol değişti mi (1/0). */
int afet_routing_update(afet_routing_t *t, uint8_t neighbor, uint16_t adv_seq, uint8_t adv_metric, uint8_t adv_next_hop,
                        float rssi_dbm, uint32_t now_ms);
int afet_routing_remove_neighbor(afet_routing_t *t, uint8_t neighbor, uint32_t now_ms);
int afet_routing_select(afet_routing_t *t, uint32_t now_ms);

#endif
