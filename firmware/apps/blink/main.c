#include "board.h"

/* İlk donanım denemesi: dört LED sırayla yanar (150 ms'de bir ilerler); USER düğmesine basılıyken hepsi yanar.
 * Kartın çalıştığını, saatin ve GPIO'nun doğru ayarlandığını gösterir. */

volatile uint32_t blink_steps; /* SWD ile RAM'den okunabilir: program çalışıyor mu kontrolü için */

int main(void)
{
    board_init();
    uint32_t next = 150;
    unsigned step = 0;
    for (;;) {
        if (board_button()) {
            for (unsigned i = 0; i < BOARD_LED_COUNT; i++) {
                board_led(i, 1);
            }
        } else if (board_millis() >= next) {
            next += 150;
            for (unsigned i = 0; i < BOARD_LED_COUNT; i++) {
                board_led(i, i == step);
            }
            step = (step + 1) % BOARD_LED_COUNT;
            blink_steps++;
        }
        __asm volatile("wfi"); /* bir sonraki kesmeye (1 ms) kadar uyu */
    }
}
