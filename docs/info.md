<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

RISCY-V02 is a 16-bit RISC processor that is logically pin-compatible with the
WDC 65C02. It provides 8x 16-bit general-purpose registers, a 2-stage pipeline
(Fetch / Execute), a barrel shifter, and fixed 16-bit instruction encoding.

The design uses a time-division multiplexed bus protocol to fit the 16-bit
address bus and 8-bit data bus onto Tiny Tapeout's limited I/O pins.

Each clock period is one CPU cycle. The clock drives a two-phase bus protocol:

- **Phase 0 (negedge to posedge):** Address output on `uo_out` and `uio`
- **Phase 1 (posedge to negedge):** Data/status on `uo_out`, data I/O on `uio`

See `src/tt_um_riscyv02_demux.v` for a reference demux implementation.

## How to test

Connect a demux circuit to reconstruct the full address and data buses from
the multiplexed output. Wire up external RAM and a clock source, then load a
program into memory. The CPU begins execution from address `$0000` after
deasserting reset.

The cocotb test suite (`test/`) exercises the full instruction set against a
64KB RAM model, including differential fuzz testing against a behavioral
emulator.

## External hardware

- External demux logic (directly connected or FPGA/CPLD)
- RAM (SRAM or FPGA block RAM)
- Clock source
