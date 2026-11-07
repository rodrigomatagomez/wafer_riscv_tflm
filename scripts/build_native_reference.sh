#!/usr/bin/env bash
# Build the native (host x86) TFLM reference oracle: same pinned
# tflite-micro commit/kernels/model bytes as the firmware, compiled with
# the host's own g++ instead of the RV32 cross toolchain.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TFLM="$ROOT/third_party/tflm_tree"
BUILD="$ROOT/build/native_reference"
mkdir -p "$BUILD"

mapfile -t CC_SRCS < <(find "$TFLM/tensorflow" "$TFLM/signal" -name "*.cc" \
    ! -iname "*test*" ! -iname "mock_micro_graph.cc" ! -iname "kernel_runner.cc")
CC_SRCS+=("$TFLM/third_party/flatbuffers/src/util.cpp")
CC_SRCS+=("$ROOT/sw/generated/wafer_model_data.cc")
CC_SRCS+=("$ROOT/sw/app/main_native.cc")
C_SRCS=("$TFLM/third_party/kissfft/kiss_fft.c")

INCLUDES=(-I"$TFLM" -I"$TFLM/third_party/flatbuffers/include"
          -I"$TFLM/third_party/kissfft" -I"$ROOT/sw/generated" -I"$ROOT/sw/app")

OBJDIR="$BUILD/obj"
mkdir -p "$OBJDIR"

echo "Compiling ${#CC_SRCS[@]} .cc + ${#C_SRCS[@]} .c files in parallel (nproc=$(nproc))..."
: > "$BUILD/build.log"
printf '%s\n' "${CC_SRCS[@]}" | xargs -P "$(nproc)" -I{} bash -c '
  src="$1"; obj="'"$OBJDIR"'/$(echo "$src" | tr "/" "_").o"
  g++ -std=c++17 -O2 -DNDEBUG '"${INCLUDES[*]}"' -c "$src" -o "$obj" 2>> "'"$BUILD"'/build.log"
' _ {}
printf '%s\n' "${C_SRCS[@]}" | xargs -P "$(nproc)" -I{} bash -c '
  src="$1"; obj="'"$OBJDIR"'/$(echo "$src" | tr "/" "_").o"
  gcc -O2 -DNDEBUG '"${INCLUDES[*]}"' -c "$src" -o "$obj" 2>> "'"$BUILD"'/build.log"
' _ {}

n_expected=$((${#CC_SRCS[@]} + ${#C_SRCS[@]}))
n_objs=$(find "$OBJDIR" -name "*.o" | wc -l)
if [ "$n_objs" -ne "$n_expected" ]; then
  echo "Compile step produced $n_objs/$n_expected object files. Errors:"
  tail -150 "$BUILD/build.log"
  exit 1
fi

g++ -std=c++17 -O2 "$OBJDIR"/*.o -o "$BUILD/native_reference" 2>> "$BUILD/build.log" \
  || { tail -80 "$BUILD/build.log"; exit 1; }

echo "Built $BUILD/native_reference"
