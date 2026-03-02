// Behavioral simulation model for SKY130 ICG cell.
// RTL simulation only; synthesis uses the real PDK cell.
module sky130_fd_sc_hd__dlclkp_1 (GCLK, GATE, CLK);
  output GCLK;
  input GATE, CLK;
  reg gate_latched;
  always @(CLK or GATE)
    if (!CLK) gate_latched = GATE;
  assign GCLK = CLK & gate_latched;
endmodule
