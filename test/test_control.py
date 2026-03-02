# SPDX-FileCopyrightText: © 2024 mysterymath
# SPDX-License-Identifier: Apache-2.0
#
# Branch and jump tests: JR, JALR, J, JAL, BZ/BNZ, single-step.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge
from test_helpers import *


@cocotb.test()
async def test_jr_computed(dut):
    """Load an address into a register, then JR to it."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x30)
    a.lw(2, 0x32)
    a.jr(1, 0)
    a.org(0x0020)
    a.sw(2, 0x40)
    a.spin()
    a.org(0x0030)
    a.db(0x20, 0x00, 0xEF, 0xBE)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0xBEEF, f"Expected 0xBEEF, got {val:#06x}"


@cocotb.test()
async def test_jr_after_lw(dut):
    """JR using a register value loaded by the immediately preceding LW."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x30)
    a.jr(1, 0)
    a.org(0x0040)
    a.li(1, 0)
    a.sw(1, 0x50)
    a.spin()
    a.org(0x0030)
    a.db(0x40, 0x00)
    a.org(0x0050)
    a.db(0xFF, 0xFF)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    lo = _read_ram(dut, 0x0050)
    hi = _read_ram(dut, 0x0051)
    assert lo == 0x00 and hi == 0x00, \
        f"SW at JR target did not execute (expected 0x0000, got {lo:#04x}{hi:#04x})"


@cocotb.test()
async def test_branches(dut):
    """BZ and BNZ branch behavior."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(2, 1)
    # BZ R1 (R1=0 after reset): taken → skip to 0x000A
    a.bz(1, 3)
    a.li(3, 0x13)
    a.sw(3, 0x40)
    a.spin()
    # BNZ R2 (R2=1): taken → skip to 0x0012
    a.bnz(2, 3)
    a.li(3, 0x13)
    a.sw(3, 0x42)
    a.spin()
    a.li(3, 0x42)
    a.sw(3, 0x40)
    a.spin()
    a.org(0x0040)
    a.db(0x00, 0x00)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0042, f"Branch test failed, got {val:#06x}"


@cocotb.test()
async def test_j_jal(dut):
    """J forward and JAL with link to R6."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.j(8)
    a.org(0x0012)
    a.jal(4)
    a.spin()
    a.org(0x001C)
    a.sw(6, 0x40)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0014, f"JAL link: expected 0x0014, got {val:#06x}"


@cocotb.test()
async def test_jalr(dut):
    """JALR: jump to rs+off, save return addr in R6."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x30)
    a.jalr(1, 0)
    a.org(0x0040)
    a.sw(6, 0x50)
    a.spin()
    a.org(0x0030)
    a.db(0x40, 0x00)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    val = _read_ram(dut, 0x0050) | (_read_ram(dut, 0x0051) << 8)
    assert val == 0x0004, f"JALR link: expected 0x0004, got {val:#06x}"


@cocotb.test()
async def test_single_step(dut):
    """Test single-step debugging using RDY/SYNC protocol."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 0x11)
    a.li(2, 0x22)
    a.li(3, 0x33)
    a.sw(1, 0x40)
    a.sw(2, 0x42)
    a.sw(3, 0x44)
    a.spin()

    def get_sync():
        return (int(dut.uo_out.value) >> 1) & 1

    def read_markers():
        m1 = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
        m2 = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
        m3 = _read_ram(dut, 0x0044) | (_read_ram(dut, 0x0045) << 8)
        return (m1, m2, m3)

    async def run_to_sync():
        dut.ui_in.value = 0x06
        for _ in range(200):
            await FallingEdge(dut.clk)
            if get_sync():
                dut.ui_in.value = 0x02
                return True
        return False

    async def single_step():
        dut.ui_in.value = 0x06
        for _ in range(200):
            await FallingEdge(dut.clk)
            if not get_sync():
                break
        for _ in range(200):
            await FallingEdge(dut.clk)
            if get_sync():
                dut.ui_in.value = 0x02
                return True
        return False

    # Reset with RDY=0
    dut.ena.value = 1
    dut.ui_in.value = 0x02
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    _load_program(dut, a.assemble())
    for addr in range(0x40, 0x46):
        dut.ram[addr].value = 0x00

    assert await run_to_sync(), "Failed to reach first boundary"

    m_before = read_markers()
    await ClockCycles(dut.clk, 20)
    m_after = read_markers()
    assert m_before == m_after, f"CPU modified state while halted"

    for i in range(3):
        assert await single_step(), f"single_step failed on LI {i+1}"

    assert await single_step(), "single_step failed on SW R1"
    m = read_markers()
    assert m == (0x0011, 0, 0), f"After SW R1: expected (0x0011, 0, 0), got {[hex(x) for x in m]}"

    assert await single_step(), "single_step failed on SW R2"
    m = read_markers()
    assert m == (0x0011, 0x0022, 0), f"After SW R2: expected, got {[hex(x) for x in m]}"

    assert await single_step(), "single_step failed on SW R3"
    m = read_markers()
    assert m == (0x0011, 0x0022, 0x0033), f"After SW R3: expected all, got {[hex(x) for x in m]}"


