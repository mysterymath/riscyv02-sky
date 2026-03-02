# SPDX-FileCopyrightText: © 2024 mysterymath
# SPDX-License-Identifier: Apache-2.0
#
# Shared test infrastructure for RISCY-V02 cocotb tests.
#
# Register convention: R0 is used as a zero-base address register throughout
# tests. After reset, all registers are 0, so R0 starts at 0 and is kept at 0
# for R,8 loads/stores (which use R0 as implicit base). R,8 loads write to
# ir[2:0] (rd); R,8 stores read data from ir[2:0] (rs). SP variants use R7.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

from asm import Asm

__all__ = [
    'cocotb', 'Clock', 'ClockCycles', 'FallingEdge',
    '_reset', '_load_program', '_read_ram', '_set_ui',
    '_measure_instruction_cycles',
    'Asm',
]


async def _reset(dut):
    """Apply reset sequence.

    rst_n deasserts after a falling edge (while clk is low), satisfying the
    bus protocol's sync-deassert requirement: the first active edge after
    reset is always a posedge.
    """
    dut.ena.value = 1
    dut.ui_in.value = 0x06  # RDY=1, NMIB=1 (inactive)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1


def _load_program(dut, program):
    """Load a program dict {addr: byte} into RAM."""
    for addr, val in program.items():
        dut.ram[addr].value = val


def _read_ram(dut, addr):
    return int(dut.ram[addr].value)


def _set_ui(dut, rdy=True, irqb=True, nmib=True):
    """Set ui_in control signals. IRQB/NMIB are active-low."""
    val = (int(rdy) << 2) | (int(nmib) << 1) | int(irqb)
    dut.ui_in.value = val


# ===========================================================================
# Cycle measurement helper
# ===========================================================================
async def _measure_instruction_cycles(dut, prog, expected_cycles, test_name):
    """Measure cycles for the first instruction in prog."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    _load_program(dut, prog)
    await _reset(dut)

    def get_sync():
        return (int(dut.uo_out.value) >> 1) & 1

    # Wait for first SYNC
    for _ in range(200):
        await FallingEdge(dut.clk)
        if get_sync():
            break

    # Count cycles until next SYNC
    cycles = 0
    # Wait for SYNC to drop
    for _ in range(200):
        await FallingEdge(dut.clk)
        cycles += 1
        if not get_sync():
            break

    # Wait for SYNC to rise
    for _ in range(200):
        await FallingEdge(dut.clk)
        cycles += 1
        if get_sync():
            break

    dut._log.info(f"{test_name}: {cycles} cycles (expected {expected_cycles})")
    assert cycles == expected_cycles, f"{test_name}: expected {expected_cycles} cycles, got {cycles}"
