# SPDX-FileCopyrightText: © 2024 mysterymath
# SPDX-License-Identifier: Apache-2.0
#
# Assembler library for RISCY-V02.
#
# Contains all instruction encoding functions (canonical source) and the Asm
# class for building programs with auto-advancing PC and label support.
#
# Encoding: RV32I-style 16-bit encoding
#   Fixed 5-bit opcode at [4:0], register at [7:5], sign at [15].
#   Immediates at [15:8] with sign always at ir[15].
#
#   Format  Layout (MSB→LSB)                                   Used by
#   ──────  ─────────────────────────────────────────────────   ────────────────
#   I       [imm8:8|rs/rd:3|opcode:5]                          24 instructions
#   B       [imm8:8|0:2|funct1:1|opcode:5]                     BT, BF
#   J       [s:1|imm[6:0]:7|imm[8:7]:2|funct1:1|opcode:5]     J, JAL
#   R       [funct2:2|rd:3|rs2:3|rs1:3|opcode:5]               R,R,R + R,R
#   SI      [0:1|funct3:3|shamt:4|rs/rd:3|opcode:5]            SLLI,SRLI,SRAI,SLLT,SRLT,RLT,RRT
#   SYS     [funct4:4|0:4|reg:3|opcode:5]                      11 system insns

__all__ = ['Asm']


# ===========================================================================
# Encoding helpers — RV32I-style 16-bit encoding
# ===========================================================================

# I-type: [imm8:8 @ 15:8][rs/rd:3 @ 7:5][opcode:5 @ 4:0]
def _encode_i(opcode, imm8, reg):
    insn = ((imm8 & 0xFF) << 8) | ((reg & 0x7) << 5) | (opcode & 0x1F)
    return (insn & 0xFF, (insn >> 8) & 0xFF)

# B-type: [imm8:8 @ 15:8][0:2 @ 7:6][funct1:1 @ 5][opcode:5 @ 4:0]  opcode=24
def _encode_b(funct1, imm8):
    insn = ((imm8 & 0xFF) << 8) | ((funct1 & 0x1) << 5) | 24
    return (insn & 0xFF, (insn >> 8) & 0xFF)

# J-type: [s:1 @ 15][imm[6:0]:7 @ 14:8][imm[8:7]:2 @ 7:6][funct1:1 @ 5][opcode:5 @ 4:0]
def _encode_j(funct1, imm10):
    imm10 &= 0x3FF
    sign = (imm10 >> 9) & 1
    imm_lo = imm10 & 0x7F            # imm[6:0] → ir[14:8]
    imm_hi = (imm10 >> 7) & 0x3      # imm[8:7] → ir[7:6]
    insn = (sign << 15) | (imm_lo << 8) | (imm_hi << 6) | ((funct1 & 1) << 5) | 25
    return (insn & 0xFF, (insn >> 8) & 0xFF)

# R-type: [funct2:2 @ 15:14][rd:3 @ 13:11][rs2:3 @ 10:8][rs1:3 @ 7:5][opcode:5 @ 4:0]
def _encode_r(opcode, funct2, rd, rs2, rs1):
    insn = ((funct2 & 0x3) << 14) | ((rd & 0x7) << 11) | ((rs2 & 0x7) << 8) \
         | ((rs1 & 0x7) << 5) | (opcode & 0x1F)
    return (insn & 0xFF, (insn >> 8) & 0xFF)

# SI-type: [funct3:3 @ 15:13][0:1 @ 12][shamt:4 @ 11:8][rs/rd:3 @ 7:5][opcode:5 @ 4:0]
def _encode_si(funct3, shamt, reg):
    insn = ((funct3 & 0x7) << 13) | ((shamt & 0xF) << 8) | ((reg & 0x7) << 5) | 30
    return (insn & 0xFF, (insn >> 8) & 0xFF)

# SYS-type: [funct4:4 @ 15:12][0:4 @ 11:8][reg:3 @ 7:5][opcode:5 @ 4:0]  opcode=31
def _encode_sys(funct4, reg=0):
    insn = ((funct4 & 0xF) << 12) | ((reg & 0x7) << 5) | 31
    return (insn & 0xFF, (insn >> 8) & 0xFF)


