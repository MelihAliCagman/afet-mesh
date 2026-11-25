#ifndef AFET_CONFIG_H
#define AFET_CONFIG_H

#include <stddef.h>
#include <stdint.h>

/* Paket biçimi (docs/protokol.md ile aynı) */
#define AFET_HEADER_BYTES 8
#define AFET_TAG_BYTES 4
#define AFET_MAX_PAYLOAD 64
#define AFET_MAX_FRAME (AFET_HEADER_BYTES + AFET_MAX_PAYLOAD + AFET_TAG_BYTES)
#define AFET_BROADCAST 255

enum { AFET_HELLO = 1, AFET_DATA = 2, AFET_ACK = 3, AFET_RERR = 4 };

/* Güvenlik */
#define AFET_MAX_JUMP 1024u
#define AFET_LATE_WINDOW 32u
#define AFET_DUP_WINDOW_MS 30000u
#define AFET_ALARM_WINDOW_MS 60000u
#define AFET_ALARM_COUNT 3u
#define AFET_HIST 64
#define AFET_MAX_SRC 16
#define AFET_EVENTS 8

/* Yönlendirme */
#define AFET_INFINITY 255
#define AFET_MAX_CANDS 8
#define AFET_SEQ_MOD 65536u

#endif
