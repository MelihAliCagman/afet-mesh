#include "aes128.h"

#include <string.h>

/* AES-128, yalnızca şifreleme yönü (CCM yalnızca şifreleme kullanır). S kutusu açılışta hesaplanır. */

static uint8_t sbox[256];
static int sbox_ready;

static uint8_t rotl8(uint8_t x, int s)
{
    return (uint8_t)((x << s) | (x >> (8 - s)));
}

static void sbox_init(void)
{
    uint8_t p = 1, q = 1;
    do {
        p = (uint8_t)(p ^ (p << 1) ^ ((p & 0x80) ? 0x1B : 0));
        q ^= (uint8_t)(q << 1);
        q ^= (uint8_t)(q << 2);
        q ^= (uint8_t)(q << 4);
        if (q & 0x80) {
            q ^= 0x09;
        }
        uint8_t x = (uint8_t)(q ^ rotl8(q, 1) ^ rotl8(q, 2) ^ rotl8(q, 3) ^ rotl8(q, 4));
        sbox[p] = (uint8_t)(x ^ 0x63);
    } while (p != 1);
    sbox[0] = 0x63;
    sbox_ready = 1;
}

static uint8_t xtime(uint8_t x)
{
    return (uint8_t)((x << 1) ^ ((x & 0x80) ? 0x1B : 0));
}

void aes128_init(aes128_ctx *ctx, const uint8_t key[16])
{
    static const uint8_t rcon[10] = {0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36};
    if (!sbox_ready) {
        sbox_init();
    }
    memcpy(ctx->rk, key, 16);
    for (int i = 4; i < 44; i++) {
        uint8_t t[4];
        memcpy(t, &ctx->rk[(i - 1) * 4], 4);
        if (i % 4 == 0) {
            uint8_t tmp = t[0];
            t[0] = (uint8_t)(sbox[t[1]] ^ rcon[i / 4 - 1]);
            t[1] = sbox[t[2]];
            t[2] = sbox[t[3]];
            t[3] = sbox[tmp];
        }
        for (int j = 0; j < 4; j++) {
            ctx->rk[i * 4 + j] = (uint8_t)(ctx->rk[(i - 4) * 4 + j] ^ t[j]);
        }
    }
}

static void add_round_key(uint8_t s[16], const uint8_t *rk)
{
    for (int i = 0; i < 16; i++) {
        s[i] ^= rk[i];
    }
}

static void sub_shift(uint8_t s[16])
{
    uint8_t t[16];
    for (int c = 0; c < 4; c++) {
        for (int r = 0; r < 4; r++) {
            t[r + 4 * c] = sbox[s[r + 4 * ((c + r) % 4)]];
        }
    }
    memcpy(s, t, 16);
}

static void mix_columns(uint8_t s[16])
{
    for (int c = 0; c < 4; c++) {
        uint8_t *a = &s[4 * c];
        uint8_t a0 = a[0], a1 = a[1], a2 = a[2], a3 = a[3];
        uint8_t all = (uint8_t)(a0 ^ a1 ^ a2 ^ a3);
        a[0] = (uint8_t)(a0 ^ all ^ xtime((uint8_t)(a0 ^ a1)));
        a[1] = (uint8_t)(a1 ^ all ^ xtime((uint8_t)(a1 ^ a2)));
        a[2] = (uint8_t)(a2 ^ all ^ xtime((uint8_t)(a2 ^ a3)));
        a[3] = (uint8_t)(a3 ^ all ^ xtime((uint8_t)(a3 ^ a0)));
    }
}

void aes128_encrypt_block(const aes128_ctx *ctx, const uint8_t in[16], uint8_t out[16])
{
    uint8_t s[16];
    memcpy(s, in, 16);
    add_round_key(s, ctx->rk);
    for (int round = 1; round < 10; round++) {
        sub_shift(s);
        mix_columns(s);
        add_round_key(s, ctx->rk + 16 * round);
    }
    sub_shift(s);
    add_round_key(s, ctx->rk + 160);
    memcpy(out, s, 16);
}
