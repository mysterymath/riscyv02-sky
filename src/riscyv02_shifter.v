/*
 * Copyright (c) 2024 mysterymath
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

// ============================================================================
// 8-bit barrel shifter (pure combinational).
//
// Extracts 8 contiguous bits from a 15-bit input:
//   result = din[shamt+7 : shamt]
//
// The 15-bit input is {fill[6:0], data[7:0]}.  For a right shift by n,
// the caller places the data byte in din[7:0] and overflow bits from the
// adjacent byte in din[14:8].  The module selects the correct 8-bit
// window via a 3-stage mux tree (shift by 4, 2, 1).
// ============================================================================

module riscyv02_shifter (
    input  wire [14:0] din,    // {fill[6:0], data[7:0]}
    input  wire [2:0]  shamt,  // 0-7
    output wire [7:0]  result  // din[shamt+7 : shamt]
);

  // Stage 1: shift by 4
  wire [10:0] s1 = shamt[2] ? din[14:4] : din[10:0];

  // Stage 2: shift by 2
  wire [8:0]  s2 = shamt[1] ? s1[10:2] : s1[8:0];

  // Stage 3: shift by 1
  assign result = shamt[0] ? s2[8:1] : s2[7:0];

endmodule
