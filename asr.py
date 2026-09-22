import os
import wave
import argparse
import subprocess
import numpy as np
import sherpa_onnx
import hashlib
import struct as _struct
from concurrent.futures import ThreadPoolExecutor

_RECOGNIZER_CACHE: dict[str, object] = {}


def _default_threads() -> int:
    return min(os.cpu_count() or 4, 8)


def _cache_key(model: str, language: str, num_threads: int) -> str:
    return f"{model}|{language}|{num_threads}"


MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

MODEL_INFO = {
    "paraformer-small": {
        "dir": "sherpa-onnx-paraformer-zh-small-2024-03-09",
        "desc": "Paraformer-zh-small INT8 (中/英, ~82MB)",
        "langs": ["zh", "en"],
    },
    "sensevoice": {
        "dir": "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17",
        "desc": "SenseVoice-Small INT8 (中/粤/英/日/韩, ~241MB)",
        "langs": ["zh", "en", "ja", "ko", "yue"],
    },
}


def create_paraformer_small_recognizer(model_dir: str = None, num_threads: int = 4):
    if model_dir is None:
        model_dir = os.path.join(MODELS_DIR, MODEL_INFO["paraformer-small"]["dir"])
    model_path = os.path.join(model_dir, "model.int8.onnx")
    tokens_path = os.path.join(model_dir, "tokens.txt")
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"Paraformer-zh-small 模型未找到: {model_path}\n"
            "请先运行: bash download_model.sh"
        )
    return sherpa_onnx.OfflineRecognizer.from_paraformer(
        paraformer=model_path,
        tokens=tokens_path,
        num_threads=num_threads,
    )


def create_sense_voice_recognizer(model_dir: str = None, language: str = "auto", num_threads: int = 4):
    if model_dir is None:
        model_dir = os.path.join(MODELS_DIR, MODEL_INFO["sensevoice"]["dir"])
    model_path = os.path.join(model_dir, "model.int8.onnx")
    tokens_path = os.path.join(model_dir, "tokens.txt")
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"SenseVoice 模型未找到: {model_path}\n"
            "请先运行: bash download_model.sh"
        )
    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=model_path,
        tokens=tokens_path,
        language=language,
        use_itn=True,
        num_threads=num_threads,
    )


def create_vad(vad_model_path: str = None):
    if vad_model_path is None:
        vad_model_path = os.path.join(MODELS_DIR, "silero_vad.onnx")
    if not os.path.exists(vad_model_path):
        raise FileNotFoundError(
            f"VAD 模型未找到: {vad_model_path}\n"
            "请先运行: bash download_model.sh"
        )
    config = sherpa_onnx.VadModelConfig(
        silero_vad=sherpa_onnx.SileroVadModelConfig(model=vad_model_path),
    )
    return sherpa_onnx.VadModel.create(config)


def read_wave(wave_path: str) -> tuple[np.ndarray, int]:
    try:
        import soundfile as sf
        samples, sample_rate = sf.read(wave_path, dtype="float32")
        if samples.ndim > 1:
            samples = samples[:, 0]
        return samples, sample_rate
    except Exception:
        with wave.open(wave_path, "rb") as f:
            sample_rate = f.getframerate()
            n_channels = f.getnchannels()
            raw = f.readframes(f.getnframes())
            data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if n_channels > 1:
                data = data[::n_channels]
            return data, sample_rate


def resample_if_needed(samples: np.ndarray, sample_rate: int, target_rate: int = 16000) -> tuple[np.ndarray, int]:
    if sample_rate == target_rate:
        return samples, target_rate
    ratio = target_rate / sample_rate
    num_samples = int(len(samples) * ratio)
    indices = np.linspace(0, len(samples) - 1, num_samples).astype(np.int64)
    return samples[indices], target_rate


