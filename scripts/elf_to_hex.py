#!/usr/bin/env python3
"""Convert a linked ELF (linked at 0x0 per sw/startup/link.ld) into a flat,
word-per-line hex memory image suitable for Verilog $readmemh into a
32-bit-wide array (tb/ram_model.sv), with no @address directives.

Usage: elf_to_hex.py <in.elf> <out.hex> [--max-bytes N]
"""
import struct
import subprocess
import sys
from pathlib import Path

RAM_BYTES = 0x00100000  # 1 MiB, must match sw/startup/link.ld


def find_objcopy():
    import shutil
    for cand in ("riscv64-unknown-elf-objcopy",):
        p = shutil.which(cand)
        if p:
            return p
    raise RuntimeError("riscv64-unknown-elf-objcopy not found on PATH; source scripts/env.sh first")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    elf_path = Path(sys.argv[1])
    hex_path = Path(sys.argv[2])
    max_bytes = RAM_BYTES
    if "--max-bytes" in sys.argv:
        max_bytes = int(sys.argv[sys.argv.index("--max-bytes") + 1])

    objcopy = find_objcopy()
    bin_path = hex_path.with_suffix(".bin")
    subprocess.run([objcopy, "-O", "binary", str(elf_path), str(bin_path)], check=True)

    data = bin_path.read_bytes()
    if len(data) > max_bytes:
        raise RuntimeError(
            f"ELF binary image is {len(data)} bytes, exceeds the {max_bytes}-byte "
            f"RAM region (sw/startup/link.ld). Report this as a genuine memory "
            f"overflow rather than silently growing memory."
        )
    pad = (-len(data)) % 4
    data = data + b"\x00" * pad

    n_words = len(data) // 4
    with hex_path.open("w") as f:
        for i in range(n_words):
            word = struct.unpack_from("<I", data, i * 4)[0]
            f.write(f"{word:08x}\n")

    print(f"Wrote {hex_path}: {n_words} words ({len(data)} bytes) from {elf_path}")


if __name__ == "__main__":
    main()
