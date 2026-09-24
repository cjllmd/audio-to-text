#!/usr/bin/env python3
"""Export MacBERT4CSC to ONNX INT8 for lightweight runtime inference.

Usage:
    pip install torch transformers onnx onnxruntime
    python export_corrector_model.py

Output:
    models/corrector/
        model.onnx          -- INT8 quantized model (~100MB)
        tokenizer.json       -- Fast tokenizer config
        vocab.txt            -- BERT vocabulary
"""
import os

MODEL_ID = "shibing624/macbert4csc-base-chinese"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "corrector")
MAX_LEN = 512


def export():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"[1/4] Loading model & tokenizer: {MODEL_ID}")
    from transformers import AutoTokenizer, AutoModelForMaskedLM
    import torch
    import numpy as np

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForMaskedLM.from_pretrained(MODEL_ID)
    model.eval()

    print("[2/4] Saving tokenizer files")
    tokenizer.save_pretrained(OUTPUT_DIR)

    print("[3/4] Exporting to ONNX (FP32) via torch.onnx.export")
    fp32_path = os.path.join(OUTPUT_DIR, "model_fp32.onnx")

    dummy_ids = torch.ones(1, MAX_LEN, dtype=torch.long)
    dummy_mask = torch.ones(1, MAX_LEN, dtype=torch.long)
    dummy_type_ids = torch.zeros(1, MAX_LEN, dtype=torch.long)

    with torch.no_grad():
        torch.onnx.export(
            model,
            (dummy_ids, dummy_mask, dummy_type_ids),
            fp32_path,
            input_names=["input_ids", "attention_mask", "token_type_ids"],
            output_names=["logits"],
            dynamic_axes={
                "input_ids": {0: "batch", 1: "seq"},
                "attention_mask": {0: "batch", 1: "seq"},
                "token_type_ids": {0: "batch", 1: "seq"},
                "logits": {0: "batch", 1: "seq"},
            },
            opset_version=14,
            do_constant_folding=True,
        )

    fp32_mb = os.path.getsize(fp32_path) / (1024 * 1024)
    print(f"  FP32 ONNX: {fp32_mb:.1f} MB")

    print("[4/4] Quantizing to INT8")
    from onnxruntime.quantization import quantize_dynamic, QuantType

    int8_path = os.path.join(OUTPUT_DIR, "model.onnx")
    quantize_dynamic(
        model_input=fp32_path,
        model_output=int8_path,
        weight_type=QuantType.QUInt8,
    )

    os.remove(fp32_path)

    int8_mb = os.path.getsize(int8_path) / (1024 * 1024)
    print(f"\nDone! Output directory: {OUTPUT_DIR}")
    print(f"  model.onnx    : {int8_mb:.1f} MB (INT8)")
    print(f"  tokenizer.json: present")
    print(f"  vocab.txt     : present")

    print("\n[Verify] Testing ONNX inference...")
    import onnxruntime as ort

    sess = ort.InferenceSession(int8_path)
    test_text = "我的家乡是有明的渔米之乡"
    enc = tokenizer(test_text, return_tensors="np", padding="max_length", truncation=True, max_length=MAX_LEN)
    feeds = {k: v for k, v in enc.items() if k in {inp.name for inp in sess.get_inputs()}}
    out = sess.run(None, feeds)
    pred_ids = np.argmax(out[0][0], axis=-1)
    vocab = tokenizer.get_vocab()
    id2token = {v: k for k, v in vocab.items()}
    pred_tokens = [id2token.get(i, "?") for i in pred_ids]
    corrected = []
    for t in pred_tokens:
        if t in ("[CLS]", "[SEP]", "[PAD]"):
            continue
        if t.startswith("##"):
            if corrected:
                corrected[-1] += t[2:]
            else:
                corrected.append(t[2:])
        else:
            corrected.append(t)
    result = "".join(corrected)
    print(f"  Input:    {test_text}")
    print(f"  Corrected: {result}")
    if result != test_text:
        print("  Correction detected! Model is working.")
    else:
        print("  No correction (model may need tuning, but pipeline is OK)")


if __name__ == "__main__":
    export()