@cocotb.test()
async def test_bnz_high_byte(dut):
    """BNZ detects nonzero in high byte only."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x30)
    a.bnz(1, 2)
    a.li(3, 0x13)
    a.sw(3, 0x40)
    a.li(3, 0x42)
    a.sw(3, 0x40)
    a.spin()
    a.org(0x0030)
    a.db(0x00, 0x01)
    a.org(0x0040)
    a.db(0x00, 0x00)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0042, f"BNZ didn't detect high byte! Got {val:#06x}"


@cocotb.test()
async def test_j_backward(dut):
    """J with negative offset jumps backward."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.j(15)
    a.org(0x0010)
    a.li(3, 0x42)
    a.sw(3, 0x40)
    a.spin()
    a.org(0x0020)
    a.j(-9)
    a.org(0x0040)
    a.db(0x00, 0x00)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0042, f"J backward failed! Got {val:#06x}"


@cocotb.test()
async def test_jal_link_value(dut):
    """JAL stores correct return address in R6."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.jal(4)
    a.spin()
    a.org(0x000A)
    a.sw(6, 0x40)
    a.spin()
    a.org(0x0040)
    a.db(0x00, 0x00)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0002, f"JAL link wrong! Got {val:#06x}"


@cocotb.test()
async def test_bz_not_taken(dut):
    """BZ on non-zero register -> branch not taken."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 5)
    a.bz(1, 3)
    a.li(2, 7)
    a.sw(2, 0x40)
    a.spin()
    a.org(0x0040)
    a.db(0x00, 0x00)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0007, f"Expected 0x0007, got {val:#06x}"


@cocotb.test()
async def test_bnz_not_taken(dut):
    """BNZ on zero register -> branch not taken."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.bnz(0, 3)
    a.li(1, 7)
    a.sw(1, 0x40)
    a.spin()
    a.org(0x0040)
    a.db(0x00, 0x00)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0007, f"Expected 0x0007, got {val:#06x}"


@cocotb.test()
async def test_jr_ignores_low_bit(dut):
    """JR ignores bit 0 of the computed target address."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # R1 = 0x0011 (odd)
    a.li(1, 0x11)
    # JR R1, 0 → should jump to 0x0010 (bit 0 ignored), not 0x0011
    a.jr(1, 0)
    # At 0x0010: identifiable instruction proves we arrived correctly
    a.org(0x0010)
    a.li(3, 0x42)
    a.sw(3, 0x40)
    a.spin()
    a.org(0x0040)
    a.db(0x00, 0x00)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0042, f"JR should ignore bit 0: expected 0x0042, got {val:#06x}"


@cocotb.test()
async def test_bt_taken(dut):
    """BT with T=1 branches forward."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # CLTI R0, 1 sets T=1 (0 < 1 = true)
    a.clti(0, 1)
    # BT +3: target = (0x0002+2) + 3*2 = 0x000A
    a.bt(3)
    # Skipped:
    a.li(1, 0x11)
    a.sw(1, 0x40)
    a.spin()
    # Branch target:
    a.li(1, 0x22)
    a.sw(1, 0x40)
    a.spin()
    a.org(0x0040)
    a.db(0x00, 0x00)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0022, f"BT taken: expected 0x0022, got {val:#06x}"


@cocotb.test()
async def test_bt_not_taken(dut):
    """BT with T=0 falls through."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # CLTI R0, 0 sets T=0 (0 < 0 = false)
    a.clti(0, 0)
    a.bt(3)
    # Fall-through:
    a.li(1, 0x33)
    a.sw(1, 0x40)
    a.spin()
    # Branch target (should NOT reach):
    a.li(1, 0x44)
    a.sw(1, 0x40)
    a.spin()
    a.org(0x0040)
    a.db(0x00, 0x00)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0033, f"BT not taken: expected 0x0033, got {val:#06x}"


@cocotb.test()
async def test_bf_taken(dut):
    """BF with T=0 branches forward."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # CLTI R0, 0 sets T=0 (0 < 0 = false)
    a.clti(0, 0)
    a.bf(3)
    a.li(1, 0x11)
    a.sw(1, 0x40)
    a.spin()
    a.li(1, 0x55)
    a.sw(1, 0x40)
    a.spin()
    a.org(0x0040)
    a.db(0x00, 0x00)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0055, f"BF taken: expected 0x0055, got {val:#06x}"


@cocotb.test()
async def test_bf_not_taken(dut):
    """BF with T=1 falls through."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # CLTI R0, 1 sets T=1 (0 < 1 = true)
    a.clti(0, 1)
    a.bf(3)
    a.li(1, 0x66)
    a.sw(1, 0x40)
    a.spin()
    a.li(1, 0x77)
    a.sw(1, 0x40)
    a.spin()
    a.org(0x0040)
    a.db(0x00, 0x00)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0066, f"BF not taken: expected 0x0066, got {val:#06x}"