# ---------------------------------------------------------------------------
# I-type instructions (opcode 0-23)
# ---------------------------------------------------------------------------

def _encode_addi(rd, imm):
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(0, imm, rd)

def _encode_li(rd, imm):
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(1, imm, rd)

def _encode_lw(rd, imm):
    """LW: rd = mem16[R0 + sext(imm)]. Base is R0."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(2, imm, rd)

def _encode_lb(rd, imm):
    """LB: rd = sext(mem[R0 + sext(imm)]). Base is R0."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(3, imm, rd)

def _encode_lbu(rd, imm):
    """LBU: rd = zext(mem[R0 + sext(imm)]). Base is R0."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(4, imm, rd)

def _encode_sw(rs, imm):
    """SW: mem16[R0 + sext(imm)] = rs. Base is R0."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(5, imm, rs)

def _encode_sb(rs, imm):
    """SB: mem[R0 + sext(imm)] = rs[7:0]. Base is R0."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(6, imm, rs)

def _encode_jr(rs, imm):
    """JR: pc = rs + sext(imm). Byte offset, no shift."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(7, imm, rs)

def _encode_jalr(rs, imm):
    """JALR: R6=pc+2; pc = rs + sext(imm). Byte offset, no shift."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(8, imm, rs)

def _encode_andi(rd, imm):
    """ANDI: rd = rd & zext(imm8). Immediate is zero-extended."""
    assert -128 <= imm <= 255, f"imm out of range: {imm}"
    return _encode_i(9, imm, rd)

def _encode_ori(rd, imm):
    """ORI: rd = rd | zext(imm8). Immediate is zero-extended."""
    assert -128 <= imm <= 255, f"imm out of range: {imm}"
    return _encode_i(10, imm, rd)

def _encode_xori(rd, imm):
    """XORI: rd = rd ^ sext(imm8). All immediates sign-extended."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(11, imm, rd)

def _encode_clti(rs, imm):
    """CLTI: T = (rs < sext(imm)). Signed comparison, sets T flag."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(12, imm, rs)

def _encode_cltui(rs, imm):
    """CLTUI: T = (rs <u zext(imm)). Unsigned comparison, sets T flag."""
    assert -128 <= imm <= 255, f"imm out of range: {imm}"
    return _encode_i(13, imm, rs)

def _encode_bz(rs, imm):
    """BZ: if rs == 0, pc += sext(imm8) << 1. Half-word offset."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(14, imm, rs)

def _encode_bnz(rs, imm):
    """BNZ: if rs != 0, pc += sext(imm8) << 1. Half-word offset."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(15, imm, rs)

def _encode_ceqi(rs, imm):
    """CEQI: T = (rs == sext(imm)). Equality comparison, sets T flag."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(16, imm, rs)

def _encode_lw_s(rd, imm):
    """LWS: rd = mem16[R7 + sext(imm)]. Base is R7 (SP)."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(17, imm, rd)

def _encode_lb_s(rd, imm):
    """LBS: rd = sext(mem[R7 + sext(imm)]). Base is R7 (SP)."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(18, imm, rd)

def _encode_lbu_s(rd, imm):
    """LBUS: rd = zext(mem[R7 + sext(imm)]). Base is R7 (SP)."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(19, imm, rd)

def _encode_sw_s(rs, imm):
    """SWS: mem16[R7 + sext(imm)] = rs. Base is R7 (SP)."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(20, imm, rs)

def _encode_sb_s(rs, imm):
    """SBS: mem[R7 + sext(imm)] = rs[7:0]. Base is R7 (SP)."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_i(21, imm, rs)

def _encode_lui(rd, imm8):
    """LUI: rd = imm8 << 8. Upper byte load."""
    assert -128 <= imm8 <= 255, f"imm8 out of range: {imm8}"
    return _encode_i(22, imm8, rd)

def _encode_auipc(rd, imm8):
    """AUIPC: rd = pc + (imm8 << 8). Upper byte add to PC."""
    assert -128 <= imm8 <= 255, f"imm8 out of range: {imm8}"
    return _encode_i(23, imm8, rd)

# ---------------------------------------------------------------------------
# B-type (opcode 24): BT, BF
# ---------------------------------------------------------------------------

def _encode_bt(imm):
    """BT: if T, pc += sext(imm8) << 1."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_b(0, imm)

