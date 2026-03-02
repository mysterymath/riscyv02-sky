/*
 * Copyright (c) 2024 mysterymath
 * SPDX-License-Identifier: Apache-2.0
 *
 * Register file: 8 x 16-bit GP registers.
 * 2 read ports (16-bit) + 1 write port (16-bit).
 *
 * Negedge-triggered DFF write: captures w_data into regs[w_sel] at the
 * falling edge of clk when w_we is asserted.
 *
 * Read ports are purely combinational (mux trees on DFF outputs).
 */

`default_nettype none

(* keep_hierarchy *)
module riscyv02_regfile (
    input  wire        clk,
    input  wire        rst_n,

    // Write port (16-bit)
    input  wire [2:0]  w_sel,
    input  wire [15:0] w_data,
    input  wire        w_we,

    // Read port 1 (16-bit)
    input  wire [2:0]  r1_sel,
    output wire [15:0] r1,

    // Read port 2 (16-bit)
    input  wire [2:0]  r2_sel,
    output wire [15:0] r2
);

  reg [15:0] regs [0:7];

  integer i;
  always @(negedge clk or negedge rst_n)
    if (!rst_n)
      for (i = 0; i < 8; i = i + 1)
        regs[i] <= 16'd0;
    else if (w_we)
      regs[w_sel] <= w_data;

  // Port 1: 8:1 mux (GP registers)
  assign r1 = regs[r1_sel];

  // Port 2: 8:1 mux (GP registers)
  assign r2 = regs[r2_sel];

endmodule
