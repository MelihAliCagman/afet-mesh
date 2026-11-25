#include "uart.h"

#include "board.h"
#include "stm32f407.h"

#define RX_SIZE 512 /* 2'nin kuvveti */

static volatile uint8_t rx_buf[RX_SIZE];
static volatile uint32_t rx_head, rx_tail, overruns;

void USART2_IRQHandler(void)
{
    uint32_t sr = USART2_SR;
    if (sr & (USART_SR_RXNE | USART_SR_ORE)) {
        uint8_t b = (uint8_t)USART2_DR; /* DR okumak RXNE ve ORE'yi temizler */
        if (rx_head - rx_tail < RX_SIZE) {
            rx_buf[rx_head % RX_SIZE] = b;
            rx_head++;
        } else {
            overruns++; /* yazılım tamponu doldu */
        }
        if (sr & USART_SR_ORE) {
            overruns++; /* donanım taşması: bayt kaçtı */
        }
    }
}

void uart_init(int loopback)
{
    RCC_AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    RCC_APB1ENR |= RCC_APB1ENR_USART2EN;
    (void)RCC_APB1ENR;

    /* PA2, PA3: alternatif işlev (10), AF7 (USART2), yukarı çekme (boştaki hat yüksek) */
    GPIOA_MODER = (GPIOA_MODER & ~((3u << 4) | (3u << 6))) | (2u << 4) | (2u << 6);
    GPIOA_AFRL = (GPIOA_AFRL & ~((0xFu << 8) | (0xFu << 12))) | (7u << 8) | (7u << 12);
    GPIOA_PUPDR = (GPIOA_PUPDR & ~((3u << 4) | (3u << 6))) | (1u << 4) | (1u << 6);
    if (loopback) {
        GPIOA_OTYPER |= (1u << 2); /* yarım çift yönlü modda TX pini açık savaklı olmalı */
    } else {
        GPIOA_OTYPER &= ~(1u << 2);
    }

    USART2_CR1 = 0;
    USART2_BRR = (board_apb1_hz() + UART_BAUD / 2u) / UART_BAUD; /* 16x örnekleme: BRR = fck / baud */
    USART2_CR3 = loopback ? USART_CR3_HDSEL : 0u;
    USART2_CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE | USART_CR1_RXNEIE;
    NVIC_ISER1 = (1u << 6);
}

void uart_write(const uint8_t *data, size_t len)
{
    for (size_t i = 0; i < len; i++) {
        while (!(USART2_SR & USART_SR_TXE)) {
        }
        USART2_DR = data[i];
    }
    while (!(USART2_SR & USART_SR_TC)) {
    }
}

int uart_read_byte(void)
{
    if (rx_head == rx_tail) {
        return -1;
    }
    uint8_t b = rx_buf[rx_tail % RX_SIZE];
    rx_tail++;
    return b;
}

uint32_t uart_overruns(void)
{
    return overruns;
}
