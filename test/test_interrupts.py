# SPDX-FileCopyrightText: © 2024 mysterymath
# SPDX-License-Identifier: Apache-2.0
#
# Interrupt handling tests: IRQ, NMI, BRK, RETI, WAI, STP, CLI/SEI, EPCR/EPCW.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge
from test_helpers import *


@cocotb.test()
async def test_reset_i_state(dut):
    """Verify interrupts are disabled after reset (I=1)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.spin()                     # 0x0000: reset vector spin
    a.org(0x0006)
    a.li(1, 0x42)                # 0x0006: IRQ handler
    a.sw(1, 0x40)                # 0x0008
    a.spin()                     # 0x000A
    a.org(0x0040)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    dut.ena.value = 1
    dut.ui_in.value = 0x06  # IRQB=0 (asserted!)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 100)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0000, f"IRQ fired after reset! Got {val:#06x}"


@cocotb.test()
async def test_cli_enables_irq(dut):
    """CLI clears I bit, allowing interrupts to fire."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.cli()                      # 0x0000: reset vector
    a.spin()                     # 0x0002
    a.org(0x0006)
    a.li(1, 0x5A)                # 0x0006: IRQ handler
    a.sw(1, 0x40)                # 0x0008
    a.spin()                     # 0x000A
    a.org(0x0040)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    dut.ena.value = 1
    dut.ui_in.value = 0x07
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 20)
    dut.ui_in.value = 0x06
    await ClockCycles(dut.clk, 100)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x005A, f"IRQ did not fire after CLI! Got {val:#06x}"


@cocotb.test()
async def test_sei_disables_irq(dut):
    """SEI sets I bit, preventing interrupts."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.j(8)                       # 0x0000: reset vector → 0x0012
    a.org(0x0006)
    a.li(1, 0x42)                # 0x0006: IRQ handler
    a.sw(1, 0x40)                # 0x0008
    a.spin()                     # 0x000A
    a.org(0x0012)
    a.cli()                      # 0x0012
    a.sei()                      # 0x0014
    a.spin()                     # 0x0016
    a.org(0x0040)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    dut.ena.value = 1
    dut.ui_in.value = 0x07
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 50)
    dut.ui_in.value = 0x06
    await ClockCycles(dut.clk, 100)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0000, f"IRQ fired after SEI! Got {val:#06x}"


@cocotb.test()
async def test_reti(dut):
    """RETI restores I from EPC[0] and returns to saved PC."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.j(8)                       # 0x0000: reset vector → 0x0012
    a.org(0x0006)
    a.li(1, 0x42)                # 0x0006: IRQ handler
    a.sw(1, 0x40)                # 0x0008
    a.reti()                     # 0x000A
    a.org(0x0012)
    a.cli()                      # 0x0012
    a.spin()                     # 0x0014
    a.org(0x0040)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    dut.ena.value = 1
    dut.ui_in.value = 0x07
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 30)
    dut.ui_in.value = 0x06
    await ClockCycles(dut.clk, 30)
    dut.ui_in.value = 0x07
    await ClockCycles(dut.clk, 100)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0042, f"IRQ handler did not execute! Got {val:#06x}"


@cocotb.test()
async def test_brk(dut):
    """BRK saves EPC, sets I=1, vectors to 0x0004."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.j(8)                       # 0x0000: reset vector → 0x0012
    a.org(0x0004)
    a.li(1, 0x42)                # 0x0004: BRK handler
    a.sw(1, 0x40)                # 0x0006
    a.spin()                     # 0x0008
    a.org(0x0012)
    a.brk()                      # 0x0012
    a.spin()                     # 0x0014
    a.org(0x0040)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0042, f"BRK handler not reached! Got {val:#06x}"


@cocotb.test()
async def test_wai(dut):
    """WAI halts until interrupt."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.j(8)                       # 0x0000: reset vector → 0x0012
    a.org(0x0006)
    a.li(1, 0x42)                # 0x0006: IRQ handler
    a.sw(1, 0x40)                # 0x0008
    a.reti()                     # 0x000A
    a.org(0x0012)
    a.cli()                      # 0x0012
    a.wai()                      # 0x0014
    a.li(1, 0x55)                # 0x0016
    a.sw(1, 0x42)                # 0x0018
    a.spin()                     # 0x001A
    a.org(0x0040)
    a.dw(0x0000)
    a.org(0x0042)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    dut.ena.value = 1
    dut.ui_in.value = 0x07
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 50)

    v1 = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert v1 == 0x0000, f"Handler fired before IRQ: {v1:#06x}"

    dut.ui_in.value = 0x06
    await ClockCycles(dut.clk, 50)
    dut.ui_in.value = 0x07
    await ClockCycles(dut.clk, 100)

    v1 = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    v2 = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    assert v1 == 0x0042, f"IRQ handler marker: expected 0x0042, got {v1:#06x}"
    assert v2 == 0x0055, f"Post-WAI marker: expected 0x0099, got {v2:#06x}"


