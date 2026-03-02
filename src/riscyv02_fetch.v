/*
 * Copyright (c) 2024 mysterymath
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

// =========================================================================
// Fetch unit: instruction fetch only, no register access.
//
// Address derived combinationally from execute's fetch_pc signal — no
// local PC register or adder needed.  When execute flushes (JR,
// interrupts), fetch resets to F_LO and fetch_pc already points to
// the new address.
//
// Instruction holding: fetch holds the instruction until execute accepts it.
// F_HI: instruction available combinationally from {uio_in, ir_r[7:0]}
// F_HOLD: instruction fully registered in ir_r, waiting for execute to accept
//
// ir_r uses negedge DFFs with enable — captures uio_in when the
// corresponding byte's fetch state is active and the bus is free.
// =========================================================================
module riscyv02_fetch (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  uio_in,
    input  wire        bus_free,
    input  wire        ir_accept,
    input  wire        flush,
    input  wire [15:0] fetch_pc,
    output wire        ir_valid,
    output wire [15:0] ir,
    output wire [15:0] ab
);

  localparam F_LO   = 2'd0;
  localparam F_HI   = 2'd1;
  localparam F_HOLD = 2'd2;

  reg [1:0]  state;
  reg [1:0]  next_state;

  reg [15:0] ir_r;
  always @(negedge clk or negedge rst_n) begin
    if (!rst_n) ir_r <= 16'h0000;
    else begin
      if ((state == F_LO) && bus_free)  ir_r[7:0]  <= uio_in;
      if ((state == F_HI) && bus_free)  ir_r[15:8] <= uio_in;
    end
  end

  // Bus address: derived from execute's fetch_pc
  assign ab = (state == F_HI) ? {fetch_pc[15:1], 1'b1} : fetch_pc;

  // Instruction output: combinational in F_HI, registered in F_HOLD
  // Note: ir_valid doesn't depend on flush to avoid combinational loops
  // with IRQ/RETI detection. The flush is handled in the sequential block.
  assign ir = (state == F_HOLD) ? ir_r : {uio_in, ir_r[7:0]};
  assign ir_valid = ((state == F_HI) && bus_free) || (state == F_HOLD);

  always @(*) begin
    next_state = state;
    if (flush)
      next_state = F_LO;
    else case (state)
      F_LO: if (bus_free)
        next_state = F_HI;

      F_HI: if (bus_free) begin
        if (ir_accept)
          next_state = F_LO;
        else
          next_state = F_HOLD;
      end

      F_HOLD: if (ir_accept)
        next_state = F_LO;

      default: next_state = 2'bx;
    endcase
  end

  always @(negedge clk or negedge rst_n) begin
    if (!rst_n)
      state <= F_LO;
    else
      state <= next_state;
  end

endmodule
