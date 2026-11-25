#ifndef AFET_SECURITY_H
#define AFET_SECURITY_H

#include "afet_config.h"
#include "ccm.h"
#include "wire.h"

/* ---- Gönderen: 32 bit çerçeve sayacı, kalıcı rezerv sınırı ---- */
typedef void (*afet_persist_fn)(void *ctx, uint32_t reserved);

typedef struct {
    afet_ccm_ctx ccm;
    uint8_t node_id;
    uint32_t value, reserved, block;
    afet_persist_fn persist;
    void *persist_ctx;
} afet_sender_t;

/* stored: flash'tan okunan son rezerv sınır (ilk açılışta 0). Açılışta sayaç stored + block'tan başlar. */
void afet_sender_init(afet_sender_t *s, const uint8_t key[16], uint8_t node_id, uint32_t stored, uint32_t block,
                      afet_persist_fn fn, void *ctx);

/* p'de dst, next_hop, ptype, ttl, payload, payload_len hazır olmalı. src, last_hop, seq ve tag doldurulur,
 * yük yerinde şifrelenir. Başarıda 0. */
int afet_sender_seal(afet_sender_t *s, afet_packet_t *p, uint32_t *counter_out);

/* ---- Alıcı: etiket doğrulama, tekrar oynatma ve klon tespiti ---- */
typedef enum {
    AFET_SEC_OK = 0,
    AFET_SEC_DUP,
    AFET_SEC_REPLAY,
    AFET_SEC_REGRESSION,
    AFET_SEC_JUMP,
    AFET_SEC_BAD_TAG,
    AFET_SEC_NO_SPACE
} afet_sec_status_t;

typedef struct {
    uint8_t used;
    uint32_t counter;
    uint8_t tag[AFET_TAG_BYTES];
    uint32_t t_ms;
} afet_hist_t;

typedef struct {
    uint8_t used;
    uint8_t src;
    uint8_t has_last;
    uint32_t last;
    afet_hist_t hist[AFET_HIST];
    uint32_t events[AFET_EVENTS];
    uint8_t event_n;
    uint8_t has_alarm;
    uint32_t last_alarm_ms;
} afet_peer_t;

typedef struct {
    afet_ccm_ctx ccm;
    afet_peer_t peers[AFET_MAX_SRC];
} afet_receiver_t;

void afet_receiver_init(afet_receiver_t *r, const uint8_t key[16]);

/* pkt mühürlü gelir; durum OK ise payload yerinde çözülmüş olur. *alarm, klon alarmı üretildiyse 1 olur. */
afet_sec_status_t afet_receiver_open(afet_receiver_t *r, afet_packet_t *pkt, uint32_t now_ms, uint8_t *alarm,
                                     uint32_t *counter_out);

#endif