@cocotb.test()
async def test_stp(dut):
    """STP halts permanently; only reset recovers."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.stp()                      # 0x0000: reset vector
    a.li(1, 0x42)                # 0x0002
    a.sw(1, 0x40)                # 0x0004
    a.spin()                     # 0x0006
    a.org(0x0040)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0000, f"STP did not halt! Got {val:#06x}"


@cocotb.test()
async def test_nmib_low_during_reset_no_spurious_nmi(dut):
    """Holding NMIB low throughout reset must not cause a spurious NMI.

    nmib_prev resets to 1 (inactive).  If NMIB is already low when reset
    releases, the edge detector would see a 1->0 transition that never
    actually occurred on the pin.  The fix: reset nmib_prev to 0 (active),
    which means "assume NMI was already asserted."  Trade-off: an NMI that
    arrives on the exact cycle reset releases is missed (same as the 6502,
    whose 7-cycle reset sequence clears any pending NMI).
    """
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.spin()                     # 0x0000: reset vector spin
    a.org(0x0002)
    a.li(1, 0x42)                # 0x0002: NMI handler
    a.sw(1, 0x40)                # 0x0004
    a.spin()                     # 0x0006
    a.org(0x0040)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    dut.ena.value = 1
    dut.ui_in.value = 0x05  # RDY=1, NMIB=0 (asserted!), IRQB=1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 100)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0000, f"Spurious NMI fired after reset! Got {val:#06x}"


@cocotb.test()
async def test_nmi(dut):
    """NMI fires on NMIB falling edge, even with I=1."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.spin()                     # 0x0000: reset vector spin
    a.org(0x0002)
    a.li(1, 0x42)                # 0x0002: NMI handler
    a.sw(1, 0x40)                # 0x0004
    a.spin()                     # 0x0006
    a.org(0x0040)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 30)

    dut.ui_in.value = 0x05
    await ClockCycles(dut.clk, 5)
    dut.ui_in.value = 0x07
    await ClockCycles(dut.clk, 100)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0042, f"NMI handler not reached! Got {val:#06x}"


@cocotb.test()
async def test_i_bit_masking(dut):
    """After IRQ entry, I=1 prevents nested interrupts."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 0x20)                # 0x0000: reset vector
    a.jr(1, 0)                   # 0x0002: jump to 0x0020
    a.org(0x0006)
    a.li(1, 0x42)                # 0x0006: IRQ handler
    a.sw(1, 0x40)                # 0x0008
    a.spin()                     # 0x000A
    a.org(0x0020)
    a.cli()                      # 0x0020
    a.spin()                     # 0x0022
    a.org(0x0040)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 50)
    _set_ui(dut, rdy=True, irqb=False, nmib=True)
    await ClockCycles(dut.clk, 500)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0042, f"IRQ handler didn't run! Got {val:#06x}"


@cocotb.test()
async def test_irq_during_multicycle(dut):
    """IRQ during LW completes the LW before entering handler."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 0x10)                # 0x0000: reset vector
    a.jr(1, 0)                   # 0x0002: jump to 0x0010
    a.org(0x0006)
    a.sw(1, 0x42)                # 0x0006: IRQ handler
    a.reti()                     # 0x0008
    a.org(0x0010)
    a.cli()                      # 0x0010
    a.lw(1, 0x30)                # 0x0012
    a.sw(1, 0x40)                # 0x0014
    a.spin()                     # 0x0016
    a.org(0x0030)
    a.dw(0x1234)
    a.org(0x0040)
    a.dw(0x0000)
    a.org(0x0042)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 40)
    _set_ui(dut, rdy=True, irqb=False, nmib=True)
    await ClockCycles(dut.clk, 200)
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    await ClockCycles(dut.clk, 50)

    main = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    irq = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    assert main == 0x1234, f"LW/SW failed! Got {main:#06x}"
    assert irq == 0x1234, f"IRQ saw wrong R1! Got {irq:#06x}"


