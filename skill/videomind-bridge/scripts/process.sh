#!/usr/bin/env bash
# VideoMind Bridge 快速处理脚本
# 用法: bash process.sh <URL> [模式] [选项]
#
# v2 模式 (默认, 无需下载/转录, Agent 友好):
#   extract    提取文字内容 (默认, 成本感知路由)
#   smart      预筛 + 按需提取
#   prescreen  仅预筛评分 (零网络, <2ms)
#   archive    提取并归档 (obsidian,local,html_player)
#
# v1 模式 (完整下载/转录):
#   full       下载→转录→AI摘要→导出
#   download   仅下载
#   transcribe 仅转录

set -euo pipefail

PROJECT_DIR="${VIDEOMIND_HOME:-$HOME/.local/share/videomind-bridge}"
URL="${1:?用法: process.sh <URL> [extract|smart|prescreen|archive|full|download|transcribe] [选项]}"
MODE="${2:-extract}"
EXTRA_ARGS="${3:-}"

if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ VideoMind Bridge 未安装。请先运行 install.sh"
    exit 1
fi

cd "$PROJECT_DIR"

case "$MODE" in
    extract|v2)
        uv run python -m src.cli "$URL" --json $EXTRA_ARGS
        ;;
    smart)
        uv run python -m src.cli "$URL" --smart --json $EXTRA_ARGS
        ;;
    prescreen)
        uv run python -m src.cli "$URL" --prescreen-only --json $EXTRA_ARGS
        ;;
    archive)
        uv run python -m src.cli "$URL" --archive "$EXTRA_ARGS" --json
        ;;
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
        echo "❌ 未知模式: $MODE (可选: extract, smart, prescreen, archive, full, download, transcribe)"
        exit 1
        ;;
esac
