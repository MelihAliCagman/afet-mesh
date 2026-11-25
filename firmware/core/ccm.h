#ifndef AFET_CCM_H
#define AFET_CCM_H

#include <stddef.h>
#include <stdint.h>

#include "aes128.h"

/* AES-128-CCM: nonce 12 bayt (uzunluk alanı 3 bayt), etiket 4 bayt. Python'daki AESCCM(tag_length=4) ile uyumlu. */
#define AFET_CCM_NONCE 12
#define AFET_CCM_TAG 4

typedef struct {
    aes128_ctx aes;
} afet_ccm_ctx;

void afet_ccm_init(afet_ccm_ctx *c, const uint8_t key[16]);

/* Şifreler ve etiketi üretir. pt ve ct aynı bellek olabilir. Başarıda 0. */
int afet_ccm_seal(const afet_ccm_ctx *c, const uint8_t nonce[AFET_CCM_NONCE], const uint8_t *aad, size_t aad_len,
                  const uint8_t *pt, size_t len, uint8_t *ct, uint8_t tag[AFET_CCM_TAG]);

/* Çözer ve etiketi doğrular. Etiket geçersizse -1 döner ve pt'ye bir şey yazılmaz. ct ve pt aynı bellek olabilir. */
int afet_ccm_open(const afet_ccm_ctx *c, const uint8_t nonce[AFET_CCM_NONCE], const uint8_t *aad, size_t aad_len,
                  const uint8_t *ct, size_t len, const uint8_t tag[AFET_CCM_TAG], uint8_t *pt);

#endif