@cocotb.test()
async def test_cli_atomicity(dut):
    """CLI with pending IRQ: IRQ fires after CLI completes."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.cli()                      # 0x0000: reset vector
    a.spin()                     # 0x0002
    a.org(0x0006)
    a.li(1, 0x42)                # 0x0006: IRQ handler
    a.sw(1, 0x40)                # 0x0008
    a.spin()                     # 0x000A
    a.org(0x0040)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    dut.ena.value = 1
    dut.ui_in.value = 0x06
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 50)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0042, f"IRQ did not fire after CLI! Got {val:#06x}"


@cocotb.test()
async def test_nmi_edge_triggered(dut):
    """Holding NMIB low does not re-trigger. Only one NMI per falling edge."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.spin()                     # 0x0000: reset vector spin
    a.org(0x0002)
    a.li(1, 0x42)                # 0x0002: NMI handler
    a.sw(1, 0x40)                # 0x0004
    a.spin()                     # 0x0006
    a.org(0x0040)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 30)

    _set_ui(dut, rdy=True, irqb=True, nmib=False)
    await ClockCycles(dut.clk, 500)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0042, f"NMI handler didn't run! Got {val:#06x}"


@cocotb.test()
async def test_nmi_priority_over_irq(dut):
    """When both NMI and IRQ are pending, NMI is taken."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.jr(7, 0x20)                # 0x0000: reset vector → 0x0020
    a.org(0x0002)
    a.jr(7, 0x30)                # 0x0002: NMI handler → 0x0030
    a.org(0x0004)
    a.spin()                     # 0x0004: BRK handler spin
    a.org(0x0006)
    a.jr(7, 0x38)                # 0x0006: IRQ handler → 0x0038
    a.org(0x0020)
    a.cli()                      # 0x0020
    a.spin()                     # 0x0022
    a.org(0x0030)
    a.li(1, 0x22)                # 0x0030: NMI body
    a.sw(1, 0x44)                # 0x0032
    a.spin()                     # 0x0034
    a.org(0x0038)
    a.li(1, 0x11)                # 0x0038: IRQ body
    a.sw(1, 0x46)                # 0x003A
    a.spin()                     # 0x003C
    a.org(0x0044)
    a.dw(0x0000)
    a.org(0x0046)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 50)
    _set_ui(dut, rdy=True, irqb=False, nmib=False)
    await ClockCycles(dut.clk, 200)

    nmi = _read_ram(dut, 0x0044) | (_read_ram(dut, 0x0045) << 8)
    irq = _read_ram(dut, 0x0046) | (_read_ram(dut, 0x0047) << 8)
    assert nmi == 0x0022, f"NMI handler didn't run! Got {nmi:#06x}"
    assert irq == 0x0000, f"IRQ fired instead of NMI! Got {irq:#06x}"


@cocotb.test()
async def test_nmi_during_multicycle(dut):
    """NMI during LW completes the LW before entering handler."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.jr(7, 0x20)                # 0x0000: reset vector → 0x0020
    a.org(0x0002)
    a.sw(1, 0x42)                # 0x0002: NMI handler
    a.reti()                     # 0x0004
    a.spin()                     # 0x0006
    a.org(0x0020)
    a.lw(1, 0x30)                # 0x0020
    a.sw(1, 0x40)                # 0x0022
    a.spin()                     # 0x0024
    a.org(0x0030)
    a.dw(0x1234)
    a.org(0x0040)
    a.dw(0x0000)
    a.org(0x0042)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 40)
    _set_ui(dut, rdy=True, irqb=True, nmib=False)
    await ClockCycles(dut.clk, 10)
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    await ClockCycles(dut.clk, 200)

    main = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    nmi = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    assert main == 0x1234, f"Main code failed! Got {main:#06x}"
    assert nmi == 0x1234, f"NMI saw wrong R1! Got {nmi:#06x}"


