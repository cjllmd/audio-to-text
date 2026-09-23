#!/usr/bin/env bash
# 音频转文字 Nuitka 打包脚本
#
# 支持平台（需在对应平台上运行）：
#   ./build.sh mac     — 当前 Mac（Intel 或 Apple Silicon 自动检测）
#   ./build.sh windows — Windows（需在 Windows 上运行）
#   ./build.sh clean   — 清理构建产物
#
# 输出：
#   dist/音频转文字-macos-x86_64.app   (Mac Intel)
#   dist/音频转文字-macos-arm64.app    (Mac Apple Silicon)
#   dist/音频转文字-windows/            (Windows)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="音频转文字"
MAIN_MODULE="gui.py"
OUTPUT_DIR="dist"
VERSION="1.0.0"

detect_mac_arch() {
    if [[ "$(uname -m)" == "arm64" ]]; then
        echo "arm64"
    else
        echo "x86_64"
    fi
}

build_mac() {
    local arch
    arch=$(detect_mac_arch)
    echo "=========================================="
    echo "  Building for macOS ($arch)"
    echo "=========================================="

    python3 -m nuitka \
        --standalone \
        --enable-plugin=tk-inter \
        --nofollow-import-to=tkinterdnd2 \
        --include-module=av \
        --include-data-files=models/silero_vad.onnx=models/silero_vad.onnx \
        --include-data-files=models/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx=models/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx \
        --include-data-files=models/sherpa-onnx-paraformer-zh-small-2024-03-09/model.int8.onnx=models/sherpa-onnx-paraformer-zh-small-2024-03-09/model.int8.onnx \
        --include-data-files=models/sherpa-onnx-paraformer-zh-small-2024-03-09/tokens.txt=models/sherpa-onnx-paraformer-zh-small-2024-03-09/tokens.txt \
        --include-data-files=models/sherpa-onnx-paraformer-zh-small-2024-03-09/am.mvn=models/sherpa-onnx-paraformer-zh-small-2024-03-09/am.mvn \
        --include-data-files=models/sherpa-onnx-paraformer-zh-small-2024-03-09/config.yaml=models/sherpa-onnx-paraformer-zh-small-2024-03-09/config.yaml \
        --include-data-files=models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/model.int8.onnx=models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/model.int8.onnx \
        --include-data-files=models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/tokens.txt=models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/tokens.txt \
        --include-data-files=models/sherpa-onnx-pyannote-segmentation-3-0/model.int8.onnx=models/sherpa-onnx-pyannote-segmentation-3-0/model.int8.onnx \
        --include-data-dir=icons=icons \
        --output-dir="${OUTPUT_DIR}" \
        --output-filename="${APP_NAME}" \
        --company-name="ASR" \
        --product-name="${APP_NAME}" \
        --file-description="音频转文字工具" \
        --file-version=${VERSION} \
        --product-version=${VERSION} \
        --macos-create-app-bundle \
        --macos-app-name="${APP_NAME}" \
        --macos-app-version=${VERSION} \
        --macos-app-icon=icons/icon.icns \
        --static-libpython=no \
        --assume-yes-for-downloads \
        --show-progress \
        --show-memory \
        ${MAIN_MODULE}

    local app_bundle="${OUTPUT_DIR}/${MAIN_MODULE}.app"
    local final_name="${OUTPUT_DIR}/${APP_NAME}-macos-${arch}.app"
    if [[ -d "${app_bundle}" ]]; then
        if [[ -d "${final_name}" ]]; then
            rm -rf "${final_name}"
        fi
        mv "${app_bundle}" "${final_name}"
        echo ""
        echo "✓ Build complete: ${final_name}"
        echo "  Size: $(du -sh "${final_name}" | cut -f1)"
    fi

    rm -rf "${OUTPUT_DIR}/${MAIN_MODULE}.build" "${OUTPUT_DIR}/${MAIN_MODULE}.dist"
}

build_windows() {
    echo "=========================================="
    echo "  Building for Windows"
    echo "=========================================="

    python -m nuitka \
        --standalone \
        --enable-plugin=tk-inter \
        --nofollow-import-to=tkinterdnd2 \
        --include-module=av \
        --include-data-files=models/silero_vad.onnx=models/silero_vad.onnx \
        --include-data-files=models/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx=models/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx \
        --include-data-files=models/sherpa-onnx-paraformer-zh-small-2024-03-09/model.int8.onnx=models/sherpa-onnx-paraformer-zh-small-2024-03-09/model.int8.onnx \
        --include-data-files=models/sherpa-onnx-paraformer-zh-small-2024-03-09/tokens.txt=models/sherpa-onnx-paraformer-zh-small-2024-03-09/tokens.txt \
        --include-data-files=models/sherpa-onnx-paraformer-zh-small-2024-03-09/am.mvn=models/sherpa-onnx-paraformer-zh-small-2024-03-09/am.mvn \
        --include-data-files=models/sherpa-onnx-paraformer-zh-small-2024-03-09/config.yaml=models/sherpa-onnx-paraformer-zh-small-2024-03-09/config.yaml \
        --include-data-files=models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/model.int8.onnx=models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/model.int8.onnx \
        --include-data-files=models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/tokens.txt=models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/tokens.txt \
        --include-data-files=models/sherpa-onnx-pyannote-segmentation-3-0/model.int8.onnx=models/sherpa-onnx-pyannote-segmentation-3-0/model.int8.onnx \
        --include-data-dir=icons=icons \
        --output-dir="${OUTPUT_DIR}" \
        --output-filename="${APP_NAME}.exe" \
        --company-name="ASR" \
        --product-name="${APP_NAME}" \
        --file-description="音频转文字工具" \
        --file-version=${VERSION} \
        --product-version=${VERSION} \
        --windows-disable-console \
        --windows-icon-from-ico=icons/icon.ico \
        --assume-yes-for-downloads \
        --show-progress \
        --show-memory \
        ${MAIN_MODULE}

    local bundle_dir="${OUTPUT_DIR}/${MAIN_MODULE}.dist"
    local final_dir="${OUTPUT_DIR}/${APP_NAME}-windows"
    if [[ -d "${bundle_dir}" ]]; then
        if [[ -d "${final_dir}" ]]; then
            rm -rf "${final_dir}"
        fi
        mv "${bundle_dir}" "${final_dir}"
        echo ""
        echo "✓ Build complete: ${final_dir}/"
        echo "  Size: $(du -sh "${final_dir}" | cut -f1)"
    fi

    rm -rf "${OUTPUT_DIR}/${MAIN_MODULE}.build"
}

clean() {
    echo "Cleaning build artifacts..."
    rm -rf "${OUTPUT_DIR}/${MAIN_MODULE}.build"
    rm -rf "${OUTPUT_DIR}/${MAIN_MODULE}.dist"
    rm -rf "${OUTPUT_DIR}/${MAIN_MODULE}.app"
    echo "Done."
}

case "${1:-mac}" in
    mac)
        build_mac
        ;;
    windows|win)
        build_windows
        ;;
    clean)
        clean
        ;;
    *)
        echo "Usage: $0 {mac|windows|clean}"
        exit 1
        ;;
esac