def _encode_bf(imm):
    """BF: if !T, pc += sext(imm8) << 1."""
    assert -128 <= imm <= 127, f"imm out of range: {imm}"
    return _encode_b(1, imm)

# ---------------------------------------------------------------------------
# J-type (opcode 25): J, JAL
# ---------------------------------------------------------------------------

def _encode_j_insn(imm10):
    """J: pc += sext(imm10) << 1."""
    assert -512 <= imm10 <= 511, f"imm10 out of range: {imm10}"
    return _encode_j(0, imm10)

def _encode_jal_insn(imm10):
    """JAL: R6 = pc+2; pc += sext(imm10) << 1. Links to R6."""
    assert -512 <= imm10 <= 511, f"imm10 out of range: {imm10}"
    return _encode_j(1, imm10)

# ---------------------------------------------------------------------------
# R-type (opcodes 26-29)
# ---------------------------------------------------------------------------

# R-ALU1 (opcode 26): ADD=00, SUB=01, AND=10, OR=11
def _encode_add(rd, rs1, rs2):  return _encode_r(26, 0, rd, rs2, rs1)
def _encode_sub(rd, rs1, rs2):  return _encode_r(26, 1, rd, rs2, rs1)
def _encode_and_rr(rd, rs1, rs2): return _encode_r(26, 2, rd, rs2, rs1)
def _encode_or_rr(rd, rs1, rs2):  return _encode_r(26, 3, rd, rs2, rs1)

# R-ALU2 (opcode 27): XOR=00, SLL=01, SRL=10, SRA=11
def _encode_xor_rr(rd, rs1, rs2): return _encode_r(27, 0, rd, rs2, rs1)
def _encode_sll(rd, rs1, rs2):  return _encode_r(27, 1, rd, rs2, rs1)
def _encode_srl(rd, rs1, rs2):  return _encode_r(27, 2, rd, rs2, rs1)
def _encode_sra(rd, rs1, rs2):  return _encode_r(27, 3, rd, rs2, rs1)

# R-MEM (opcode 28): LWR=00, LBR=01, LBUR=10, SWR=11
# Loads: rd @ [13:11]=dest, rs1 @ [7:5]=addr, rs2=dc
# Stores: rs2 @ [10:8]=data, rs1 @ [7:5]=addr, rd=dc
def _encode_lw_rr(rd, rs):  return _encode_r(28, 0, rd, 0, rs)
def _encode_lb_rr(rd, rs):  return _encode_r(28, 1, rd, 0, rs)
def _encode_lbu_rr(rd, rs): return _encode_r(28, 2, rd, 0, rs)
def _encode_sw_rr(data, rs):  return _encode_r(28, 3, 0, data, rs)

# R-MISC (opcode 29): SBR=00, CLT=01, CLTU=10, CEQ=11
def _encode_sb_rr(data, rs):  return _encode_r(29, 0, 0, data, rs)
def _encode_clt(rs1, rs2):  return _encode_r(29, 1, 0, rs2, rs1)
def _encode_cltu(rs1, rs2): return _encode_r(29, 2, 0, rs2, rs1)
def _encode_ceq(rs1, rs2):  return _encode_r(29, 3, 0, rs2, rs1)

# ---------------------------------------------------------------------------
# SI-type (opcode 30): SLLI, SRLI, SRAI
# ---------------------------------------------------------------------------

def _encode_slli(rd, shamt): return _encode_si(0b000, shamt, rd)
def _encode_srli(rd, shamt): return _encode_si(0b010, shamt, rd)
def _encode_srai(rd, shamt): return _encode_si(0b011, shamt, rd)

def _encode_sllt(rd): return _encode_si(0b100, 0, rd)
def _encode_rlt(rd):  return _encode_si(0b101, 0, rd)
def _encode_srlt(rd): return _encode_si(0b110, 0, rd)
def _encode_rrt(rd):  return _encode_si(0b111, 0, rd)

