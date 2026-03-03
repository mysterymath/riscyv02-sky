/*
 * Copyright (c) 2024 mysterymath
 * SPDX-License-Identifier: Apache-2.0
 *
 * RISCY-V02 — 16-bit RISC processor, pin-compatible with WDC 65C02.
 * Architecture: 2-stage pipeline (Fetch / Execute) with 8-bit muxed bus.
 * ISA: fixed 16-bit encoding (see riscyv02_execute.v).
 *
 * Bus protocol: shared with the 6502 comparison model (TT mux/demux).
 *
 *   mux_sel=0 (address out):
 *     uo_out[7:0]  = AB[7:0]
 *     uio_out[7:0] = AB[15:8]   (uio_oe = 8'hFF, all output)
 *
 *   mux_sel=1 (data + status):
 *     uo_out[0]    = RWB
 *     uo_out[1]    = SYNC (instruction boundary indicator)
 *     uo_out[7:2]  = 0
 *     uio[7:0]     = D[7:0] bidirectional data bus
 *     uio_oe       = RWB ? 8'h00 : 8'hFF
 *
 * Control inputs:
 *   ui_in[0]     = IRQB (active-low interrupt request, level-sensitive)
 *   ui_in[1]     = NMIB (active-low non-maskable interrupt, edge-triggered)
 *   ui_in[2]     = RDY  (active-high ready input for wait states / single-step)
 */

