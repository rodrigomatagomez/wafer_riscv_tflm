#!/usr/bin/env python3
"""Train Model A (and Model B if needed), quantize to int8, evaluate.

Reproduces claude_implementation_prompt.txt Section 4 (model/training/
quantization protocol) and the quality-target check in Section 11.

Usage:
    ml/venv/bin/python3 ml/train_and_quantize.py
"""
import hashlib
import json
import os
import random
from pathlib import Path

os.environ["PYTHONHASHSEED"] = "2026"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
os.environ["TF_DETERMINISTIC_OPS"] = "1"

import numpy as np
import tensorflow as tf
from sklearn.metrics import f1_score, confusion_matrix, accuracy_score

SEED = 2026
ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
MODELS = ROOT / "models"
RESULTS = ROOT / "results"
MODELS.mkdir(parents=True, exist_ok=True)
RESULTS.mkdir(parents=True, exist_ok=True)

CLASSES = ["Center", "Edge-Ring", "Scratch", "none"]
NUM_CLASSES = 4
QUALITY_TARGET_MACRO_F1 = 0.85
REP_SAMPLES_PER_CLASS_CAP = 50  # 4 classes * 50 = 200 total cap, per prompt


def set_seeds(seed=SEED):
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_splits():
    data = np.load(PROCESSED / "tensors.npz", allow_pickle=True)
    X = data["X"].astype(np.float32)
    y = data["class_idx"].astype(np.int64)
    split = data["split"]
    masks = {s: (split == s) for s in ["train", "val", "test"]}
    out = {}
    for s, m in masks.items():
        out[s] = (X[m], y[m])
    return out


def build_model(hidden_units: int) -> tf.keras.Model:
    inputs = tf.keras.Input(shape=(32, 32, 2), name="wafer_input")
    x = tf.keras.layers.Flatten()(inputs)
    x = tf.keras.layers.Dense(hidden_units, activation="relu", name=f"dense_{hidden_units}")(x)
    outputs = tf.keras.layers.Dense(NUM_CLASSES, activation=None, name="logits")(x)
    model = tf.keras.Model(inputs, outputs)
    return model


def train_one(hidden_units: int, splits, tag: str):
    set_seeds(SEED)
    model = build_model(hidden_units)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True),
        metrics=["accuracy"],
    )
    Xtr, ytr = splits["train"]
    Xva, yva = splits["val"]

    ckpt_path = MODELS / f"model_{tag}_best.weights.h5"
    callbacks = [
        tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=3, restore_best_weights=True),
        tf.keras.callbacks.ModelCheckpoint(str(ckpt_path), monitor="val_loss", save_best_only=True, save_weights_only=True),
    ]
    history = model.fit(
        Xtr, ytr,
        validation_data=(Xva, yva),
        epochs=20,
        batch_size=64,
        shuffle=True,
        callbacks=callbacks,
        verbose=2,
    )
    # EarlyStopping restore_best_weights already applied; also persist full model.
    saved_model_path = MODELS / f"model_{tag}_float.keras"
    model.save(saved_model_path)
    hist_path = RESULTS / f"training_history_{tag}.json"
    with hist_path.open("w") as f:
        json.dump({k: [float(v) for v in vv] for k, vv in history.history.items()}, f, indent=2)
    return model, saved_model_path


def eval_float(model, X, y):
    logits = model.predict(X, verbose=0)
    pred = np.argmax(logits, axis=1)
    macro_f1 = f1_score(y, pred, average="macro")
    per_class_f1 = f1_score(y, pred, average=None, labels=list(range(NUM_CLASSES))).tolist()
    acc = accuracy_score(y, pred)
    cm = confusion_matrix(y, pred, labels=list(range(NUM_CLASSES))).tolist()
    return {
        "macro_f1": float(macro_f1),
        "per_class_f1": {CLASSES[i]: per_class_f1[i] for i in range(NUM_CLASSES)},
        "accuracy": float(acc),
        "confusion_matrix": cm,
        "n": int(len(y)),
    }


def make_representative_dataset(splits):
    Xtr, ytr = splits["train"]
    rng = np.random.default_rng(SEED)
    chosen = []
    for c in range(NUM_CLASSES):
        idx = np.where(ytr == c)[0]
        idx_sorted = np.sort(idx)
        perm = rng.permutation(len(idx_sorted))
        take = idx_sorted[perm[: min(REP_SAMPLES_PER_CLASS_CAP, len(idx_sorted))]]
        chosen.append(take)
    chosen = np.concatenate(chosen)
    rep_X = Xtr[chosen]

    def gen():
        for i in range(rep_X.shape[0]):
            yield [rep_X[i:i + 1].astype(np.float32)]

    return gen, int(rep_X.shape[0])


def quantize_int8(saved_model_path: Path, splits, tag: str):
    rep_gen, n_rep = make_representative_dataset(splits)
    converter = tf.lite.TFLiteConverter.from_keras_model(tf.keras.models.load_model(saved_model_path))
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = rep_gen
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    tflite_model = converter.convert()
    out_path = MODELS / f"model_{tag}_int8.tflite"
    out_path.write_bytes(tflite_model)
    return out_path, n_rep


