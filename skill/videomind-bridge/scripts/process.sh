#!/usr/bin/env bash
# VideoMind Bridge 快速处理脚本（2026-11-25 A2 之后：只剩 v2）
# 用法: bash process.sh <URL 或本地文件> [模式] [选项]
#
# 模式:
#   extract    提取文字内容（默认，成本感知路由）
#   smart      预筛 + 按需提取
#   prescreen  仅预筛评分（零网络）
#   archive    提取并归档（第三个参数传目标，如 obsidian,local）
#   local      本地文件 → 只做 ASR 转写（手动下载的视频）
#
# 注意: v1 的 full / download / transcribe 模式已随 v1 流水线删除，
#       传了会直接报未知模式（故意不保留"看起来还能跑"的兼容层）。

set -euo pipefail

PROJECT_DIR="${VIDEOMIND_HOME:-$HOME/.local/share/videomind-bridge}"
USAGE="用法: process.sh <URL 或本地文件> [extract|smart|prescreen|archive|local] [选项]"
URL="${1:?$USAGE}"
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
        if [ -z "$EXTRA_ARGS" ]; then
            echo "❌ archive 模式需要归档目标，例如: process.sh <URL> archive obsidian,local"
            exit 2
        fi
        uv run python -m src.cli "$URL" --archive "$EXTRA_ARGS" --json
        ;;
    local)
        uv run python -m src.cli "$URL" --json $EXTRA_ARGS
        ;;
    *)
        echo "❌ 未知模式: $MODE（可选: extract, smart, prescreen, archive, local）"
        echo "   v1 的 full/download/transcribe 已于 2026-11-25 删除；本地文件请用 local 模式。"
        exit 1
        ;;
esac
