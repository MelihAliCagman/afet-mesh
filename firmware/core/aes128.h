#ifndef AFET_AES128_H
#define AFET_AES128_H

#include <stdint.h>

typedef struct {
    uint8_t rk[176];
} aes128_ctx;

void aes128_init(aes128_ctx *ctx, const uint8_t key[16]);
void aes128_encrypt_block(const aes128_ctx *ctx, const uint8_t in[16], uint8_t out[16]);

#endif