def inspect_tflite(tflite_path: Path):
    interp = tf.lite.Interpreter(model_path=str(tflite_path))
    interp.allocate_tensors()
    inp = interp.get_input_details()[0]
    out = interp.get_output_details()[0]
    ops = []
    try:
        ops = [d["op_name"] if "op_name" in d else str(d) for d in interp._get_ops_details()]
    except Exception:
        pass
    return {
        "input": {
            "dtype": str(inp["dtype"]),
            "shape": inp["shape"].tolist(),
            "scale": float(inp["quantization"][0]),
            "zero_point": int(inp["quantization"][1]),
        },
        "output": {
            "dtype": str(out["dtype"]),
            "shape": out["shape"].tolist(),
            "scale": float(out["quantization"][0]),
            "zero_point": int(out["quantization"][1]),
        },
        "operators": ops,
    }, interp


def eval_tflite(interp, X, y, input_detail, output_detail):
    scale, zp = input_detail["quantization"][0], input_detail["quantization"][1]
    preds = []
    for i in range(X.shape[0]):
        x_q = np.round(X[i:i + 1] / scale + zp)
        x_q = np.clip(x_q, -128, 127).astype(np.int8)
        interp.set_tensor(input_detail["index"], x_q)
        interp.invoke()
        logits = interp.get_tensor(output_detail["index"])[0]
        preds.append(int(np.argmax(logits)))
    preds = np.array(preds)
    macro_f1 = f1_score(y, preds, average="macro")
    per_class_f1 = f1_score(y, preds, average=None, labels=list(range(NUM_CLASSES))).tolist()
    acc = accuracy_score(y, preds)
    cm = confusion_matrix(y, preds, labels=list(range(NUM_CLASSES))).tolist()
    return {
        "macro_f1": float(macro_f1),
        "per_class_f1": {CLASSES[i]: per_class_f1[i] for i in range(NUM_CLASSES)},
        "accuracy": float(acc),
        "confusion_matrix": cm,
        "n": int(len(y)),
    }


def run_config(hidden_units: int, tag: str, splits):
    print(f"\n=== Training model {tag} (hidden={hidden_units}) ===", flush=True)
    model, saved_path = train_one(hidden_units, splits, tag)

    float_metrics = {
        "val": eval_float(model, *splits["val"]),
        "test": eval_float(model, *splits["test"]),
    }

    tflite_path, n_rep = quantize_int8(saved_path, splits, tag)
    meta, interp = inspect_tflite(tflite_path)
    input_detail = interp.get_input_details()[0]
    output_detail = interp.get_output_details()[0]

    int8_metrics = {
        "val": eval_tflite(interp, *splits["val"], input_detail, output_detail),
        "test": eval_tflite(interp, *splits["test"], input_detail, output_detail),
    }

    return {
        "tag": tag,
        "hidden_units": hidden_units,
        "float_checkpoint": str(saved_path.relative_to(ROOT)),
        "tflite_path": str(tflite_path.relative_to(ROOT)),
        "tflite_sha256": sha256_file(tflite_path),
        "representative_samples_used": n_rep,
        "quantization": meta,
        "float_metrics": float_metrics,
        "int8_metrics": int8_metrics,
    }


def main():
    splits = load_splits()
    for name, (X, y) in splits.items():
        print(name, X.shape, y.shape, "class counts:", np.bincount(y, minlength=NUM_CLASSES))

    result_a = run_config(16, "A", splits)
    print(f"\nModel A quantized val macro-F1 = {result_a['int8_metrics']['val']['macro_f1']:.4f}", flush=True)

    all_results = {"A": result_a}
    chosen_tag = "A"

    if result_a["int8_metrics"]["val"]["macro_f1"] < QUALITY_TARGET_MACRO_F1:
        print("Model A below quality target on quantized validation data; training Model B (hidden=32).", flush=True)
        result_b = run_config(32, "B", splits)
        all_results["B"] = result_b
        print(f"Model B quantized val macro-F1 = {result_b['int8_metrics']['val']['macro_f1']:.4f}", flush=True)
        if result_b["int8_metrics"]["val"]["macro_f1"] > result_a["int8_metrics"]["val"]["macro_f1"]:
            chosen_tag = "B"

    chosen = all_results[chosen_tag]
    report = {
        "seed": SEED,
        "classes": CLASSES,
        "quality_target_macro_f1": QUALITY_TARGET_MACRO_F1,
        "configurations_tried": list(all_results.keys()),
        "chosen_configuration": chosen_tag,
        "selection_rule": "quantized validation macro-F1 only",
        "results": all_results,
        "final_test_macro_f1_int8": chosen["int8_metrics"]["test"]["macro_f1"],
        "quality_target_met_on_test": bool(chosen["int8_metrics"]["test"]["macro_f1"] >= QUALITY_TARGET_MACRO_F1),
    }
    with (RESULTS / "ml_metrics.json").open("w") as f:
        json.dump(report, f, indent=2)
    print("\n=== FINAL ===")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    print("Wrote:", RESULTS / "ml_metrics.json")


if __name__ == "__main__":
    main()
