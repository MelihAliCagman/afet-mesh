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
#define RCC_AHB1ENR_GPIOAEN (1u << 0)
#define RCC_AHB1ENR_GPIODEN (1u << 3)

#define GPIOA_MODER REG32(0x40020000u)
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


/* Hata ayıklama izleme birimi: çevrim sayacı (DWT) ile süre ölçümü */
#define DEMCR REG32(0xE000EDFCu)
#define DWT_CTRL REG32(0xE0001000u)
#define DWT_CYCCNT REG32(0xE0001004u)

#endif
