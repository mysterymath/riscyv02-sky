// RISCY-V02 demoboard firmware
//
// Emulates 64 KiB of SRAM and a simple UART peripheral on the TT demoboard's
// RP2350.  Core 1 runs a bus-servicing loop that drives the project clock via
// GPIO (no PWM); core 0 handles USB serial I/O and the UART peripheral bridge.
//
// Build:
//   cmake -B build -G Ninja && cmake --build build
// Flash:
//   Drag build/riscyv02_firmware.uf2 to the RP2350's USB mass storage device.

#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "tt_pins.h"

// ---------------------------------------------------------------------------
// Memory map
// ---------------------------------------------------------------------------
#define MEM_SIZE       0x10000  // 64 KiB
#define UART_BASE      0xFF00   // UART peripheral registers
#define UART_TX_DATA   0xFF00   // Write: send byte over USB
#define UART_RX_DATA   0xFF01   // Read: receive byte from USB
#define UART_STATUS    0xFF02   // Read: bit 0 = TX ready, bit 1 = RX available

static uint8_t mem[MEM_SIZE];

// UART peripheral state (shared between cores)
static volatile uint8_t uart_rx_buf;
static volatile bool    uart_rx_ready;

// ---------------------------------------------------------------------------
// TT demoboard control
// ---------------------------------------------------------------------------

static void tt_init_gpio(void) {
    // Control signals
    gpio_init(TT_GP_PROJCLK);
    gpio_init(TT_GP_NPROJECTRST);
    gpio_init(TT_GP_NCRST);
    gpio_init(TT_GP_CINC);
    gpio_init(TT_GP_CENA);

    gpio_set_dir(TT_GP_PROJCLK, GPIO_OUT);
    gpio_set_dir(TT_GP_NPROJECTRST, GPIO_OUT);
    gpio_set_dir(TT_GP_NCRST, GPIO_OUT);
    gpio_set_dir(TT_GP_CINC, GPIO_OUT);
    gpio_set_dir(TT_GP_CENA, GPIO_OUT);

    gpio_put(TT_GP_PROJCLK, 0);
    gpio_put(TT_GP_NPROJECTRST, 1);  // Not in reset
    gpio_put(TT_GP_NCRST, 1);        // Not in reset
    gpio_put(TT_GP_CINC, 0);
    gpio_put(TT_GP_CENA, 0);

    // ui_in[7:0] — outputs from RP2350 to ASIC
    for (int i = 0; i < 4; i++) {
        gpio_init(TT_GP_UI_IN0 + i);
        gpio_set_dir(TT_GP_UI_IN0 + i, GPIO_OUT);
        gpio_init(TT_GP_UI_IN4 + i);
        gpio_set_dir(TT_GP_UI_IN4 + i, GPIO_OUT);
    }

    // uo_out[7:0] — inputs from ASIC to RP2350
    for (int i = 0; i < 4; i++) {
        gpio_init(TT_GP_UO_OUT0 + i);
        gpio_set_dir(TT_GP_UO_OUT0 + i, GPIO_IN);
        gpio_init(TT_GP_UO_OUT4 + i);
        gpio_set_dir(TT_GP_UO_OUT4 + i, GPIO_IN);
    }

    // uio[7:0] — bidirectional, start as inputs
    for (int i = 0; i < 8; i++) {
        gpio_init(TT_GP_UIO_BASE + i);
        gpio_set_dir(TT_GP_UIO_BASE + i, GPIO_IN);
    }
}

// Select project N on the TT mux controller.
static void tt_select_project(uint16_t n) {
    gpio_put(TT_GP_CENA, 0);
    gpio_put(TT_GP_CINC, 0);

    // Reset mux counter
    gpio_put(TT_GP_NCRST, 0);
    sleep_ms(10);
    gpio_put(TT_GP_NCRST, 1);
    sleep_ms(10);

    // Pulse cinc N times
    for (uint16_t i = 0; i < n; i++) {
        gpio_put(TT_GP_CINC, 1);
        sleep_us(100);
        gpio_put(TT_GP_CINC, 0);
        sleep_us(100);
    }

    // Enable selected project
    gpio_put(TT_GP_CENA, 1);
}

// Assert then release project reset.
static void tt_reset_project(void) {
    gpio_put(TT_GP_NPROJECTRST, 0);
    sleep_ms(2);
    gpio_put(TT_GP_NPROJECTRST, 1);
}

// ---------------------------------------------------------------------------
// Core 1: bus-servicing loop (software-driven clock)
//
// Core 1 drives the project clock directly via GPIO, advancing the ASIC one
// phase at a time.  This eliminates all timing pressure — each phase takes
// as long as it needs, with zero bus contention and deterministic behavior.
//
// Bus protocol (one CPU cycle = one clk period):
//   clk LOW  (mux_sel=0): Address phase
//     uo_out[7:0] = AB[7:0], uio[7:0] = AB[15:8] (driven by ASIC)
//   clk HIGH (mux_sel=1): Data phase
//     uo_out[0] = RWB, uo_out[1] = SYNC
//     uio[7:0] = D[7:0] (ASIC drives on write, RP2350 drives on read)
// ---------------------------------------------------------------------------

