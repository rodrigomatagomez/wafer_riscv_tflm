#!/usr/bin/env python3
"""Select up to 1000 unique WM-811K maps per class and split by lot.

Reproduces claude_implementation_prompt.txt Section 3 (REAL DATA AND PROVENANCE).

Pandas compatibility note: LSWMD.pkl was pickled with an old pandas version
whose internal module layout changed (pandas.indexes -> pandas.core.indexes.*,
and pandas.core.indexes.numeric was later removed entirely in pandas 2.x).
The sys.modules aliases below are the actual fix verified against pandas 2.3.3
running on Python 3.9 in this project's isolated venv (ml/venv). The archive
also contains legacy Python 2 byte strings, hence encoding="latin1".

Usage:
    ml/venv/bin/python3 ml/select_and_split.py
"""
import hashlib
import json
import sys
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pandas.core.indexes as _idx
import pandas.core.indexes.base as _base
import pandas.core.indexes.range as _range

sys.modules["pandas.indexes"] = _idx
sys.modules["pandas.indexes.base"] = _base
sys.modules["pandas.indexes.range"] = _range

ROOT = Path(__file__).resolve().parents[1]
RAW_PKL = ROOT / "data" / "raw" / "LSWMD.pkl"
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SEED = 2026
CLASSES = ["Center", "Edge-Ring", "Scratch", "none"]  # fixed output mapping 0..3
CLASS_TO_IDX = {c: i for i, c in enumerate(CLASSES)}
PER_CLASS_CAP = 1000
SPLIT_TARGET = {"train": 0.70, "val": 0.15, "test": 0.15}


def extract_failure_type(cell):
    """failureType cells are either an empty ndarray or a 1x1 ndarray of str."""
    if hasattr(cell, "size") and cell.size > 0:
        return str(cell[0][0])
    return None


def hash_map(arr: np.ndarray) -> str:
    return hashlib.sha1(arr.tobytes() + str(arr.shape).encode("utf-8")).hexdigest()


def load_raw_dataframe() -> pd.DataFrame:
    with RAW_PKL.open("rb") as f:
        df = pickle.load(f, encoding="latin1")
    return df


