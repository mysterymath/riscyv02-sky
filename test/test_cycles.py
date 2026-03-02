# SPDX-FileCopyrightText: © 2024 mysterymath
# SPDX-License-Identifier: Apache-2.0
#
# Cycle count tests: verify instruction throughput.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge
from test_helpers import *


@cocotb.test()
async def test_cycle_count_nop(dut):
    """NOP (ADDI R0, 0) takes 2 cycles."""
    a = Asm()
    a.nop()
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 2, "NOP")


@cocotb.test()
async def test_cycle_count_lw(dut):
    """LW takes 4 cycles throughput."""
    a = Asm()
    a.lw(1, 0x30)
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 4, "LW")


@cocotb.test()
async def test_cycle_count_sw(dut):
    """SW takes 4 cycles throughput."""
    a = Asm()
    a.sw(7, 0x30)
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 4, "SW")


@cocotb.test()
async def test_cycle_count_jr(dut):
    """JR (same page) takes 3 cycles."""
    a = Asm()
    # JR R7, 0 → PC = 0+0 = 0x0000 (spin at self), same page = 3 cycles
    a.jr(7, 0)
    await _measure_instruction_cycles(dut, a.assemble(), 3, "JR")


@cocotb.test()
async def test_cycle_count_sei(dut):
    """SEI takes 2 cycles."""
    a = Asm()
    a.sei()
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 2, "SEI")


@cocotb.test()
async def test_cycle_count_cli(dut):
    """CLI takes 2 cycles."""
    a = Asm()
    a.cli()
    a.spin()
    # Must use IRQB=1 to avoid IRQ firing after CLI clears I
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    _load_program(dut, a.assemble())
    dut.ena.value = 1
    dut.ui_in.value = 0x07  # RDY=1, NMIB=1, IRQB=1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    # Measure from first SYNC to next
    def get_sync():
        return (int(dut.uo_out.value) >> 1) & 1
    for _ in range(200):
        await FallingEdge(dut.clk)
        if get_sync():
            break
    cycles = 0
    for _ in range(200):
        await FallingEdge(dut.clk)
        cycles += 1
        if not get_sync():
            break
    for _ in range(200):
        await FallingEdge(dut.clk)
        cycles += 1
        if get_sync():
            break
    dut._log.info(f"CLI: {cycles} cycles (expected 2)")
    assert cycles == 2, f"CLI: expected 2 cycles, got {cycles}"


@cocotb.test()
async def test_cycle_count_li(dut):
    """LI takes 2 cycles (no memory phase, fetch overlaps execute)."""
    a = Asm()
    a.li(1, 42)
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 2, "LI")


@cocotb.test()
async def test_cycle_count_add(dut):
    """ADD takes 2 cycles (no memory phase)."""
    a = Asm()
    a.add(1, 2, 3)
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 2, "ADD")


@cocotb.test()
async def test_cycle_count_lb(dut):
    """LB takes 3 cycles (byte load completes at E_MEM_LO)."""
    a = Asm()
    a.lb(1, 0x30)
    a.spin()
    a.org(0x30)
    a.db(0x42)
    await _measure_instruction_cycles(dut, a.assemble(), 3, "LB")


@cocotb.test()
async def test_cycle_count_sb(dut):
    """SB takes 3 cycles (1 memory byte)."""
    a = Asm()
    a.sb(7, 0x30)
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 3, "SB")


@cocotb.test()
async def test_cycle_count_addi(dut):
    """ADDI takes 2 cycles (no memory phase)."""
    a = Asm()
    a.addi(1, 5)
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 2, "ADDI")


@cocotb.test()
async def test_cycle_count_auipc(dut):
    """AUIPC takes 2 cycles (no memory phase)."""
    a = Asm()
    a.auipc(1, 1)
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 2, "AUIPC")


@cocotb.test()
async def test_cycle_count_branch_taken(dut):
    """BZ taken (same page) takes 3 cycles."""
    a = Asm()
    # R0 = 0 from reset, BZ R0 is always taken, same page = 3 cycles
    a.bz(0, 1)
    a.nop()
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 3, "BZ taken (same page)")


@cocotb.test()
async def test_cycle_count_branch_taken_page_cross(dut):
    """BZ taken (page cross) takes 4 cycles."""
    a = Asm()
    # BZ R0, 127: next_pc=0x0002, target=0x0002+127*2=0x0100 (page cross)
    a.bz(0, 127)
    a.org(0x0100)
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 4, "BZ taken (page cross)")


@cocotb.test()
async def test_cycle_count_j(dut):
    """J (same page, small offset) takes 3 cycles."""
    a = Asm()
    # J -1: target = next_pc - 2 = 0x0000, same page, small offset
    a.j(-1)
    await _measure_instruction_cycles(dut, a.assemble(), 3, "J (same page)")


