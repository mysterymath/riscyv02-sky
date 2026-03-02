# SPDX-FileCopyrightText: © 2024 mysterymath
# SPDX-License-Identifier: Apache-2.0
#
# ALU, logic, shift, comparison, and immediate tests.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
from test_helpers import *


@cocotb.test()
async def test_add_basic(dut):
    """ADD rd, rs1, rs2 basic addition."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 5)
    a.li(2, 3)
    a.add(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 8, f"Expected 8, got {val}"


@cocotb.test()
async def test_sub_basic(dut):
    """SUB rd, rs1, rs2 basic subtraction."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 10)
    a.li(2, 3)
    a.sub(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 7, f"Expected 7, got {val}"


@cocotb.test()
async def test_li_basic(dut):
    """LI rd, imm9 with positive and negative values."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 42)
    a.sw(1, 0x40)
    a.li(2, -5)
    a.sw(2, 0x42)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    v1 = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    v2 = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    assert v1 == 42, f"Expected 42, got {v1}"
    assert v2 == 0xFFFB, f"Expected 0xFFFB, got {v2:#06x}"


@cocotb.test()
async def test_addi_basic(dut):
    """ADDI rd, imm9 adds immediate to register."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 100)
    a.addi(1, 50)
    a.sw(1, 0x40)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 150, f"Expected 150, got {val}"


@cocotb.test()
async def test_logic_imm(dut):
    """ANDI, ORI, XORI with 8-bit immediates (ANDI/ORI zext, XORI sext)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 0x7F)
    a.andi(1, 0x0F)
    a.sw(1, 0x40)
    a.li(2, 0x10)
    a.ori(2, 0x03)
    a.sw(2, 0x42)
    a.li(3, 0x55)
    a.xori(3, 0x0F)
    a.sw(3, 0x44)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)

    v1 = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    v2 = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    v3 = _read_ram(dut, 0x0044) | (_read_ram(dut, 0x0045) << 8)
    assert v1 == 0x000F, f"ANDI: expected 0x000F, got {v1:#06x}"
    assert v2 == 0x0013, f"ORI: expected 0x0013, got {v2:#06x}"
    assert v3 == 0x005A, f"XORI: expected 0x005A, got {v3:#06x}"


@cocotb.test()
async def test_lui(dut):
    """LUI: rd = imm8 << 8."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lui(1, 1)
    a.sw(1, 0x40)
    a.lui(2, -1)
    a.sw(2, 0x42)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    v1 = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    v2 = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    assert v1 == 0x0100, f"LUI 1: expected 0x0100, got {v1:#06x}"
    assert v2 == 0xFF00, f"LUI -1: expected 0xFF00, got {v2:#06x}"


@cocotb.test()
async def test_shifts(dut):
    """SLLI, SRLI, SRAI basic."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 1)
    a.slli(1, 4)
    a.sw(1, 0x40)
    a.li(2, 0x40)
    a.slli(2, 2)
    a.srli(2, 4)
    a.sw(2, 0x42)
    a.li(3, -16)
    a.srai(3, 2)
    a.sw(3, 0x44)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 400)

    v1 = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    v2 = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    v3 = _read_ram(dut, 0x0044) | (_read_ram(dut, 0x0045) << 8)
    assert v1 == 16, f"SLLI 1<<4: expected 16, got {v1}"
    assert v2 == 0x10, f"SRLI 0x100>>4: expected 0x10, got {v2:#06x}"
    assert v3 == 0xFFFC, f"SRAI -16>>2: expected 0xFFFC, got {v3:#06x}"


@cocotb.test()
async def test_clt_cltu(dut):
    """CLT and CLTU comparisons (T-flag + read_t)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 5)
    a.li(2, 10)
    a.clt(1, 2)
    a.read_t(3)
    a.sw(3, 0x40)
    a.clt(2, 1)
    a.read_t(4)
    a.sw(4, 0x42)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)

    v1 = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    v2 = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    assert v1 == 1, f"CLT 5<10: expected 1, got {v1}"
    assert v2 == 0, f"CLT 10<5: expected 0, got {v2}"


