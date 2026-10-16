import multiprocessing as mp
import time, os

try:
    mp.set_start_method("spawn", force=True)
except RuntimeError:
    pass

import gui

audio = "models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/test_wavs/zh.wav"
argv = ["asr.py", audio, "--model", "sensevoice", "--language", "auto", "--threads", "0", "--json-output"]

q = mp.Queue(maxsize=1)
p = mp.Process(target=gui._asr_worker, args=(q, argv), daemon=True)
start = time.monotonic()
p.start()
data = None
while True:
    try:
        data = q.get_nowait()
        break
    except Exception:
        if time.monotonic() - start > 120:
            data = {"ok": False, "error": "timeout"}
            break
        time.sleep(0.08)
print(json_text := "OK" if data.get("ok") else "FAIL")
print(f"elapsed={time.monotonic()-start:.1f}s ok={data.get('ok')} text={data.get('text', data.get('error',''))[:40]}")
p.join(timeout=5)