static void core1_bus_service(void) {
    // Clock starts LOW (set by tt_init_gpio). uio starts as input.
    while (true) {
        // --- Address Phase (clk LOW, mux_sel=0) ---
        // ASIC drives AB on uo_out[7:0] and uio[7:0].
        // uio is already input (released at end of previous iteration).
        uint32_t gpio = gpio_get_all();
        uint16_t addr = ((uint16_t)tt_read_uio(gpio) << 8)
                      | tt_read_uo_out(gpio);

        // Speculatively prepare read data
        uint8_t data;
        if (addr == UART_RX_DATA)
            data = uart_rx_buf;
        else if (addr == UART_STATUS)
            data = (multicore_fifo_wready() ? 0x01 : 0x00)
                 | (uart_rx_ready           ? 0x02 : 0x00);
        else
            data = mem[addr];

        // --- Posedge: latch address into demux, enter data phase ---
        gpio_put(TT_GP_PROJCLK, 1);

        // Data phase (clk HIGH, mux_sel=1).
        // uo_out[0] = RWB, uio = D[7:0].
        gpio = gpio_get_all();
        if (tt_read_uo_out(gpio) & 0x01) {
            // Read cycle (RWB=1): drive data onto uio
            tt_write_uio(data);
            tt_uio_set_dir(0xFF);
            if (addr == UART_RX_DATA)
                uart_rx_ready = false;
        } else {
            // Write cycle (RWB=0): capture data from uio
            uint8_t wd = tt_read_uio(gpio);
            if (addr == UART_TX_DATA) {
                if (multicore_fifo_wready())
                    multicore_fifo_push_blocking(wd);
            } else {
                mem[addr] = wd;
            }
        }

        // --- Negedge: CPU latches read data, enter address phase ---
        // Release uio BEFORE driving clk low (no bus contention).
        tt_uio_set_dir(0x00);
        gpio_put(TT_GP_PROJCLK, 0);
    }
}

// ---------------------------------------------------------------------------
// Core 0: program upload and UART bridge
//
// Upload protocol (over USB serial):
//   1. Firmware prints banner + "Ready" prompt
//   2. Host sends: 'L' <addr_lo> <addr_hi> <len_lo> <len_hi> <data...>
//   3. Firmware loads data into mem[], prints "OK <len> bytes at <addr>"
//   4. Repeat for additional segments
//   5. Host sends: 'G' — firmware starts the CPU
//   6. Host sends: 'R' — firmware stops the CPU, resets, re-enters upload
// ---------------------------------------------------------------------------

int main(void) {
    stdio_init_all();

    tt_init_gpio();

    // TODO: Read project index from config or command line.
    uint16_t project_index = 0;
    tt_select_project(project_index);

    // Set ui_in: IRQB=1 (inactive), NMIB=1 (inactive), RDY=1 (ready)
    tt_write_ui_in(0x07);

    tt_reset_project();

    printf("\nRISCY-V02 demoboard firmware\n");
    printf("Project index: %d\n", project_index);
    printf("Commands: L <addr16> <len16> <data...> | G (go) | R (reset)\n");

    while (true) {
        printf("Ready\n");

        // Upload loop: accept L/G commands until 'G' starts the CPU
        bool running = false;
        while (!running) {
            int cmd = getchar();
            switch (cmd) {
            case 'L': {
                uint16_t addr = (uint8_t)getchar();
                addr |= (uint16_t)(uint8_t)getchar() << 8;
                uint16_t len = (uint8_t)getchar();
                len |= (uint16_t)(uint8_t)getchar() << 8;
                for (uint16_t i = 0; i < len; i++)
                    mem[addr + i] = (uint8_t)getchar();
                printf("OK %u bytes at 0x%04X\n", len, addr);
                break;
            }
            case 'G':
                running = true;
                break;
            }
        }

        // Launch core 1 — it drives the clock, so the CPU starts immediately
        multicore_launch_core1(core1_bus_service);
        printf("Running\n");

        // UART bridge loop: core 0 handles USB ↔ UART
        bool halted = false;
        while (!halted) {
            // UART TX: core 1 pushes bytes into the multicore FIFO
            if (multicore_fifo_rvalid()) {
                uint8_t tx = (uint8_t)multicore_fifo_pop_blocking();
                putchar(tx);
            }

            // UART RX: buffer one byte from USB for the CPU to read
            if (!uart_rx_ready) {
                int c = getchar_timeout_us(0);
                if (c != PICO_ERROR_TIMEOUT) {
                    if (c == '\x12') {  // Ctrl-R: reset
                        halted = true;
                    } else {
                        uart_rx_buf = (uint8_t)c;
                        uart_rx_ready = true;
                    }
                }
            }
        }

        // Stop core 1, reset project, re-enter upload loop
        multicore_reset_core1();
        gpio_put(TT_GP_PROJCLK, 0);
        tt_uio_set_dir(0x00);
        tt_reset_project();
        printf("Reset\n");
    }
}
