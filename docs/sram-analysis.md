# Register File SRAM Analysis

Standard cell synthesis implements the register file with latches (~20T each) and mux trees, but a real chip would use SRAM cells (~8T each) — the 8×16-bit 2R1W array is perfectly regular. This over-counting inflates the RISCY-V02 transistor count by ~2,000T and makes the comparison with the 6502 misleading. This section designs an equivalent 8T SRAM register file from first principles, counts every transistor, and computes the adjusted figures.

## Why This Discount Is Fair

The discount applies only to **regular storage arrays** — identical bit cells in a grid with shared decode/sense logic. The same methodology applied to the 6502 yields zero discount: its registers (A, X, Y, SP) are asymmetric, each wired to different datapath elements, and would not use SRAM in any implementation.

## Standard Cell Register File (Synthesized)

The register file is a single Verilog module (`riscyv02_regfile`) marked `(* keep_hierarchy *)` so its cell counts appear as a sub-module in `stat.json`. It contains 20 leader latches (write staging), 128 follower latches (8 regs × 16 bits, the pure storage array), and combinational decode/mux trees. The `transistor_count.py` script reads the actual count from each build's `stat.json`.

## 8T SRAM Register File Design

### How SRAM Works

The basic SRAM cell stores one bit using two cross-coupled inverters (P1/N1 and P2/N2). Each inverter drives the other's input, creating two stable states: Q=0/QB=1 or Q=1/QB=0. Once set, the feedback loop is self-reinforcing — the cell holds its value indefinitely as long as power is applied.

To *read* the standard 6T cell, the controller first precharges both bit lines (BL and BLB) to VDD. Then the word line (WL) turns on two NMOS access transistors (N3, N4), connecting the storage nodes to the bit lines. The side storing a 0 begins to discharge its bit line through the access transistor and the pulling-down NMOS of that side's inverter. The side storing a 1 holds its bit line high. A sense amplifier detects the resulting voltage difference. This read is mildly *destructive*: the high bit line pushes current into the low storage node, fighting the cell. The storage inverters must be stronger than the access transistors (the "cell ratio") to prevent a read upset. For an 8-row array this disturbance is negligible — the bit-line capacitance is so small that the fight barely moves the storage node.

To *write*, the controller drives BL and BLB to opposite values (one high, one low) and asserts WL. The driven bit lines overpower the storage inverters, flipping the cell if needed. This is why write drivers must be stronger than the cell — the "pull-up ratio."

### Why 8T

6T SRAM provides 1 port. Our register file requires 2 simultaneous reads (the ALU needs both operands in the same cycle). The minimum cell for 2 ports is 8T:

- **6T** = 4T storage + 2T access = 1 port
- **8T** = 4T storage + 2T RW access + 2T read-only = 2 ports (1RW + 1R)

The read-only port adds two NMOS transistors: N5 (access, gated by a separate read word line WL_r) and N6 (driver, whose gate connects to QB). The read bit line (RBL) is precharged high. When WL_r is asserted: if QB=1 (meaning Q=0), N6 conducts and N5 passes current — RBL discharges to ground, reading "0". If QB=0 (meaning Q=1), N6 is off — RBL stays high, reading "1". So RBL directly represents Q without inversion.

The key advantage of this read-only port is that it never disturbs the storage nodes. N5 and N6 are in series between RBL and ground — they can pull RBL down, but they can't push current into the storage inverters. This allows simultaneous reads on both ports without interference.

We time-share the RW port: reads during clk=1, writes during clk=0. The R-only port provides the second simultaneous read. This matches our pipeline exactly.

### 8T Bit Cell

```
Storage:   P1 P2 N1 N2  (cross-coupled inverters)     = 4T
RW port:   N3 N4        (access NMOS, gated by WL_rw)  = 2T
R port:    N5 N6        (N5=access gated by WL_r,      = 2T
                         N6=driver gated by QB)
                                                       ────
                                                         8T
```

### Clock Phases

The SRAM register file is synchronous, organized around two clock phases:

**Phase 1 — clk=1 (read).** Both read decoders assert their word lines (WL_rw for port 1, WL_r for port 2). The bit lines were precharged high during the previous clk=0 phase, so they start at VDD. Selected cells discharge their respective bit lines according to the stored values. For an 8-row array the parasitic loading is minimal — each bit line sees only 8 access transistors — so the discharge completes quickly, producing a full-swing result well before mid-phase. The execute unit reads r1 and r2 combinationally during this window.

**Phase 2 — clk=0 (write + precharge).** Read word lines are deasserted and bit lines float. If w_we=1, the write decoder asserts WL_rw for the selected row while write drivers force BL and BLB to w_data and ~w_data, flipping cells as needed. After the write completes, precharge transistors pull BL and BLB back to VDD, and equalize transistors short BL to BLB to eliminate any residual voltage difference before the next read. The single-ended read bit lines (RBL) are restored by weak PMOS keepers that hold RBL high whenever no cell is pulling it down.

### Mapping to the CPU Pipeline

The SRAM register file is a drop-in replacement for the standard cell latch-based implementation — same interface, same timing contract:

- **Write staging:** The leader latches capture w_data, w_sel, and w_we at the falling edge of clk (end of the read phase), holding them stable for the entire write phase. The follower latches in the standard cell implementation are transparent during clk=0 — exactly matching the SRAM's write-during-clk=0 window.
- **Read ports:** Both implementations are combinational during clk=1. The SRAM produces output via bit-line discharge; the standard cell version produces output via mux tree propagation. The execute unit sees valid data by mid-phase in either case.
- **Precharge and equalize** happen during clk=0, overlapping with the write phase. This is invisible to the CPU — by the time clk rises and the next read begins, all bit lines are back at VDD and ready.

### Storage Array

8 rows x 16 columns = 128 cells x 8T = **1,024T**

### Write Path

Writes occur during clk=0 through the RW port. The write decoder selects one of 8 rows, the write-enable gate qualifies the word line, and 16 inverters generate complementary drive pairs for the bit lines. Both bytes are written simultaneously (16-bit write port).

#### Row Decoder (w_sel -> 8 one-hot lines)

A 3-to-8 decoder for all 8 rows using `w_sel[2:0]`:

| Component | Count | Tx/each | Transistors |
|---|---|---|---|
| INV (complement w_sel[2:0]) | 3 | 2 | 6 |
| AND3 (NAND3 + INV, one per row) | 8 | 8 | 64 |
| **Subtotal** | | | **70** |

#### Word Line Gating

Each decoded row line is ANDed with w_we to produce the write word line. Both byte halves share one word line (no byte select):

| Component | Purpose | Count | Tx/each | Transistors |
|---|---|---|---|---|
| AND2 | WL[i] = row[i] AND w_we | 8 | 6 | 48 |
| **Subtotal** | | | | **48** |

#### Write Drivers

Generate complementary data for the bit lines. Each column needs both the true and complement data values — the inverters produce ~w_data, while w_data itself drives BL directly. 16 data/complement pairs drive all 16 columns:

| Component | Purpose | Count | Tx/each | Transistors |
|---|---|---|---|---|
| INV | ~w_data[i] (complement) | 16 | 2 | 32 |
| **Subtotal** | | | | **32** |

**Write decode + drivers total: 150T**

#### Write Staging

Both the standard cell regfile and the SRAM equivalent need write staging. The standard cell version uses leader latches (included in the module). The SRAM equivalent uses input latches to hold w_data/w_sel/w_we stable during the write pulse:

| Component | Count | Tx/each | Transistors |
|---|---|---|---|
| Data latch (TG + inverter loop) | 16 | 6 | 96 |
| Address latch | 3 | 6 | 18 |
| Enable latch (with reset) | 1 | 8 | 8 |
| **Subtotal** | | | **122** |

**Write path total: 150 + 122 = 272T**

### Read Path 1 (RW Port, Differential)

Before each read, the bit lines must start at a known voltage (VDD). Three types of PMOS device handle this: precharge transistors pull BL and BLB individually to VDD, and an equalize transistor shorts BL to BLB so any residual imbalance is eliminated. All are gated by ~clk — active during the write phase (clk=0), off during the read phase (clk=1).

During clk=1, the RW port reads r1_sel. This is a 3-bit address selecting one of 8 rows. Differential bit lines (BL/BLB) give correct polarity directly. Full 16-bit output (no byte select).