# ---------------------------------------------------------------------------
# System (opcode 31)
# ---------------------------------------------------------------------------

# funct4 assignments (ir[15:12]):
#   0=SEI, 1=CLI, 2=WAI, 3=STP
#   4=EPCR, 5=EPCW, 6=SRR, 7=SRW
#   8=RETI, 12+=INT (ir[15:14]=11, vector at ir[7:6])

def _encode_sei():  return _encode_sys(0)
def _encode_cli():  return _encode_sys(1)
def _encode_reti(): return _encode_sys(8)
def _encode_wai():  return _encode_sys(2)
def _encode_stp():  return _encode_sys(3)

def _encode_epcr(rd):
    """EPCR Rd: copy EPC to Rd."""
    return _encode_sys(4, rd)

def _encode_epcw(rs):
    """EPCW Rs: copy Rs to EPC."""
    return _encode_sys(5, rs)

def _encode_srr(rd):
    """SRR Rd: rd = {12'b0, ESR[1:0], I, T}."""
    return _encode_sys(6, rd)

def _encode_srw(rs):
    """SRW Rs: ESR = rs[3:2], {I, T} = rs[1:0]."""
    return _encode_sys(7, rs)

def _encode_brk():
    """BRK: INT with vector 1 → handler at $0004.
    ir[7:6]=01 for vector 1, so reg field [7:5]=010=2."""
    return _encode_sys(12, 2)

def _encode_nop():
    """NOP = ADDI R0, 0 = 0x0000."""
    return (0x00, 0x00)

def _spin(addr=None):
    """Self-loop: J -1 (pc-relative, works at any address)."""
    return _encode_j_insn(imm10=-1)


# ===========================================================================
# Assembler class
# ===========================================================================

