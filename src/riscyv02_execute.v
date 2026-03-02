/*
 * Copyright (c) 2024 mysterymath
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

// ============================================================================
// Execute unit: FSM + ALU + register file.
//
// All instruction state is held in a single 16-bit ir register containing the
// raw instruction word.
// All decode properties are derived from named instruction fields (opcode, funct3,
// funct4, imm8, etc.) and format-level group signals.
//
// All instructions dispatch to E_EXEC_LO. Simple instructions (SEI, CLI,
// SRW, not-taken branches) complete in 1 exec cycle. Two-cycle ops
// (ALU reg/imm, shifts, comparisons, AUIPC, cross-page branches)
// continue to E_EXEC_HI. Memory instructions proceed from E_EXEC_HI
// to E_MEM_LO/HI for bus access.
//
// Register file ports are 16 bits wide. All regfile writes are deferred to
// E_EXEC_HI (or E_MEM_HI), so source operands are never corrupted
// mid-instruction. The ALU serializes 8 bits at a time internally; tmp[7:0]
// holds the lo-byte result between E_EXEC_LO and E_EXEC_HI.
//
// ALU input muxes (alu_a, alu_b, alu_op) are extracted as standalone
// combinational blocks outside the state machine. This makes the format-level
// muxing structure visible:
//   alu_a:  4-way LO / 3-way HI — zero, flags, PC, register
//   alu_b:  4-way LO / 5-way HI — driven by format groups
//   alu_op: pure instruction function — independent of state
//
// ISA encoding: RV32I-style 16-bit encoding
// ------------------------------------------
// Fixed 5-bit opcode at [4:0]. Register rs1/rd at [7:5]. Sign at [15].
// Immediates at [15:8] with sign always at ir[15].
//
//   Format  Layout (MSB to LSB)                              Instructions
//   I       [imm8:8|rs/rd:3|opcode:5]                        24 (incl LUI,AUIPC)
//   B       [imm8:8|0:2|funct1:1|opcode:5]                   BT, BF
//   J       [s:1|imm[6:0]:7|imm[8:7]:2|funct1:1|opcode:5]   J, JAL
//   R       [funct2:2|rd:3|rs2:3|rs1:3|opcode:5]             R,R,R(8) + R,R(8)
//   SI      [0:1|funct3:3|shamt:4|rs/rd:3|opcode:5]          SLLI,SRLI,SRAI,SLLT,SRLT,RLT,RRT
//   SYS     [funct4:4|0:4|reg:3|opcode:5]                    11 system insns
//
// ADDI has opcode 0 so that 0x0000 = ADDI R0, 0 = NOP.
// T flag: single-bit condition flag set by comparisons (CLTI, CLTUI, CEQI,
// CLT, CLTU, CEQ), tested by BT/BF branches. SR = {I, T}; ESR saves SR on INT.
// ============================================================================

module riscyv02_execute (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  uio_in,
    input  wire        irqb,         // Interrupt request (active low, level-sensitive)
    input  wire        nmi_pending,  // NMI pending (from project.v, ungated domain)
    input  wire        nmi_edge,     // NMI combinational edge (same-cycle detection)
    input  wire        ir_valid,
    input  wire [15:0] fetch_ir,
    output wire        bus_active,
    output reg  [15:0] ab,
    output reg  [7:0]  dout,
    output reg         rwb,
    output wire        ir_accept,
    output wire        nmi_ack,      // NMI acknowledged (combinational, clears nmi_pending)
    output wire        waiting,      // WAI: halted until interrupt (gates cpu_clk)
    output wire        stopped,      // STP: halted permanently, only reset recovers
    // Fetch pipeline flush and next-instruction address
    output reg         fetch_flush,
    output wire [15:0] fetch_pc
);

  // ==========================================================================
  // Interface and State
  // ==========================================================================

  // FSM states
  localparam E_IDLE    = 3'd0;  // Waiting for instruction
  localparam E_EXEC_LO = 3'd1;  // Execute / address compute low byte
  localparam E_EXEC_HI = 3'd2;  // Execute / address compute high byte
  localparam E_MEM_LO  = 3'd3;  // Memory access low byte
  localparam E_MEM_HI  = 3'd4;  // Memory access high byte (can accept next)

  reg [2:0]  state;
  reg [15:0] ir;        // Instruction register (raw instruction word)
  // Cycle-to-cycle temporary (mem addr, branch target, ALU/shift result).
  // Declared as regs below, captured in the main sequential block.
  reg        carry_r;     // ALU carry (DFF — feeds ci_ext)
  // tmp is pre-incremented at E_MEM_LO: tmp_lo += 1, tmp_hi += carry (registered)
  wire [15:0] tmp = {tmp_hi, tmp_lo};

  // Interrupt and PC state
  reg [15:1] pc;        // Program counter (word address; byte addr = {pc, 1'b0})
  reg        i_bit;     // Interrupt disable flag (0=enabled, 1=disabled)
  reg        t_bit;     // T flag (condition result from comparisons)
  reg  [1:0] esr;       // Exception status register: saved {i_bit, t_bit}
  reg [15:0] epc;       // Exception PC (byte address)

  // -------------------------------------------------------------------------
  // Named instruction fields (pure aliases — zero synthesis cost)
  // -------------------------------------------------------------------------
  wire [4:0] opcode      = ir[4:0];
  wire [1:0] funct2         = ir[15:14];
  wire [7:0] imm8        = ir[15:8];
  wire [2:0] rs1_rd      = ir[7:5];     // I/SI/SYS register field
  wire [2:0] rs2         = ir[10:8];    // R-type second source
  wire [2:0] rd_r        = ir[13:11];   // R-type destination
  wire zext_imm = is_andi || is_ori || is_cltui;
  wire [7:0] imm_sext_hi = {8{ir[15] & ~zext_imm}}; // HI-byte: sext default, zext for ANDI/ORI/CLTUI
  wire [7:0] branch_lo   = {ir[14:8], 1'b0}; // ×2 branch/jump LO byte
  wire [4:0] fetch_opcode = fetch_ir[4:0];

  // -------------------------------------------------------------------------
  // Instruction decode: all properties derived from named fields
  // -------------------------------------------------------------------------

  // --- I-type ---
  wire is_addi  = opcode == 5'd0;
  wire is_li    = opcode == 5'd1;
  wire is_jr    = opcode == 5'd7;
  wire is_jalr  = opcode == 5'd8;
  wire is_andi  = opcode == 5'd9;
  wire is_ori   = opcode == 5'd10;
  wire is_xori  = opcode == 5'd11;
  wire is_clti  = opcode == 5'd12;
  wire is_cltui = opcode == 5'd13;
  wire is_ceqi  = opcode == 5'd16;
  wire is_lui   = opcode == 5'd22;
  wire is_auipc = opcode == 5'd23;

  // --- B-type (opcode 24, funct1 at [5]) ---
  // BT/BF polarity: ir[5] (0=BT, 1=BF); [7:6] pinned to 0
  wire is_t_branch = opcode == 5'd24 && ir[7:6] == 2'b00;

  // --- J-type (opcode 25, funct1 at [5]) ---
  // J/JAL polarity: ir[5] (0=J, 1=JAL)
  wire is_jump_imm = opcode == 5'd25;
  wire is_jal      = opcode == 5'd25 && ir[5];

  // --- R-type (opcodes 26-29, funct2 at [15:14]) ---
  wire is_alu1     = opcode == 5'd26;                    // ADD/SUB/AND/OR
  wire is_alu2     = opcode == 5'd27;                    // XOR/SLL/SRL/SRA
  wire is_alu_rrr  = is_alu1 || (is_alu2 && funct2 == 2'd0);  // ADD..OR + XOR
  wire is_shift_rr = is_alu2 && |funct2;                    // SLL/SRL/SRA
  wire is_rrr      = is_alu1 || is_alu2;                 // opcodes 26-27

  // R-type comparisons (opcode 29, funct2 1-3)
  wire is_clt  = opcode == 5'd29 && funct2 == 2'd1;
  wire is_cltu = opcode == 5'd29 && funct2 == 2'd2;
  wire is_ceq  = opcode == 5'd29 && funct2 == 2'd3;

  // --- SI-type (opcode 30, funct3 at [15:13]: [15]=T, [14]=right, [13]=mode) ---
  // ir[12] must be 0; ir[12]=1 decodes as 2-cycle NOP (no duplicate encodings).
  wire is_slli = opcode == 5'd30 && ir[15:12] == 4'd0;   // 000_0
  wire is_srli = opcode == 5'd30 && ir[15:12] == 4'd4;   // 010_0
  wire is_srai = opcode == 5'd30 && ir[15:12] == 4'd6;   // 011_0

  // SI-type shift/rotate through T (funct3[2]=1, i.e. ir[15]=1)
  // 100_0=SLLT, 101_0=RLT, 110_0=SRLT, 111_0=RRT
  wire is_si_t        = opcode == 5'd30 && ir[15] && !ir[12];
  wire is_si_t_right  = is_si_t && ir[14];
  wire is_si_t_rotate = is_si_t && ir[13];

  // R-type shifts (opcode 27, funct2 1-3)
  wire is_srl = is_alu2 && funct2 == 2'd2;
  wire is_sra = is_alu2 && funct2 == 2'd3;

  // --- System (opcode 31, funct4 at [15:12]) ---
  wire is_sei  = opcode == 5'd31 && ir[15:12] == 4'd0;
  wire is_cli  = opcode == 5'd31 && ir[15:12] == 4'd1;
  wire is_wai  = opcode == 5'd31 && ir[15:12] == 4'd2;
  wire is_stp  = opcode == 5'd31 && ir[15:12] == 4'd3;
  wire is_epcr = opcode == 5'd31 && ir[15:12] == 4'd4;
  wire is_epcw = opcode == 5'd31 && ir[15:12] == 4'd5;
  wire is_srr  = opcode == 5'd31 && ir[15:12] == 4'd6;
  wire is_srw  = opcode == 5'd31 && ir[15:12] == 4'd7;
  wire is_reti = opcode == 5'd31 && ir[15:12] == 4'd8;
  wire is_int  = opcode == 5'd31 && ir[15:14] == 2'b11;

  // --- Behavioral groups ---

  localparam LINK_REG = 3'd6;

  // Memory groups (range checks for compact opcode classification)
  wire is_r9_load  = opcode >= 5'd2  && opcode <= 5'd4;   // LW/LB/LBU
  wire is_r9_store = opcode == 5'd5  || opcode == 5'd6;    // SW/SB
  wire is_sp_load  = opcode >= 5'd17 && opcode <= 5'd19;   // LWS/LBS/LBUS
  wire is_sp_store = opcode == 5'd20 || opcode == 5'd21;   // SWS/SBS
  wire is_rr_load  = opcode == 5'd28 && funct2 != 2'd3;       // LWR/LBR/LBUR
  wire is_rr_store = (opcode == 5'd28 && funct2 == 2'd3) || (opcode == 5'd29 && funct2 == 2'd0); // SWR/SBR
  wire is_rr_mem   = is_rr_load || is_rr_store;

  // Combined memory properties for E_MEM and r_hi
  wire mem_is_store      = is_r9_store || is_rr_store || is_sp_store;
  wire mem_is_byte_load  = (opcode == 5'd3  || opcode == 5'd4)    // LB/LBU
                        || (opcode == 5'd18 || opcode == 5'd19)   // LBS/LBUS
                        || (opcode == 5'd28 && (funct2 == 2'd1 || funct2 == 2'd2)); // LBR/LBUR
  wire mem_is_byte_store = opcode == 5'd6 || opcode == 5'd21     // SB/SBS
                        || (opcode == 5'd29 && funct2 == 2'd0);     // SBR
  wire mem_is_lbu        = opcode == 5'd4 || opcode == 5'd19     // LBU/LBUS
                        || (opcode == 5'd28 && funct2 == 2'd2);     // LBUR

  // I-type ALU write group (LI/LUI routed through ALU as ADD 0)
  wire is_i_alu_wr = is_addi || is_andi || is_ori || is_xori || is_li || is_lui;

  // Shift groups
  wire is_shift_imm   = is_slli || is_srli || is_srai || is_si_t;
  wire is_shift       = is_shift_rr || is_shift_imm;
  wire is_right_shift = is_srl || is_sra || is_srli || is_srai || is_si_t_right;
  wire is_arith_shift = is_sra || is_srai;

  // T-flag comparisons (set T, no register write)
  wire is_cmp_imm = is_clti || is_cltui || is_ceqi;
  wire is_cmp_rr  = is_clt || is_cltu || is_ceq;

  // Jump/branch
  wire is_branch   = opcode == 5'd14 || opcode == 5'd15;  // BZ/BNZ, polarity = opcode[0]
  wire is_pc_rel   = is_branch || is_t_branch || is_jump_imm;
  wire is_jr_jalr  = is_jr || is_jalr;

  // ALU source selects (format-level)
  wire is_pc_base = is_auipc || is_pc_rel;    // alu_a = PC (vs register)

  // ==========================================================================
  // Shared Infrastructure
  // ==========================================================================

  // -------------------------------------------------------------------------
  // Register file (16-bit interface)
  // -------------------------------------------------------------------------
  reg  [2:0]  r1_sel;
  wire [15:0] r1;
  wire [15:0] r2;
  reg         w_we;
  reg  [15:0] w_data;

  // -------------------------------------------------------------------------
  // Temporary register: negedge DFFs with enable.
  //   tmp_lo[7:0]:  captured at E_EXEC_LO
  //   tmp_hi[7:0]:  captured at E_EXEC_HI
  //   carry_r:      DFF (feeds ALU ci_ext)
  // -------------------------------------------------------------------------
  reg [7:0] tmp_lo;
  reg [7:0] tmp_hi;

  wire is_mem_phase = (state == E_MEM_LO || state == E_MEM_HI);

  // -------------------------------------------------------------------------
  // Bus outputs (state-independent: only depends on memory phase)
  // -------------------------------------------------------------------------
  assign bus_active = is_mem_phase;

  // AB for both E_MEM_LO and E_MEM_HI is just tmp — at E_MEM_LO the
  // sequential block overwrites tmp with tmp+1, so E_MEM_HI reads the
  // incremented address with no carry chain on the critical path.
  always @(*) begin
    ab = 16'bx;
    if (is_mem_phase)
      ab = tmp;
  end

  always @(*) begin
    dout = 8'bx;
    rwb  = 1'bx;
    if (is_mem_phase) begin
      dout = r2_hi_r ? r2[15:8] : r2[7:0];
      rwb  = !mem_is_store;
    end
  end

  // w_sel: write port register select (3-bit GP only)
  reg [2:0] w_sel_mux;
  always @(*) begin
    if (is_jal || is_jalr)
      w_sel_mux = LINK_REG;                                    // JAL/JALR → R6
    else if (is_rrr || is_rr_load)
      w_sel_mux = rd_r;                                        // R-type: rd at [13:11]
    else
      w_sel_mux = rs1_rd;                                      // Default: reg at [7:5]
  end

  // r2_sel: read port 2 register select
  //   Default rs2 works for R,R,R (rs2), R-type stores (data), and R,R loads (dc).
  //   Override to rs1_rd for I-type stores (data reg in I-type reg field).
  reg [2:0] r2_sel;
  always @(*) begin
    if (is_r9_store || is_sp_store) r2_sel = rs1_rd;
    else                            r2_sel = rs2;
  end
  reg        r2_hi_r;   // dout byte select: 0=r2[7:0], 1=r2[15:8]

  riscyv02_regfile u_regfile (
    .clk    (clk),
    .rst_n  (rst_n),
    .w_sel  (w_sel_mux),
    .w_data (w_data),
    .w_we   (w_we),
    .r1_sel (r1_sel),
    .r1     (r1),
    .r2_sel (r2_sel),
    .r2     (r2)
  );

  // -------------------------------------------------------------------------
  // ALU
  // -------------------------------------------------------------------------
  reg  [7:0] alu_a;
  reg  [7:0] alu_b;
  reg  [2:0] alu_op;
  wire [7:0] alu_result;
  wire       alu_co;

  // alu_new_op: always 1 in E_EXEC_LO (new operation), 0 in E_EXEC_HI (carry continuation)
  wire alu_new_op = (state == E_EXEC_LO);

  riscyv02_alu u_alu (
    .a      (alu_a),
    .b      (alu_b),
    .op     (alu_op),
    .new_op (alu_new_op),
    .ci_ext (carry_r),
    .co     (alu_co),
    .result (alu_result)
  );

  // -------------------------------------------------------------------------
  // ALU input muxes (format-level, outside state machine)
  // -------------------------------------------------------------------------

  // alu_a: 4-way LO (zero / flags / PC / reg), 3-way HI (zero / PC / reg)
  always @(*) begin
    if (alu_new_op) begin
      if (is_srr)               alu_a = {4'b0, esr, i_bit, t_bit};
      else if (is_li || is_lui) alu_a = 8'd0;
      else if (is_pc_base)      alu_a = {pc[7:1], 1'b0};
      else if (is_epcr)         alu_a = epc[7:0];
      else                      alu_a = r1[7:0];
    end else begin
      if (is_li || is_lui || is_srr) alu_a = 8'd0;
      else if (is_pc_base)           alu_a = pc[15:8];
      else if (is_epcr)              alu_a = epc[15:8];
      else                           alu_a = r1[15:8];
    end
  end

  // alu_b: format-level operand select
  //   LO: 4-way — branch_lo / r2 / 0 / imm8
  //   HI: 5-way — J/JAL sext / imm8(AUIPC) / r2 / 0 / imm_sext_hi
  //   The J/JAL HI entry (sext of imm10[9:7]) is an encoding wart — it's
  //   the only instruction with a unique alu_b extraction in HI.
  always @(*) begin
    if (alu_new_op) begin
      if (is_pc_rel)                  alu_b = branch_lo;
      else if (is_rrr || is_cmp_rr)   alu_b = r2[7:0];
      else if (is_rr_mem || is_auipc || is_lui || is_epcr || is_epcw || is_srr) alu_b = 8'd0;
      else                            alu_b = imm8;
    end else begin
      if (is_jump_imm)                alu_b = {{6{ir[15]}}, ir[7], ir[6]};
      else if (is_auipc || is_lui)     alu_b = imm8;
      else if (is_rrr || is_cmp_rr)   alu_b = r2[15:8];
      else if (is_rr_mem || is_epcr || is_epcw || is_srr) alu_b = 8'd0;
      else                            alu_b = imm_sext_hi;
    end
  end

  // alu_op: pure instruction function (same in LO and HI)
  always @(*) begin
    if (is_alu1)                                                alu_op = {1'b0, funct2};
    else if ((is_alu2 && funct2 == 2'd0) || is_ceqi || is_ceq
          || is_xori)                                           alu_op = 3'd4;  // XOR
    else if (is_clti || is_cltui || is_clt || is_cltu)          alu_op = 3'd1;  // SUB
    else if (is_andi)                                           alu_op = 3'd2;  // AND
    else if (is_ori)                                            alu_op = 3'd3;  // OR
    else                                                        alu_op = 3'd0;  // ADD
  end

  // -------------------------------------------------------------------------
  // Barrel shifter
  // -------------------------------------------------------------------------
  wire [3:0] shamt = is_shift_rr ? r2[3:0] : is_si_t ? 4'd1 : ir[11:8];

  reg  [14:0] shifter_din;
  /* verilator lint_off UNOPTFLAT */
  wire [7:0]  shifter_result;
  /* verilator lint_on UNOPTFLAT */

  riscyv02_shifter u_shifter (
    .din    (shifter_din),
    .shamt  (shamt[2:0]),
    .result (shifter_result)
  );

  function [7:0] rev8(input [7:0] v);
    rev8 = {v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7]};
  endfunction

  function [6:0] rev7(input [6:0] v);
    rev7 = {v[0], v[1], v[2], v[3], v[4], v[5], v[6]};
  endfunction

  // -------------------------------------------------------------------------
  // Combinational register-file select from (state, ir)
  // -------------------------------------------------------------------------

  // r1_sel: registered read port 1 select.
  // Set at dispatch (from fetch_ir) and at E_EXEC_HI→E_MEM transitions.
  // Registering removes the instruction decode chain from the critical
  // path (regfile read → ALU → writeback).

  // -------------------------------------------------------------------------
  // Combinational intermediates and next-state values
  // -------------------------------------------------------------------------
  reg        insn_completing;
  reg        jump;
  reg        insn_i_bit;    // Instruction's effect on i_bit (before interrupt override)

  // Next-state values for all DFFs (computed in combinational block)
  reg [2:0]  next_state;
  reg [15:0] next_ir;
  reg        next_carry_r;
  reg [15:1] next_pc;
  reg        next_i_bit;
  reg        next_t_bit;
  reg [1:0]  next_esr;
  reg        next_r2_hi_r;
  reg [2:0]  next_r1_sel;
  reg [15:0] next_epc;

  // Combinational signal for tmp[7:0] DFF at E_EXEC_LO negedge
  reg [7:0]  next_tmp_lo;

  // Comparison sign-of-B: ir[15] for I-type, r2[15] for R-type
  wire cmp_b_sign = is_cmp_rr ? r2[15] : ir[15];

  // Interrupt control
  wire fsm_ready = (state == E_IDLE) || insn_completing;
  wire take_nmi = fsm_ready && (nmi_pending || nmi_edge);
  /* verilator lint_off UNOPTFLAT */
  wire take_irq = fsm_ready && !irqb && !insn_i_bit && !take_nmi;
  /* verilator lint_on UNOPTFLAT */
  assign ir_accept = fsm_ready && ir_valid && !take_nmi && !take_irq && !jump;
  assign waiting = (state == E_IDLE) && is_wai;
  assign stopped = (state == E_IDLE) && is_stp;

  // ==========================================================================
  // State-Property Block
  // ==========================================================================

  assign fetch_pc = {pc, 1'b0};

  always @(*) begin
    // --- Next-state defaults: hold all registers ---
    next_state      = state;
    next_ir         = ir;
    next_carry_r    = carry_r;
    next_pc         = pc;
    next_i_bit      = i_bit;
    next_t_bit      = t_bit;
    next_esr        = esr;
    next_epc        = epc;
    next_r2_hi_r    = r2_hi_r;
    next_r1_sel     = r1_sel;

    // --- Output defaults ---
    w_data          = {alu_result, tmp[7:0]};
    w_we            = 1'b0;
    insn_completing = 1'b0;
    jump            = 1'b0;
    insn_i_bit      = i_bit;
    shifter_din     = 15'b0;
    next_tmp_lo     = alu_result;

    case (state)
      E_EXEC_LO: begin
        // Most instructions just let the format-level ALU muxes compute
        // their result into tmp_lo (default: next_tmp_lo = alu_result).
        // Only instructions with non-ALU behavior need explicit blocks.
        if (is_jr_jalr) begin
          // JR same-page: high byte unchanged, 1 exec cycle
          if (is_jr && (alu_co == ir[15])) begin
            jump            = 1'b1;
            next_pc         = {r1[15:8], alu_result[7:1]};
            insn_completing = 1'b1;
          end
        end else if (is_shift) begin
          if (shamt[3]) begin
            // Cross-byte: fill byte for the vacated half
            if (is_right_shift)
              next_tmp_lo = is_arith_shift ? {8{r1[15]}} : 8'h00;
            else
              next_tmp_lo = 8'h00;
          end else if (is_right_shift) begin
            // Right shift hi byte: fill from sign/zero/T, input is {fill, r1[15:8]}
            if (is_arith_shift)
              shifter_din = {{7{r1[15]}}, r1[15:8]};
            else if (is_si_t_rotate)
              shifter_din = {6'b0, t_bit, r1[15:8]};
            else
              shifter_din = {7'b0, r1[15:8]};
            next_tmp_lo = shifter_result;
          end else begin
            // Left shift lo byte: reverse, right-shift, reverse
            // RLT: fill bit 0 with old T; others fill with 0
            shifter_din = {6'b0, is_si_t_rotate ? t_bit : 1'b0, rev8(r1[7:0])};
            next_tmp_lo = rev8(shifter_result);
          end
        end else if (is_pc_rel) begin
          // Not-taken branches: complete in 1 exec cycle
          if ((is_branch && !((!(|r1)) ^ opcode[0]))
           || (is_t_branch && !(t_bit ^ ir[5])))
            insn_completing = 1'b1;
          // Same-page taken: high byte unchanged, 1 exec cycle (3 total)
          else if (((is_branch   && (!(|r1) ^ opcode[0]))
                 || (is_t_branch && (t_bit ^ ir[5]))
                 || (is_jump_imm && !ir[5] && ir[7:6] == {2{ir[15]}}))
                && alu_co == ir[15]) begin
            jump            = 1'b1;
            next_pc         = {pc[15:8], alu_result[7:1]};
            insn_completing = 1'b1;
          end
        end else if (is_int) begin
          if (ir[7:6] != 2'b11) begin
            next_epc   = {pc, 1'b0};
            next_esr   = {i_bit, t_bit};
            insn_i_bit = 1'b1;
            next_pc    = {13'b0, ir[7:6] + 2'd1};
            jump       = 1'b1;
          end
          insn_completing = 1'b1;
        end else if (is_reti) begin
          next_pc    = epc[15:1];
          insn_i_bit = esr[1];
          next_t_bit = esr[0];
          jump       = 1'b1;
          insn_completing = 1'b1;
        end else if (is_sei || is_cli) begin
          insn_i_bit      = is_cli ? 1'b0 : 1'b1;
          insn_completing = 1'b1;
        end else if (is_srw) begin
          insn_i_bit      = r1[1];
          next_t_bit      = r1[0];
          next_esr        = r1[3:2];
          insn_completing = 1'b1;
        end
        next_carry_r = alu_co;
        if (is_wai || is_stp)
          next_state = E_IDLE;
        else if (insn_completing)
          next_state = E_IDLE;
        else
          next_state = E_EXEC_HI;
      end

      E_EXEC_HI: begin
        if (is_r9_load || is_r9_store || is_sp_load || is_sp_store) begin
          if (!mem_is_store)
            next_r1_sel = rs1_rd;  // data reg readback for loads
          next_state = E_MEM_LO;
        end else if (is_auipc) begin
          w_we            = 1'b1;
          insn_completing = 1'b1;
          next_state      = E_IDLE;
        end else if (is_rr_mem) begin
          if (!mem_is_store)
            next_r1_sel = rd_r;  // R-type load dest readback
          next_state = E_MEM_LO;
        end else if (is_jr_jalr) begin
          jump            = 1'b1;
          next_pc         = {alu_result, tmp[7:1]};
          insn_completing = 1'b1;
          if (is_jalr) begin
            w_data = {pc, 1'b0};
            w_we   = 1'b1;
          end
          next_state = E_IDLE;
        end else begin
          // Execute high byte: completes this cycle
          // (SEI/CLI/SRW/not-taken branches complete at E_EXEC_LO)
          insn_completing = 1'b1;
          if (is_i_alu_wr || is_alu_rrr || is_epcr || is_srr)
            w_we = 1'b1;
          else if (is_epcw)
            next_epc = {alu_result, tmp[7:0]};
          else if (is_cmp_imm || is_cmp_rr) begin
            if (is_ceqi || is_ceq)
              next_t_bit = ~((|tmp[7:0]) || (|alu_result));
            else if (is_cltui || is_cltu)
              next_t_bit = ~alu_co;
            else
              next_t_bit = (r1[15] ^ cmp_b_sign) ? r1[15] : alu_result[7];
          end else if (is_shift) begin
            if (shamt[3]) begin
              if (is_right_shift) begin
                shifter_din = {is_arith_shift ? {7{r1[15]}} : 7'b0, r1[15:8]};
                w_data = {tmp[7:0], shifter_result};
                w_we   = 1'b1;
              end else begin
                shifter_din = {7'b0, rev8(r1[7:0])};
                w_data = {rev8(shifter_result), tmp[7:0]};
                w_we   = 1'b1;
              end
            end else if (is_right_shift) begin
              shifter_din = {r1[14:8], r1[7:0]};
              w_data = {tmp[7:0], shifter_result};
              w_we   = 1'b1;
            end else begin
              shifter_din = {rev7(r1[7:1]), rev8(r1[15:8])};
              w_data = {rev8(shifter_result), tmp[7:0]};
              w_we   = 1'b1;
            end
            if (is_si_t)
              next_t_bit = ir[14] ? r1[0] : r1[15];
          end else if (is_pc_rel) begin
            if ((is_branch && (!(|r1) ^ opcode[0]))
             || (is_t_branch && (t_bit ^ ir[5]))
             || is_jump_imm) begin
              jump    = 1'b1;
              next_pc = {alu_result, tmp[7:1]};
            end
            if (is_jal) begin
              w_data = {pc, 1'b0};
              w_we   = 1'b1;
            end
          end
          next_state = E_IDLE;
        end
      end

      E_MEM_LO: begin
        if (mem_is_byte_store)
          insn_completing = 1'b1;
        else if (mem_is_byte_load) begin
          // Byte loads complete here: sign/zero-extend and write directly
          insn_completing = 1'b1;
          if (mem_is_lbu)
            w_data = {8'h00, uio_in};
          else
            w_data = {{8{uio_in[7]}}, uio_in};
          w_we = 1'b1;
        end else if (!mem_is_store) begin
          // Word load: write lo byte, preserve hi byte (read back at E_MEM_HI)
          w_data = {r1[15:8], uio_in};
          w_we   = 1'b1;
        end
        next_r2_hi_r   = mem_is_store;
        next_state     = (mem_is_byte_store || mem_is_byte_load) ? E_IDLE : E_MEM_HI;
      end

      E_MEM_HI: begin
        insn_completing = 1'b1;
        w_data          = {uio_in, r1[7:0]};
        w_we            = !mem_is_store;
        next_state      = E_IDLE;
      end

      E_IDLE: ;
      default: next_state = 3'bx;
    endcase

    next_i_bit = insn_i_bit;

    // -----------------------------------------------------------------
    // Interrupt entry (overrides state machine)
    // -----------------------------------------------------------------
    if (take_nmi || take_irq) begin
      next_ir    = 16'h0000;           // Clear WAI/STP latch
      next_epc   = {next_pc, 1'b0};
      next_esr   = {insn_i_bit, next_t_bit};
      next_i_bit = 1'b1;
      next_pc    = take_nmi ? 15'd1 : 15'd3;
      next_state = E_IDLE;
    end

    // -----------------------------------------------------------------
    // Instruction dispatch (overrides everything)
    // -----------------------------------------------------------------
    if (ir_accept) begin
      next_pc      = pc + 15'd1;
      next_ir      = fetch_ir;
      next_r2_hi_r = 1'b0;
      if (fetch_opcode >= 5'd2 && fetch_opcode <= 5'd6)
        next_r1_sel = 3'd0;
      else if (fetch_opcode >= 5'd17 && fetch_opcode <= 5'd21)
        next_r1_sel = 3'd7;
      else
        next_r1_sel = fetch_ir[7:5];
      next_state = E_EXEC_LO;
    end

    fetch_flush = take_nmi || take_irq || jump;
  end

  // ==========================================================================
  // Sequential (negedge clk): register next-state values
  // ==========================================================================

  always @(negedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state     <= E_IDLE;
      ir        <= 16'h0000;
      carry_r   <= 1'b0;
      pc        <= 15'h0000;
      i_bit     <= 1'b1;
      t_bit     <= 1'b0;
      esr       <= 2'b10;  // {I=1, T=0}
      r2_hi_r   <= 1'b0;
      tmp_lo    <= 8'h00;
      tmp_hi    <= 8'h00;
      r1_sel    <= 3'd0;
      epc       <= 16'h0000;
    end else begin
      state     <= next_state;
      ir        <= next_ir;
      carry_r   <= next_carry_r;
      pc        <= next_pc;
      i_bit     <= next_i_bit;
      t_bit     <= next_t_bit;
      esr       <= next_esr;
      epc       <= next_epc;
      r2_hi_r   <= next_r2_hi_r;
      r1_sel    <= next_r1_sel;
      if (state == E_EXEC_LO) tmp_lo <= next_tmp_lo;
      else if (state == E_MEM_LO) tmp_lo <= tmp_lo + 8'd1;
      if (state == E_EXEC_HI) tmp_hi <= alu_result;
      else if (state == E_MEM_LO) tmp_hi <= tmp_hi + {7'd0, &tmp_lo};
    end
  end

  // NMI acknowledgment: combinational — clears nmi_pending the same
  // negedge the FSM processes the NMI.  No multi-cycle handshake needed;
  // fsm_ready prevents re-taking while the handler runs.
  assign nmi_ack = take_nmi;

endmodule
