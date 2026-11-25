/* Yalnızca bilgisayarda test için: ctypes'ın yapı boyutlarını ve alanları okuyabilmesi için yardımcılar. */
#include "lora_time.h"
#include "routing.h"
#include "security.h"

size_t afet_sizeof_sender(void) { return sizeof(afet_sender_t); }
size_t afet_sizeof_receiver(void) { return sizeof(afet_receiver_t); }
size_t afet_sizeof_routing(void) { return sizeof(afet_routing_t); }
size_t afet_sizeof_duty(void) { return sizeof(afet_duty_t); }

void afet_routing_get(const afet_routing_t *t, uint8_t *valid, uint8_t *next_hop, uint16_t *metric, uint16_t *gw_seq,
                      uint32_t *switches)
{
    *valid = t->route.valid;
    *next_hop = t->route.next_hop;
    *metric = t->route.metric;
    *gw_seq = t->route.gw_seq;
    *switches = t->switches;
}