@cocotb.test()
async def test_cycle_count_reti(dut):
    """RETI takes 3 cycles (1 execute + 2 fetch)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # RETI at 0x0000 returns to EPC (0x0000 after reset) -> infinite loop
    a.reti()

    def get_sync():
        return (int(dut.uo_out.value) >> 1) & 1

    _load_program(dut, a.assemble())
    # Custom reset with IRQB=1 so RETI restoring I=0 doesn't trigger IRQ
    dut.ena.value = 1
    dut.ui_in.value = 0x07  # RDY=1, NMIB=1, IRQB=1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1

    for _ in range(200):
        await FallingEdge(dut.clk)
        if get_sync():
            break
    cycles = 0
    for _ in range(200):
        await FallingEdge(dut.clk)
        cycles += 1
        if not get_sync():
            break
    for _ in range(200):
        await FallingEdge(dut.clk)
        cycles += 1
        if get_sync():
            break

    dut._log.info(f"RETI: {cycles} cycles (expected 3)")
    assert cycles == 3, f"RETI: expected 3 cycles, got {cycles}"


@cocotb.test()
async def test_cycle_count_wai(dut):
    """WAI with pending masked IRQ takes 2 cycles (wakes immediately)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.wai()
    a.spin()

    def get_sync():
        return (int(dut.uo_out.value) >> 1) & 1

    _load_program(dut, a.assemble())
    # Reset with IRQB=0 (pending but masked by I=1)
    dut.ena.value = 1
    dut.ui_in.value = 0x06  # RDY=1, NMIB=1, IRQB=0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1

    for _ in range(100):
        await FallingEdge(dut.clk)
        if get_sync():
            break

    cycles = 0
    for _ in range(100):
        await FallingEdge(dut.clk)
        cycles += 1
        if not get_sync():
            break
    for _ in range(100):
        await FallingEdge(dut.clk)
        cycles += 1
        if get_sync():
            break

    dut._log.info(f"WAI: {cycles} cycles (expected 2)")
    assert cycles == 2, f"WAI: expected 2 cycles, got {cycles}"


@cocotb.test()
async def test_cycle_count_stp(dut):
    """STP takes 1 cycle to halt."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.stp()

    def get_sync():
        return (int(dut.uo_out.value) >> 1) & 1

    _load_program(dut, a.assemble())
    dut.ena.value = 1
    dut.ui_in.value = 0x07
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1

    for _ in range(100):
        await FallingEdge(dut.clk)
        if get_sync():
            break

    cycles = 0
    for _ in range(100):
        await FallingEdge(dut.clk)
        cycles += 1
        if not get_sync():
            break

    dut._log.info(f"STP: {cycles} cycle(s) to halt (expected 1)")
    assert cycles == 1, f"STP: expected 1 cycle, got {cycles}"

    for _ in range(50):
        await FallingEdge(dut.clk)
        assert not get_sync(), "SYNC high after STP -- CPU not halted!"


@cocotb.test()
async def test_cycle_count_brk(dut):
    """BRK takes 3 cycles (1 execute + 2 fetch)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.brk()
    # BRK handler at 0x0004: spin
    a.org(0x0004)
    a.spin()

    def get_sync():
        return (int(dut.uo_out.value) >> 1) & 1

    _load_program(dut, a.assemble())
    dut.ena.value = 1
    dut.ui_in.value = 0x07
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1

    for _ in range(100):
        await FallingEdge(dut.clk)
        if get_sync():
            break

    cycles = 0
    for _ in range(20):
        await FallingEdge(dut.clk)
        cycles += 1
        if get_sync():
            break

    dut._log.info(f"BRK: {cycles} cycles (expected 3)")
    assert cycles == 3, f"BRK: expected 3 cycles, got {cycles}"


@cocotb.test()
async def test_cycle_count_lbu(dut):
    """LBU takes 3 cycles (byte load completes at E_MEM_LO)."""
    a = Asm()
    a.lbu(1, 0)
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 3, "LBU")


@cocotb.test()
async def test_cycle_count_lw_s(dut):
    """LWS takes 4 cycles (same as LW)."""
    a = Asm()
    a.lw_s(1, 0x30)
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 4, "LWS")


@cocotb.test()
async def test_cycle_count_sw_s(dut):
    """SWS takes 4 cycles (same as SW)."""
    a = Asm()
    a.sw_s(1, 0x30)
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 4, "SWS")


@cocotb.test()
async def test_cycle_count_lb_s(dut):
    """LBS takes 3 cycles (same as LB)."""
    a = Asm()
    a.lb_s(1, 0x30)
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 3, "LBS")


@cocotb.test()
async def test_cycle_count_sb_s(dut):
    """SBS takes 3 cycles (same as SB)."""
    a = Asm()
    a.sb_s(1, 0x30)
    a.spin()
    await _measure_instruction_cycles(dut, a.assemble(), 3, "SBS")
