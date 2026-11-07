#!/usr/bin/env bash
# Build a bare-metal rv32im program: crt0 + given sources -> ELF -> hex.
# Usage: scripts/build_fw.sh <output_name_no_ext> <source1.c|.S> [more sources...]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/env.sh" > /dev/null

NAME="$1"; shift
SOURCES=("$@")

BUILD_DIR="$ROOT/build/$NAME"
mkdir -p "$BUILD_DIR"

CFLAGS=(-march=rv32im -mabi=ilp32 -O2 -g -ffreestanding -fno-exceptions -fno-rtti
        -fno-builtin -nostdlib -Wall -Wextra
        -I"$ROOT/sw/startup")
CXXFLAGS=("${CFLAGS[@]}" -std=c++17 -fno-threadsafe-statics -fno-use-cxa-atexit)
CCFLAGS=("${CFLAGS[@]}" -std=c17)

OBJS=()
compile_one() {
  local src="$1"
  local base
  base="$(basename "$src")"
  local obj="$BUILD_DIR/${base}.o"
  case "$src" in
    *.S) riscv64-unknown-elf-gcc "${CFLAGS[@]}" -c "$src" -o "$obj" ;;
    *.c) riscv64-unknown-elf-gcc "${CCFLAGS[@]}" -c "$src" -o "$obj" ;;
    *.cc|*.cpp) riscv64-unknown-elf-g++ "${CXXFLAGS[@]}" -c "$src" -o "$obj" ;;
    *) echo "unknown source type: $src" >&2; exit 1 ;;
  esac
  OBJS+=("$obj")
}

compile_one "$ROOT/sw/startup/crt0.S"
for s in "${SOURCES[@]}"; do
  compile_one "$s"
done

LIBGCC_DIR="$(riscv64-unknown-elf-gcc -march=rv32im -mabi=ilp32 -print-libgcc-file-name | xargs dirname)"

riscv64-unknown-elf-gcc -march=rv32im -mabi=ilp32 -nostdlib \
    -T "$ROOT/sw/startup/link.ld" -Wl,--no-relax -Wl,-Map="$BUILD_DIR/$NAME.map" \
    "${OBJS[@]}" -L"$LIBGCC_DIR" -lgcc \
    -o "$BUILD_DIR/$NAME.elf"

riscv64-unknown-elf-objdump -d "$BUILD_DIR/$NAME.elf" > "$BUILD_DIR/$NAME.dis"
riscv64-unknown-elf-size "$BUILD_DIR/$NAME.elf" > "$BUILD_DIR/$NAME.size"
python3 "$ROOT/scripts/elf_to_hex.py" "$BUILD_DIR/$NAME.elf" "$BUILD_DIR/$NAME.hex"

echo "Built $BUILD_DIR/$NAME.elf"
cat "$BUILD_DIR/$NAME.size"
