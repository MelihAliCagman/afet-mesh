#ifndef BOARD_H
#define BOARD_H

#include <stdint.h>

/* STM32F4DISCOVERY: LED'ler PD12 (yeşil), PD13 (turuncu), PD14 (kırmızı), PD15 (mavi); USER düğmesi PA0.
 * Saat: 8 MHz kristal + PLL ile 168 MHz (kristal yoksa dahili 16 MHz ile devam edilir). */
#define BOARD_LED_COUNT 4

void board_init(void);
uint32_t board_cpu_hz(void);
uint32_t board_apb1_hz(void); /* PLL açıkken 42 MHz, değilse 16 MHz */
uint32_t board_millis(void);
void board_cycles_start(void);
uint32_t board_cycles(void);
void board_led(unsigned index, int on);
int board_button(void);

#endif
