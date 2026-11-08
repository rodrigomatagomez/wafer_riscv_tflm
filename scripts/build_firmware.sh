#!/usr/bin/env bash
# Build the bare-metal rv32im_core firmware: crt0 + platform glue + TFLM
# (reference kernels, pinned commit) + the embedded model/input constants.
# Unlike scripts/build_fw.sh (used for the processor directed tests), this
# links against the toolchain's bundled newlib + libstdc++ (not -nostdlib):
# TFLM's C++ code needs memcpy/memset/new/delete, which -nostdlib would not
# provide. sw/platform_rv32/syscalls.c supplies the handful of OS-level
# hooks newlib calls into (_sbrk, _write, ...).
#
# CASE_START / CASE_COUNT (environment variables, both optional, default
# unset = full 20-case manifest): select which sub-range of the fixed
# comparison manifest this firmware image runs, per docs/decisions.md and
# claude_implementation_prompt.txt Section 6 ("a controlled way to run a
# selected comparison case or range"). Only sw/app/main_firmware.cc depends
# on these values (via -D defines), so every other TFLM/platform object
# file is compiled once into a shared cache ($BUILD/obj) and reused across
# configs -- "reuse unchanged TFLM object files where practical rather than
# recompiling every dependency for each case". Each config gets its own
# main_firmware.o and final ELF under a config-tagged subdirectory, plus a
# firmware_config.json recording the exact CASE_START/CASE_COUNT and the
# resulting ELF's SHA-256, so a later reader can tell exactly which case
# range a given .elf/.hex corresponds to.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/env.sh" > /dev/null
TFLM="$ROOT/third_party/tflm_tree"
BUILD="$ROOT/build/firmware"
OBJDIR="$BUILD/obj"
mkdir -p "$OBJDIR"

CASE_START="${CASE_START:-}"
CASE_COUNT="${CASE_COUNT:-}"
if [ -n "$CASE_START" ] || [ -n "$CASE_COUNT" ]; then
  CONFIG_TAG="case_${CASE_START:-0}_${CASE_COUNT:-all}"
else
  CONFIG_TAG="case_full"
fi
CONFIG_DIR="$BUILD/configs/$CONFIG_TAG"
mkdir -p "$CONFIG_DIR"

INCLUDES=(-I"$TFLM" -I"$TFLM/third_party/flatbuffers/include"
          -I"$TFLM/third_party/kissfft"
          -I"$ROOT/sw/generated" -I"$ROOT/sw/app" -I"$ROOT/sw/startup")
CXXFLAGS=(-march=rv32im -mabi=ilp32 -std=c++17 -O2 -DNDEBUG
          -fno-exceptions -fno-rtti -fno-threadsafe-statics -fno-use-cxa-atexit
          "${INCLUDES[@]}")
CFLAGS=(-march=rv32im -mabi=ilp32 -std=c17 -O2 -DNDEBUG "${INCLUDES[@]}")

MAIN_SRC="$ROOT/sw/app/main_firmware.cc"
mapfile -t CC_SRCS < <(find "$TFLM/tensorflow" "$TFLM/signal" -name "*.cc" \
    ! -iname "*test*" ! -iname "mock_micro_graph.cc" ! -iname "kernel_runner.cc" \
    ! -iname "debug_log.cc")
CC_SRCS+=("$ROOT/sw/platform_rv32/flatbuffers_locale_stub.cc")
CC_SRCS+=("$ROOT/sw/platform_rv32/debug_log.cc")
CC_SRCS+=("$ROOT/sw/generated/wafer_model_data.cc")
# main_firmware.cc is intentionally NOT in this shared-cache list: it is the
# only translation unit affected by CASE_START/CASE_COUNT, so it is compiled
# separately below into the config-specific directory instead of the shared
# $OBJDIR cache.
C_SRCS=("$TFLM/third_party/kissfft/kiss_fft.c" "$ROOT/sw/platform_rv32/syscalls.c")

echo "Compiling ${#CC_SRCS[@]} shared .cc + ${#C_SRCS[@]} shared .c files in parallel (nproc=$(nproc))..."
: > "$BUILD/build.log"
# Object reuse is mtime-based, not existence-based: an object is only skipped
# if it is newer than its own source file. This prevents silently retaining
# a stale object after its source changes (previously only existence was
# checked, which could not detect a modified source with an already-present
# object of the same name).
printf '%s\n' "${CC_SRCS[@]}" | xargs -P "$(nproc)" -I{} bash -c '
  src="$1"; obj="'"$OBJDIR"'/$(echo "$src" | tr "/" "_").o"
  [ -f "$obj" ] && [ "$obj" -nt "$src" ] && exit 0
  riscv64-unknown-elf-g++ '"${CXXFLAGS[*]}"' -c "$src" -o "$obj" 2>> "'"$BUILD"'/build.log"
