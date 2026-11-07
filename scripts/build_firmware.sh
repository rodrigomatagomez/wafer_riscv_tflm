#!/usr/bin/env bash
# Build the bare-metal rv32im_core firmware: crt0 + platform glue + TFLM
# (reference kernels, pinned commit) + the embedded model/input constants.
# Unlike scripts/build_fw.sh (used for the processor directed tests), this
# links against the toolchain's bundled newlib + libstdc++ (not -nostdlib):
# TFLM's C++ code needs memcpy/memset/new/delete, which -nostdlib would not
# provide. sw/platform_rv32/syscalls.c supplies the handful of OS-level
# hooks newlib calls into (_sbrk, _write, ...).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/env.sh" > /dev/null
TFLM="$ROOT/third_party/tflm_tree"
BUILD="$ROOT/build/firmware"
OBJDIR="$BUILD/obj"
mkdir -p "$OBJDIR"

INCLUDES=(-I"$TFLM" -I"$TFLM/third_party/flatbuffers/include"
          -I"$TFLM/third_party/kissfft"
          -I"$ROOT/sw/generated" -I"$ROOT/sw/app" -I"$ROOT/sw/startup")
CXXFLAGS=(-march=rv32im -mabi=ilp32 -std=c++17 -O2 -DNDEBUG
          -fno-exceptions -fno-rtti -fno-threadsafe-statics -fno-use-cxa-atexit
          "${INCLUDES[@]}")
CFLAGS=(-march=rv32im -mabi=ilp32 -std=c17 -O2 -DNDEBUG "${INCLUDES[@]}")

mapfile -t CC_SRCS < <(find "$TFLM/tensorflow" "$TFLM/signal" -name "*.cc" \
    ! -iname "*test*" ! -iname "mock_micro_graph.cc" ! -iname "kernel_runner.cc" \
    ! -iname "debug_log.cc")
CC_SRCS+=("$ROOT/sw/platform_rv32/flatbuffers_locale_stub.cc")
CC_SRCS+=("$ROOT/sw/platform_rv32/debug_log.cc")
CC_SRCS+=("$ROOT/sw/generated/wafer_model_data.cc")
CC_SRCS+=("$ROOT/sw/app/main_firmware.cc")
C_SRCS=("$TFLM/third_party/kissfft/kiss_fft.c" "$ROOT/sw/platform_rv32/syscalls.c")

echo "Compiling ${#CC_SRCS[@]} .cc + ${#C_SRCS[@]} .c files in parallel (nproc=$(nproc))..."
: > "$BUILD/build.log"
printf '%s\n' "${CC_SRCS[@]}" | xargs -P "$(nproc)" -I{} bash -c '
  src="$1"; obj="'"$OBJDIR"'/$(echo "$src" | tr "/" "_").o"
  riscv64-unknown-elf-g++ '"${CXXFLAGS[*]}"' -c "$src" -o "$obj" 2>> "'"$BUILD"'/build.log"
' _ {}
printf '%s\n' "${C_SRCS[@]}" | xargs -P "$(nproc)" -I{} bash -c '
  src="$1"; obj="'"$OBJDIR"'/$(echo "$src" | tr "/" "_").o"
  riscv64-unknown-elf-gcc '"${CFLAGS[*]}"' -c "$src" -o "$obj" 2>> "'"$BUILD"'/build.log"
' _ {}

n_expected=$((${#CC_SRCS[@]} + ${#C_SRCS[@]}))
n_objs=$(find "$OBJDIR" -name "*.o" | wc -l)
if [ "$n_objs" -ne "$n_expected" ]; then
  echo "Compile step produced $n_objs/$n_expected object files. Errors:"
  tail -150 "$BUILD/build.log"
  exit 1
fi

CRT0_OBJ="$BUILD/crt0.o"
riscv64-unknown-elf-gcc -march=rv32im -mabi=ilp32 -c "$ROOT/sw/startup/crt0.S" -o "$CRT0_OBJ"

LIBGCC_DIR="$(riscv64-unknown-elf-gcc -march=rv32im -mabi=ilp32 -print-libgcc-file-name | xargs dirname)"

riscv64-unknown-elf-g++ -march=rv32im -mabi=ilp32 \
    -T "$ROOT/sw/startup/link.ld" -Wl,--no-relax \
    -Wl,-Map="$BUILD/firmware.map" \
    -nostartfiles \
    "$CRT0_OBJ" "$OBJDIR"/*.o -L"$LIBGCC_DIR" \
    -Wl,--start-group -lstdc++ -lsupc++ -lc_nano -lm -lgcc -lnosys -Wl,--end-group \
    -o "$BUILD/firmware.elf" 2>> "$BUILD/build.log" || { tail -80 "$BUILD/build.log"; exit 1; }

riscv64-unknown-elf-objdump -d "$BUILD/firmware.elf" > "$BUILD/firmware.dis"
riscv64-unknown-elf-size "$BUILD/firmware.elf" | tee "$BUILD/firmware.size"
python3 "$ROOT/scripts/elf_to_hex.py" "$BUILD/firmware.elf" "$BUILD/firmware.hex"

echo "Built $BUILD/firmware.elf"