def main():
    print("Loading LSWMD.pkl ...", flush=True)
    df = load_raw_dataframe()
    df = df.reset_index(drop=True)
    df["sample_id"] = df.index.astype(int)
    df["ft"] = df["failureType"].apply(extract_failure_type)

    sub = df[df["ft"].isin(CLASSES)].copy()
    sub["map_hash"] = sub["waferMap"].apply(hash_map)

    # Deterministic de-duplication within each class: keep the first
    # occurrence (lowest original sample_id) of each distinct map.
    sub = sub.sort_values("sample_id")
    before = len(sub)
    sub = sub.drop_duplicates(subset=["ft", "map_hash"], keep="first")
    print(f"Exact-duplicate maps removed within target classes: {before - len(sub)}", flush=True)

    rng = np.random.default_rng(SEED)
    selected_rows = []
    selection_report = {}
    for cls in CLASSES:  # fixed, deterministic class processing order
        pool = sub[sub["ft"] == cls]["sample_id"].to_numpy()
        pool_sorted = np.sort(pool)  # deterministic order before shuffling
        perm = rng.permutation(len(pool_sorted))
        chosen = pool_sorted[perm[: min(PER_CLASS_CAP, len(pool_sorted))]]
        selection_report[cls] = {
            "unique_available": int(len(pool_sorted)),
            "selected": int(len(chosen)),
        }
        selected_rows.append(chosen)
    selected_ids = np.concatenate(selected_rows)
    picked = sub[sub["sample_id"].isin(selected_ids)].copy()
    picked = picked.sort_values("sample_id").reset_index(drop=True)
    print("Selection report:", json.dumps(selection_report, indent=2), flush=True)

    # ---- Lot-aware split ----
    # Assign whole lots to splits (never split a lot across train/val/test).
    # Greedy deterministic bin-packing: process lots in a seeded random order,
    # each lot goes to whichever split currently has the largest remaining
    # deficit versus its 70/15/15 target, counted in samples.
    lot_groups = picked.groupby("lotName")
    lot_names = sorted(lot_groups.groups.keys())  # deterministic base order
    lot_order_perm = rng.permutation(len(lot_names))
    lot_names = [lot_names[i] for i in lot_order_perm]

    total = len(picked)
    target_counts = {k: v * total for k, v in SPLIT_TARGET.items()}
    current_counts = {k: 0 for k in SPLIT_TARGET}
    lot_to_split = {}
    for lot in lot_names:
        size = len(lot_groups.get_group(lot))
        deficits = {k: target_counts[k] - current_counts[k] for k in SPLIT_TARGET}
        best_split = max(deficits, key=lambda k: deficits[k])
        lot_to_split[lot] = best_split
        current_counts[best_split] += size

    picked["split"] = picked["lotName"].map(lot_to_split)

    # ---- Verify all 4 classes appear in all 3 splits; repair if needed ----
    def class_split_counts(frame):
        return frame.groupby(["ft", "split"]).size().unstack(fill_value=0)

    counts = class_split_counts(picked)
    missing = []
    for cls in CLASSES:
        for sp in SPLIT_TARGET:
            c = int(counts.loc[cls, sp]) if (cls in counts.index and sp in counts.columns) else 0
            if c == 0:
                missing.append((cls, sp))

    repairs = []
    for cls, sp in missing:
        # Find a single-sample lot of this class currently in a split that has
        # more than one lot carrying this class, and move it to `sp`.
        cls_rows = picked[picked["ft"] == cls]
        lot_sizes_for_cls = cls_rows.groupby("lotName").size()
        donor_candidates = [
            lot for lot in lot_sizes_for_cls.index
            if lot_to_split[lot] != sp and lot_sizes_for_cls[lot] == 1
        ]
        if not donor_candidates:
            repairs.append({"class": cls, "split": sp, "status": "unrepaired_no_donor_lot"})
            continue
        donor_lot = sorted(donor_candidates)[0]
        picked.loc[picked["lotName"] == donor_lot, "split"] = sp
        lot_to_split[donor_lot] = sp
        repairs.append({"class": cls, "split": sp, "status": "moved_lot", "lot": donor_lot})

    # ---- Integrity checks ----
    lot_split_map = picked.groupby("lotName")["split"].nunique()
    lots_split_across = lot_split_map[lot_split_map > 1]
    assert len(lots_split_across) == 0, f"Lot(s) spanning multiple splits: {lots_split_across}"

    dup_hash_counts = picked.groupby("map_hash")["split"].nunique()
    dup_across_split = dup_hash_counts[dup_hash_counts > 1]
    cross_split_duplicate_maps = int(len(dup_across_split))

    final_counts = class_split_counts(picked)
    final_total = len(picked)
    final_props = {sp: float(picked["split"].eq(sp).sum()) / final_total for sp in SPLIT_TARGET}

    manifest = picked[["sample_id", "lotName", "ft", "split", "map_hash"]].rename(
        columns={"lotName": "lot_id", "ft": "class_name"}
    )
    manifest["class_idx"] = manifest["class_name"].map(CLASS_TO_IDX)
    manifest = manifest.sort_values("sample_id").reset_index(drop=True)
    manifest.to_csv(OUT_DIR / "selection_manifest.csv", index=False)

    # Cache the selected raw waferMap arrays (as object arrays) so later
    # preprocessing does not need to re-load the 2 GiB pickle.
    maps_by_id = {int(r.sample_id): df.loc[r.sample_id, "waferMap"] for _, r in manifest.iterrows()}
    np.savez_compressed(
        OUT_DIR / "selected_wafer_maps.npz",
        **{str(k): v for k, v in maps_by_id.items()},
    )

    report = {
        "seed": SEED,
        "classes": CLASSES,
        "per_class_cap": PER_CLASS_CAP,
        "selection_report": selection_report,
        "exact_duplicates_removed_within_class": int(before - len(sub)),
        "total_selected": int(final_total),
        "split_target_proportions": SPLIT_TARGET,
        "split_actual_proportions": final_props,
        "class_by_split_counts": {
            cls: {sp: int(final_counts.loc[cls, sp]) if (cls in final_counts.index and sp in final_counts.columns) else 0
                  for sp in SPLIT_TARGET}
            for cls in CLASSES
        },
        "unique_lots_selected": int(picked["lotName"].nunique()),
        "lots_spanning_multiple_splits": int(len(lots_split_across)),
        "cross_split_duplicate_maps": cross_split_duplicate_maps,
        "missing_class_split_combinations_before_repair": missing,
        "repairs_applied": repairs,
    }
    with (OUT_DIR / "selection_report.json").open("w") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))
    print("Wrote:", OUT_DIR / "selection_manifest.csv")
    print("Wrote:", OUT_DIR / "selected_wafer_maps.npz")
    print("Wrote:", OUT_DIR / "selection_report.json")


if __name__ == "__main__":
    main()
