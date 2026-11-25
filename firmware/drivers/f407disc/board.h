#ifndef BOARD_H
#define BOARD_H

#include <stdint.h>

/* STM32F4DISCOVERY: LED'ler PD12 (yeşil), PD13 (turuncu), PD14 (kırmızı), PD15 (mavi); USER düğmesi PA0.
 * Saat: sıfırlama sonrası dahili 16 MHz (HSI); ek saat ayarı yapılmaz. */
#define BOARD_CPU_HZ 16000000u
#define BOARD_LED_COUNT 4

void board_init(void);
uint32_t board_millis(void);
void board_led(unsigned index, int on);
int board_button(void);

#endif