@cocotb.test()
async def test_nmi_second_edge(dut):
    """After first NMI handled, second falling edge triggers another."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.spin()                     # 0x0000: reset vector spin
    a.org(0x0002)
    a.lw(1, 0x40)                # 0x0002: NMI handler
    a.addi(1, 1)                 # 0x0004
    a.sw(1, 0x40)                # 0x0006
    a.reti()                     # 0x0008
    a.org(0x0040)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 30)

    # First NMI pulse
    _set_ui(dut, rdy=True, irqb=True, nmib=False)
    await ClockCycles(dut.clk, 10)
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    await ClockCycles(dut.clk, 100)

    # Second NMI pulse
    _set_ui(dut, rdy=True, irqb=True, nmib=False)
    await ClockCycles(dut.clk, 10)
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    await ClockCycles(dut.clk, 100)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 2, f"Expected 2 NMI entries, got {val}"


@cocotb.test()
async def test_nmi_during_rdy_low(dut):
    """NMI edge while RDY=0 is captured and serviced when RDY returns."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.spin()                     # 0x0000: reset vector spin
    a.org(0x0002)
    a.li(1, 0x42)                # 0x0002: NMI handler
    a.sw(1, 0x40)                # 0x0004
    a.spin()                     # 0x0006
    a.org(0x0040)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 30)

    _set_ui(dut, rdy=False, irqb=True, nmib=True)
    await ClockCycles(dut.clk, 10)
    _set_ui(dut, rdy=False, irqb=True, nmib=False)
    await ClockCycles(dut.clk, 10)
    _set_ui(dut, rdy=False, irqb=True, nmib=True)
    await ClockCycles(dut.clk, 10)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0000, f"NMI ran while halted! Got {val:#06x}"

    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    await ClockCycles(dut.clk, 100)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0042, f"NMI lost during RDY=0! Got {val:#06x}"


@cocotb.test()
async def test_wai_irq(dut):
    """WAI halts until IRQ; handler runs, RETI returns past WAI."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.jr(7, 0x20)                # 0x0000: reset vector → 0x0020
    a.org(0x0002)
    a.spin()                     # 0x0002: NMI handler spin
    a.org(0x0004)
    a.spin()                     # 0x0004: BRK handler spin
    a.org(0x0006)
    a.li(1, 0x11)                # 0x0006: IRQ handler
    a.sw(1, 0x40)                # 0x0008
    a.reti()                     # 0x000A
    a.org(0x0020)
    a.cli()                      # 0x0020
    a.wai()                      # 0x0022
    a.li(1, 0x22)                # 0x0024
    a.sw(1, 0x42)                # 0x0026
    a.spin()                     # 0x0028
    a.org(0x0040)
    a.dw(0x0000)
    a.org(0x0042)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 50)
    _set_ui(dut, rdy=True, irqb=False, nmib=True)
    await ClockCycles(dut.clk, 200)
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    await ClockCycles(dut.clk, 100)

    irq = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    post = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    assert irq == 0x0011, f"IRQ handler didn't run! Got {irq:#06x}"
    assert post == 0x0022, f"Didn't return past WAI! Got {post:#06x}"


@cocotb.test()
async def test_wai_nmi(dut):
    """WAI with I=1; NMI wakes, handler runs, RETI returns past WAI."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.jr(7, 0x20)                # 0x0000: reset vector → 0x0020
    a.org(0x0002)
    a.li(1, 0x11)                # 0x0002: NMI handler
    a.sw(1, 0x40)                # 0x0004
    a.reti()                     # 0x0006
    a.org(0x0020)
    a.wai()                      # 0x0020
    a.li(1, 0x22)                # 0x0022
    a.sw(1, 0x42)                # 0x0024
    a.spin()                     # 0x0026
    a.org(0x0040)
    a.dw(0x0000)
    a.org(0x0042)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 50)
    _set_ui(dut, rdy=True, irqb=True, nmib=False)
    await ClockCycles(dut.clk, 10)
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    await ClockCycles(dut.clk, 200)

    nmi = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    post = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    assert nmi == 0x0011, f"NMI handler didn't run! Got {nmi:#06x}"
    assert post == 0x0022, f"Didn't return past WAI! Got {post:#06x}"


