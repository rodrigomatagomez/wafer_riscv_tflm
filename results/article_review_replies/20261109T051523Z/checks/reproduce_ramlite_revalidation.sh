#!/usr/bin/env bash
# Reproduces the 4 new, bounded RAM-lite re-validation runs (+ 2 repetitions
# each of the random-program pair) used in this review-reply package.
# Does NOT run automatically as part of publishing this package -- this is a
# recipe for a future run, derived only from scripts/build_fw.sh,
# scripts/gen_random_program.py, and the installed zenith --help, not
# invented. See ../checks/commands_used.txt for the exact commands actually
# executed when this evidence was produced (2026-11-08/09).
#
# Usage:
#   PORTAL_PATH=$(flatpak-spawn --host true 2>/dev/null; \
#     your-mcp-call-to list_projects | jq -r .active_project.root_path) \
#   bash reproduce_ramlite_revalidation.sh
#
# PORTAL_PATH is session-specific (assigned by xdg-document-portal on each
# Animas grant) and is NOT hard-coded here -- re-read it live via
# mcp__animas__list_projects before each use.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
: "${PORTAL_PATH:?Set PORTAL_PATH to the current xdg-document-portal root (see mcp__animas__list_projects.active_project.root_path)}"
OUT="${1:-$ROOT/results/rtl_logs}"
mkdir -p "$OUT"

cd "$ROOT"
bash scripts/build_fw.sh test_002_loads_stores tb/directed/test_002_loads_stores.S

# Sanity: confirm build/random_program/random.hex matches a fresh regen
TMP="$(mktemp -d)"
python3 scripts/gen_random_program.py 1100 "$TMP/random_check"
diff "$TMP/random_check.hex" build/random_program/random.hex
rm -rf "$TMP"

P="$PORTAL_PATH"

flatpak run --branch=1.0.2 --command=sh com.mifraltech.animaseda -c \
  "cd '$P' && zenith rtl/*.sv tb/*.sv -top soc_tb \
   +MEMFILE=build/test_002_loads_stores/test_002_loads_stores.hex \
   +MAXCYCLES=200000 +TRACE=1 +RUNID=ramlite_reval_a_full \
   +READYWAIT=3 +RANDWAIT=5 +FIXEDLAT=4 +HEARTBEAT=0" \
  > "$OUT/ramlite_reval_a_full.log" 2>&1

flatpak run --branch=1.0.2 --command=sh com.mifraltech.animaseda -c \
  "cd '$P' && zenith rtl/*.sv tb/*.sv -top soc_tb +define+RAM_LITE \
   +MEMFILE=build/test_002_loads_stores/test_002_loads_stores.hex \
   +MAXCYCLES=200000 +TRACE=1 +RUNID=ramlite_reval_b_lite \
   +READYWAIT=3 +RANDWAIT=5 +FIXEDLAT=4 +HEARTBEAT=0" \
  > "$OUT/ramlite_reval_b_lite.log" 2>&1

for rep in "" _rep2 _rep3; do
  flatpak run --branch=1.0.2 --command=sh com.mifraltech.animaseda -c \
    "cd '$P' && zenith --seed 4242 rtl/*.sv tb/*.sv -top soc_tb \
     +MEMFILE=build/random_program/random.hex +MAXCYCLES=200000 +TRACE=1 \
     +RUNID=ramlite_reval_c_full$rep +FIXEDLAT=3 +READYWAIT=2 +RANDWAIT=5 \
     +HEARTBEAT=0" > "$OUT/ramlite_reval_c_full$rep.log" 2>&1

  flatpak run --branch=1.0.2 --command=sh com.mifraltech.animaseda -c \
    "cd '$P' && zenith --seed 4242 rtl/*.sv tb/*.sv -top soc_tb +define+RAM_LITE \
     +MEMFILE=build/random_program/random.hex +MAXCYCLES=200000 +TRACE=1 \
     +RUNID=ramlite_reval_d_lite$rep +FIXEDLAT=3 +READYWAIT=2 +RANDWAIT=5 \
     +HEARTBEAT=0" > "$OUT/ramlite_reval_d_lite$rep.log" 2>&1
done

echo "Banners (verify before trusting any run):"
grep -m1 "^SIM_BANNER" "$OUT"/ramlite_reval_*.log

echo
echo "Instruction-level diffs (expect exit 0 once cycle= is stripped):"
diff <(grep "^RETIRE" "$OUT/ramlite_reval_a_full.log" | sed -E 's/cycle=[0-9]+/cycle=X/') \
     <(grep "^RETIRE" "$OUT/ramlite_reval_b_lite.log" | sed -E 's/cycle=[0-9]+/cycle=X/') \
  && echo "test_002 full vs lite: instruction-level MATCH"
diff <(grep "^RETIRE" "$OUT/ramlite_reval_c_full.log" | sed -E 's/cycle=[0-9]+/cycle=X/') \
     <(grep "^RETIRE" "$OUT/ramlite_reval_d_lite.log" | sed -E 's/cycle=[0-9]+/cycle=X/') \
  && echo "random1100 full vs lite: instruction-level MATCH"
