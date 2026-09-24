import os
import re
import sys

_ORT_SESSION = None
_TOKENIZER = None
_VOCAB = None
_AVAILABLE = None

_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "corrector")
_MODEL_PATH = os.path.join(_MODEL_DIR, "model.onnx")
_MAX_LEN = 512
_PAD_ID = 0


def _log(msg):
    print(f"[corrector] {msg}", file=sys.stderr, flush=True)


def is_available() -> bool:
    global _AVAILABLE
    if _AVAILABLE is None:
        _AVAILABLE = os.path.isfile(_MODEL_PATH)
        if _AVAILABLE:
            _log(f"model found: {_MODEL_PATH}")
        else:
            _log(f"model NOT found: {_MODEL_PATH}")
    return _AVAILABLE


def _get_session():
    global _ORT_SESSION
    if _ORT_SESSION is None:
        import onnxruntime as ort
        _log("loading ONNX session...")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _ORT_SESSION = ort.InferenceSession(_MODEL_PATH, sess_options=opts)
        _log("ONNX session ready")
    return _ORT_SESSION


def _get_tokenizer():
    global _TOKENIZER, _VOCAB
    if _TOKENIZER is not None:
        return _TOKENIZER, _VOCAB

    tokenizer_json = os.path.join(_MODEL_DIR, "tokenizer.json")
    vocab_txt = os.path.join(_MODEL_DIR, "vocab.txt")

    if not os.path.isfile(tokenizer_json):
        _log(f"tokenizer.json not found: {tokenizer_json}")
        return None, None

    _log("loading tokenizer...")
    from tokenizers import Tokenizer
    _TOKENIZER = Tokenizer.from_file(tokenizer_json)
    _TOKENIZER.enable_padding(pad_id=_PAD_ID, pad_token="[PAD]")
    _TOKENIZER.enable_truncation(max_length=_MAX_LEN)
    _log("tokenizer ready")

    if os.path.isfile(vocab_txt):
        with open(vocab_txt, "r", encoding="utf-8") as f:
            _VOCAB = [line.rstrip("\n") for line in f]
        _log(f"vocab loaded: {len(_VOCAB)} tokens")
    else:
        _log(f"vocab.txt not found: {vocab_txt}")
        _VOCAB = None

    return _TOKENIZER, _VOCAB


def _correct_chunk(text: str) -> str:
    tok, vocab = _get_tokenizer()
    if tok is None or vocab is None:
        return text

    encoding = tok.encode(text)
    input_ids = encoding.ids
    attention_mask = encoding.attention_mask
    token_type_ids = [0] * len(input_ids)

    import numpy as np
    input_ids_arr = np.array([input_ids], dtype=np.int64)
    attention_mask_arr = np.array([attention_mask], dtype=np.int64)
    token_type_ids_arr = np.array([token_type_ids], dtype=np.int64)

    sess = _get_session()
    input_names = {inp.name for inp in sess.get_inputs()}
    feeds = {}
    if "input_ids" in input_names:
        feeds["input_ids"] = input_ids_arr
    if "attention_mask" in input_names:
        feeds["attention_mask"] = attention_mask_arr
    if "token_type_ids" in input_names:
        feeds["token_type_ids"] = token_type_ids_arr

    outputs = sess.run(None, feeds)
    logits = outputs[0]

    predicted_ids = np.argmax(logits[0], axis=-1).tolist()

    corrected_ids = list(input_ids)
    changed = False

    for i in range(1, len(input_ids)):
        if attention_mask[i] == 0:
            break
        orig_id = input_ids[i]
        pred_id = predicted_ids[i]

        if orig_id == pred_id:
            continue

        orig_token = vocab[orig_id] if orig_id < len(vocab) else ""
        pred_token = vocab[pred_id] if pred_id < len(vocab) else ""

        if orig_token.startswith("[") and orig_token.endswith("]"):
            continue
        if pred_token.startswith("[") and pred_token.endswith("]"):
            continue
        if pred_token.startswith("##") and not orig_token.startswith("##"):
            continue
        if not pred_token.startswith("##") and orig_token.startswith("##"):
            continue

        corrected_ids[i] = pred_id
        changed = True

    if not changed:
        return text

    corrected_ids = [tid for tid in corrected_ids if tid < len(vocab)]
    corrected_tokens = [vocab[tid] for tid in corrected_ids]

    result_parts = []
    for i, token in enumerate(corrected_tokens):
        if token in ("[CLS]", "[SEP]", "[PAD]"):
            continue
        if token.startswith("##"):
            if result_parts:
                result_parts[-1] += token[2:]
            else:
                result_parts.append(token[2:])
        else:
            result_parts.append(token)

    return "".join(result_parts)


def _correct_segment(text: str) -> str:
    if len(text) > _MAX_LEN:
        chunks = []
        for i in range(0, len(text), _MAX_LEN - 32):
            chunk = text[i : i + _MAX_LEN - 32]
            chunks.append(_correct_chunk(chunk))
        return "".join(chunks)
    return _correct_chunk(text)


def correct_text(text: str) -> str:
    if not text or not text.strip():
        return text

    if not is_available():
        return text

    lines = text.split("\n")
    corrected_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            corrected_lines.append(line)
            continue

        prefix_match = re.match(
            r"^(\u8bf4\u8bdd\u4eba\d+\s+\[[\d.]+s\s*-\s*[\d.]+s\]:\s*)(.+)$",
            stripped,
        )
        if prefix_match:
            prefix = prefix_match.group(1)
            content = prefix_match.group(2)
            corrected_content = _correct_segment(content)
            corrected_lines.append(prefix + corrected_content)
        else:
            corrected_lines.append(_correct_segment(stripped))

    return "\n".join(corrected_lines)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", action="store_true")
    parser.add_argument("text", nargs="?")
    args = parser.parse_args()

    if args.text:
        input_text = args.text
    else:
        input_text = sys.stdin.read().strip()

    if not input_text:
        if args.json_output:
            print(json.dumps({"ok": False, "error": "no input"}, ensure_ascii=False))
        else:
            print("no input")
        sys.exit(1)

    try:
        result = correct_text(input_text)
        if args.json_output:
            print(json.dumps({"ok": True, "text": result}, ensure_ascii=False))
        else:
            print(result)
    except Exception as e:
        if args.json_output:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        else:
            print(f"error: {e}", file=sys.stderr)
        sys.exit(1)