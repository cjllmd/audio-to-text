#!/bin/bash
set -e

MODEL_DIR="$(cd "$(dirname "$0")" && pwd)/models"
mkdir -p "$MODEL_DIR"

echo "=== 下载 SenseVoice-Small INT8 模型 (中/粤/英/日/韩, ~229MB) ==="
cd "$MODEL_DIR"
if [ ! -d "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17" ]; then
    curl -SL -O https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2
    tar xvf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2
    rm sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2
    echo "SenseVoice INT8 模型下载完成"
else
    echo "SenseVoice INT8 模型已存在，跳过"
fi

echo ""
echo "=== 下载 Silero VAD 模型 (~0.6MB) ==="
if [ ! -f "silero_vad.onnx" ]; then
    curl -SL -O https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx
    echo "Silero VAD 模型下载完成"
else
    echo "Silero VAD 模型已存在，跳过"
fi

echo ""
echo "=== 下载 Pyannote 说话人分割模型 (~6.6MB) ==="
if [ ! -d "sherpa-onnx-pyannote-segmentation-3-0" ]; then
    curl -SL -O https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2
    tar xvf sherpa-onnx-pyannote-segmentation-3-0.tar.bz2
    rm sherpa-onnx-pyannote-segmentation-3-0.tar.bz2
    echo "Pyannote 分割模型下载完成"
else
    echo "Pyannote 分割模型已存在，跳过"
fi

echo ""
echo "=== 下载 3D-Speaker 说话人嵌入模型 (中/英, ~27MB) ==="
if [ ! -f "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx" ]; then
    curl -SL -O https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx
    echo "3D-Speaker 嵌入模型下载完成"
else
    echo "3D-Speaker 嵌入模型已存在，跳过"
fi

echo ""
echo "=== 所有模型下载完成 ==="
echo "模型目录: $MODEL_DIR"
echo ""
echo "模型大小:"
for d in "$MODEL_DIR"/*/; do
    if [ -d "$d" ]; then
        name=$(basename "$d")
        size=$(du -sh "$d" | cut -f1)
        echo "  $name: $size"
    fi
done