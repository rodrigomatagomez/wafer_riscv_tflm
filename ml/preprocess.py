#!/usr/bin/env python3
"""Preprocess selected WM-811K maps into fixed 32x32x2 tensors.

Reproduces claude_implementation_prompt.txt Section 4 (PREPROCESSING AND MODEL),
first paragraph. Channel 0 = waferMap > 0 (die present). Channel 1 =
waferMap == 2 (defective die). Both channels are independently resized to fit
inside a 32x32 canvas, preserving aspect ratio, using nearest-neighbor
interpolation, then centered with zero padding.

Exact resize/padding convention (must match the C++ firmware/host reference
exactly byte-for-byte, so it is pinned here precisely):

  scale = min(32 / H, 32 / W)                      # fit, do not exceed 32 on either axis
  new_h = max(1, round(H * scale))
  new_w = max(1, round(W * scale))
  For output index i in [0, new_h):  src_row = min(H-1, floor((i + 0.5) * H / new_h))
  For output index j in [0, new_w):  src_col = min(W-1, floor((j + 0.5) * W / new_w))
  pad_top  = (32 - new_h) // 2         pad_bottom = 32 - new_h - pad_top
  pad_left = (32 - new_w) // 2         pad_left_... = 32 - new_w - pad_left
  Canvas is zero-initialized; the resized image is placed at
  [pad_top : pad_top+new_h, pad_left : pad_left+new_w].

Usage:
    ml/venv/bin/python3 ml/preprocess.py
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
RESULTS = ROOT / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

CANVAS = 32


def nearest_resize(binary_map: np.ndarray, out_h: int, out_w: int) -> np.ndarray:
    h, w = binary_map.shape
    row_idx = np.minimum(h - 1, np.floor((np.arange(out_h) + 0.5) * h / out_h).astype(np.int64))
    col_idx = np.minimum(w - 1, np.floor((np.arange(out_w) + 0.5) * w / out_w).astype(np.int64))
    return binary_map[np.ix_(row_idx, col_idx)]


def resize_to_canvas(binary_map: np.ndarray, canvas: int = CANVAS) -> np.ndarray:
    h, w = binary_map.shape
    scale = min(canvas / h, canvas / w)
    new_h = max(1, round(h * scale))
    new_w = max(1, round(w * scale))
    new_h = min(new_h, canvas)
    new_w = min(new_w, canvas)
    resized = nearest_resize(binary_map, new_h, new_w)
    out = np.zeros((canvas, canvas), dtype=np.float32)
    pad_top = (canvas - new_h) // 2
    pad_left = (canvas - new_w) // 2
    out[pad_top:pad_top + new_h, pad_left:pad_left + new_w] = resized.astype(np.float32)
    return out


def preprocess_one(wafer_map: np.ndarray) -> np.ndarray:
    """Returns float32 array shape (32,32,2), NHWC channel order, C-order flatten."""
    ch0 = (wafer_map > 0).astype(np.float32)
    ch1 = (wafer_map == 2).astype(np.float32)
    out0 = resize_to_canvas(ch0)
    out1 = resize_to_canvas(ch1)
    return np.stack([out0, out1], axis=-1)  # (32,32,2)


def save_example_figure(sample_id, wafer_map, processed, class_name, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(9, 3))
    axes[0].imshow(wafer_map, cmap="viridis", vmin=0, vmax=2)
    axes[0].set_title(f"original ({wafer_map.shape[0]}x{wafer_map.shape[1]})")
    axes[1].imshow(processed[:, :, 0], cmap="gray", vmin=0, vmax=1)
    axes[1].set_title("channel 0: die present")
    axes[2].imshow(processed[:, :, 1], cmap="gray", vmin=0, vmax=1)
    axes[2].set_title("channel 1: defective die")
    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(f"sample_id={sample_id} class={class_name}")
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


def main():
    manifest = pd.read_csv(PROCESSED / "selection_manifest.csv")
    npz = np.load(PROCESSED / "selected_wafer_maps.npz", allow_pickle=True)

    tensors = np.zeros((len(manifest), CANVAS, CANVAS, 2), dtype=np.float32)
    examples_dir = RESULTS / "preprocessing_examples"
    examples_dir.mkdir(parents=True, exist_ok=True)

    example_picks = manifest.groupby("class_name").head(2)  # 2 examples per class
    saved_examples = []

    for row_pos, row in enumerate(manifest.itertuples(index=False)):
        wm = npz[str(row.sample_id)]
        proc = preprocess_one(wm)
        tensors[row_pos] = proc
        if row.sample_id in set(example_picks["sample_id"]):
            out_path = examples_dir / f"sample_{row.sample_id}_{row.class_name}.png"
            save_example_figure(row.sample_id, wm, proc, row.class_name, out_path)
            saved_examples.append(str(out_path.relative_to(ROOT)))

    np.savez_compressed(
        PROCESSED / "tensors.npz",
        X=tensors,
        sample_id=manifest["sample_id"].to_numpy(),
        class_idx=manifest["class_idx"].to_numpy(),
        split=manifest["split"].to_numpy(),
    )

    report = {
        "canvas_size": CANVAS,
        "n_samples": int(len(manifest)),
        "tensor_shape": list(tensors.shape),
        "value_range_observed": [float(tensors.min()), float(tensors.max())],
        "unique_values_observed": sorted(set(np.unique(tensors).tolist())),
        "example_figures": saved_examples,
    }
    with (RESULTS / "preprocessing_report.json").open("w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    print("Wrote:", PROCESSED / "tensors.npz")


if __name__ == "__main__":
    main()
