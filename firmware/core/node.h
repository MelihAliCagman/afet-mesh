#ifndef AFET_NODE_H
#define AFET_NODE_H

#include "afet_config.h"
#include "routing.h"
#include "security.h"
#include "wire.h"

#define AFET_MAX_PENDING 8
#define AFET_MAX_TXQ 8
#define AFET_MAX_NEIGH 16
#define AFET_NEVER 0xFFFFFFFFu

/* Radyo soyutlaması (radio_if): UART sahte radyo da, gerçek LoRa sürücüsü de bu arayüzü doldurur. */
typedef struct {
    void (*tx)(void *ctx, const uint8_t *frame, size_t len); /* yayını başlatır */
    int (*channel_busy)(void *ctx);                           /* CSMA için; NULL olabilir */
    uint32_t (*rand32)(void *ctx);
    void *ctx;
} afet_radio_if_t;

typedef void (*afet_deliver_fn)(void *ctx, uint8_t src, const uint8_t *payload, size_t len, uint32_t counter,
                                uint32_t now_ms);

typedef struct {
    uint8_t gateway_id;
    uint32_t hello_period_ms, timeout_ms, ack_timeout_ms;
    uint8_t max_retry, csma, fast_detect, rerr_on, data_ttl;
    uint32_t backoff_slot_ms;
    uint8_t max_backoff;
    uint32_t counter_block;
} afet_node_cfg_t;

typedef struct {
    uint32_t tx_frames, rx_frames, acked, retx, backoffs;
    uint32_t drop_ttl, drop_no_route, drop_retry, drop_pending_full, drop_security;
    uint32_t delivered, sec_alarms;
} afet_stats_t;

typedef struct {
    uint8_t used, origin;
    uint16_t seq;
    uint8_t frame[AFET_MAX_FRAME];
    uint8_t len, tries;
    uint32_t deadline_ms;
} afet_pending_t;

typedef struct {
    uint8_t used;
    uint8_t frame[AFET_MAX_FRAME];
    uint8_t len, attempt;
    uint32_t due_ms;
} afet_txq_t;

typedef struct {
    uint8_t used, id;
    float rssi;
    uint32_t last_seen_ms;
} afet_neigh_t;

typedef struct {
    uint8_t id, is_gateway, alive;
    afet_node_cfg_t cfg;
    afet_radio_if_t radio;
    afet_deliver_fn deliver;
    void *deliver_ctx;
    afet_sender_t sender;
    afet_receiver_t receiver;
    afet_routing_t routing;
    afet_pending_t pending[AFET_MAX_PENDING];
    afet_txq_t txq[AFET_MAX_TXQ];
    afet_neigh_t neigh[AFET_MAX_NEIGH];
    uint32_t next_hello_ms;
    uint16_t gw_seq;
    afet_stats_t stats;
} afet_node_t;

void afet_node_default_cfg(afet_node_cfg_t *cfg);
void afet_node_init(afet_node_t *n, uint8_t id, uint8_t is_gateway, const afet_node_cfg_t *cfg,
                    const afet_radio_if_t *radio, const uint8_t key[16], uint32_t stored_counter,
                    afet_persist_fn persist, void *persist_ctx, uint32_t now_ms);
void afet_node_set_deliver(afet_node_t *n, afet_deliver_fn fn, void *ctx);
void afet_node_on_rx(afet_node_t *n, const uint8_t *raw, size_t len, float rssi_dbm, uint32_t now_ms);
void afet_node_tick(afet_node_t *n, uint32_t now_ms);
int afet_node_send_data(afet_node_t *n, const uint8_t *payload, size_t len, uint32_t now_ms);
uint32_t afet_node_next_wakeup(const afet_node_t *n);
void afet_node_kill(afet_node_t *n);

#endif
