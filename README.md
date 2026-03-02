![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/fpga/badge.svg)

# RISCY-V02

A 16-bit RISC processor, logically pin-compatible with the WDC 65C02.
Designed for [Tiny Tapeout](https://tinytapeout.com) SKY130.

## Overview

RISCY-V02 exists to challenge the notion that the 6502 was a "local optimum"
in its transistor budget. Given the constraints of 1970s home computers
(~1 MHz DRAM, so raw clock speed doesn't help), could RISC have been a better
design choice? This design argues yes: pipelining, barrel shifters, and more
registers beat microcode PLAs, questionable addressing modes, and hardware BCD.

**Highlights:**

- 8x 16-bit general-purpose registers (vs 3x 8-bit on 6502)
- 2-stage pipeline (Fetch/Execute) with speculative fetch
- 61 fixed 16-bit instructions
- 2-cycle interrupt entry (vs 7 on 6502)
- 13,844 SRAM-adjusted transistors (vs 13,176 for 6502 on same process)
- 1.0-2.6x faster than 6502 across common routines

## Documentation

The full datasheet is in **[docs/info.md](docs/info.md)**, covering:

- Bus protocol and pinout
- Complete ISA reference with cycle counts
- Instruction encoding
- Pipeline timing and self-modifying code rules
- Interrupt architecture
- Code comparisons vs 6502 (memcpy, multiply, CRC, etc.)
- Demo board firmware and programming workflow
- Bus demux design for async SRAM

## Tiny Tapeout Details

| Property | Value |
|---|---|
| Top module | `tt_um_riscyv02` |
| Tiles | 1x2 |
| Clock | TBD (fMax binary search pending) |
| Process | SKY130 |
| Language | Verilog |

### Pinout

**Inputs (`ui_in`)**

| Pin | Function |
|---|---|
| `ui_in[0]` | IRQB (active-low interrupt request) |
| `ui_in[1]` | NMIB (active-low NMI, edge-triggered) |
| `ui_in[2]` | RDY (active-high ready) |
| `ui_in[7:3]` | Unused |

**Outputs (`uo_out`) and Bidirectional (`uio`)**

Pins are time-multiplexed between address and data phases:

| Phase | `uo_out[7:0]` | `uio[7:0]` |
|---|---|---|
| Address (clk LOW) | AB[7:0] | AB[15:8] (output) |
| Data (clk HIGH) | {0, SYNC, RWB} | D[7:0] (bidirectional) |

## Building

### Tests

```
cd test && make
```

### Hardening

```
cd test && make harden
cd test && make metrics
```

## Resources

- [Tiny Tapeout](https://tinytapeout.com)
- [LibreLane (hardening flow)](https://www.zerotoasiccourse.com/terminology/librelane/)
- [TT community Discord](https://tinytapeout.com/discord)
