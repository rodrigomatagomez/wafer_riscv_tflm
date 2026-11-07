#!/usr/bin/env python3
"""Deterministic (seed 2026) generator of a long random RV32IM instruction
stream, restricted to the register-only ALU + M-extension subset (no
loads/stores/branches/jumps), so the resulting program is inherently safe
to execute (no memory accesses, no control flow to validate) while still
exercising a huge, random cross-section of opcode/funct3/funct7/operand
combinations against the independent Python reference model.

Per claude_implementation_prompt.txt Section 6: "Include at least 1000
retired instructions from fixed-seed generated programs in addition to
directed tests."

Usage:
    python3 scripts/gen_random_program.py <n_instructions> <out_prefix>
Writes <out_prefix>.hex (word-per-line, for $readmemh) and
<out_prefix>.words.json (the raw instruction words, for the reference model).
"""
import json
import random
import sys
from pathlib import Path

SEED = 2026
EBREAK = 0x00100073


def enc_r(funct7, rs2, rs1, funct3, rd, opcode):
    return ((funct7 & 0x7F) << 25) | ((rs2 & 0x1F) << 20) | ((rs1 & 0x1F) << 15) | \
           ((funct3 & 0x7) << 12) | ((rd & 0x1F) << 7) | (opcode & 0x7F)


def enc_i(imm12, rs1, funct3, rd, opcode):
    return ((imm12 & 0xFFF) << 20) | ((rs1 & 0x1F) << 15) | \
           ((funct3 & 0x7) << 12) | ((rd & 0x1F) << 7) | (opcode & 0x7F)


OPC_OP = 0b0110011
OPC_OP_IMM = 0b0010011

ALU_FUNCT3 = [0b000, 0b001, 0b010, 0b011, 0b100, 0b101, 0b110, 0b111]
MULDIV_FUNCT3 = [0b000, 0b001, 0b010, 0b011, 0b100, 0b101, 0b110, 0b111]


def random_instruction(rng):
    rd = rng.randint(1, 31)   # avoid x0 as destination so writes are observable
    rs1 = rng.randint(0, 31)
    rs2 = rng.randint(0, 31)
    kind = rng.choice(["op_alu", "op_imm", "muldiv"])

    if kind == "op_imm":
        f3 = rng.choice(ALU_FUNCT3)
        if f3 in (0b001, 0b101):  # SLLI / SRLI / SRAI: imm encodes shamt + funct7-like bits
            shamt = rng.randint(0, 31)
            f7 = 0b0100000 if (f3 == 0b101 and rng.random() < 0.5) else 0b0000000
            imm12 = (f7 << 5) | shamt
        else:
            imm12 = rng.randint(-2048, 2047) & 0xFFF
        return enc_i(imm12, rs1, f3, rd, OPC_OP_IMM)

    if kind == "op_alu":
        f3 = rng.choice(ALU_FUNCT3)
        f7 = 0b0100000 if (f3 in (0b000, 0b101) and rng.random() < 0.5) else 0b0000000
        return enc_r(f7, rs2, rs1, f3, rd, OPC_OP)

    # muldiv
    f3 = rng.choice(MULDIV_FUNCT3)
    return enc_r(0b0000001, rs2, rs1, f3, rd, OPC_OP)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1100
    out_prefix = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("build/random_program/random")
    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(SEED)
    words = [random_instruction(rng) for _ in range(n)]
    words.append(EBREAK)

    hex_path = out_prefix.with_suffix(".hex")
    with hex_path.open("w") as f:
        for w in words:
            f.write(f"{w:08x}\n")

    json_path = Path(str(out_prefix) + ".words.json")
    with json_path.open("w") as f:
        json.dump({"seed": SEED, "n_instructions": n, "words": words}, f)

    print(f"Wrote {hex_path} ({len(words)} words) and {json_path}")


if __name__ == "__main__":
    main()