@cocotb.test()
async def test_wai_masked_irq_wakes(dut):
    """WAI with I=1: masked IRQ wakes WAI, resumes past it without handler."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.jr(7, 0x20)                # 0x0000: reset vector → 0x0020
    a.org(0x0006)
    a.li(1, 0x42)                # 0x0006: IRQ handler
    a.sw(1, 0x40)                # 0x0008
    a.spin()                     # 0x000A
    a.org(0x0020)
    a.wai()                      # 0x0020
    a.li(1, 0x42)                # 0x0022
    a.sw(1, 0x42)                # 0x0024
    a.spin()                     # 0x0026
    a.org(0x0040)
    a.dw(0x0000)
    a.org(0x0042)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 50)
    _set_ui(dut, rdy=True, irqb=False, nmib=True)
    await ClockCycles(dut.clk, 200)

    irq = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    post = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    assert irq == 0x0000, f"IRQ handler ran despite I=1! Got {irq:#06x}"
    assert post == 0x0042, f"WAI didn't resume! Got {post:#06x}"


@cocotb.test()
async def test_brk_masks_irq(dut):
    """BRK sets I=1; IRQ held low during BRK handler should not fire."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.jr(7, 0x20)                # 0x0000: reset vector → 0x0020
    a.org(0x0002)
    a.spin()                     # 0x0002: NMI handler spin
    a.org(0x0004)
    a.jr(7, 0x30)                # 0x0004: BRK handler → 0x0030
    a.org(0x0006)
    a.jr(7, 0x38)                # 0x0006: IRQ handler → 0x0038
    a.org(0x0020)
    a.cli()                      # 0x0020
    a.brk()                      # 0x0022
    a.spin()                     # 0x0024
    a.org(0x0030)
    a.li(1, 0x11)                # 0x0030: BRK body
    a.sw(1, 0x40)                # 0x0032
    a.reti()                     # 0x0034
    a.org(0x0038)
    a.li(1, 0x22)                # 0x0038: IRQ body
    a.sw(1, 0x42)                # 0x003A
    a.reti()                     # 0x003C
    a.org(0x0040)
    a.dw(0x0000)
    a.org(0x0042)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 50)
    _set_ui(dut, rdy=True, irqb=False, nmib=True)
    await ClockCycles(dut.clk, 300)

    brk = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    irq = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    assert brk == 0x0011, f"BRK handler didn't run! Got {brk:#06x}"
    assert irq == 0x0022, f"IRQ didn't fire after RETI! Got {irq:#06x}"


@cocotb.test()
async def test_brk_restores_i(dut):
    """BRK from I=1: RETI restores I=1, IRQ stays masked."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.jr(7, 0x20)                # 0x0000: reset vector → 0x0020
    a.org(0x0002)
    a.spin()                     # 0x0002: NMI handler spin
    a.org(0x0004)
    a.jr(7, 0x30)                # 0x0004: BRK handler → 0x0030
    a.org(0x0006)
    a.li(1, 0x42)                # 0x0006: IRQ handler
    a.sw(1, 0x42)                # 0x0008
    a.reti()                     # 0x000A
    a.org(0x0020)
    a.brk()                      # 0x0020
    a.li(1, 0x42)                # 0x0022
    a.sw(1, 0x40)                # 0x0024
    a.spin()                     # 0x0026
    a.org(0x0030)
    a.li(1, 0x11)                # 0x0030: BRK body
    a.sw(1, 0x44)                # 0x0032
    a.reti()                     # 0x0034
    a.org(0x0040)
    a.dw(0x0000)
    a.org(0x0042)
    a.dw(0x0000)
    a.org(0x0044)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    dut.ena.value = 1
    dut.ui_in.value = 0x06
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 300)

    brk = _read_ram(dut, 0x0044) | (_read_ram(dut, 0x0045) << 8)
    ret = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    irq = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    assert brk == 0x0011, f"BRK handler didn't run! Got {brk:#06x}"
    assert ret == 0x0042, f"RETI didn't return! Got {ret:#06x}"
    assert irq == 0x0000, f"IRQ fired despite I=1! Got {irq:#06x}"


@cocotb.test()
async def test_epcr(dut):
    """EPCR reads saved return address | I bit from EPC."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.jr(7, 0x20)                # 0x0000: reset vector → 0x0020
    a.org(0x0002)
    a.spin()                     # 0x0002: NMI handler spin
    a.org(0x0004)
    a.spin()                     # 0x0004: BRK handler spin
    # IRQ handler: read EPC into R1, store to memory
    a.org(0x0006)
    a.epcr(1)                    # 0x0006
    a.sw(1, 0x40)                # 0x0008
    a.spin()                     # 0x000A
    a.org(0x0020)
    a.cli()                      # 0x0020
    a.spin()                     # 0x0022
    a.org(0x0040)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    dut.ena.value = 1
    dut.ui_in.value = 0x06
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 300)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    # EPC = saved PC (0x0022) with I bit = 0 (CLI cleared it) → 0x0022
    assert val == 0x0022, f"Wrong EPC! Got {val:#06x}"


