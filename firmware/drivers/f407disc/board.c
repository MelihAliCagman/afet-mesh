#include "board.h"

#include "stm32f407.h"

static volatile uint32_t ticks_ms;

void SysTick_Handler(void)
{
    ticks_ms++;
}

void board_init(void)
{
    DBGMCU_CR |= DBGMCU_CR_LOWPOWER_DEBUG; /* uyku komutlarında bile hata ayıklayıcı bağlanabilsin */

    RCC_AHB1ENR |= RCC_AHB1ENR_GPIOAEN | RCC_AHB1ENR_GPIODEN;
    (void)RCC_AHB1ENR; /* saat açıldıktan sonra yazmaça erişmeden önce kısa bekleme */

    /* PD12..PD15 çıkış (MODER'da pin başına 2 bit, 01 = çıkış) */
    uint32_t m = GPIOD_MODER;
    for (unsigned pin = 12; pin <= 15; pin++) {
        m &= ~(3u << (2 * pin));
        m |= (1u << (2 * pin));
    }
    GPIOD_MODER = m;
    GPIOA_MODER &= ~3u; /* PA0 giriş */

    SYST_RVR = BOARD_CPU_HZ / 1000u - 1u; /* 1 ms */
    SYST_CVR = 0;
    SYST_CSR = 7u; /* işlemci saati, kesme açık, sayaç açık */
}

uint32_t board_millis(void)
{
    return ticks_ms;
}

void board_led(unsigned index, int on)
{
    if (index >= BOARD_LED_COUNT) {
        return;
    }
    unsigned pin = 12 + index;
    GPIOD_BSRR = on ? (1u << pin) : (1u << (pin + 16)); /* BSRR: alt 16 bit set, üst 16 bit reset */
}

int board_button(void)
{
    return (GPIOA_IDR & 1u) != 0;
}