def create_speaker_diarization(
    segmentation_model_dir: str = None,
    embedding_model_path: str = None,
    num_threads: int = 4,
    num_clusters: int = -1,
    clustering_threshold: float = 0.5,
):
    if segmentation_model_dir is None:
        segmentation_model_dir = os.path.join(MODELS_DIR, "sherpa-onnx-pyannote-segmentation-3-0")
    if embedding_model_path is None:
        embedding_model_path = os.path.join(MODELS_DIR, "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx")

    seg_model = os.path.join(segmentation_model_dir, "model.int8.onnx")
    if not os.path.exists(seg_model):
        raise FileNotFoundError(
            f"说话人分割模型未找到: {seg_model}\n"
            "请先运行: bash download_model.sh"
        )
    if not os.path.exists(embedding_model_path):
        raise FileNotFoundError(
            f"说话人嵌入模型未找到: {embedding_model_path}\n"
            "请先运行: bash download_model.sh"
        )

    segmentation_config = sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
        pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
            model=seg_model,
        ),
    )

    embedding_config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
        model=embedding_model_path,
        num_threads=num_threads,
    )

    clustering_config = sherpa_onnx.FastClusteringConfig(
        num_clusters=num_clusters,
        threshold=clustering_threshold,
    )

    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=segmentation_config,
        embedding=embedding_config,
        clustering=clustering_config,
        min_duration_on=0.3,
        min_duration_off=0.5,
    )

    return sherpa_onnx.OfflineSpeakerDiarization(config)


def _verify_core_auth() -> None:
    from license import check_auth, check_trial_or_registered
    if not check_auth():
        ok, msg = check_trial_or_registered()
        if not ok:
            raise RuntimeError(msg or "授权验证失败")


def transcribe_with_diarization(
    audio_path: str,
    model: str = "paraformer-small",
    language: str = "auto",
    num_threads: int = 0,
    num_clusters: int = -1,
    clustering_threshold: float = 0.5,
) -> str:
    _verify_core_auth()
    if num_threads <= 0:
        num_threads = _default_threads()
    samples, sample_rate = read_wave(audio_path)
    samples, sample_rate = resample_if_needed(samples, sample_rate, 16000)

    diarization = create_speaker_diarization(
        num_threads=num_threads,
        num_clusters=num_clusters,
        clustering_threshold=clustering_threshold,
    )

    result = diarization.process(samples.tolist())

    segments = result.sort_by_start_time()
    if not segments:
        return ""

    recognizer = create_recognizer(model, language, num_threads)

    speaker_map = {}
    next_id = 1

    decode_tasks = []
    for seg in segments:
        raw_speaker = seg.speaker
        if raw_speaker not in speaker_map:
            speaker_map[raw_speaker] = next_id
            next_id += 1
        speaker_id = speaker_map[raw_speaker]

        start_sample = int(seg.start * sample_rate)
        end_sample = int(seg.end * sample_rate)
        start_sample = max(0, min(start_sample, len(samples)))
        end_sample = max(start_sample, min(end_sample, len(samples)))

        if end_sample - start_sample < int(sample_rate * 0.1):
            continue

        segment_samples = samples[start_sample:end_sample]
        decode_tasks.append((speaker_id, seg.start, seg.end, segment_samples))

    def _decode_task(task):
        sid, start, end, seg_samples = task
        text = _decode_segment(recognizer, sample_rate, seg_samples)
        return sid, start, end, text

    if len(decode_tasks) <= 1:
        decoded = [_decode_task(t) for t in decode_tasks]
    else:
        decode_workers = max(1, min(num_threads, len(decode_tasks)))
        with ThreadPoolExecutor(max_workers=decode_workers) as pool:
            decoded = list(pool.map(_decode_task, decode_tasks))

    speaker_lines = []
    for sid, start, end, text in decoded:
        if text:
            time_str = f"[{start:.1f}s - {end:.1f}s]"
            speaker_lines.append(f"说话人{sid} {time_str}: {text}")

    return "\n".join(speaker_lines)


def create_recognizer(model: str, language: str = "auto", num_threads: int = 4):
    key = _cache_key(model, language, num_threads)
    if key in _RECOGNIZER_CACHE:
        return _RECOGNIZER_CACHE[key]
    if model == "paraformer-small":
        rec = create_paraformer_small_recognizer(num_threads=num_threads)
    elif model == "sensevoice":
        rec = create_sense_voice_recognizer(language=language, num_threads=num_threads)
    else:
        raise ValueError(f"不支持的模型: {model}，可选: {', '.join(MODEL_INFO.keys())}")
    _RECOGNIZER_CACHE[key] = rec
    return rec


def _decode_segment(recognizer, sample_rate: int, segment: np.ndarray) -> str:
    stream = recognizer.create_stream()
    stream.accept_waveform(sample_rate, segment)
    recognizer.decode_stream(stream)
    return stream.result.text.strip()