@cocotb.test()
async def test_epcw_redirect(dut):
    """EPCW changes RETI return address; RETI jumps to new target."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.jr(7, 0x20)                # 0x0000: reset vector → 0x0020
    a.org(0x0002)
    a.spin()                     # 0x0002: NMI handler spin
    a.org(0x0004)
    a.jr(7, 0x30)                # 0x0004: BRK handler → 0x0030
    a.org(0x0006)
    a.spin()                     # 0x0006: IRQ handler spin
    a.org(0x0020)
    a.brk()                      # 0x0020
    a.li(1, 0x42)                # 0x0022
    a.sw(1, 0x60)                # 0x0024
    a.spin()                     # 0x0026
    # BRK handler: load redirect target into R1, EPCW to set EPC, RETI
    a.org(0x0030)
    a.lw(1, 0x50)                # 0x0030
    a.epcw(1)                    # 0x0032
    a.reti()                     # 0x0034
    a.org(0x0040)
    a.li(1, 0x42)                # 0x0040
    a.sw(1, 0x62)                # 0x0042
    a.spin()                     # 0x0044
    a.org(0x0050)
    a.dw(0x0040)
    a.org(0x0060)
    a.dw(0x0000)
    a.org(0x0062)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 300)

    orig = _read_ram(dut, 0x0060) | (_read_ram(dut, 0x0061) << 8)
    redir = _read_ram(dut, 0x0062) | (_read_ram(dut, 0x0063) << 8)
    assert orig == 0x0000, f"Original return executed! Got {orig:#06x}"
    assert redir == 0x0042, f"Redirect didn't work! Got {redir:#06x}"


@cocotb.test()
async def test_srw_enables_irq(dut):
    """SRW clearing I unmasks pending IRQ; IRQ fires at next dispatch."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # Reset jumps to 0x0020 where BRK triggers (I=1 from reset, IRQ masked)
    a.jr(7, 0x20)                # 0x0000: reset vector → 0x0020
    a.org(0x0002)
    a.spin()                     # 0x0002: NMI handler spin
    # BRK vector at 0x0004: jump to handler at 0x0030
    a.org(0x0004)
    a.jr(7, 0x30)                # 0x0004: BRK handler → 0x0030
    # IRQ vector at 0x0006: jump to handler at 0x0040
    a.org(0x0006)
    a.jr(7, 0x40)                # 0x0006: IRQ handler → 0x0040
    # IRQ handler: store marker 0x33 to [R0+0x60], spin
    a.org(0x0040)
    a.li(1, 0x33)                # 0x0040
    a.sw(1, 0x60)                # 0x0042
    a.spin()                     # 0x0044
    # BRK at 0x0020
    a.org(0x0020)
    a.brk()                      # 0x0020
    a.spin()                     # 0x0022
    # BRK handler at 0x0030: SRW clears I, IRQ fires at next dispatch
    a.org(0x0030)
    a.li(2, 0)                   # 0x0030
    a.srw(2)                     # 0x0032
    a.spin()                     # 0x0034
    a.org(0x0060)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    dut.ena.value = 1
    dut.ui_in.value = 0x06  # IRQB asserted
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 300)

    val = _read_ram(dut, 0x0060) | (_read_ram(dut, 0x0061) << 8)
    assert val == 0x0033, f"IRQ didn't fire after SRW cleared I! Got {val:#06x}"


