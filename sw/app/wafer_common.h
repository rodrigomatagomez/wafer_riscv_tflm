// Shared TFLM setup for both the native reference and the bare-metal
// firmware: same pinned tflite-micro commit, same model bytes (compiled
// once by ml/model_to_c_array.py), same reference kernels, same quantized
// input bytes (ml/select_comparison_cases.py). Only the reporting /
// cycle-measurement mechanism differs per platform (see sw/app/main_native.cc
// vs sw/app/main_firmware.cc).
#pragma once

#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_log.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/system_setup.h"
#include "wafer_model_data.h"
#include "comparison_inputs.h"

// Sized empirically (see docs/findings.md / results/memory_usage.json for
// the measured peak via tflite::RecordingMicroInterpreter during bring-up);
// kept here as the single source of truth for both platforms.
constexpr int kTensorArenaSize = 8192;

inline int ArgmaxTieLowestIndex(const int8_t scores[4]) {
  int best = 0;
  for (int i = 1; i < 4; i++) {
    if (scores[i] > scores[best]) best = i;
  }
  return best;
}
