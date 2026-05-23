#!/usr/bin/env bash
# VideoMind Bridge 安装脚本
# 用法: bash install.sh [项目目录]

set -euo pipefail

PROJECT_DIR="${1:-$HOME/.local/share/videomind-bridge}"
REPO_URL="https://github.com/your-org/VideoMind-Bridge.git"

echo "=== VideoMind Bridge 安装脚本 ==="

# 检查必需工具
check_dependency() {
    if command -v "$1" &>/dev/null; then
        echo "✅ $1 已安装: $(command -v "$1")"
        return 0
    else
        echo "❌ $1 未安装"
        return 1
    fi
}

echo ""
echo "--- 检查必需依赖 ---"
MISSING=0

if ! check_dependency uv; then
    MISSING=1
    echo "   安装方式: brew install uv 或 curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

if ! check_dependency yt-dlp; then
    MISSING=1
    echo "   安装方式: brew install yt-dlp 或 pip install yt-dlp"
fi

if [ $MISSING -ne 0 ]; then
    echo ""
    echo "⚠️  缺少必需依赖，请先安装后再继续。"
    exit 1
fi

echo ""
echo "--- 检查可选依赖 ---"
check_dependency ffmpeg || echo "   (可选) 安装: brew install ffmpeg"

# 克隆项目
echo ""
echo "--- 安装 VideoMind Bridge ---"
if [ -d "$PROJECT_DIR" ]; then
    echo "📁 项目目录已存在: $PROJECT_DIR"
    echo "   执行更新..."
    cd "$PROJECT_DIR"
    git pull --ff-only || echo "   ⚠️ Git 更新失败，使用现有版本"
else
    echo "📁 克隆项目到: $PROJECT_DIR"
    git clone "$REPO_URL" "$PROJECT_DIR"
    cd "$PROJECT_DIR"
fi

# 安装 Python 依赖
echo ""
echo "--- 安装 Python 依赖 ---"
uv sync

# 检查 API Key
echo ""
echo "--- 检查 AI API Key ---"
API_KEY_SET=0
for KEY_VAR in DEEPSEEK_API_KEY ZHIPU_API_KEY MOONSHOT_API_KEY MINIMAX_API_KEY DOUBAO_API_KEY; do
    if [ -n "${!KEY_VAR:-}" ]; then
        echo "✅ $KEY_VAR 已设置"
        API_KEY_SET=1
    fi
done

if [ $API_KEY_SET -eq 0 ]; then
    echo "⚠️  未检测到 AI API Key"
    echo "   AI摘要功能将不可用，但转录和下载功能正常"
    echo "   设置方式: export DEEPSEEK_API_KEY=sk-your-key"
fi

# 验证安装
echo ""
echo "--- 验证安装 ---"
if uv run python -m src.cli --help &>/dev/null; then
    echo "✅ VideoMind Bridge 安装成功！"
    echo ""
    echo "快速开始:"
    echo "  cd $PROJECT_DIR"
    echo "  uv run python -m src.cli 'https://bilibili.com/video/BV1xx' --json"
else
    echo "❌ 安装验证失败，请检查错误信息"
    exit 1
fi
