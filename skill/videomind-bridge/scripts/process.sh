#!/usr/bin/env bash
# VideoMind Bridge 快速处理脚本
# 用法: bash process.sh <URL> [模式] [选项]

set -euo pipefail

PROJECT_DIR="${VIDEOMIND_HOME:-$HOME/.local/share/videomind-bridge}"
URL="${1:?用法: process.sh <URL> [full|download|transcribe]}"
MODE="${2:-full}"
EXTRA_ARGS="${3:-}"

if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ VideoMind Bridge 未安装。请先运行 install.sh"
    exit 1
fi

cd "$PROJECT_DIR"

case "$MODE" in
    full)
        uv run python -m src.cli "$URL" --mode full --json $EXTRA_ARGS
        ;;
    download)
        uv run python -m src.cli "$URL" --mode download --json $EXTRA_ARGS
        ;;
    transcribe)
        uv run python -m src.cli "$URL" --mode transcribe --json $EXTRA_ARGS
        ;;
    *)
        echo "❌ 未知模式: $MODE (可选: full, download, transcribe)"
        exit 1
        ;;
esac
