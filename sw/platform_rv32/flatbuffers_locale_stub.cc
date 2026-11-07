// Bare-metal stub for flatbuffers::ClassicLocale. The full upstream
// implementation (third_party/flatbuffers/src/util.cpp) uses realpath(),
// newlocale()/freelocale(), none of which newlib-nano provides for this
// target. Those locale-independent strtod/strtoll helpers are only
// exercised by flatbuffers *text* (JSON/schema) parsing, which this
// firmware never does at runtime -- the model is loaded as a compiled
// binary via tflite::GetModel(), not parsed from text. This stub only
// exists to satisfy the linker for code paths (e.g. flexbuffers::Reference
// accessors pulled in transitively by some reference kernels) that are
// never actually invoked for this model's operator set.
#include "flatbuffers/util.h"

namespace flatbuffers {
#if defined(FLATBUFFERS_LOCALE_INDEPENDENT) && (FLATBUFFERS_LOCALE_INDEPENDENT > 0)
ClassicLocale::ClassicLocale() {}
ClassicLocale::~ClassicLocale() {}
ClassicLocale ClassicLocale::instance_;
#endif
}  // namespace flatbuffers
