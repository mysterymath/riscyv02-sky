#ifndef TT_PINS_H
#define TT_PINS_H

#include "hardware/gpio.h"

// TT06+ demoboard GPIO assignments (also used for IHP shuttles).

// Control signals
#define TT_GP_PROJCLK      0   // Project clock (PWM output)
#define TT_GP_NPROJECTRST   1   // Project reset (active low)
#define TT_GP_NCRST         2   // Mux controller reset (active low)
#define TT_GP_CINC          3   // Mux controller increment (rising edge)
#define TT_GP_CENA          4   // Mux controller enable

// ASIC output pins (active during both bus phases — directly readable)
// uo_out[0:3] = GPIO 5-8, uo_out[4:7] = GPIO 13-16  (NOT contiguous)
#define TT_GP_UO_OUT0       5
#define TT_GP_UO_OUT1       6
#define TT_GP_UO_OUT2       7
#define TT_GP_UO_OUT3       8
#define TT_GP_UO_OUT4      13
#define TT_GP_UO_OUT5      14
#define TT_GP_UO_OUT6      15
#define TT_GP_UO_OUT7      16

// ASIC input pins (directly writable — directly mapped to ui_in)
// ui_in[0:3] = GPIO 9-12, ui_in[4:7] = GPIO 17-20  (NOT contiguous)
#define TT_GP_UI_IN0        9
#define TT_GP_UI_IN1       10
#define TT_GP_UI_IN2       11
#define TT_GP_UI_IN3       12
#define TT_GP_UI_IN4       17
#define TT_GP_UI_IN5       18
#define TT_GP_UI_IN6       19
#define TT_GP_UI_IN7       20

// Bidirectional pins (directly mapped — contiguous)
// uio[0:7] = GPIO 21-28
#define TT_GP_UIO0         21
#define TT_GP_UIO_BASE     21   // For byte-wide operations

// Masks for gpio_get_all() / gpio_put_masked()
#define TT_UIO_MASK        (0xFFu << TT_GP_UIO_BASE)  // GPIO 21-28

// ---------------------------------------------------------------------------
// Byte scatter/gather for the non-contiguous uo_out and ui_in pin groups.
//
// GPIO layout (from gpio_get_all()):
//   Bits  5- 8: uo_out[0:3]
//   Bits 13-16: uo_out[4:7]
//   Bits  9-12: ui_in[0:3]
//   Bits 17-20: ui_in[4:7]
//   Bits 21-28: uio[0:7]
// ---------------------------------------------------------------------------

// Extract uo_out[7:0] from a raw gpio_get_all() value.
static inline uint8_t tt_read_uo_out(uint32_t gpio_all) {
    uint8_t lo = (gpio_all >> TT_GP_UO_OUT0) & 0x0F;  // bits 5-8 → [3:0]
    uint8_t hi = (gpio_all >> TT_GP_UO_OUT4) & 0x0F;  // bits 13-16 → [3:0]
    return lo | (hi << 4);
}

// Extract uio[7:0] from a raw gpio_get_all() value.
static inline uint8_t tt_read_uio(uint32_t gpio_all) {
    return (gpio_all >> TT_GP_UIO_BASE) & 0xFF;
}

// Write ui_in[7:0] via gpio_put_masked().
static inline void tt_write_ui_in(uint8_t val) {
    uint32_t lo = (uint32_t)(val & 0x0F) << TT_GP_UI_IN0;  // [3:0] → bits 9-12
    uint32_t hi = (uint32_t)(val >> 4)    << TT_GP_UI_IN4;  // [7:4] → bits 17-20
    uint32_t mask = (0x0Fu << TT_GP_UI_IN0) | (0x0Fu << TT_GP_UI_IN4);
    gpio_put_masked(mask, lo | hi);
}

// Write uio[7:0] via gpio_put_masked() (caller must set direction first).
static inline void tt_write_uio(uint8_t val) {
    gpio_put_masked(TT_UIO_MASK, (uint32_t)val << TT_GP_UIO_BASE);
}

// Set uio direction: 1 = RP2350 drives (output), 0 = ASIC drives (input).
static inline void tt_uio_set_dir(uint8_t oe_mask) {
    gpio_set_dir_masked(TT_UIO_MASK, (uint32_t)oe_mask << TT_GP_UIO_BASE);
}

#endif // TT_PINS_H