def transcribe_file(
    audio_path: str,
    model: str = "paraformer-small",
    language: str = "auto",
    use_vad: bool = True,
    num_threads: int = 0,
) -> str:
    _verify_core_auth()
    if num_threads <= 0:
        num_threads = _default_threads()
    recognizer = create_recognizer(model, language, num_threads)

    samples, sample_rate = read_wave(audio_path)
    samples, sample_rate = resample_if_needed(samples, sample_rate, 16000)

    if not use_vad:
        stream = recognizer.create_stream()
        stream.accept_waveform(sample_rate, samples)
        recognizer.decode_stream(stream)
        return stream.result.text

    vad = create_vad()

    window_size = vad.window_size()
    speech_segments = []
    current_chunks = []

    offset = 0
    n = len(samples)
    while offset < n:
        end = min(offset + window_size, n)
        chunk = samples[offset:end]
        if len(chunk) < window_size:
            chunk = np.pad(chunk, (0, window_size - len(chunk)))
        is_speech = vad.is_speech(chunk.tolist())
        if is_speech:
            current_chunks.append(samples[offset:end])
        else:
            if current_chunks:
                speech_segments.append(np.concatenate(current_chunks).astype(np.float32))
                current_chunks = []
        offset = end

    if current_chunks:
        speech_segments.append(np.concatenate(current_chunks).astype(np.float32))

    if not speech_segments:
        return ""

    if len(speech_segments) == 1:
        text = _decode_segment(recognizer, sample_rate, speech_segments[0])
        return text

    decode_workers = max(1, min(num_threads, len(speech_segments)))
    with ThreadPoolExecutor(max_workers=decode_workers) as pool:
        futures = [
            pool.submit(_decode_segment, recognizer, sample_rate, seg)
            for seg in speech_segments
        ]
        results = [f.result() for f in futures]

    return "".join(t for t in results if t)


def _convert_via_av(input_path: str, wav_path: str) -> str:
    import av
    inp = av.open(input_path)
    stream = next(s for s in inp.streams if s.type == "audio")
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    chunks = []
    for frame in inp.decode(stream):
        for r in resampler.resample(frame):
            chunks.append(r.to_ndarray())
    for r in resampler.resample(None):
        chunks.append(r.to_ndarray())
    inp.close()
    if not chunks:
        raise RuntimeError("PyAV 解码无音频数据")
    audio = np.concatenate(chunks).flatten().astype(np.int16)
    import soundfile as sf
    sf.write(wav_path, audio, 16000, subtype="PCM_16")
    return wav_path


def convert_to_wav(input_path: str) -> str:
    if input_path.lower().endswith(".wav"):
        return input_path
    wav_path = os.path.splitext(input_path)[0] + "_temp.wav"
    try:
        return _convert_via_av(input_path, wav_path)
    except ImportError:
        pass
    except Exception:
        pass
    try:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-nostdin", "-threads", "0",
                "-y", "-i", input_path,
                "-vn", "-map_metadata", "-1",
                "-ar", "16000", "-ac", "1",
                "-acodec", "pcm_s16le",
                "-fflags", "+fastseek",
                wav_path,
            ],
            capture_output=True, check=True, timeout=120,
        )
        return wav_path
    except FileNotFoundError:
        pass
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg 转换失败: {e.stderr.decode(errors='replace') if e.stderr else e}")
    try:
        import soundfile as sf
    except ImportError:
        raise ImportError("非 WAV 格式需要 av、ffmpeg 或 soundfile，请安装其一")
    data, sr = sf.read(input_path, dtype="float32")
    if data.ndim > 1:
        data = data[:, 0]
    if sr != 16000:
        try:
            from scipy.signal import resample_poly
            gcd = np.gcd(16000, sr)
            up = 16000 // gcd
            down = sr // gcd
            data = resample_poly(data, up, down).astype(np.float32)
        except ImportError:
            ratio = 16000 / sr
            num_samples = int(len(data) * ratio)
            indices = np.linspace(0, len(data) - 1, num_samples).astype(np.int64)
            data = data[indices]
        sr = 16000
    data_int16 = np.clip(data * 32767, -32768, 32767).astype(np.int16)
    sf.write(wav_path, data_int16, sr, subtype="PCM_16")
    return wav_path


