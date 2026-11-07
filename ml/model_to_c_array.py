#!/usr/bin/env python3
"""Embed the chosen quantized .tflite model as a C array, in the same
format TFLM's own examples use (see third_party/tflm_tree/examples/
hello_world/models/*.cc), so the exact same model bytes are linked into
both the native reference and the bare-metal firmware.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
SW_GEN = ROOT / "sw" / "generated"
SW_GEN.mkdir(parents=True, exist_ok=True)

ml_metrics = json.load(open(RESULTS / "ml_metrics.json"))
TAG = ml_metrics["chosen_configuration"]
TFLITE_PATH = ROOT / "models" / f"model_{TAG}_int8.tflite"
SYM = "g_wafer_model_data"


def main():
    data = TFLITE_PATH.read_bytes()
    h = SW_GEN / "wafer_model_data.h"
    h.write_text(
        "#include <cstdint>\n\n"
        f"constexpr unsigned int {SYM}_size = {len(data)};\n"
        f"extern const unsigned char {SYM}[];\n"
    )
    cc = SW_GEN / "wafer_model_data.cc"
    hexvals = ",".join(f"0x{b:02x}" for b in data)
    cc.write_text(
        '#include "wafer_model_data.h"\n\n'
        f"alignas(16) const unsigned char {SYM}[] = {{{hexvals}}};\n"
    )
    print(f"Wrote {h} and {cc} ({len(data)} bytes from {TFLITE_PATH})")


if __name__ == "__main__":
    main()