@cocotb.test()
async def test_auipc(dut):
    """AUIPC: rd = pc + (imm8 << 8)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.auipc(1, 0)
    a.sw(1, 0x40)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)

    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0002, f"AUIPC 0: expected 0x0002, got {val:#06x}"


@cocotb.test()
async def test_clti_cltui_ceqi(dut):
    """CLTI, CLTUI, CEQI all set T flag; read_t reads T into a register."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(2, 5)
    a.clti(2, 10)
    a.read_t(1)
    a.sw_s(1, 0x40)
    a.clti(2, 3)
    a.read_t(1)
    a.sw_s(1, 0x42)
    a.ceqi(2, 5)
    a.read_t(1)
    a.sw_s(1, 0x44)
    a.ceqi(2, 3)
    a.read_t(1)
    a.sw_s(1, 0x46)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 400)

    v1 = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    v2 = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    v3 = _read_ram(dut, 0x0044) | (_read_ram(dut, 0x0045) << 8)
    v4 = _read_ram(dut, 0x0046) | (_read_ram(dut, 0x0047) << 8)
    assert v1 == 1, f"CLTI 5<10: expected 1, got {v1}"
    assert v2 == 0, f"CLTI 5<3: expected 0, got {v2}"
    assert v3 == 1, f"CEQI 5==5: expected T=1, got {v3}"
    assert v4 == 0, f"CEQI 5==3: expected T=0, got {v4}"


