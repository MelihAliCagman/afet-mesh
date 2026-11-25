#include "board.h"

#include "stm32f407.h"

static volatile uint32_t ticks_ms;
static uint32_t cpu_hz = 16000000u;

/* 8 MHz kristal -> PLL: VCO = 8/8 x 336 = 336 MHz, SYSCLK = 336/2 = 168 MHz, APB1 = 42 MHz, APB2 = 84 MHz. */
static void clock_init_168mhz(void)
{
    RCC_CR |= (1u << 16); /* HSEON */
    uint32_t t = 2000000u;
    while (!(RCC_CR & (1u << 17)) && --t) {
    }
    if (!t) {
        RCC_CR &= ~(1u << 16); /* kristal yok: dahili 16 MHz ile devam */
        return;
    }
    FLASH_ACR = 5u | (1u << 8) | (1u << 9) | (1u << 10); /* 5 bekleme durumu, komut ve veri önbelleği */
    RCC_PLLCFGR = 8u | (336u << 6) | (0u << 16) | (1u << 22) | (7u << 24);
    RCC_CR |= (1u << 24);
    t = 2000000u;
    while (!(RCC_CR & (1u << 25)) && --t) {
    }
    if (!t) {
        RCC_CR &= ~(1u << 24);
        return;
    }
    RCC_CFGR = (RCC_CFGR & ~((0xFu << 4) | (7u << 10) | (7u << 13))) | (5u << 10) | (4u << 13); /* AHB /1, APB1 /4, APB2 /2 */
    RCC_CFGR = (RCC_CFGR & ~3u) | 2u; /* sistem saati = PLL */
    t = 2000000u;
    while ((((RCC_CFGR >> 2) & 3u) != 2u) && --t) {
    }
    if (t) {
        cpu_hz = 168000000u;
    }
}

uint32_t board_cpu_hz(void)
{
    return cpu_hz;
}

uint32_t board_apb1_hz(void)
{
    return cpu_hz == 168000000u ? 42000000u : cpu_hz;
}

void board_cycles_start(void)
{
    DEMCR |= (1u << 24); /* TRCENA */
    DWT_CYCCNT = 0;
    DWT_CTRL |= 1u; /* CYCCNTENA */
}

uint32_t board_cycles(void)
{
    return DWT_CYCCNT;
}

void SysTick_Handler(void)
{
    ticks_ms++;
}

void board_init(void)
{
    DBGMCU_CR |= DBGMCU_CR_LOWPOWER_DEBUG; /* uyku komutlarında bile hata ayıklayıcı bağlanabilsin */

    clock_init_168mhz();

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

    SYST_RVR = cpu_hz / 1000u - 1u; /* 1 ms */
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
