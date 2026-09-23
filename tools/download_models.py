#!/usr/bin/env python3
"""
跨平台模型下载脚本（macOS / Windows / Linux）。

在 CI 中替代 download_model.sh（Windows runner 可能没有 bash）。
本地首次使用也建议运行此脚本：
    python tools/download_models.py

所有模型从 k2-fsa/sherpa-onnx 的 GitHub Releases 下载。
"""

import os
import sys
import tarfile
import urllib.request
import hashlib

# 项目根目录
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(PROJECT_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download"

MANIFEST = [
    {
        "name": "silero_vad.onnx",
        "url": f"{BASE}/asr-models/silero_vad.onnx",
        "type": "file",
    },
    {
        "name": "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17",
        "url": f"{BASE}/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2",
        "type": "tar",
    },
    {
        "name": "sherpa-onnx-pyannote-segmentation-3-0",
        "url": f"{BASE}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2",
        "type": "tar",
    },
    {
        "name": "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx",
        "url": f"{BASE}/speaker-recongition-models/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx",
        "type": "file",
    },
]


def _progress(block_count: int, block_size: int, total_size: int) -> None:
    if total_size <= 0:
        return
    downloaded = block_count * block_size
    percent = min(100, downloaded * 100 // total_size)
    bar_len = 30
    filled = bar_len * percent // 100
    bar = "█" * filled + "░" * (bar_len - filled)
    mb = downloaded / 1024 / 1024
    total_mb = total_size / 1024 / 1024
    sys.stdout.write(f"\r  {bar} {percent}% ({mb:.1f}/{total_mb:.1f} MB)")
    sys.stdout.flush()
    if downloaded >= total_size:
        sys.stdout.write("\n")


def download_file(url: str, dest: str) -> None:
    print(f"  下载: {os.path.basename(dest)}")
    urllib.request.urlretrieve(url, dest, _progress)
    size_mb = os.path.getsize(dest) / 1024 / 1024
    print(f"  完成: {size_mb:.1f} MB\n")


def download_and_extract_tar(url: str, dest_dir: str) -> None:
    """下载 tar.bz2 并解压到目标目录。"""
    name = os.path.basename(url)
    tmp = os.path.join(dest_dir, name)
    print(f"  下载: {name}")
    urllib.request.urlretrieve(url, tmp, _progress)
    size_mb = os.path.getsize(tmp) / 1024 / 1024
    print(f"  解压: {name} ({size_mb:.1f} MB)")
    with tarfile.open(tmp, "r:bz2") as tar:
        tar.extractall(path=dest_dir)
    os.remove(tmp)
    print(f"  完成\n")


def main() -> None:
    print(f"模型目录: {MODELS_DIR}")
    print("=" * 50)

    for item in MANIFEST:
        name = item["name"]
        dest_path = os.path.join(MODELS_DIR, name)

        # 检查是否已存在
        if item["type"] == "tar":
            if os.path.isdir(dest_path):
                print(f"  ✓ 跳过: {name}（已存在）")
                continue
            download_and_extract_tar(item["url"], MODELS_DIR)
        else:
            if os.path.isfile(dest_path):
                print(f"  ✓ 跳过: {name}（已存在）")
                continue
            download_file(item["url"], dest_path)

    print("=" * 50)
    print("所有模型下载完成！")
    print(f"模型目录: {MODELS_DIR}")
    print()
    print("文件列表:")
    for root, dirs, files in os.walk(MODELS_DIR):
        for f in files:
            fp = os.path.join(root, f)
            size_mb = os.path.getsize(fp) / 1024 / 1024
            if f.endswith((".onnx", ".txt")):
                print(f"  {os.path.relpath(fp, MODELS_DIR):50s} {size_mb:>6.1f} MB")


if __name__ == "__main__":
    main()