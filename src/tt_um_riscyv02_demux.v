/*
 * Demux wrapper: reconstructs 65C02-style bus signals from TT muxed pins.
 *
 * PURPOSE
 *
 *   The TT (Tiny Tapeout) chip multiplexes a 16-bit address bus and 8-bit
 *   data bus onto limited I/O pins.  This module demultiplexes those pins
 *   back into familiar bus signals suitable for connecting to async SRAM,
 *   ROM, and peripherals on a PCB.
 *
 *   It is "executable PCB wiring documentation": the logic here is what
 *   you'd implement with discrete gates and flip-flops on a real board.
 *   It also serves as a simulation wrapper for verifying the full mux/demux
 *   round-trip against the Dormann test suite or other test programs.
 *
 * CONNECTION
 *
 *   Wire this module's TT-side ports directly to the chip's pins:
 *
 *     tt_um_riscyv02_demux demux (
 *         .ui_in  (chip_ui_in),    // active-low control inputs → chip
 *         .uo_out (chip_uo_out),   // ← chip output bus
 *         .uio_in (chip_uio_in),   // read data → chip
 *         .uio_out(chip_uio_out),  // ← chip bidir bus (out)
 *         .uio_oe (chip_uio_oe),   // ← chip bidir bus (OE)
 *         .clk    (chip_clk),      // shared clock
 *         .rst_n  (chip_rst_n),    // shared reset
 *         // Reconstructed bus → your SRAM, ROM, peripherals:
 *         .ADDR   (ADDR),
 *         .DATA_O (DATA_O),
 *         .DATA_I (DATA_I),
 *         .DATA_OE(DATA_OE),
 *         .PHI2   (PHI2),
 *         .RWB    (RWB),
 *         .SYNC   (SYNC),
 *         // Control inputs from peripherals:
 *         .IRQB   (irqb),
 *         .NMIB   (nmib),
 *         .RDY    (rdy)
 *     );
 *
 * BUS PROTOCOL
 *
 *   The chip's internal mux_sel register toggles on every clock edge,
 *   alternating between address phase and data phase.  Because mux_sel
 *   is a DFF (not combinational), it transitions tCQ *after* each clock
 *   edge.  This means the previous phase's outputs are still stable at
 *   the clock edge, providing natural hold time for sampling.
 *
 *   Timing diagram (one full bus cycle):
 *
 *          posedge           negedge           posedge
 *             │                 │                 │
 *       ┌─────┘                 └─────────────────┘
 *  clk  │       HIGH (data)        LOW (addr)      HIGH ...
 *       └─────┐                 ┌─────────────────┐
 *             │                 │                 │
 *     mux_sel:  still 0 → 1     still 1 → 0       still 0 → 1
 *                (addr)  (data)  (data)  (addr)    (addr)  (data)
 *
 *   At posedge clk:
 *     mux_sel is still 0 (address phase).
 *     uo_out[7:0]  = AB[7:0]   (address low byte)
 *     uio_out[7:0] = AB[15:8]  (address high byte)
 *     → Capture ADDR into posedge DFFs.
 *
 *   At negedge clk:
 *     mux_sel is still 1 (data phase).
 *     uo_out[0]    = RWB       (1=read, 0=write)
 *     uo_out[1]    = SYNC      (instruction boundary)
 *     uo_out[7:2]  = 0
 *     uio_out[7:0] = write data (when RWB=0)
 *     uio_oe       = RWB ? 8'h00 : 8'hFF
 *     uio_in       = read data  (when RWB=1)
 *
 * SAFE-DEFAULT GATING
 *
 *   During address phase (clk LOW), uo_out carries address bits — garbage
 *   if interpreted as control signals.  Naive approaches (negedge DFF
 *   capture of RWB) introduce a half-cycle stale value that causes
 *   spurious writes on write→read transitions.
 *
 *   Instead, RWB and SYNC are gated combinationally with clk:
 *
 *     RWB  = uo_out[0] | ~clk    →  1 (read/safe) during address phase
 *     SYNC = uo_out[1] & clk     →  0 (inactive) during address phase
 *
 *   This makes the standard 65C02 async SRAM formulas work directly:
 *
 *     WE# = ~(PHI2 & ~RWB) = ~clk | uo_out[0]
 *       → HIGH (inactive) during address phase (clk=0)
 *       → reflects real RWB during data phase (clk=1)
 *
 *     OE# = ~(PHI2 & RWB) = ~(clk & uo_out[0])
 *       → HIGH (inactive) during address phase (clk=0)
 *       → reflects real RWB during data phase (clk=1)
 *
 *   With these formulas, writes latch on WE# rising edge (clk falling),
 *   and reads are combinational while OE# is active (data phase, clk HIGH).
 *   No glitches occur during address phase because both WE# and OE# are
 *   forced inactive.
 *
 * CONTROL INPUTS
 *
 *   ui_in[0] = IRQB  (active-low, level-sensitive interrupt request)
 *   ui_in[1] = NMIB  (active-low, edge-triggered non-maskable interrupt)
 *   ui_in[2] = RDY   (active-high, stall/single-step)
 *   ui_in[7:3] unused
 *
 * DATA BUS ACTIVE-LOW CAVEAT
 *
 *   DATA_OE is derived from uio_oe: when all bits are 8'hFF, the CPU is
 *   driving write data.  During address phase, uio_oe is also 8'hFF
 *   (driving address high byte), so DATA_OE is high in both address phase
 *   and write data phase.  External logic should only sample DATA_OE
 *   during data phase (PHI2 HIGH).  On a PCB, you'd gate with:
 *
 *     DATA_DIR = PHI2 & DATA_OE   (1 = CPU→SRAM, 0 = SRAM→CPU)
 *
 *   Or equivalently, use WE#/OE# which already incorporate the phase.
 */

