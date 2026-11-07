// Native (host x86) TFLM reference oracle. Same pinned tflite-micro
// commit/kernels/model bytes as the bare-metal firmware (sw/app/
// main_firmware.cc); this is the "exact-output oracle" required by
// claude_implementation_prompt.txt Section 7. Prints one JSON line per
// case to stdout for scripts/compare_results.py to consume.
#include <cstdio>
#include <cstring>

#include "wafer_common.h"

int main() {
  tflite::InitializeTarget();

  static tflite::MicroMutableOpResolver<2> resolver;
  resolver.AddFullyConnected();
  resolver.AddReshape();

  const tflite::Model* model = tflite::GetModel(g_wafer_model_data);
  alignas(16) static uint8_t tensor_arena[kTensorArenaSize];
  static tflite::MicroInterpreter interpreter(model, resolver, tensor_arena,
                                               kTensorArenaSize);
  if (interpreter.AllocateTensors() != kTfLiteOk) {
    fprintf(stderr, "AllocateTensors failed\n");
    return 1;
  }
  fprintf(stderr, "arena_used_bytes=%zu\n", interpreter.arena_used_bytes());

  TfLiteTensor* input = interpreter.input(0);
  TfLiteTensor* output = interpreter.output(0);

  for (int i = 0; i < N_COMPARISON_CASES; i++) {
    memcpy(input->data.int8, comparison_inputs[i], INPUT_BYTES_PER_CASE);
    if (interpreter.Invoke() != kTfLiteOk) {
      fprintf(stderr, "Invoke failed on case %d\n", i);
      return 1;
    }
    int8_t scores[4];
    for (int c = 0; c < 4; c++) scores[c] = output->data.int8[c];
    int pred = ArgmaxTieLowestIndex(scores);
    printf("{\"case_id\": %d, \"scores\": [%d, %d, %d, %d], \"predicted_class\": %d}\n",
           i, scores[0], scores[1], scores[2], scores[3], pred);
  }
  return 0;
}