class Asm:
    def __init__(self, org=0):
        self.pc = org
        self.prog = {}
        self.labels = {}
        self.fixups = []

    def _emit(self, bytepair):
        self.prog[self.pc] = bytepair[0]
        self.prog[self.pc + 1] = bytepair[1]
        self.pc += 2

    def label(self, name):
        assert name not in self.labels, f"duplicate label: {name}"
        self.labels[name] = self.pc

    def org(self, addr):
        self.pc = addr

    def db(self, *bytes):
        for b in bytes:
            self.prog[self.pc] = b & 0xFF
            self.pc += 1

    def dw(self, word):
        self.prog[self.pc] = word & 0xFF
        self.prog[self.pc + 1] = (word >> 8) & 0xFF
        self.pc += 2

    def string(self, s):
        self.db(*s.encode(), 0)

    # I-type instructions
    def li(self, rd, imm):      self._emit(_encode_li(rd, imm))
    def addi(self, rd, imm):    self._emit(_encode_addi(rd, imm))
    def lw(self, rd, imm):      self._emit(_encode_lw(rd, imm))
    def lb(self, rd, imm):      self._emit(_encode_lb(rd, imm))
    def lbu(self, rd, imm):     self._emit(_encode_lbu(rd, imm))
    def sw(self, rs, imm):      self._emit(_encode_sw(rs, imm))
    def sb(self, rs, imm):      self._emit(_encode_sb(rs, imm))
    def jr(self, rs, imm):      self._emit(_encode_jr(rs, imm))
    def jalr(self, rs, imm):    self._emit(_encode_jalr(rs, imm))
    def andi(self, rd, imm):    self._emit(_encode_andi(rd, imm))
    def ori(self, rd, imm):     self._emit(_encode_ori(rd, imm))
    def xori(self, rd, imm):    self._emit(_encode_xori(rd, imm))
    def clti(self, rs, imm):    self._emit(_encode_clti(rs, imm))
    def cltui(self, rs, imm):   self._emit(_encode_cltui(rs, imm))
    def ceqi(self, rs, imm):    self._emit(_encode_ceqi(rs, imm))
    # SP-relative
    def lw_s(self, rd, imm):    self._emit(_encode_lw_s(rd, imm))
    def lb_s(self, rd, imm):    self._emit(_encode_lb_s(rd, imm))
    def lbu_s(self, rd, imm):   self._emit(_encode_lbu_s(rd, imm))
    def sw_s(self, rs, imm):    self._emit(_encode_sw_s(rs, imm))
    def sb_s(self, rs, imm):    self._emit(_encode_sb_s(rs, imm))
    # LUI / AUIPC (I-type, imm8 << 8)
    def lui(self, rd, imm8):    self._emit(_encode_lui(rd, imm8))
    def auipc(self, rd, imm8):  self._emit(_encode_auipc(rd, imm8))
    # R-type ALU
    def add(self, rd, rs1, rs2):   self._emit(_encode_add(rd, rs1, rs2))
    def sub(self, rd, rs1, rs2):   self._emit(_encode_sub(rd, rs1, rs2))
    def and_(self, rd, rs1, rs2):  self._emit(_encode_and_rr(rd, rs1, rs2))
    def or_(self, rd, rs1, rs2):   self._emit(_encode_or_rr(rd, rs1, rs2))
    def xor(self, rd, rs1, rs2):   self._emit(_encode_xor_rr(rd, rs1, rs2))
    def sll(self, rd, rs1, rs2):   self._emit(_encode_sll(rd, rs1, rs2))
    def srl(self, rd, rs1, rs2):   self._emit(_encode_srl(rd, rs1, rs2))
    def sra(self, rd, rs1, rs2):   self._emit(_encode_sra(rd, rs1, rs2))
    # SI-type shifts
    def slli(self, rd, shamt):  self._emit(_encode_slli(rd, shamt))
    def srli(self, rd, shamt):  self._emit(_encode_srli(rd, shamt))
    def srai(self, rd, shamt):  self._emit(_encode_srai(rd, shamt))
    # SI-type shift/rotate through T
    def sllt(self, rd):         self._emit(_encode_sllt(rd))
    def srlt(self, rd):         self._emit(_encode_srlt(rd))
    def rlt(self, rd):          self._emit(_encode_rlt(rd))
    def rrt(self, rd):          self._emit(_encode_rrt(rd))
    # R-type memory
    def lw_rr(self, rd, rs):    self._emit(_encode_lw_rr(rd, rs))
    def lb_rr(self, rd, rs):    self._emit(_encode_lb_rr(rd, rs))
    def lbu_rr(self, rd, rs):   self._emit(_encode_lbu_rr(rd, rs))
    def sw_rr(self, rs2, rs1):  self._emit(_encode_sw_rr(rs2, rs1))
    def sb_rr(self, rs2, rs1):  self._emit(_encode_sb_rr(rs2, rs1))
    # R-type comparisons
    def clt(self, rs1, rs2):    self._emit(_encode_clt(rs1, rs2))
    def cltu(self, rs1, rs2):   self._emit(_encode_cltu(rs1, rs2))
    def ceq(self, rs1, rs2):    self._emit(_encode_ceq(rs1, rs2))
    # System
    def sei(self):              self._emit(_encode_sei())
    def cli(self):              self._emit(_encode_cli())
    def reti(self):             self._emit(_encode_reti())
    def epcr(self, rd):         self._emit(_encode_epcr(rd))
    def epcw(self, rs):         self._emit(_encode_epcw(rs))
    def srr(self, rd):          self._emit(_encode_srr(rd))
    def srw(self, rs):          self._emit(_encode_srw(rs))
    def brk(self):              self._emit(_encode_brk())
    def wai(self):              self._emit(_encode_wai())
    def stp(self):              self._emit(_encode_stp())
    def nop(self):              self._emit(_encode_nop())

    # Branch/jump instructions — accept label string or integer offset
    def bz(self, rs, target):
        if isinstance(target, str):
            self.fixups.append(('bz', self.pc, rs, target))
            self._emit((0, 0))
        else:
            self._emit(_encode_bz(rs, target))

    def bnz(self, rs, target):
        if isinstance(target, str):
            self.fixups.append(('bnz', self.pc, rs, target))
            self._emit((0, 0))
        else:
            self._emit(_encode_bnz(rs, target))

    def bt(self, target):
        if isinstance(target, str):
            self.fixups.append(('bt', self.pc, target))
            self._emit((0, 0))
        else:
            self._emit(_encode_bt(target))

    def bf(self, target):
        if isinstance(target, str):
            self.fixups.append(('bf', self.pc, target))
            self._emit((0, 0))
        else:
            self._emit(_encode_bf(target))

    def j(self, target):
        if isinstance(target, str):
            self.fixups.append(('j', self.pc, target))
            self._emit((0, 0))
        else:
            self._emit(_encode_j_insn(target))

    def jal(self, target):
        if isinstance(target, str):
            self.fixups.append(('jal', self.pc, target))
            self._emit((0, 0))
        else:
            self._emit(_encode_jal_insn(target))

    # Pseudo-instructions
    def read_t(self, rd):
        """Read T flag into rd: SRR rd; ANDI rd, 1."""
        self._emit(_encode_srr(rd))
        self._emit(_encode_andi(rd, 1))

    def spin(self):
        """Self-loop: J -1."""
        self._emit(_spin())

    def la(self, rd, target):
        """Load 16-bit address: LUI rd, hi; ADDI rd, lo."""
        if isinstance(target, str):
            self.fixups.append(('la', self.pc, rd, target))
            self._emit((0, 0))  # LUI placeholder
            self._emit((0, 0))  # ADDI placeholder
        else:
            hi = (target >> 8) & 0xFF
            lo = target & 0xFF
            if lo & 0x80:
                hi = (hi + 1) & 0xFF
            lo_s = lo - 256 if lo & 0x80 else lo
            self._emit(_encode_lui(rd, hi))
            self._emit(_encode_addi(rd, lo_s))

    # Output methods
    def segments(self):
        """Return [(start_addr, bytes), ...] of contiguous segments."""
        mem = self.assemble()
        if not mem:
            return []
        addrs = sorted(mem.keys())
        segs = []
        start = addrs[0]
        data = [mem[start]]
        for a in addrs[1:]:
            if a == start + len(data):
                data.append(mem[a])
            else:
                segs.append((start, bytes(data)))
                start = a
                data = [mem[a]]
        segs.append((start, bytes(data)))
        return segs

    def save_binary(self, filename):
        """Write flat binary (address 0 to max). Gaps are zero-filled."""
        mem = self.assemble()
        if not mem:
            return
        size = max(mem.keys()) + 1
        buf = bytearray(size)
        for addr, byte in mem.items():
            buf[addr] = byte
        with open(filename, 'wb') as f:
            f.write(buf)

    # Assemble — resolve label fixups and return {addr: byte}
    def assemble(self):
        for fixup in self.fixups:
            kind, addr = fixup[0], fixup[1]
            if kind in ('bz', 'bnz'):
                _, addr, rs, label = fixup
                assert label in self.labels, f"undefined label: {label}"
                imm = (self.labels[label] - addr) // 2 - 1
                bytepair = (_encode_bz if kind == 'bz' else _encode_bnz)(rs, imm)
            elif kind in ('bt', 'bf'):
                _, addr, label = fixup
                assert label in self.labels, f"undefined label: {label}"
                imm = (self.labels[label] - addr) // 2 - 1
                bytepair = (_encode_bt if kind == 'bt' else _encode_bf)(imm)
            elif kind in ('j', 'jal'):
                _, addr, label = fixup
                assert label in self.labels, f"undefined label: {label}"
                imm = (self.labels[label] - addr) // 2 - 1
                bytepair = (_encode_j_insn if kind == 'j' else _encode_jal_insn)(imm)
            elif kind == 'la':
                _, addr, rd, label = fixup
                assert label in self.labels, f"undefined label: {label}"
                target = self.labels[label]
                hi = (target >> 8) & 0xFF
                lo = target & 0xFF
                if lo & 0x80:
                    hi = (hi + 1) & 0xFF
                lo_s = lo - 256 if lo & 0x80 else lo
                lui = _encode_lui(rd, hi)
                addi = _encode_addi(rd, lo_s)
                self.prog[addr] = lui[0]
                self.prog[addr + 1] = lui[1]
                self.prog[addr + 2] = addi[0]
                self.prog[addr + 3] = addi[1]
                continue
            self.prog[addr] = bytepair[0]
            self.prog[addr + 1] = bytepair[1]
        return self.prog