`default_nettype none

module tt_um_riscyv02_demux (
    // TT chip pins (directly wired to chip)
    output wire [7:0] ui_in,     // → TT chip ui_in
    input  wire [7:0] uo_out,    // ← TT chip uo_out
    output reg  [7:0] uio_in,    // → TT chip uio_in (read data to CPU)
    input  wire [7:0] uio_out,   // ← TT chip uio_out
    input  wire [7:0] uio_oe,    // ← TT chip uio_oe

    // TT infrastructure (directly wired to chip)
    input  wire       clk,       // TT clock
    input  wire       rst_n,     // TT reset (active-low)

    // Reconstructed bus signals (directly usable by SRAM/ROM/peripherals)
    output reg [15:0] ADDR,      // latched address bus
    output wire [7:0] DATA_O,    // write data from CPU (active when DATA_OE=1)
    input  wire [7:0] DATA_I,    // read data to CPU (active when RWB=1)
    output wire       DATA_OE,   // high when CPU is writing (DATA_O valid)
    output wire       PHI2,      // bus phase / CPU clock (= clk)
    output wire       RWB,       // read/write: 1=read, 0=write
    output wire       SYNC,      // instruction boundary indicator

    // Control inputs (directly from peripherals)
    input  wire       IRQB,      // active-low interrupt request (directly to chip)
    input  wire       NMIB,      // active-low non-maskable interrupt (directly to chip)
    input  wire       RDY        // active-high ready / single-step (directly to chip)
);

  // PHI2 = clk directly.
  assign PHI2 = clk;

  // -----------------------------------------------------------------------
  // Address latch: capture at posedge clk.
  //
  // At posedge clk, the chip's mux_sel is still 0 (address phase) because
  // the toggle FF hasn't fired yet. So uo_out = AB[7:0] and
  // uio_out = AB[15:8] are stable with tCQ hold time.
  // -----------------------------------------------------------------------
  always @(posedge clk or negedge rst_n)
    if (!rst_n)
      ADDR <= 16'h0000;
    else
      ADDR <= {uio_out, uo_out};

  // -----------------------------------------------------------------------
  // RWB / SYNC: combinational with safe defaults during address phase.
  //
  // During address phase (clk LOW), uo_out carries address bits — garbage
  // for control signals. Gate with clk to present safe defaults:
  //   RWB  = 1 (read) during address phase, real value during data phase
  //   SYNC = 0 (inactive) during address phase, real value during data phase
  //
  // This makes standard async SRAM formulas work directly:
  //   WE# = ~(PHI2 & ~RWB) = ~clk | uo_out[0]
  //   OE# = ~(PHI2 & RWB)  = ~(clk & uo_out[0])
  // -----------------------------------------------------------------------
  assign RWB  = uo_out[0] | ~clk;
  assign SYNC = uo_out[1] & clk;

  // -----------------------------------------------------------------------
  // DATA bus.
  //
  // DATA_OE: combinational from uio_oe. During data phase (mux_sel=1),
  // uio_oe == 8'hFF means the CPU is writing. During address phase
  // (mux_sel=0), uio_oe is always 8'hFF (address output), so DATA_OE
  // is high in both cases. External logic should gate with PHI2:
  //   DATA_DIR = PHI2 & DATA_OE
  //
  // DATA_O: uio_out during data phase (directly passed through).
  //   Carries address high byte during address phase — don't use then.
  //
  // DATA_I: fed back to chip continuously via uio_in.
  //   The chip only samples it during data phase read cycles.
  // -----------------------------------------------------------------------
  assign DATA_OE = (uio_oe == 8'hFF);
  assign DATA_O  = uio_out;

  always @(*)
    uio_in = DATA_I;

  // -----------------------------------------------------------------------
  // Route control inputs to TT chip ui_in.
  //
  // RISCY-V02 control inputs (active-low unless noted):
  //   ui_in[0] = IRQB  (level-sensitive interrupt request)
  //   ui_in[1] = NMIB  (edge-triggered non-maskable interrupt)
  //   ui_in[2] = RDY   (active-high ready / single-step)
  //   ui_in[7:3] = 0   (unused)
  // -----------------------------------------------------------------------
  assign ui_in = {5'b00000, RDY, NMIB, IRQB};

endmodule