' _ {}
printf '%s\n' "${C_SRCS[@]}" | xargs -P "$(nproc)" -I{} bash -c '
  src="$1"; obj="'"$OBJDIR"'/$(echo "$src" | tr "/" "_").o"
  [ -f "$obj" ] && [ "$obj" -nt "$src" ] && exit 0
  riscv64-unknown-elf-gcc '"${CFLAGS[*]}"' -c "$src" -o "$obj" 2>> "'"$BUILD"'/build.log"
' _ {}

n_expected=$((${#CC_SRCS[@]} + ${#C_SRCS[@]}))
n_objs=$(find "$OBJDIR" -name "*.o" | wc -l)
if [ "$n_objs" -ne "$n_expected" ]; then
  echo "Shared compile step produced $n_objs/$n_expected object files. Errors:"
  tail -150 "$BUILD/build.log"
  exit 1
fi

MAIN_DEFINES=()
[ -n "$CASE_START" ] && MAIN_DEFINES+=(-DCASE_START="$CASE_START")
[ -n "$CASE_COUNT" ] && MAIN_DEFINES+=(-DCASE_COUNT="$CASE_COUNT")

MAIN_OBJ="$CONFIG_DIR/main_firmware.o"
echo "Compiling main_firmware.cc for config '$CONFIG_TAG' (${MAIN_DEFINES[*]:-defaults: full 20-case manifest})..."
riscv64-unknown-elf-g++ "${CXXFLAGS[@]}" "${MAIN_DEFINES[@]}" -c "$MAIN_SRC" -o "$MAIN_OBJ" \
    2>> "$BUILD/build.log" || { tail -80 "$BUILD/build.log"; exit 1; }

CRT0_OBJ="$BUILD/crt0.o"
CRT0_SRC="$ROOT/sw/startup/crt0.S"
if [ ! -f "$CRT0_OBJ" ] || [ "$CRT0_SRC" -nt "$CRT0_OBJ" ]; then
  riscv64-unknown-elf-gcc -march=rv32im -mabi=ilp32 -c "$CRT0_SRC" -o "$CRT0_OBJ"
fi

LIBGCC_DIR="$(riscv64-unknown-elf-gcc -march=rv32im -mabi=ilp32 -print-libgcc-file-name | xargs dirname)"

riscv64-unknown-elf-g++ -march=rv32im -mabi=ilp32 \
    -T "$ROOT/sw/startup/link.ld" -Wl,--no-relax \
    -Wl,-Map="$CONFIG_DIR/firmware.map" \
    -nostartfiles \
    "$CRT0_OBJ" "$MAIN_OBJ" "$OBJDIR"/*.o -L"$LIBGCC_DIR" \
    -Wl,--start-group -lstdc++ -lsupc++ -lc_nano -lm -lgcc -lnosys -Wl,--end-group \
    -o "$CONFIG_DIR/firmware.elf" 2>> "$BUILD/build.log" || { tail -80 "$BUILD/build.log"; exit 1; }

riscv64-unknown-elf-objdump -d "$CONFIG_DIR/firmware.elf" > "$CONFIG_DIR/firmware.dis"
riscv64-unknown-elf-size "$CONFIG_DIR/firmware.elf" | tee "$CONFIG_DIR/firmware.size"
python3 "$ROOT/scripts/elf_to_hex.py" "$CONFIG_DIR/firmware.elf" "$CONFIG_DIR/firmware.hex"

ELF_SHA256="$(sha256sum "$CONFIG_DIR/firmware.elf" | awk '{print $1}')"
BUILD_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > "$CONFIG_DIR/firmware_config.json" <<EOF
{
  "config_tag": "$CONFIG_TAG",
  "case_start": ${CASE_START:-0},
  "case_count_requested": "${CASE_COUNT:-null}",
  "elf_path": "$CONFIG_DIR/firmware.elf",
  "elf_sha256": "$ELF_SHA256",
  "hex_path": "$CONFIG_DIR/firmware.hex",
  "build_timestamp_utc": "$BUILD_TS"
}
EOF

# Also drop a copy at the stable legacy path ($BUILD/firmware.elf etc.) for
# the full-manifest config only, since scripts/run_fw.sh and older tooling
# reference that fixed path.
if [ "$CONFIG_TAG" = "case_full" ]; then
  cp "$CONFIG_DIR/firmware.elf" "$BUILD/firmware.elf"
  cp "$CONFIG_DIR/firmware.hex" "$BUILD/firmware.hex"
  cp "$CONFIG_DIR/firmware.map" "$BUILD/firmware.map"
  cp "$CONFIG_DIR/firmware.dis" "$BUILD/firmware.dis"
  cp "$CONFIG_DIR/firmware.size" "$BUILD/firmware.size"
fi

echo "Built $CONFIG_DIR/firmware.elf (config=$CONFIG_TAG, sha256=$ELF_SHA256)"
echo "Config record: $CONFIG_DIR/firmware_config.json"