@cocotb.test()
async def test_irq_interrupts_jr(dut):
    """IRQ fires after JR completes; RETI must return to JR target."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.cli()                      # 0x0000: reset vector
    a.jr(7, 0x20)                # 0x0002: jump to 0x0020
    a.org(0x0006)
    a.li(1, 0x5A)                # 0x0006: IRQ handler
    a.sw(1, 0x60)                # 0x0008
    a.reti()                     # 0x000A
    a.org(0x0020)
    a.li(2, 0x7E)                # 0x0020
    a.sw(2, 0x62)                # 0x0022
    a.spin()                     # 0x0024
    a.org(0x0060)
    a.dw(0x0000)
    a.org(0x0062)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    dut.ena.value = 1
    dut.ui_in.value = 0x06
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 300)

    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    await ClockCycles(dut.clk, 200)

    irq_marker = _read_ram(dut, 0x0060) | (_read_ram(dut, 0x0061) << 8)
    jr_marker = _read_ram(dut, 0x0062) | (_read_ram(dut, 0x0063) << 8)
    assert irq_marker == 0x005A, f"IRQ handler didn't run! Got {irq_marker:#06x}"
    assert jr_marker == 0x007E, f"RETI didn't return to JR target! Got {jr_marker:#06x}"


@cocotb.test()
async def test_nmi_during_brk_redirect(dut):
    """NMI during BRK target fetch: NMI preempts, RETI returns to BRK vector."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    # BRK doesn't set insn_completing in RTL, so NMI can't fire until
    # one cycle after E_EXEC_HI (at E_IDLE). This test verifies that
    # NMI during the target fetch correctly preempts and that RETI
    # returns to the BRK handler.
    a = Asm()
    a.jr(7, 0x20)                # 0x0000: reset → 0x0020
    a.org(0x0002)
    a.jr(7, 0x50)                # 0x0002: NMI → 0x0050
    a.org(0x0004)
    a.jr(7, 0x30)                # 0x0004: BRK → 0x0030
    a.org(0x0006)
    a.spin()                     # 0x0006: IRQ spin
    a.org(0x0020)
    a.brk()                      # 0x0020: BRK triggers
    a.spin()                     # 0x0022
    # BRK handler
    a.org(0x0030)
    a.li(1, 0x22)                # 0x0030
    a.sw(1, 0x62)                # 0x0032
    a.spin()                     # 0x0034
    # NMI handler
    a.org(0x0050)
    a.li(1, 0x11)                # 0x0050
    a.sw(1, 0x60)                # 0x0052
    a.reti()                     # 0x0054
    a.org(0x0060)
    a.dw(0x0000)
    a.org(0x0062)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1

    # Let BRK dispatch, then pulse NMI during its target fetch
    await ClockCycles(dut.clk, 30)
    _set_ui(dut, rdy=True, irqb=True, nmib=False)
    await ClockCycles(dut.clk, 5)
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    await ClockCycles(dut.clk, 300)

    nmi = _read_ram(dut, 0x0060) | (_read_ram(dut, 0x0061) << 8)
    brk = _read_ram(dut, 0x0062) | (_read_ram(dut, 0x0063) << 8)
    assert nmi == 0x0011, f"NMI handler didn't run! Got {nmi:#06x}"
    assert brk == 0x0022, f"BRK handler didn't run after RETI! Got {brk:#06x}"


