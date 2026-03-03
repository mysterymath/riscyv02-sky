/*
 * Testbench for tt_um_riscyv02.
 *
 * Models the external bus environment: a demux address register feeding a
 * 64KB async SRAM.
 *
 * Reset requirement: rst_n must deassert synchronous to negedge clk (i.e.,
 * while clk is low), so the first active edge is always a posedge.  This
 * is standard "async assert, sync deassert" practice and eliminates the
 * need for any startup write-suppression logic.
 *
 * Bus timing (one CPU cycle = one clk period):
 *
 *   posedge clk — address phase:
 *     addr register captures AB from {uio_out, uo_out}.
 *     SRAM read output (uio_in) settles to ram[addr].
 *
 *   negedge clk — data phase:
 *     CPU reads uio_in (for fetches and loads).
 *     Writes are captured: if RWB==0 (uo_out[0]), ram[addr] <= uio_out.
 */

`default_nettype none
`timescale 1ns / 1ps

module tb ();

  initial begin
`ifndef NODUMP
    $dumpfile("tb.fst");
    $dumpvars(0, tb);
`endif
    #1;
  end

  // Clock, reset, and enable are driven by cocotb.
  reg       clk;
  reg       rst_n;
  reg       ena;
  reg [7:0] ui_in;

  wire [7:0] uo_out;
  wire [7:0] uio_out;
  wire [7:0] uio_oe;

`ifdef GL_TEST
  wire VPWR = 1'b1;
  wire VGND = 1'b0;
`endif

  // 64KB RAM — zero-initialized.  Program contents are written by cocotb
  // before reset, so the `initial` here is equivalent to flash being
  // blank at manufacturing.
  reg [7:0] ram [0:65535];
  integer i;
  initial for (i = 0; i < 65536; i = i + 1) ram[i] = 8'h00;

  // -----------------------------------------------------------------------
  // Address register: models the demux's posedge-triggered address capture.
  //
  // Resets to 0x0000, matching the real demux and the CPU's reset PC.
  // -----------------------------------------------------------------------
  reg [15:0] addr;

  // Bidirectional I/O pin model: when uio_oe drives (address phase / writes),
  // uio_in reads back uio_out (the CPU's own output).  When tristated (read
  // data phase), uio_in sees SRAM data — matching real pad behavior.
  wire [7:0] uio_in = (uio_oe & uio_out) | (~uio_oe & ram[addr]);

  tt_um_riscyv02 user_project (
      .ui_in  (ui_in),
      .uo_out (uo_out),
      .uio_in (uio_in),
      .uio_out(uio_out),
      .uio_oe (uio_oe),
      .ena    (ena),
      .clk    (clk),
      .rst_n  (rst_n)
`ifdef GL_TEST
      , .VPWR (VPWR),
      .VGND (VGND)
`endif
  );
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
      addr <= 16'h0000;
    else
      addr <= {uio_out, uo_out};
  end

  // -----------------------------------------------------------------------
  // Write capture: at negedge clk (data phase).
  //
  // At negedge the bus is in data phase: uo_out[0] = RWB, uio_out = data.
  // RWB=0 means the CPU is writing.  Gated on rst_n to suppress writes
  // while the clock runs during reset.  No additional startup guard is
  // needed — rst_n deasserts synchronous to negedge clk, so the first
  // negedge after reset is always a valid data phase (mux_sel=1).
  // -----------------------------------------------------------------------
  always @(negedge clk) begin
    if (rst_n && !uo_out[0])
      ram[addr] <= uio_out;
  end

endmodule
