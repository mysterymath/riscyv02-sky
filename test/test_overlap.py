# SPDX-FileCopyrightText: © 2024 mysterymath
# SPDX-License-Identifier: Apache-2.0
#
# Register overlap tests: verify correct behavior when destination register
# overlaps a source register. Tests both known-buggy cases and safe cases.

from test_helpers import *


# Data slots at 0x60+, output slots at 0x40+.
# Each test uses at most 2 data slots (4 bytes) and 1 output slot (2 bytes).

@cocotb.test()
async def test_sll_rr_rd_eq_rs2(dut):
    """SLL R2, R1, R2: rd == rs2 (shift amount). Shift amount corrupted."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    # R1 = 0x00FF, R2 = 0x0004 (shamt=4). Expected: 0x00FF << 4 = 0x0FF0.
    # Bug: R2_lo overwritten with shifted lo byte, corrupts shamt in HI cycle.
    a = Asm()
    a.lw(1, 0x60)
    a.lw(2, 0x62)
    a.sll(2, 1, 2)
    a.sw_s(2, 0x40)
    a.spin()
    a.org(0x40); a.dw(0x0000)
    a.org(0x60); a.dw(0x00FF)
    a.org(0x62); a.dw(0x0004)
    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x40) | (_read_ram(dut, 0x41) << 8)
    assert val == 0x0FF0, f"SLL rd==rs2: expected 0x0FF0, got {val:#06x}"


# ===========================================================================
# Safe cases: verify no corruption
# ===========================================================================

@cocotb.test()
async def test_add_rd_eq_rs1(dut):
    """ADD R1, R1, R2: rd == rs1. Safe (writes lo, reads hi next cycle)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    # R1 = 0x1234, R2 = 0x4321. Expected: 0x5555.
    a = Asm()
    a.lw(1, 0x60)
    a.lw(2, 0x62)
    a.add(1, 1, 2)
    a.sw_s(1, 0x40)
    a.spin()
    a.org(0x40); a.dw(0x0000)
    a.org(0x60); a.dw(0x1234)
    a.org(0x62); a.dw(0x4321)
    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x40) | (_read_ram(dut, 0x41) << 8)
    assert val == 0x5555, f"ADD rd==rs1: expected 0x5555, got {val:#06x}"


@cocotb.test()
async def test_sub_rd_eq_rs2(dut):
    """SUB R2, R1, R2: rd == rs2. Safe (writes lo, reads hi next cycle)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    # R1 = 0x5555, R2 = 0x1234. Expected: 0x4321.
    a = Asm()
    a.lw(1, 0x60)
    a.lw(2, 0x62)
    a.sub(2, 1, 2)
    a.sw_s(2, 0x40)
    a.spin()
    a.org(0x40); a.dw(0x0000)
    a.org(0x60); a.dw(0x5555)
    a.org(0x62); a.dw(0x1234)
    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x40) | (_read_ram(dut, 0x41) << 8)
    assert val == 0x4321, f"SUB rd==rs2: expected 0x4321, got {val:#06x}"


@cocotb.test()
async def test_addi_self(dut):
    """ADDI R1, 3: always self-overlapping. Safe (lo then hi)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    # R1 = 0x0100. ADDI R1, 3. Expected: 0x0103.
    a = Asm()
    a.lw(1, 0x60)
    a.addi(1, 3)
    a.sw_s(1, 0x40)
    a.spin()
    a.org(0x40); a.dw(0x0000)
    a.org(0x60); a.dw(0x0100)
    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x40) | (_read_ram(dut, 0x41) << 8)
    assert val == 0x0103, f"ADDI self: expected 0x0103, got {val:#06x}"


@cocotb.test()
async def test_srl_rr_rd_eq_rs2(dut):
    """SRL R2, R1, R2: rd == rs2 (shamt reg). Safe (writes hi, reads lo)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    # R1 = 0x8000, R2 = 0x0004. Expected: 0x8000 >>u 4 = 0x0800.
    a = Asm()
    a.lw(1, 0x60)
    a.lw(2, 0x62)
    a.srl(2, 1, 2)
    a.sw_s(2, 0x40)
    a.spin()
    a.org(0x40); a.dw(0x0000)
    a.org(0x60); a.dw(0x8000)
    a.org(0x62); a.dw(0x0004)
    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x40) | (_read_ram(dut, 0x41) << 8)
    assert val == 0x0800, f"SRL rd==rs2: expected 0x0800, got {val:#06x}"


@cocotb.test()
async def test_slli_self(dut):
    """SLLI R1, 4: R,4 always self-overlapping. Safe (uses tmp)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    # R1 = 0x00FF. SLLI R1, 4. Expected: 0x0FF0.
    a = Asm()
    a.lw(1, 0x60)
    a.slli(1, 4)
    a.sw_s(1, 0x40)
    a.spin()
    a.org(0x40); a.dw(0x0000)
    a.org(0x60); a.dw(0x00FF)
    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x40) | (_read_ram(dut, 0x41) << 8)
    assert val == 0x0FF0, f"SLLI self: expected 0x0FF0, got {val:#06x}"


@cocotb.test()
async def test_jalr_link_overlap(dut):
    """JALR R6: source reg == link reg R6. Reads R6 for target, then overwrites with link."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    # R6 = 0x0040. JALR R6, 0 → jump to 0x0040, save return addr to R6.
    a = Asm()
    a.lw(6, 0x60)
    jalr_pc = a.pc
    a.jalr(6, 0)
    # At 0x0040: store R6 (should be return address = jalr_pc + 2)
    a.org(0x0040)
    a.sw_s(6, 0x50)
    a.spin()
    a.org(0x50); a.dw(0x0000)
    a.org(0x60); a.dw(0x0040)
    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x50) | (_read_ram(dut, 0x51) << 8)
    expected = jalr_pc + 2
    assert val == expected, f"JALR R6: expected {expected:#06x}, got {val:#06x}"


@cocotb.test()
async def test_lw_rr_rd_eq_rs(dut):
    """LWR R1, R1: rd == rs. Load overwrites pointer (defined behavior)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    # R1 = 0x0030. Memory at 0x0030 = 0xBEEF.
    # Load from [R1] into R1 → R1 = 0xBEEF (pointer lost, data correct).
    a = Asm()
    a.li(1, 0x30)
    a.lw_rr(1, 1)
    a.sw_s(1, 0x40)
    a.spin()
    a.org(0x30); a.dw(0xBEEF)
    a.org(0x40); a.dw(0x0000)
    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x40) | (_read_ram(dut, 0x41) << 8)
    assert val == 0xBEEF, f"LWR rd==rs: expected 0xBEEF, got {val:#06x}"