def main():
    parser = argparse.ArgumentParser(description="音频转文字 - 基于 sherpa-onnx (onnxruntime)")
    parser.add_argument("audio", nargs="?", help="音频文件路径 (支持 wav/mp3/flac 等)")
    parser.add_argument(
        "--model",
        choices=list(MODEL_INFO.keys()),
        default="paraformer-small",
        help="识别模型 (默认: paraformer-small)",
    )
    parser.add_argument(
        "--language",
        choices=["auto", "zh", "en", "ja", "ko", "yue"],
        default="auto",
        help="语言 (仅 SenseVoice 支持, 默认: auto 自动检测)",
    )
    parser.add_argument("--no-vad", action="store_true", help="禁用 VAD 语音活动检测")
    parser.add_argument("--threads", type=int, default=0, help="推理线程数 (0=自动, 默认: 0)")
    parser.add_argument("--json-output", action="store_true", help="JSON 格式输出（供 GUI 调用）")
    parser.add_argument("--diarize", action="store_true", help="区分说话人")
    parser.add_argument("--num-speakers", type=int, default=-1, help="说话人数量（-1 为自动）")
    parser.add_argument(
        "--interactive", action="store_true", help="交互模式，连续输入文件路径识别"
    )
    args = parser.parse_args()

    if args.interactive:
        print("=" * 50)
        print("  音频转文字 - 交互模式")
        print(f"  模型: {args.model} - {MODEL_INFO[args.model]['desc']}")
        print("=" * 50)
        while True:
            try:
                audio_path = input("\n请输入音频文件路径 (或 q 退出): ").strip().strip('"').strip("'")
            except (EOFError, KeyboardInterrupt):
                print("\n退出")
                break
            if audio_path.lower() in ("q", "quit", "exit"):
                break
            if not audio_path:
                continue
            if not os.path.exists(audio_path):
                print(f"文件不存在: {audio_path}")
                continue
            try:
                temp_wav = None
                wav_path = convert_to_wav(audio_path)
                if wav_path != audio_path:
                    temp_wav = wav_path
                text = transcribe_file(
                    wav_path,
                    model=args.model,
                    language=args.language,
                    use_vad=not args.no_vad,
                    num_threads=args.threads,
                )
                print(f"\n识别结果: {text}")
                if temp_wav and os.path.exists(temp_wav):
                    os.remove(temp_wav)
            except Exception as e:
                print(f"识别失败: {e}")
        return

    if not args.audio:
        parser.print_help()
        print("\n可用模型:")
        for name, info in MODEL_INFO.items():
            marker = " (默认)" if name == "paraformer-small" else ""
            print(f"  {name}: {info['desc']}{marker}")
        print("\n示例:")
        print("  python asr.py audio.wav")
        print("  python asr.py audio.mp3 --model sensevoice")
        print("  python asr.py audio.wav --language zh --no-vad")
        print("  python asr.py --interactive --model paraformer-small")
        return

    if not os.path.exists(args.audio):
        print(f"文件不存在: {args.audio}")
        return

    temp_wav = None
    try:
        wav_path = convert_to_wav(args.audio)
        if wav_path != args.audio:
            temp_wav = wav_path
            if not args.json_output:
                print(f"已将 {os.path.splitext(args.audio)[1]} 转换为 WAV 格式")

        if not args.json_output:
            print(f"模型: {args.model} ({MODEL_INFO[args.model]['desc']}) | VAD: {'关' if args.no_vad else '开'}")

        if args.diarize:
            text = transcribe_with_diarization(
                wav_path,
                model=args.model,
                language=args.language,
                num_threads=args.threads,
                num_clusters=args.num_speakers,
            )
        else:
            text = transcribe_file(
                wav_path,
                model=args.model,
                language=args.language,
                use_vad=not args.no_vad,
                num_threads=args.threads,
            )

        if args.json_output:
            import json
            print(json.dumps({"ok": True, "text": text}, ensure_ascii=False))
        else:
            print(f"\n识别结果:\n{text}")
    except Exception as e:
        if args.json_output:
            import json
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        else:
            print(f"识别失败: {e}")
    finally:
        if temp_wav and os.path.exists(temp_wav):
            os.remove(temp_wav)


if __name__ == "__main__":
    main()