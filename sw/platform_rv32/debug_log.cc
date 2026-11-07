// Bare-metal rv32im_core implementation of TFLM's required DebugLog hook
// (tensorflow/lite/micro/new_platform_support.md Step 2). Replaces the
// tflite-micro tree's default (which calls vfprintf(stderr, ...), not
// available without an OS). Output goes to MMIO_TX one byte at a time.
// micro_time.cc and system_setup.cc are NOT overridden: their upstream
// default implementations already return 0 / are no-ops, which is exactly
// what a CSR-free, no-OS target needs (prompt Section 5: "Do not rely on
// CSRs for cycle counting" -- the real Invoke() cycle measurement is done
// externally by the testbench via the MEASURE MMIO register, not through
// this TFLM-internal profiling hook).
#include <cstdarg>
#include <cstdio>

#include "tensorflow/lite/micro/debug_log.h"
#include "../startup/mmio.h"

extern "C" void DebugLog(const char* format, va_list args) {
  char buffer[256];
  int n = vsnprintf(buffer, sizeof(buffer), format, args);
  if (n < 0) return;
  if (n >= static_cast<int>(sizeof(buffer))) n = sizeof(buffer) - 1;
  for (int i = 0; i < n; i++) {
    mmio_putc(buffer[i]);
  }
}

extern "C" int DebugVsnprintf(char* buffer, size_t buf_size, const char* format,
                               va_list vlist) {
  return vsnprintf(buffer, buf_size, format, vlist);
}
