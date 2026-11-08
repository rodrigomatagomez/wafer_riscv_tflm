// Bare-metal rv32im_core firmware: runs the actual pinned-commit TFLM
// reference-kernel interpreter on real RTL-simulated hardware, over the
// same 20 deterministic comparison cases as sw/app/main_native.cc, and
// reports results over the MMIO register file (prompt Section 5) so the
// testbench can capture them from genuine processor transactions.
//
// CASE_START / CASE_COUNT (compile-time, e.g. -DCASE_START=0 -DCASE_COUNT=1):
// restrict this firmware image to a sub-range of the fixed 20-case
// manifest, so a single RTL invocation (currently several minutes of
// wall-clock simulation time per Invoke(), see docs/issues.md ISS-004) can
// complete one case, or a few, at a time instead of requiring all 20 to
// finish in one run. MMIO_CASE_ID always carries the case's ORIGINAL
// global index (0..19) from results/comparison_manifest.json -- it is
// never re-based to a local 0-based index -- so a partial run's results
// remain directly comparable to build/native_reference/output.jsonl by
// case_id. Defaults (no -D flags) reproduce the original full-20-case
// behavior exactly.
#ifndef CASE_START
#define CASE_START 0
#endif
#ifndef CASE_COUNT
#define CASE_COUNT N_COMPARISON_CASES
#endif

#include <cstring>

#include "wafer_common.h"
#include "../startup/mmio.h"

static_assert(CASE_START >= 0, "CASE_START must be >= 0");
static_assert(CASE_COUNT >= 1, "CASE_COUNT must be >= 1");
static_assert(CASE_START + CASE_COUNT <= N_COMPARISON_CASES,
              "CASE_START + CASE_COUNT exceeds N_COMPARISON_CASES -- out of range");

// File-scope (true global) objects: constructed unconditionally via
// crt0.S's .init_array loop. An earlier draft declared these as
// function-local statics inside main(); on this toolchain/target
// combination, local statics with non-trivial constructors use Itanium-ABI
// "guarded" dynamic initialization (a hidden guard-variable check), and
// that guarded path silently failed to construct tflite::MicroInterpreter
// -- its internal MicroAllocator ended up with whatever garbage was in
// .bss instead of running its constructor, so model_is_allocating_ read as
// true on the very first AllocateTensors() call. Diagnostic markers
// confirmed control flow reached past the declaration (proving the guard
// branch was taken) while the object's observable state showed the
// constructor never ran. Moving these to global scope uses the simple,
// unconditional .init_array mechanism instead, which this project's own
// crt0.S already drives explicitly.
alignas(16) static uint8_t tensor_arena[kTensorArenaSize];
static tflite::MicroMutableOpResolver<2> resolver;
static const tflite::Model* model = tflite::GetModel(g_wafer_model_data);
static tflite::MicroInterpreter interpreter(model, resolver, tensor_arena,
                                             kTensorArenaSize);

int main() {
  tflite::InitializeTarget();
  mmio_putc('1');

  resolver.AddFullyConnected();
  mmio_putc('3');
  resolver.AddReshape();
  mmio_putc('4');
  mmio_putc('6');
  if (interpreter.AllocateTensors() != kTfLiteOk) {
    MMIO_STATUS = 2; // firmware/TFLM error
    __asm__ volatile("ebreak");
    while (1) {}
  }

  TfLiteTensor* input = interpreter.input(0);
  TfLiteTensor* output = interpreter.output(0);

  // i is the GLOBAL case index (0..N_COMPARISON_CASES-1) throughout --
  // CASE_START only moves where this loop begins, it never re-bases the
  // numbering written to MMIO_CASE_ID or used to index comparison_inputs.
  for (int i = CASE_START; i < CASE_START + CASE_COUNT; i++) {
    MMIO_CASE_ID = static_cast<uint32_t>(i);
    memcpy(input->data.int8, comparison_inputs[i], INPUT_BYTES_PER_CASE);

    MMIO_MEASURE = 1; // immediately before Invoke()
    TfLiteStatus status = interpreter.Invoke();
    MMIO_MEASURE = 2; // immediately after Invoke()

    if (status != kTfLiteOk) {
      MMIO_STATUS = 2;
      __asm__ volatile("ebreak");
      while (1) {}
    }

    int8_t scores[4];
    for (int c = 0; c < 4; c++) scores[c] = output->data.int8[c];
    int pred = ArgmaxTieLowestIndex(scores);

    MMIO_SCORE_0 = static_cast<uint32_t>(static_cast<int32_t>(scores[0]));
    MMIO_SCORE_1 = static_cast<uint32_t>(static_cast<int32_t>(scores[1]));
    MMIO_SCORE_2 = static_cast<uint32_t>(static_cast<int32_t>(scores[2]));
    MMIO_SCORE_3 = static_cast<uint32_t>(static_cast<int32_t>(scores[3]));
    MMIO_PREDICTED_CLASS = static_cast<uint32_t>(pred);
  }

  MMIO_STATUS = 1; // all cases finished without execution errors
  __asm__ volatile("ebreak");
  while (1) {}
}