`default_nettype none

// =========================================================================
// Top module: mux_sel, bus arbitration, output muxes
// =========================================================================
module tt_um_riscyv02 (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output reg  [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

  wire [7:0] din     = uio_in;
  wire [7:0] ui_in_s = ui_in;

  // -----------------------------------------------------------------------
  // RDY input and clock gating
  // -----------------------------------------------------------------------
  wire rdy = ui_in_s[2];

  // Gated clock for CPU logic — freezes when RDY=0, waiting (WAI), or stopped (STP)
  wire exec_waiting, exec_stopped;
  wire wake = nmi_pending || nmi_edge || !irqb;
  wire cpu_rdy = rdy && !exec_stopped && (!exec_waiting || wake);
  wire cpu_clk;
  /* verilator lint_off PINMISSING */ // Power pins connected during PnR
  sky130_fd_sc_hd__dlclkp_1 u_cpu_icg (
    .CLK  (clk),
    .GATE (cpu_rdy),
    .GCLK (cpu_clk)
  );
  /* verilator lint_on PINMISSING */

  // -----------------------------------------------------------------------
  // NMI edge detection — ungated clock so edges during RDY=0 are captured.
  //
  // nmib_prev resets to 0 (active), meaning "assume NMI was already
  // asserted."  This prevents a spurious edge if NMIB is held low
  // during reset.  Trade-off: an NMI arriving on the exact cycle reset
  // releases is missed — same as the 6502, whose reset sequence clears
  // any pending NMI.
  // -----------------------------------------------------------------------
  wire nmib = ui_in_s[1];  // Active-low non-maskable interrupt (edge-triggered)

  reg nmib_prev;
  always @(negedge clk or negedge rst_n)
    if (!rst_n) nmib_prev <= 1'b0;
    else        nmib_prev <= nmib;

  wire nmi_edge = nmib_prev && !nmib;

  /* verilator lint_off UNOPTFLAT */
  wire exec_nmi_ack;
  /* verilator lint_on UNOPTFLAT */

  // -----------------------------------------------------------------------
  // NMI pending latch — cross-domain handshake
  //
  // nmi_pending should SET on the ungated clock (capture edges even when
  // the CPU is stalled or waiting) but CLEAR on the gated clock (only
  // when the CPU actually processes the NMI).  A single register can't
  // be clocked by two clocks, so we synthesize this indirectly:
  //
  //   cpu_rdy_latched mirrors the ICG's internal latch.  The ICG
  //   (sky130_fd_sc_hd__dlclkp_1) is transparent-low: during CLK=0 it follows
  //   cpu_rdy; at posedge CLK it captures and holds.  A posedge FF
  //   sampling cpu_rdy has the same capture point, so at every ungated
  //   negedge, cpu_rdy_latched == 1 iff the ICG produced a gated
  //   negedge on that same instant — i.e., the CPU is actually clocked.
  //
  //   Conditioning the pending clear on cpu_rdy_latched ensures:
  //     - WAI wake: cpu_rdy goes high combinationally at the ungated
  //       negedge (via wake), but cpu_rdy_latched still reflects the
  //       *previous* posedge capture (0, since the CPU was halted).
  //       The clear is blocked; nmi_edge sets pending normally.
  //       On the *next* negedge, cpu_rdy_latched = 1 (captured at the
  //       intervening posedge), and the CPU's first gated negedge
  //       processes the NMI and clears pending simultaneously.
  //     - RDY stall: cpu_rdy_latched = 0, so stale exec_nmi_ack from
  //       the frozen execute state can't spuriously clear pending.
  //     - Normal operation: cpu_rdy_latched = 1, exec_nmi_ack fires
  //       the same negedge execute takes the NMI, pending clears
  //       immediately.  Next cycle: pending = 0, no double-take.
  // -----------------------------------------------------------------------
  reg cpu_rdy_latched;
  always @(posedge clk or negedge rst_n)
    if (!rst_n) cpu_rdy_latched <= 1'b0;
    else        cpu_rdy_latched <= cpu_rdy;

  reg nmi_pending;
  always @(negedge clk or negedge rst_n)
    if (!rst_n)                                    nmi_pending <= 1'b0;
    else if (cpu_rdy_latched && exec_nmi_ack)      nmi_pending <= 1'b0;
    else if (nmi_edge)                             nmi_pending <= 1'b1;

  // -----------------------------------------------------------------------
  // Mux select: dual-edge register (shared with 6502 comparison model).
  // Runs on clk so protocol timing continues even when CPU is halted.
  //
  // Timing diagram (mux_sel toggles on both clock edges):
  //
  //       ┌───┐   ┌───┐   ┌───┐   ┌───┐
  //  clk  │   │   │   │   │   │   │   │
  //    ───┘   └───┘   └───┘   └───┘   └───
  //       0   1   0   1   0   1   0   1      <- mux_sel
  //       └─┬─┘   └─┬─┘   └─┬─┘   └─┬─┘
  //        addr    data   addr    data
  //
  // mux_sel=0: Address phase (AB on uo_out/uio_out)
  // mux_sel=1: Data phase (RWB/SYNC on uo_out, D on uio)
  // -----------------------------------------------------------------------
  wire mux_sel = q ^ q_d;

  reg q;
  always @(posedge clk or negedge rst_n)
    if (!rst_n)        q <= 1'b0;
    else if (!mux_sel) q <= ~q;

  reg q_d;
  always @(negedge clk or negedge rst_n)
    if (!rst_n)       q_d <= 1'b0;
    else if (mux_sel) q_d <= ~q_d;

  // -----------------------------------------------------------------------
  // Inter-module wires
  // -----------------------------------------------------------------------
  wire        ir_valid;
  wire [15:0] fetch_ir;
  wire [15:0] fetch_ab;

  wire        exec_bus_active;
  /* verilator lint_off UNOPTFLAT */
  wire        exec_ir_accept;
  /* verilator lint_on UNOPTFLAT */
  wire [15:0] exec_ab;
  wire [7:0]  exec_dout;
  wire        exec_rwb;
  wire        flush;
  wire [15:0] fetch_pc;

  // -----------------------------------------------------------------------
  // Submodule instances
  // -----------------------------------------------------------------------
  riscyv02_fetch u_fetch (
    .clk        (cpu_clk),
    .rst_n      (rst_n),
    .uio_in     (din),
    .bus_free   (!exec_bus_active),
    .ir_accept  (exec_ir_accept),
    .flush      (flush),
    .fetch_pc   (fetch_pc),
    .ir_valid   (ir_valid),
    .ir         (fetch_ir),
    .ab         (fetch_ab)
  );

  // Interrupt inputs
  wire irqb = ui_in_s[0];  // Active-low interrupt request (level-sensitive)

  riscyv02_execute u_execute (
    .clk           (cpu_clk),
    .rst_n         (rst_n),
    .uio_in        (din),
    .irqb          (irqb),
    .nmi_pending   (nmi_pending),
    .nmi_edge      (nmi_edge),
    .ir_valid      (ir_valid),
    .fetch_ir      (fetch_ir),
    .bus_active    (exec_bus_active),
    .ab            (exec_ab),
    .dout          (exec_dout),
    .rwb           (exec_rwb),
    .ir_accept     (exec_ir_accept),
    .nmi_ack       (exec_nmi_ack),
    .waiting       (exec_waiting),
    .stopped       (exec_stopped),
    .fetch_flush   (flush),
    .fetch_pc      (fetch_pc)
  );

  // -----------------------------------------------------------------------
  // Bus arbitration
  // -----------------------------------------------------------------------
  (* keep *) wire [15:0] AB  = exec_bus_active ? exec_ab  : fetch_ab;
  (* keep *) wire        RWB = exec_bus_active ? exec_rwb : 1'b1;
  (* keep *) wire [7:0]  DO  = exec_dout;

  // -----------------------------------------------------------------------
  // SYNC: instruction boundary indicator.
  //
  // Registered ir_accept: SYNC goes high one cycle after execute accepts
  // a new instruction.  SYNC=1 indicates "a new instruction has been
  // dispatched to execute."  This matches 6502 semantics where SYNC is
  // high during opcode fetch, marking the boundary between instructions.
  // -----------------------------------------------------------------------
  reg sync_r;
  always @(negedge cpu_clk or negedge rst_n)
    if (!rst_n) sync_r <= 1'b0;
    else        sync_r <= exec_ir_accept;

  (* keep *) wire SYNC = sync_r;

  // -----------------------------------------------------------------------
  // Output muxes (shared protocol with 6502 comparison model)
  //
  // All bus signals routed through bus_keep modules so that (* keep *)
  // net names are guaranteed to survive synthesis as real path waypoints.
  // Without the hierarchy barrier, synthesis can invert or restructure
  // logic so that the critical path bypasses the kept net, breaking the
  // SDC false-path constraints that rely on those names.
  // -----------------------------------------------------------------------
  wire [7:0] do_kept, ab_lo_kept, ab_hi_kept;
  wire       rwb_kept, sync_kept;

  bus_keep   u_do_keep    (.in(DO),       .out(do_kept));
  bus_keep   u_ab_lo_keep (.in(AB[7:0]),  .out(ab_lo_kept));
  bus_keep   u_ab_hi_keep (.in(AB[15:8]), .out(ab_hi_kept));
  bus_keep_1 u_rwb_keep   (.in(RWB),     .out(rwb_kept));
  bus_keep_1 u_sync_keep  (.in(SYNC),    .out(sync_kept));

  assign uo_out  = mux_sel ? {6'b0, sync_kept, rwb_kept} : ab_lo_kept;
  assign uio_out = mux_sel ? do_kept                     : ab_hi_kept;

  // uio_oe: tristate during mux_sel read cycles, drive otherwise
  always @(*) begin
    if (mux_sel && rwb_kept)
      uio_oe = 8'h00;  // Read: tristate for external data
    else
      uio_oe = 8'hFF;  // Write or address phase: drive
  end

  // Unused
  wire _unused = &{ena, ui_in_s[7:3], 1'b0};

endmodule

// =========================================================================
// Bus keep — keep_hierarchy prevents synthesis from restructuring logic
// across the port boundary, ensuring that (* keep *) net names (DO, AB)
// in the parent module are always on the timing path.  This makes SDC
// set_false_path -through constraints on those nets robust against
// synthesis inversions or restructuring.
// =========================================================================
(* keep_hierarchy *)
module bus_keep (
    input  wire [7:0] in,
    output wire [7:0] out
);
    assign out = in;
endmodule

(* keep_hierarchy *)
module bus_keep_1 (
    input  wire in,
    output wire out
);
    assign out = in;
endmodule

