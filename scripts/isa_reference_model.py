#!/usr/bin/env python3
"""Independent RV32IM functional reference model, written directly from the
RISC-V ISA specification (https://docs.riscv.org/reference/isa/) WITHOUT
reading or reusing rtl/rv32im_core.sv or any other DUT logic. Used as the
fallback independent ISA reference per claude_implementation_prompt.txt
Section 6, since Spike cannot run on this host (docs/issues.md ISS-001).

Supports exactly the subset exercised by scripts/gen_random_program.py:
register-register and register-immediate ALU ops (OP, OP-IMM) and the
complete M extension (OP with funct7=0000001). Does not implement
loads/stores/branches/jumps/LUI/AUIPC/FENCE/SYSTEM — not needed for the
random-instruction-stream comparison, which deliberately stays in this
safe (no memory, no control flow) subset. See docs/decisions.md D-002 and
docs/findings.md for scope rationale.
"""
from dataclasses import dataclass, field


MASK32 = 0xFFFFFFFF


def to_signed32(x):
    x &= MASK32
    return x - (1 << 32) if x & 0x80000000 else x


def to_unsigned32(x):
    return x & MASK32


@dataclass
class CpuState:
    pc: int = 0
    regs: list = field(default_factory=lambda: [0] * 32)

    def read(self, i):
        return 0 if i == 0 else self.regs[i]

    def write(self, i, value):
        if i != 0:
            self.regs[i] = value & MASK32


OPC_OP = 0b0110011
OPC_OP_IMM = 0b0010011


def sign_ext(value, bits):
    mask = 1 << (bits - 1)
    value &= (1 << bits) - 1
    return (value ^ mask) - mask


def decode_fields(instr):
    opcode = instr & 0x7F
    rd = (instr >> 7) & 0x1F
    funct3 = (instr >> 12) & 0x7
    rs1 = (instr >> 15) & 0x1F
    rs2 = (instr >> 20) & 0x1F
    funct7 = (instr >> 25) & 0x7F
    imm_i = sign_ext(instr >> 20, 12)
    return dict(opcode=opcode, rd=rd, funct3=funct3, rs1=rs1, rs2=rs2,
                funct7=funct7, imm_i=imm_i)


def alu_op(funct3, funct7, a, b, is_imm):
    a_u = to_unsigned32(a)
    b_u = to_unsigned32(b)
    a_s = to_signed32(a)
    b_s = to_signed32(b)
    shamt = b_u & 0x1F
    if funct3 == 0b000:
        if is_imm:
            return to_unsigned32(a + b)
        return to_unsigned32(a - b) if funct7 == 0b0100000 else to_unsigned32(a + b)
    if funct3 == 0b001:
        return to_unsigned32(a_u << shamt)
    if funct3 == 0b010:
        return 1 if a_s < b_s else 0
    if funct3 == 0b011:
        return 1 if a_u < b_u else 0
    if funct3 == 0b100:
        return a_u ^ b_u
    if funct3 == 0b101:
        if funct7 == 0b0100000:
            return to_unsigned32(a_s >> shamt)
        return a_u >> shamt
    if funct3 == 0b110:
        return a_u | b_u
    if funct3 == 0b111:
        return a_u & b_u
    raise ValueError(f"bad alu funct3 {funct3}")


def muldiv_op(funct3, rs1_val, rs2_val):
    a = to_signed32(rs1_val)
    b = to_signed32(rs2_val)
    au = to_unsigned32(rs1_val)
    bu = to_unsigned32(rs2_val)

    if funct3 == 0b000:  # MUL
        return to_unsigned32(a * b)
    if funct3 == 0b001:  # MULH (signed x signed)
        return to_unsigned32((a * b) >> 32)
    if funct3 == 0b010:  # MULHSU (signed x unsigned)
        return to_unsigned32((a * bu) >> 32)
    if funct3 == 0b011:  # MULHU (unsigned x unsigned)
        return to_unsigned32((au * bu) >> 32)
    if funct3 == 0b100:  # DIV
        if b == 0:
            return MASK32
        if a == -(1 << 31) and b == -1:
            return to_unsigned32(a)
        q = abs(a) // abs(b)
        if (a < 0) != (b < 0):
            q = -q
        return to_unsigned32(q)
    if funct3 == 0b101:  # DIVU
        if bu == 0:
            return MASK32
        return to_unsigned32(au // bu)
    if funct3 == 0b110:  # REM
        if b == 0:
            return to_unsigned32(a)
        if a == -(1 << 31) and b == -1:
            return 0
        r = abs(a) % abs(b)
        if a < 0:
            r = -r
        return to_unsigned32(r)
    if funct3 == 0b111:  # REMU
        if bu == 0:
            return to_unsigned32(au)
        return to_unsigned32(au % bu)
    raise ValueError(f"bad muldiv funct3 {funct3}")


def step(state: CpuState, instr: int):
    """Execute one instruction (OP / OP-IMM subset only). Returns
    (rd_we, rd_addr, rd_wdata) and advances state.pc by 4."""
    f = decode_fields(instr)
    opcode = f["opcode"]
    rd, rs1, rs2 = f["rd"], f["rs1"], f["rs2"]
    funct3, funct7 = f["funct3"], f["funct7"]

    rs1_val = state.read(rs1)
    if opcode == OPC_OP_IMM:
        result = alu_op(funct3, funct7 if funct3 in (0b001, 0b101) else 0,
                         rs1_val, to_unsigned32(f["imm_i"]), is_imm=True)
        rd_we = True
    elif opcode == OPC_OP:
        rs2_val = state.read(rs2)
        if funct7 == 0b0000001:
            result = muldiv_op(funct3, rs1_val, rs2_val)
        else:
            result = alu_op(funct3, funct7, rs1_val, rs2_val, is_imm=False)
        rd_we = True
    else:
        raise ValueError(f"unsupported opcode {opcode:#09b} in reference-model subset")

    if rd_we:
        state.write(rd, result)
    rd_wdata = state.read(rd) if rd != 0 else 0
    state.pc = to_unsigned32(state.pc + 4)
    return rd_we, rd, rd_wdata


def run_trace(words):
    """Run a flat instruction stream starting at pc=0, all-zero regs.
    Returns a list of dicts: pc, instr, rd_we, rd_addr, rd_wdata."""
    state = CpuState()
    trace = []
    for instr in words:
        pc_before = state.pc
        rd_we, rd_addr, rd_wdata = step(state, instr)
        trace.append({
            "pc": pc_before,
            "instr": instr,
            "rd_we": int(rd_we),
            "rd_addr": rd_addr,
            "rd_wdata": rd_wdata,
        })
    return trace
