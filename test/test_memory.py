# SPDX-FileCopyrightText: © 2024 mysterymath
# SPDX-License-Identifier: Apache-2.0
#
# Memory operation tests: LW/SW, LB/LBU/SB, R,R loads/stores.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
from test_helpers import *


@cocotb.test()
async def test_lw_sw_jr_basic(dut):
    """LW from memory, SW to memory, JR to spin loop."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x30)
    a.sw(1, 0x32)
    a.spin()
    a.org(0x30)
    a.dw(0x1234)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    lo = _read_ram(dut, 0x0032)
    hi = _read_ram(dut, 0x0033)
    assert lo == 0x34, f"Expected 0x34 at 0x0032, got {lo:#04x}"
    assert hi == 0x12, f"Expected 0x12 at 0x0033, got {hi:#04x}"


@cocotb.test()
async def test_negative_offsets(dut):
    """Use negative offsets with R0 as base."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(0, 0x50)           # R0 = 0x50
    a.lw(1, -2)             # R1 = mem16[R0-2] = mem16[0x4E]
    a.sw_s(1, 0x60)         # mem16[R7+0x60] = R1
    a.spin()
    a.org(0x4E)
    a.dw(0xCAFE)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)

    val = _read_ram(dut, 0x0060) | (_read_ram(dut, 0x0061) << 8)
    assert val == 0xCAFE, f"Expected 0xCAFE, got {val:#06x}"


@cocotb.test()
async def test_byte_ops(dut):
    """LB, LBU, SB byte memory operations."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lb(1, 0x30)
    a.sw(1, 0x40)
    a.lbu(2, 0x30)
    a.sw(2, 0x42)
    a.sb(2, 0x44)
    a.spin()
    a.org(0x30)
    a.db(0x85)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    v_lb = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    v_lbu = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    v_sb = _read_ram(dut, 0x0044)
    assert v_lb == 0xFF85, f"LB: expected 0xFF85, got {v_lb:#06x}"
    assert v_lbu == 0x0085, f"LBU: expected 0x0085, got {v_lbu:#06x}"
    assert v_sb == 0x85, f"SB: expected 0x85, got {v_sb:#04x}"


@cocotb.test()
async def test_rr_load_store(dut):
    """R,R format load/store with explicit rd and rs."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 0x30)
    a.lw_rr(2, 1)
    a.li(3, 0x50)
    a.sw_rr(2, 3)
    a.spin()
    a.org(0x30)
    a.dw(0xDEAD)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    val = _read_ram(dut, 0x0050) | (_read_ram(dut, 0x0051) << 8)
    assert val == 0xDEAD, f"R,R load/store: expected 0xDEAD, got {val:#06x}"


@cocotb.test()
async def test_lb_sign_extend(dut):
    """LB sign-extends 0x80 to 0xFF80."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lb(1, 0x30)
    a.sw(1, 0x40)
    a.spin()
    a.org(0x30)
    a.db(0x80)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0xFF80, f"LB sign extend failed! Got {val:#06x}"


@cocotb.test()
async def test_lbu_zero_extend(dut):
    """LBU zero-extends 0x80 to 0x0080."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lbu(1, 0x30)
    a.sw(1, 0x40)
    a.spin()
    a.org(0x30)
    a.db(0x80)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0080, f"LBU zero extend failed! Got {val:#06x}"


@cocotb.test()
async def test_byte_negative_offset(dut):
    """LB with negative offset computes correct address."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(0, 0x20)           # R0 = 0x20
    a.lb(1, -1)             # R1 = sext(mem[R0-1]) = 0x007F
    a.sw_s(1, 0x40)         # mem16[R7+0x40] = R1
    a.spin()
    a.org(0x1F)
    a.db(0x7F)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x007F, f"Expected 0x007F, got {val:#06x}"


@cocotb.test()
async def test_sp_lw_sw(dut):
    """LWS/SWS: word load/store via R7 (SP) with offset."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # LWS R1, 0x30 — load from R7+0x30 = 0x0030
    a.lw_s(1, 0x30)
    # SWS R1, 0x50 — store to R7+0x50 = 0x0050
    a.sw_s(1, 0x50)
    a.spin()
    a.org(0x30)
    a.dw(0xBEEF)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    val = _read_ram(dut, 0x0050) | (_read_ram(dut, 0x0051) << 8)
    assert val == 0xBEEF, f"SP LW/SW: expected 0xBEEF, got {val:#06x}"


@cocotb.test()
async def test_sp_lb_sb(dut):
    """LBS/LBUS/SBS: byte load/store via R7 (SP)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # LBS R1, 0x30 — sign-extend load from R7+0x30
    a.lb_s(1, 0x30)
    a.sw_s(1, 0x40)
    # LBUS R2, 0x30 — zero-extend load from R7+0x30
    a.lbu_s(2, 0x30)
    a.sw_s(2, 0x42)
    # SBS R1, 0x44 — store low byte of R1
    a.sb_s(1, 0x44)
    a.spin()
    a.org(0x30)
    a.db(0x85)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)

    v_lb = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    v_lbu = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    v_sb = _read_ram(dut, 0x0044)
    assert v_lb == 0xFF85, f"LBS: expected 0xFF85, got {v_lb:#06x}"
    assert v_lbu == 0x0085, f"LBUS: expected 0x0085, got {v_lbu:#06x}"
    assert v_sb == 0x85, f"SBS: expected 0x85, got {v_sb:#04x}"


@cocotb.test()
async def test_sp_negative_offset(dut):
    """SP load/store with negative offset."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # Set R7 = 0x50
    a.li(7, 0x50)
    # Store data: LI R1, 0x42; SWS R1, -2 → stores at R7-2 = 0x4E
    a.li(1, 0x42)
    a.sw_s(1, -2)
    # Load it back: LWS R2, -2 → loads from 0x4E
    a.lw_s(2, -2)
    # Store R2 to a known location for checking
    a.sw_s(2, 0x10)         # R7+0x10 = 0x60
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)

    val = _read_ram(dut, 0x0060) | (_read_ram(dut, 0x0061) << 8)
    assert val == 0x0042, f"SP neg offset: expected 0x0042, got {val:#06x}"


@cocotb.test()
async def test_sp_arbitrary_register(dut):
    """SP loads/stores work with any register, not just R0."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # Load to R5 (not R0): LWS R5, 0x30
    a.lw_s(5, 0x30)
    # Store from R5: SWS R5, 0x50
    a.sw_s(5, 0x50)
    a.spin()
    a.org(0x30)
    a.dw(0xABCD)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    val = _read_ram(dut, 0x0050) | (_read_ram(dut, 0x0051) << 8)
    assert val == 0xABCD, f"SP arb reg: expected 0xABCD, got {val:#06x}"
