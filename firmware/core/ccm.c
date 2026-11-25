#include "ccm.h"

#include <string.h>

#define L_BYTES 3 /* uzunluk alanı: 15 - nonce(12) */

void afet_ccm_init(afet_ccm_ctx *c, const uint8_t key[16])
{
    aes128_init(&c->aes, key);
}

static void xor_into(uint8_t *dst, const uint8_t *src, size_t n)
{
    for (size_t i = 0; i < n; i++) {
        dst[i] ^= src[i];
    }
}

/* CBC-MAC: B0, ek veri (AAD) blokları, yük blokları. Sonuç ilk 4 bayt etikettir (henüz S0 ile örtülmemiş). */
static void cbc_mac(const afet_ccm_ctx *c, const uint8_t nonce[AFET_CCM_NONCE], const uint8_t *aad, size_t aad_len,
                    const uint8_t *pt, size_t len, uint8_t x[16])
{
    uint8_t b[16];
    b[0] = (uint8_t)((aad_len ? 0x40 : 0x00) | (((AFET_CCM_TAG - 2) / 2) << 3) | (L_BYTES - 1));
    memcpy(b + 1, nonce, AFET_CCM_NONCE);
    b[13] = (uint8_t)(len >> 16);
    b[14] = (uint8_t)(len >> 8);
    b[15] = (uint8_t)len;
    aes128_encrypt_block(&c->aes, b, x);

    if (aad_len) {
        /* AAD uzunluğu 2 bayt öne eklenir (aad_len < 0xFF00 varsayılır; başlığımız 5 bayt) */
        uint8_t buf[16];
        size_t pos = 0, total = aad_len + 2;
        uint8_t first[2] = {(uint8_t)(aad_len >> 8), (uint8_t)aad_len};
        while (pos < total) {
            memset(buf, 0, 16);
            for (size_t i = 0; i < 16 && pos + i < total; i++) {
                size_t k = pos + i;
                buf[i] = k < 2 ? first[k] : aad[k - 2];
            }
            xor_into(x, buf, 16);
            aes128_encrypt_block(&c->aes, x, x);
            pos += 16;
        }
    }
    for (size_t pos = 0; pos < len; pos += 16) {
        size_t n = len - pos < 16 ? len - pos : 16;
        uint8_t buf[16] = {0};
        memcpy(buf, pt + pos, n);
        xor_into(x, buf, 16);
        aes128_encrypt_block(&c->aes, x, x);
    }
}

static void ctr_block(const afet_ccm_ctx *c, const uint8_t nonce[AFET_CCM_NONCE], uint32_t counter, uint8_t s[16])
{
    uint8_t a[16];
    a[0] = (uint8_t)(L_BYTES - 1);
    memcpy(a + 1, nonce, AFET_CCM_NONCE);
    a[13] = (uint8_t)(counter >> 16);
    a[14] = (uint8_t)(counter >> 8);
    a[15] = (uint8_t)counter;
    aes128_encrypt_block(&c->aes, a, s);
}

static void ctr_crypt(const afet_ccm_ctx *c, const uint8_t nonce[AFET_CCM_NONCE], const uint8_t *in, size_t len,
                      uint8_t *out)
{
    uint8_t s[16];
    for (size_t pos = 0, i = 1; pos < len; pos += 16, i++) {
        size_t n = len - pos < 16 ? len - pos : 16;
        ctr_block(c, nonce, (uint32_t)i, s);
        for (size_t j = 0; j < n; j++) {
            out[pos + j] = (uint8_t)(in[pos + j] ^ s[j]);
        }
    }
}

int afet_ccm_seal(const afet_ccm_ctx *c, const uint8_t nonce[AFET_CCM_NONCE], const uint8_t *aad, size_t aad_len,
                  const uint8_t *pt, size_t len, uint8_t *ct, uint8_t tag[AFET_CCM_TAG])
{
    uint8_t x[16], s0[16];
    cbc_mac(c, nonce, aad, aad_len, pt, len, x);
    ctr_block(c, nonce, 0, s0);
    for (int i = 0; i < AFET_CCM_TAG; i++) {
        tag[i] = (uint8_t)(x[i] ^ s0[i]);
    }
    ctr_crypt(c, nonce, pt, len, ct);
    return 0;
}

int afet_ccm_open(const afet_ccm_ctx *c, const uint8_t nonce[AFET_CCM_NONCE], const uint8_t *aad, size_t aad_len,
                  const uint8_t *ct, size_t len, const uint8_t tag[AFET_CCM_TAG], uint8_t *pt)
{
    uint8_t tmp[256], x[16], s0[16];
    if (len > sizeof(tmp)) {
        return -2;
    }
    ctr_crypt(c, nonce, ct, len, tmp);
    cbc_mac(c, nonce, aad, aad_len, tmp, len, x);
    ctr_block(c, nonce, 0, s0);
    uint8_t diff = 0;
    for (int i = 0; i < AFET_CCM_TAG; i++) {
        diff |= (uint8_t)((x[i] ^ s0[i]) ^ tag[i]);
    }
    if (diff) {
        return -1;
    }
    memcpy(pt, tmp, len);
    return 0;
}