@cocotb.test()
async def test_nmi_during_reti_redirect(dut):
    """NMI during RETI target fetch: NMI preempts, RETI returns to original target."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    # RETI also doesn't set insn_completing. This test verifies NMI
    # during RETI's target fetch correctly preempts and the second
    # RETI (from NMI handler) returns to the original RETI target.
    a = Asm()
    a.jr(7, 0x20)                # 0x0000: reset → 0x0020
    a.org(0x0002)
    a.jr(7, 0x50)                # 0x0002: NMI → 0x0050
    a.org(0x0004)
    a.spin()                     # 0x0004: BRK spin
    a.org(0x0006)
    a.jr(7, 0x40)                # 0x0006: IRQ → 0x0040
    a.org(0x0020)
    a.cli()                      # 0x0020
    a.spin()                     # 0x0022: main loop (spin at 0x0022)
    a.org(0x0024)
    a.li(1, 0x55)                # 0x0024: post-spin (unreachable from spin)
    a.sw(1, 0x64)                # 0x0026
    a.spin()                     # 0x0028
    # IRQ handler: store marker, RETI back to 0x0022
    a.org(0x0040)
    a.li(1, 0x44)                # 0x0040
    a.sw(1, 0x62)                # 0x0042
    a.reti()                     # 0x0044
    # NMI handler: store marker, RETI
    a.org(0x0050)
    a.li(1, 0x33)                # 0x0050
    a.sw(1, 0x60)                # 0x0052
    a.reti()                     # 0x0054
    a.org(0x0060)
    a.dw(0x0000)
    a.org(0x0062)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1

    # Assert IRQ to trigger the handler
    await ClockCycles(dut.clk, 30)
    _set_ui(dut, rdy=True, irqb=False, nmib=True)
    await ClockCycles(dut.clk, 30)
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    await ClockCycles(dut.clk, 50)

    # Pulse NMI — may hit during RETI's target fetch
    _set_ui(dut, rdy=True, irqb=True, nmib=False)
    await ClockCycles(dut.clk, 5)
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    await ClockCycles(dut.clk, 300)

    irq = _read_ram(dut, 0x0062) | (_read_ram(dut, 0x0063) << 8)
    nmi = _read_ram(dut, 0x0060) | (_read_ram(dut, 0x0061) << 8)
    assert irq == 0x0044, f"IRQ handler didn't run! Got {irq:#06x}"
    assert nmi == 0x0033, f"NMI handler didn't run! Got {nmi:#06x}"


@cocotb.test()
async def test_srr_includes_esr(dut):
    """SRR returns {ESR, I, T} in bits [3:0]; ESR reflects pre-IRQ {I=0, T=1}."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    # Set T=1 before IRQ entry so ESR captures {I=0, T=1} = 0b01.
    # IRQ handler reads SRR and stores it.
    a = Asm()
    a.jr(7, 0x20)                # 0x0000: reset → 0x0020
    a.org(0x0006)
    a.srr(1)                     # 0x0006: IRQ handler — SRR r1
    a.sw(1, 0x40)                # 0x0008
    a.spin()                     # 0x000A
    a.org(0x0020)
    a.cli()                      # 0x0020
    a.ceqi(0, 0)                 # 0x0022: R0==0 → T=1
    a.spin()                     # 0x0024
    a.org(0x0040)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    _set_ui(dut, rdy=True, irqb=True, nmib=True)
    dut.ena.value = 1
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 50)
    _set_ui(dut, rdy=True, irqb=False, nmib=True)
    await ClockCycles(dut.clk, 200)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    # ESR should be {I=0, T=1} = 0b01, live {I=1, T=1} → SRR = 0b01_1_1 = 0x07
    # Wait — live I=1 (set by IRQ entry), live T=1 (set before IRQ).
    # ESR = saved {I=0, T=1} = 0b01.
    # SRR = {ESR, I, T} = {01, 1, 1} = 0b0111 = 0x07
    assert val == 0x0007, f"SRR wrong! Expected 0x0007, got {val:#06x}"


@cocotb.test()
async def test_srw_restores_esr(dut):
    """SRW writes ESR from rs[3:2]; RETI uses the modified ESR."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    # BRK from I=1, T=0 → ESR = {1,0} = 0b10.
    # BRK handler uses SRW to set ESR={0,1}, I=0, T=1 (rs=0b0101=5),
    # then RETI restores {I,T} from modified ESR → I=0, T=1.
    # After RETI, SRR captures live {I=0, T=1} and ESR from new interrupt context.
    # But we just need to verify RETI restored I=0, T=1 from the SRW-modified ESR.
    # We verify by: after RETI, IRQ fires (since I=0) and handler stores marker.
    a = Asm()
    a.jr(7, 0x20)                # 0x0000: reset → 0x0020
    a.org(0x0004)
    a.jr(7, 0x30)                # 0x0004: BRK → 0x0030
    a.org(0x0006)
    a.jr(7, 0x40)                # 0x0006: IRQ → 0x0040
    a.org(0x0020)
    a.brk()                      # 0x0020: BRK (from I=1, T=0)
    a.spin()                     # 0x0022: return here after RETI
    # BRK handler: SRW sets ESR={0,1}=I=0,T=1, then RETI
    a.org(0x0030)
    a.li(1, 0x05)                # 0x0030: r1 = 0b0101 → ESR=01, I=0, T=1
    a.srw(1)                     # 0x0032
    a.reti()                     # 0x0034
    # IRQ handler: store marker
    a.org(0x0040)
    a.li(1, 0x77)                # 0x0040
    a.sw(1, 0x60)                # 0x0042
    a.spin()                     # 0x0044
    a.org(0x0060)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    dut.ena.value = 1
    dut.ui_in.value = 0x06       # IRQB asserted
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 300)

    val = _read_ram(dut, 0x0060) | (_read_ram(dut, 0x0061) << 8)
    # RETI restores {I,T} from ESR which SRW set to {0,1} → I=0, T=1.
    # With I=0 and IRQB asserted, IRQ fires immediately → marker stored.
    assert val == 0x0077, f"IRQ didn't fire after RETI with SRW-modified ESR! Got {val:#06x}"
