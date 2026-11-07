#!/usr/bin/env bash
# Source this file to get a working RV32IM bare-metal toolchain in $PATH.
# See docs/decisions.md D-004 for why the library shim is needed.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

source /etc/profile.d/*lmod* 2>/dev/null || true
# NOTE: must NOT pipe this through anything (e.g. `| grep`) — piping runs
# `module load` in a subshell, so the PATH/env changes it makes are lost
# the moment the pipeline exits. Caught by hand: every toolchain binary
# silently vanished from PATH after adding `| grep -v '^[INFO]'` for log
# cosmetics. Redirect fd 2 only, directly, no pipeline.
module load riscv-gnu-toolchain/elf-multilib/2026.07.15-elf 2>/dev/null

export LD_LIBRARY_PATH="$ROOT/third_party/lib_shim:${LD_LIBRARY_PATH:-}"

echo "RV32IM toolchain ready: $(which riscv64-unknown-elf-gcc)"
