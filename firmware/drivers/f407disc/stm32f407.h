#ifndef STM32F407_H
#define STM32F407_H

#include <stdint.h>

/* STM32F407 için yalnızca kullandığımız yazmaçlar (RM0090). Hazır kitaplık kullanılmaz. */
#define REG32(addr) (*(volatile uint32_t *)(addr))

#define RCC_CR REG32(0x40023800u)
#define RCC_PLLCFGR REG32(0x40023804u)
#define RCC_CFGR REG32(0x40023808u)
#define FLASH_ACR REG32(0x40023C00u)
#define RCC_AHB1ENR REG32(0x40023830u)
#define RCC_APB1ENR REG32(0x40023840u)
#define RCC_APB1ENR_USART2EN (1u << 17)
#define RCC_AHB1ENR_GPIOAEN (1u << 0)
#define RCC_AHB1ENR_GPIODEN (1u << 3)

#define GPIOA_MODER REG32(0x40020000u)
#define GPIOA_OTYPER REG32(0x40020004u)
#define GPIOA_PUPDR REG32(0x4002000Cu)
#define GPIOA_AFRL REG32(0x40020020u)
#define GPIOA_IDR REG32(0x40020010u)
#define GPIOD_MODER REG32(0x40020C00u)
#define GPIOD_ODR REG32(0x40020C14u)
#define GPIOD_BSRR REG32(0x40020C18u)

/* Cortex-M4 çekirdek yazmaçları */
#define SYST_CSR REG32(0xE000E010u)
#define SYST_RVR REG32(0xE000E014u)
#define SYST_CVR REG32(0xE000E018u)
#define SCB_CPACR REG32(0xE000ED88u)

/* DBGMCU_CR: işlemci uykuda (sleep/stop/standby) iken de hata ayıklama saati açık kalsın; yoksa SWD bağlantısı koparır */
#define DBGMCU_CR REG32(0xE0042004u)
#define DBGMCU_CR_LOWPOWER_DEBUG 7u


/* USART2 (PA2 = TX, PA3 = RX, AF7) */
#define USART2_SR REG32(0x40004400u)
#define USART2_DR REG32(0x40004404u)
#define USART2_BRR REG32(0x40004408u)
#define USART2_CR1 REG32(0x4000440Cu)
#define USART2_CR3 REG32(0x40004414u)
#define USART_SR_ORE (1u << 3)
#define USART_SR_RXNE (1u << 5)
#define USART_SR_TC (1u << 6)
#define USART_SR_TXE (1u << 7)
#define USART_CR1_RE (1u << 2)
#define USART_CR1_TE (1u << 3)
#define USART_CR1_RXNEIE (1u << 5)
#define USART_CR1_UE (1u << 13)
#define USART_CR3_HDSEL (1u << 3)
#define NVIC_ISER1 REG32(0xE000E104u) /* USART2 kesmesi: IRQ 38 -> bit 6 */

/* Hata ayıklama izleme birimi: çevrim sayacı (DWT) ile süre ölçümü */
#define DEMCR REG32(0xE000EDFCu)
#define DWT_CTRL REG32(0xE0001000u)
#define DWT_CYCCNT REG32(0xE0001004u)

#endif
