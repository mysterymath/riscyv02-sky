# SPDX-FileCopyrightText: © 2024 mysterymath
# SPDX-License-Identifier: Apache-2.0
#
# Reset behavior observation test.
#
# Captures the exact value of every output pin at every clock edge after
# reset release.  Uses string representation to preserve X/Z values.
#
# Bus phase is determined by edge type: posedge = address phase,
# negedge = data phase.  This matches the CPU's mux_sel toggle without
# requiring a testbench replica of that signal.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, FallingEdge


def _sig(value):
    """Format a signal value preserving X/Z."""
    s = str(value)
    if 'x' in s.lower() or 'z' in s.lower():
        return s
    return f"0x{int(value):02X}"


def _sig16(hi, lo):
    """Format a 16-bit value from two 8-bit signals."""
    hs = str(hi)
    ls = str(lo)
    if 'x' in hs.lower() or 'z' in hs.lower() or \
       'x' in ls.lower() or 'z' in ls.lower():
        return f"{hs}:{ls}"
    return f"0x{int(hi):02X}{int(lo):02X}"


def _interp_addr(dut):
    """Interpret pins as address phase."""
    return f"ADDR AB={_sig16(dut.uio_out.value, dut.uo_out.value)}"


def _interp_data(dut):
    """Interpret pins as data phase."""
    try:
        rwb = int(dut.uo_out.value) & 1
        sync = (int(dut.uo_out.value) >> 1) & 1
        return f"DATA RWB={rwb} SYNC={sync} DO={_sig(dut.uio_out.value)}"
    except (ValueError, TypeError):
        return "DATA ???"


@cocotb.test()
async def test_reset_pin_trace(dut):
    """Log every output pin at every edge for the first 30 cycles after reset.

    This is an observation test — it always passes. The output is used to
    verify the emulator's reset behavior matches the RTL.
    """
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    # Load a known program: NOP (0x0000) everywhere, except a spin loop
    # at address 0 so behavior is deterministic.
    # J -1 at address 0: self-loop
    from asm import Asm
    a = Asm()
    a.spin()
    prog = a.assemble()
    for i in range(65536):
        dut.ram[i].value = 0
    for addr, val in prog.items():
        dut.ram[addr].value = val

    # Reset
    dut.ena.value = 1
    dut.ui_in.value = 0x07  # RDY=1, NMIB=1, IRQB=1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1

    dut._log.info("=== Pin trace after reset release ===")
    dut._log.info("Edge | uo_out   | uio_out  | uio_oe   | phase | interpretation")
    dut._log.info("-----|----------|----------|----------|-------|---------------")

    for cycle in range(30):
        await RisingEdge(dut.clk)
        uo = _sig(dut.uo_out.value)
        uio = _sig(dut.uio_out.value)
        oe = _sig(dut.uio_oe.value)
        interp = _interp_addr(dut)
        dut._log.info(f"  +{cycle:02d} | {uo:8s} | {uio:8s} | {oe:8s} | addr  | {interp}")

        await FallingEdge(dut.clk)
        uo = _sig(dut.uo_out.value)
        uio = _sig(dut.uio_out.value)
        oe = _sig(dut.uio_oe.value)
        interp = _interp_data(dut)
        dut._log.info(f"  -{cycle:02d} | {uo:8s} | {uio:8s} | {oe:8s} | data  | {interp}")


@cocotb.test()
async def test_reset_with_nop_program(dut):
    """Same trace but with all-NOP RAM (ADDI R0, 0 = 0x0000).

    Sequential NOPs exercise the basic pipeline without any control flow.
    """
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    for i in range(65536):
        dut.ram[i].value = 0

    dut.ena.value = 1
    dut.ui_in.value = 0x07
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1

    dut._log.info("=== Pin trace: all-NOP program ===")
    dut._log.info("Edge | uo_out   | uio_out  | uio_oe   | phase | interpretation")
    dut._log.info("-----|----------|----------|----------|-------|---------------")

    for cycle in range(20):
        await RisingEdge(dut.clk)
        uo = _sig(dut.uo_out.value)
        uio = _sig(dut.uio_out.value)
        oe = _sig(dut.uio_oe.value)
        interp = _interp_addr(dut)
        dut._log.info(f"  +{cycle:02d} | {uo:8s} | {uio:8s} | {oe:8s} | addr  | {interp}")

        await FallingEdge(dut.clk)
        uo = _sig(dut.uo_out.value)
        uio = _sig(dut.uio_out.value)
        oe = _sig(dut.uio_oe.value)
        interp = _interp_data(dut)
        dut._log.info(f"  -{cycle:02d} | {uo:8s} | {uio:8s} | {oe:8s} | data  | {interp}")