| Component | Purpose | Count | Tx/each | Transistors |
|---|---|---|---|---|
| INV | complement r1_sel[2:0] | 3 | 2 | 6 |
| AND3 | row decode (one per row) | 8 | 8 | 64 |
| PMOS | precharge BL[0..15] | 16 | 1 | 16 |
| PMOS | precharge BLB[0..15] | 16 | 1 | 16 |
| PMOS | equalize BL=BLB | 16 | 1 | 16 |
| **Subtotal** | | | | **118** |

In a large SRAM (hundreds of rows), bit-line capacitance is dominated by the access transistors of unselected cells — the voltage swing is tiny and slow, requiring sense amplifiers (differential comparator circuits, ~40–60T per column) to detect it. Our 8-row array has minimal parasitic loading: each bit line sees only 8 access transistors. The full-swing discharge completes well within the half-cycle read window, so sense amplifiers are not needed. This saves ~1,000T across 16 columns.

### Read Path 2 (R-Only Port, Single-Ended)

The single-ended read bit line (RBL) uses a weak PMOS pull-up (keeper) instead of active precharge. The keeper holds RBL high when no cell is pulling it down. When a selected cell with Q=0 discharges RBL, the keeper is weak enough that the NMOS pull-down chain (N5+N6) wins. This is cheaper than precharge+equalize (1T vs 3T per column) but slower — acceptable here because the R-only port has no bit-line sharing conflict to create voltage imbalances.

Port 2 uses a 3-bit address and the 8T cell's dedicated read path: N5 (access, gated by read word line) in series with N6 (driver, gated by QB). Full 16-bit output (no byte select).

| Component | Purpose | Count | Tx/each | Transistors |
|---|---|---|---|---|
| INV | complement r2_sel inputs | 3 | 2 | 6 |
| AND3 | row decode (one per row) | 8 | 8 | 64 |
| PMOS | pull-up keeper RBL[0..15] | 16 | 1 | 16 |
| **Subtotal** | | | | **86** |

### Grand Total

| Component | Transistors | % |
|---|---|---|
| Storage array (128 x 8T) | 1,024 | 68.3% |
| Write path (decode + drivers + staging) | 272 | 18.1% |
| Read path 1 (RW, differential) | 118 | 7.9% |
| Read path 2 (R, single-ended) | 86 | 5.7% |
| **Total** | **1,500** | **100%** |

### Gate Transistor Counts Used

All counts use standard CMOS complementary logic:

| Gate | Transistors | Structure |
|---|---|---|
| INV | 2 | 1 PMOS + 1 NMOS |
| NAND2 | 4 | 2P parallel + 2N series |
| AND2 | 6 | NAND2 + INV |
| NAND3 | 6 | 3P parallel + 3N series |
| AND3 | 8 | NAND3 + INV |
| MUX2 | 6 | 2 transmission gates + 1 INV |
| PMOS (precharge/keeper) | 1 | single transistor |

## Comparison

| | Standard Cell | 8T SRAM |
|---|---|---|
| Write staging | 20 leader latches × 20T = 400 | 20 latches × 6T = 122 (TG-based) |
| Storage | 128 follower latches × 20T = 2,560 | 128 cells × 8T = 1,024 |
| Peripherals | decode + read mux trees | Decode + drivers = 354 |
| **Total** | **(from synthesis)** | **1,500** |

The SRAM saves on both storage (8T vs 20T per bit) and peripherals (word-line decode replaces 8:1 mux trees). Write staging is present in both implementations.

## SRAM-Adjusted Figures

Computed by `transistor_count.py` from each build's `stat.json`.

| Metric | Value |
|---|---|
| Register file (8T SRAM equivalent) | 1,500 |
| Other values | (computed by `transistor_count.py`) |

## Methodology Notes

Transistor counts are exact: standard cell counts from the PDK's CDL SPICE netlist (one M-line = one MOSFET), SRAM counts from the circuit design above using textbook CMOS. The 8T cell count is definitional. No SRAM macro exists at this size for IHP sg13g2 — the smallest available (64×32, 2048 bits) is 16× larger than needed. This is a paper design representing what a custom chip would use.

