#ifndef UART_H
#define UART_H

#include <stddef.h>
#include <stdint.h>

/* USART2: PA2 = TX, PA3 = RX, 115200 8N1. İki kart arası bağlantı: TX <-> RX çapraz ve ortak GND (ikisi de 3,3 V).
 * loopback = 1: yarım çift yönlü iç mod; gönderilen baytlar kablo olmadan kendi alıcısına döner (sürücü testi için). */
#define UART_BAUD 115200u

void uart_init(int loopback);
void uart_write(const uint8_t *data, size_t len); /* bekleyerek yollar */
int uart_read_byte(void);                          /* alınan bayt veya -1 (kesmeyle dolan halka tampon) */
uint32_t uart_overruns(void);

#endif
