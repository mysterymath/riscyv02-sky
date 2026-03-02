/*
 * Copyright (c) 2024 mysterymath
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module riscyv02_alu (
    input  wire [7:0] a,
    input  wire [7:0] b,
    input  wire [2:0] op,      // Operation select
    input  wire       new_op,  // 1 = new operation (ci=0/1), 0 = continue (ci=ci_ext)
    input  wire       ci_ext,  // External carry-in (from tmp[8] in execute unit)
    output wire       co,
    output reg  [7:0] result
);
  localparam OP_SUB = 3'd1;
  localparam OP_AND = 3'd2;
  localparam OP_OR  = 3'd3;
  localparam OP_XOR = 3'd4;

  wire sub = (op == OP_SUB);
  wire [7:0] b_eff = b ^ {8{sub}};   // invert b for subtraction
  wire ci = new_op ? sub : ci_ext;    // SUB: ci=1 for new_op (two's complement)
  wire [7:0] sum;
  assign {co, sum} = a + b_eff + {8'd0, ci};

  always @(*)
    case (op)
      OP_AND:  result = a & b;
      OP_OR:   result = a | b;
      OP_XOR:  result = a ^ b;
      default: result = sum;    // ADD, SUB
    endcase
endmodule