@cocotb.test()
async def test_shift_rr(dut):
    """SLL, SRL, SRA with register shift amounts."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 1)
    a.li(2, 4)
    a.sll(3, 1, 2)
    a.sw(3, 0x40)
    a.li(4, 1)
    a.slli(4, 8)
    a.srl(5, 4, 2)
    a.sw(5, 0x42)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)

    v1 = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    v2 = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    assert v1 == 16, f"SLL 1<<4: expected 16, got {v1}"
    assert v2 == 0x10, f"SRL 0x100>>4: expected 0x10, got {v2:#06x}"


# ===========================================================================
# Corner cases
# ===========================================================================

@cocotb.test()
async def test_sub_borrow(dut):
    """SUB with borrow across 16 bits."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 1)
    a.li(2, 2)
    a.sub(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0xFFFF, f"Expected 0xFFFF, got {val:#06x}"


@cocotb.test()
async def test_addi_negative(dut):
    """ADDI with negative immediate."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 10)
    a.addi(1, -3)
    a.sw(1, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 7, f"ADDI -3 failed! Got {val}"


@cocotb.test()
async def test_addi_overflow(dut):
    """ADDI overflow wraps at 16 bits."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x30)
    a.addi(1, 3)
    a.sw(1, 0x40)
    a.spin()
    # Data setup
    a.org(0x30)
    a.db(0xFE, 0xFF)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0001, f"ADDI overflow! Got {val:#06x}"


@cocotb.test()
async def test_lui_negative(dut):
    """LUI with negative imm8: (-1 & 0xFF) << 8 = 0xFF00."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lui(1, -1)
    a.sw(1, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0xFF00, f"LUI -1 failed! Got {val:#06x}"


@cocotb.test()
async def test_lui_zero(dut):
    """LUI with imm8=0: result = 0x0000."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 0x42)
    a.lui(1, 0)
    a.sw(1, 0x40)
    a.spin()
    # Pre-fill output area with non-zero to detect no-write
    a.org(0x40)
    a.db(0xFF, 0xFF)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0000, f"LUI 0 failed! Got {val:#06x}"


@cocotb.test()
async def test_sll_by_8(dut):
    """SLL by 8: crosses byte boundary."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 0x2B)
    a.li(2, 8)
    a.sll(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x2B00, f"SLL by 8 failed! Got {val:#06x}"


@cocotb.test()
async def test_sra_negative(dut):
    """SRA preserves sign bit for negative numbers."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x30)
    a.li(2, 4)
    a.sra(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()
    # Data setup
    a.org(0x30)
    a.db(0x00, 0xFF)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0xFFF0, f"SRA negative failed! Got {val:#06x}"


@cocotb.test()
async def test_slli_by_8(dut):
    """SLLI by 8 crosses byte boundary."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 0x2B)
    a.slli(1, 8)
    a.sw(1, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x2B00, f"SLLI by 8 failed! Got {val:#06x}"


@cocotb.test()
async def test_srai_negative(dut):
    """SRAI preserves sign for negative numbers."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x30)
    a.srai(1, 4)
    a.sw(1, 0x40)
    a.spin()
    # Data setup
    a.org(0x30)
    a.db(0x00, 0x80)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0xF800, f"SRAI negative failed! Got {val:#06x}"


@cocotb.test()
async def test_li_negative(dut):
    """LI with negative immediate: sext(-1) = 0xFFFF."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, -1)
    a.sw(1, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0xFFFF, f"LI -1 failed! Got {val:#06x}"


@cocotb.test()
async def test_alu_same_reg(dut):
    """ADD rd, rs, rs with same source doubles the value."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 0x42)
    a.add(2, 1, 1)
    a.sw(2, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0084, f"ADD same reg failed! Got {val:#06x}"


@cocotb.test()
async def test_and_basic(dut):
    """AND R3, R1, R2: 0xFF0F & 0x0FFF = 0x0F0F."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.lw(2, 0x12)
    a.and_(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0x0F, 0xFF)
    a.org(0x12)
    a.db(0xFF, 0x0F)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0F0F, f"Expected 0x0F0F, got {val:#06x}"


@cocotb.test()
async def test_or_basic(dut):
    """OR R3, R1, R2: 0xF000 | 0x00F0 = 0xF0F0."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.lw(2, 0x12)
    a.or_(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0x00, 0xF0)
    a.org(0x12)
    a.db(0xF0, 0x00)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0xF0F0, f"Expected 0xF0F0, got {val:#06x}"


@cocotb.test()
async def test_xor_basic(dut):
    """XOR R3, R1, R2: 0xFFFF ^ 0xAAAA = 0x5555."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.lw(2, 0x12)
    a.xor(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0xFF, 0xFF)
    a.org(0x12)
    a.db(0xAA, 0xAA)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x5555, f"Expected 0x5555, got {val:#06x}"


@cocotb.test()
async def test_clt_equal(dut):
    """CLT: 5 < 5 -> T=0."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 5)
    a.li(2, 5)
    a.clt(1, 2)
    a.read_t(3)
    a.sw(3, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0000, f"Expected 0x0000, got {val:#06x}"


@cocotb.test()
async def test_clt_negative(dut):
    """CLT: -5 < 5 -> T=1 (signed)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, -5)
    a.li(2, 5)
    a.clt(1, 2)
    a.read_t(3)
    a.sw(3, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0001, f"Expected 0x0001, got {val:#06x}"


@cocotb.test()
async def test_clt_negative_false(dut):
    """CLT: 5 < -5 -> T=0 (signed)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 5)
    a.li(2, -5)
    a.clt(1, 2)
    a.read_t(3)
    a.sw(3, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0000, f"Expected 0x0000, got {val:#06x}"


@cocotb.test()
async def test_cltu_true(dut):
    """CLTU: 5 <u 10 -> T=1."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 5)
    a.li(2, 10)
    a.cltu(1, 2)
    a.read_t(3)
    a.sw(3, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0001, f"Expected 0x0001, got {val:#06x}"


@cocotb.test()
async def test_cltu_false(dut):
    """CLTU: 10 <u 5 -> T=0."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 10)
    a.li(2, 5)
    a.cltu(1, 2)
    a.read_t(3)
    a.sw(3, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0000, f"Expected 0x0000, got {val:#06x}"


@cocotb.test()
async def test_cltu_large(dut):
    """CLTU: 5 <u 0xFFFF -> T=1."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 5)
    a.li(2, -1)
    a.cltu(1, 2)
    a.read_t(3)
    a.sw(3, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0001, f"Expected 0x0001, got {val:#06x}"


@cocotb.test()
async def test_cltu_large_reverse(dut):
    """CLTU: 0xFFFF <u 5 -> T=0."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, -1)
    a.li(2, 5)
    a.cltu(1, 2)
    a.read_t(3)
    a.sw(3, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0000, f"Expected 0x0000, got {val:#06x}"


@cocotb.test()
async def test_li_zero(dut):
    """LI R1, 0 -> 0x0000."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 42)
    a.li(1, 0)
    a.sw(1, 0x40)
    a.spin()
    # Pre-fill output area with non-zero to detect no-write
    a.org(0x40)
    a.db(0xFF, 0xFF)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0000, f"Expected 0x0000, got {val:#06x}"


@cocotb.test()
async def test_andi_all_ones(dut):
    """ANDI R1, 0x0F: 0xABCD & 0x000F = 0x000D (zext imm8)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.andi(1, 0x0F)
    a.sw(1, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0xCD, 0xAB)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x000D, f"Expected 0x000D, got {val:#06x}"


@cocotb.test()
async def test_ori_all_ones(dut):
    """ORI R1, 0x0F: 0x1234 | 0x000F = 0x123F (zext imm8)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.ori(1, 0x0F)
    a.sw(1, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0x34, 0x12)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x123F, f"Expected 0x123F, got {val:#06x}"


@cocotb.test()
async def test_xori_all_ones(dut):
    """XORI R1, 0x0F: 0x1234 ^ 0x000F = 0x123B (sext imm8)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.xori(1, 0x0F)
    a.sw(1, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0x34, 0x12)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x123B, f"Expected 0x123B, got {val:#06x}"


@cocotb.test()
async def test_clti_negative(dut):
    """CLTI: -2 < -1 -> T=1 (signed compare)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, -2)
    a.clti(1, -1)
    a.read_t(2)
    a.sw_s(2, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0001, f"Expected 0x0001, got {val:#06x}"


@cocotb.test()
async def test_clti_equal(dut):
    """CLTI: 5 < 5 -> T=0."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 5)
    a.clti(1, 5)
    a.read_t(2)
    a.sw_s(2, 0x40)
    a.spin()
    # Pre-fill output area with non-zero to detect no-write
    a.org(0x40)
    a.db(0xFF, 0xFF)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0000, f"Expected 0x0000, got {val:#06x}"


@cocotb.test()
async def test_cltui_true(dut):
    """CLTUI: 5 <u 10 -> T=1."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 5)
    a.cltui(1, 10)
    a.read_t(2)
    a.sw_s(2, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0001, f"Expected 0x0001, got {val:#06x}"


@cocotb.test()
async def test_cltui_false(dut):
    """CLTUI: 0xFFFF <u zext(3)=3 -> T=0."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, -1)
    a.cltui(1, 3)
    a.read_t(2)
    a.sw_s(2, 0x40)
    a.spin()
    # Pre-fill output area with non-zero to detect no-write
    a.org(0x40)
    a.db(0xFF, 0xFF)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0000, f"Expected 0x0000, got {val:#06x}"


@cocotb.test()
async def test_ceqi_equality(dut):
    """CEQI: 5 == 5 -> T=1 (equality test)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 5)
    a.ceqi(1, 5)
    a.read_t(2)
    a.sw_s(2, 0x40)
    a.spin()
    # Pre-fill output area with non-zero to detect no-write
    a.org(0x40)
    a.db(0xFF, 0xFF)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0001, f"Expected 0x0001, got {val:#06x}"


@cocotb.test()
async def test_sll_by_zero(dut):
    """SLL: 0xABCD << 0 = 0xABCD (identity)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.li(2, 0)
    a.sll(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0xCD, 0xAB)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0xABCD, f"Expected 0xABCD, got {val:#06x}"


@cocotb.test()
async def test_sll_by_15(dut):
    """SLL: 0x0001 << 15 = 0x8000."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 1)
    a.li(2, 15)
    a.sll(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x8000, f"Expected 0x8000, got {val:#06x}"


@cocotb.test()
async def test_sll_cross_byte(dut):
    """SLL: 0x0037 << 9 = 0x6E00 (crosses byte boundary)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.li(1, 0x37)
    a.li(2, 9)
    a.sll(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x6E00, f"Expected 0x6E00, got {val:#06x}"


@cocotb.test()
async def test_srl_by_zero(dut):
    """SRL: 0xABCD >> 0 = 0xABCD (identity)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.li(2, 0)
    a.srl(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0xCD, 0xAB)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0xABCD, f"Expected 0xABCD, got {val:#06x}"


@cocotb.test()
async def test_srl_by_8(dut):
    """SRL: 0xAB00 >> 8 = 0x00AB."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.li(2, 8)
    a.srl(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0x00, 0xAB)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x00AB, f"Expected 0x00AB, got {val:#06x}"


@cocotb.test()
async def test_srl_by_15(dut):
    """SRL: 0x8000 >> 15 = 0x0001."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.li(2, 15)
    a.srl(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0x00, 0x80)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0001, f"Expected 0x0001, got {val:#06x}"


@cocotb.test()
async def test_sra_positive(dut):
    """SRA: 0x1234 >>s 4 = 0x0123 (positive, zero-fills)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.li(2, 4)
    a.sra(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0x34, 0x12)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0123, f"Expected 0x0123, got {val:#06x}"


@cocotb.test()
async def test_sra_by_8_negative(dut):
    """SRA: 0x8000 >>s 8 = 0xFF80 (sign extends across byte boundary)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.li(2, 8)
    a.sra(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0x00, 0x80)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0xFF80, f"Expected 0xFF80, got {val:#06x}"


@cocotb.test()
async def test_sra_by_15_negative(dut):
    """SRA: 0x8000 >>s 15 = 0xFFFF."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.li(2, 15)
    a.sra(3, 1, 2)
    a.sw(3, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0x00, 0x80)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0xFFFF, f"Expected 0xFFFF, got {val:#06x}"


@cocotb.test()
async def test_srli_by_8(dut):
    """SRLI R1, 8: 0xAB00 >> 8 = 0x00AB."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.srli(1, 8)
    a.sw(1, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0x00, 0xAB)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x00AB, f"Expected 0x00AB, got {val:#06x}"


@cocotb.test()
async def test_srai_by_15_negative(dut):
    """SRAI R1, 15: 0x8000 >>s 15 = 0xFFFF."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.srai(1, 15)
    a.sw(1, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0x00, 0x80)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0xFFFF, f"Expected 0xFFFF, got {val:#06x}"


@cocotb.test()
async def test_auipc_positive_offset(dut):
    """AUIPC with positive imm8: R1 = PC+2 + (1 << 8) = 0x0002 + 0x0100 = 0x0102."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.auipc(1, 1)
    a.sw(1, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0102, f"Expected 0x0102, got {val:#06x}"


@cocotb.test()
async def test_auipc_negative_offset(dut):
    """AUIPC at 0x0080 with imm8=-1: R1 = 0x0082 + (0xFF << 8) = 0xFF82."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.j(63)
    a.org(0x0080)
    a.auipc(2, -1)
    a.sw(2, 0x50)
    a.spin()
    # Clear output area
    a.org(0x50)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 400)
    val = _read_ram(dut, 0x0050) | (_read_ram(dut, 0x0051) << 8)
    assert val == 0xFF82, f"Expected 0xFF82, got {val:#06x}"


@cocotb.test()
async def test_auipc_with_lw(dut):
    """AUIPC + LW for PC-relative data access (primary use case)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # AUIPC R0, 0 -> R0 = 0x0002 (sets base for subsequent LW)
    a.auipc(0, 0)
    # LW R1, 0x0E -> R1 = mem16[R0+0x0E] = mem16[0x0010] = 0xBEEF
    a.lw(1, 0x0E)
    # R0 is non-zero; use SWS to store via R7
    a.sw_s(1, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0xEF, 0xBE)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0xBEEF, f"Expected 0xBEEF, got {val:#06x}"


@cocotb.test()
async def test_auipc_large_imm7(dut):
    """AUIPC with large imm8 (63): R1 = 0x0002 + (63 << 8) = 0x3F02."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.auipc(1, 63)
    a.sw(1, 0x40)
    a.spin()
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 200)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x3F02, f"Expected 0x3F02, got {val:#06x}"


@cocotb.test()
async def test_sllt(dut):
    """SLLT: shift left by 1, capture old bit 15 into T."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # R1 = 0x8001: bit 15 set, bit 0 set
    a.li(1, 1)
    a.lui(2, 0x80)
    a.or_(1, 1, 2)        # R1 = 0x8001
    a.sllt(1)            # R1 = 0x0002, T = 1 (old bit 15)
    a.sw(1, 0x40)
    a.read_t(3)
    a.sw(3, 0x42)
    # Now test with bit 15 clear
    a.li(1, 0x55)          # R1 = 0x0055
    a.sllt(1)            # R1 = 0x00AA, T = 0
    a.sw(1, 0x44)
    a.read_t(3)
    a.sw(3, 0x46)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 400)

    v1 = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    t1 = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    v2 = _read_ram(dut, 0x0044) | (_read_ram(dut, 0x0045) << 8)
    t2 = _read_ram(dut, 0x0046) | (_read_ram(dut, 0x0047) << 8)
    assert v1 == 0x0002, f"SLLT 0x8001: expected 0x0002, got {v1:#06x}"
    assert t1 == 1, f"SLLT T: expected 1, got {t1}"
    assert v2 == 0x00AA, f"SLLT 0x0055: expected 0x00AA, got {v2:#06x}"
    assert t2 == 0, f"SLLT T: expected 0, got {t2}"


@cocotb.test()
async def test_srlt(dut):
    """SRLT: shift right by 1, capture old bit 0 into T."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # R1 = 0x8001: bit 0 set
    a.li(1, 1)
    a.lui(2, 0x80)
    a.or_(1, 1, 2)        # R1 = 0x8001
    a.srlt(1)            # R1 = 0x4000, T = 1 (old bit 0)
    a.sw(1, 0x40)
    a.read_t(3)
    a.sw(3, 0x42)
    # Now test with bit 0 clear
    a.li(1, 0x44)          # R1 = 0x0044
    a.srlt(1)            # R1 = 0x0022, T = 0
    a.sw(1, 0x44)
    a.read_t(3)
    a.sw(3, 0x46)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 400)

    v1 = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    t1 = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    v2 = _read_ram(dut, 0x0044) | (_read_ram(dut, 0x0045) << 8)
    t2 = _read_ram(dut, 0x0046) | (_read_ram(dut, 0x0047) << 8)
    assert v1 == 0x4000, f"SRLT 0x8001: expected 0x4000, got {v1:#06x}"
    assert t1 == 1, f"SRLT T: expected 1, got {t1}"
    assert v2 == 0x0022, f"SRLT 0x0044: expected 0x0022, got {v2:#06x}"
    assert t2 == 0, f"SRLT T: expected 0, got {t2}"


@cocotb.test()
async def test_rlt(dut):
    """RLT: rotate left through T (old T → bit 0, old bit 15 → T)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # Set T=1 via comparison, then rotate
    a.li(1, 1)
    a.clti(1, 2)           # T = 1 (1 < 2)
    a.li(1, 0x55)          # R1 = 0x0055
    a.rlt(1)               # R1 = 0x00AB (<<1, old T=1 into bit 0), T = 0
    a.sw(1, 0x40)
    a.read_t(3)
    a.sw(3, 0x42)
    # Chain: rotate again with T=0
    a.li(1, 0x55)          # R1 = 0x0055, T=0 from above
    a.rlt(1)               # R1 = 0x00AA (<<1, old T=0 into bit 0), T = 0
    a.sw(1, 0x44)
    a.read_t(3)
    a.sw(3, 0x46)
    # Test with bit 15 set
    a.li(1, 1)
    a.lui(2, 0x80)
    a.or_(1, 1, 2)         # R1 = 0x8001, T=0
    a.rlt(1)               # R1 = 0x0002, T = 1 (old bit 15)
    a.sw(1, 0x48)
    a.read_t(3)
    a.sw(3, 0x4A)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 500)

    v1 = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    t1 = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    v2 = _read_ram(dut, 0x0044) | (_read_ram(dut, 0x0045) << 8)
    t2 = _read_ram(dut, 0x0046) | (_read_ram(dut, 0x0047) << 8)
    v3 = _read_ram(dut, 0x0048) | (_read_ram(dut, 0x0049) << 8)
    t3 = _read_ram(dut, 0x004A) | (_read_ram(dut, 0x004B) << 8)
    assert v1 == 0x00AB, f"RLT 0x0055 T=1: expected 0x00AB, got {v1:#06x}"
    assert t1 == 0, f"RLT T: expected 0, got {t1}"
    assert v2 == 0x00AA, f"RLT 0x0055 T=0: expected 0x00AA, got {v2:#06x}"
    assert t2 == 0, f"RLT T: expected 0, got {t2}"
    assert v3 == 0x0002, f"RLT 0x8001 T=0: expected 0x0002, got {v3:#06x}"
    assert t3 == 1, f"RLT T: expected 1, got {t3}"


@cocotb.test()
async def test_rrt(dut):
    """RRT: rotate right through T (old T → bit 15, old bit 0 → T)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    # Set T=1, then rotate right
    a.li(1, 1)
    a.clti(1, 2)           # T = 1
    a.li(1, 0x44)          # R1 = 0x0044
    a.rrt(1)               # R1 = 0x8022 (>>1, T=1 into bit 15), T = 0
    a.sw(1, 0x40)
    a.read_t(3)
    a.sw(3, 0x42)
    # Chain: rotate again with T=0
    a.li(1, 0x44)          # R1 = 0x0044, T=0
    a.rrt(1)               # R1 = 0x0022, T = 0
    a.sw(1, 0x44)
    a.read_t(3)
    a.sw(3, 0x46)
    # Test with bit 0 set
    a.li(1, 0x55)          # R1 = 0x0055, T=0
    a.rrt(1)               # R1 = 0x002A, T = 1 (old bit 0)
    a.sw(1, 0x48)
    a.read_t(3)
    a.sw(3, 0x4A)
    a.spin()

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 500)

    v1 = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    t1 = _read_ram(dut, 0x0042) | (_read_ram(dut, 0x0043) << 8)
    v2 = _read_ram(dut, 0x0044) | (_read_ram(dut, 0x0045) << 8)
    t2 = _read_ram(dut, 0x0046) | (_read_ram(dut, 0x0047) << 8)
    v3 = _read_ram(dut, 0x0048) | (_read_ram(dut, 0x0049) << 8)
    t3 = _read_ram(dut, 0x004A) | (_read_ram(dut, 0x004B) << 8)
    assert v1 == 0x8022, f"RRT 0x0044 T=1: expected 0x8022, got {v1:#06x}"
    assert t1 == 0, f"RRT T: expected 0, got {t1}"
    assert v2 == 0x0022, f"RRT 0x0044 T=0: expected 0x0022, got {v2:#06x}"
    assert t2 == 0, f"RRT T: expected 0, got {t2}"
    assert v3 == 0x002A, f"RRT 0x0055 T=0: expected 0x002A, got {v3:#06x}"
    assert t3 == 1, f"RRT T: expected 1, got {t3}"


@cocotb.test()
async def test_andi_byte_mask(dut):
    """ANDI R1, 0xFF: 0xABCD & zext(0xFF)=0x00FF = 0x00CD (byte mask)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.andi(1, 0xFF)
    a.sw(1, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0xCD, 0xAB)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x00CD, f"Expected 0x00CD, got {val:#06x}"


@cocotb.test()
async def test_ori_high_bit(dut):
    """ORI R1, 0x80: 0x1234 | zext(0x80)=0x0080 = 0x12B4 (no sign bleed)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.ori(1, 0x80)
    a.sw(1, 0x40)
    a.spin()
    # Data setup
    a.org(0x10)
    a.db(0x34, 0x12)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x12B4, f"Expected 0x12B4, got {val:#06x}"


@cocotb.test()
async def test_cltui_large_imm(dut):
    """CLTUI: 300 <u zext(200)=200 -> T=0 (clean unsigned compare)."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    a = Asm()
    a.lw(1, 0x10)
    a.cltui(1, 200)
    a.read_t(2)
    a.sw_s(2, 0x40)
    a.spin()
    # Data setup: 300 = 0x012C
    a.org(0x10)
    a.db(0x2C, 0x01)
    # Clear output area
    a.org(0x40)
    a.dw(0x0000)

    _load_program(dut, a.assemble())
    await _reset(dut)
    await ClockCycles(dut.clk, 300)
    val = _read_ram(dut, 0x0040) | (_read_ram(dut, 0x0041) << 8)
    assert val == 0x0000, f"Expected T=0, got {val:#06x}"
