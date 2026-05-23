#!/bin/bash
# VideoMind Bridge macOS 应用打包脚本
# 使用方法: ./build_macos_app.sh

set -e  # 遇到错误立即退出

echo "🚀 VideoMind Bridge macOS 应用打包工具"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Python 版本
echo -e "\n📋 检查环境..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python 版本: $python_version"

# 检查是否在虚拟环境中
if [[ -z "${VIRTUAL_ENV}" ]]; then
    echo -e "${YELLOW}⚠️  未检测到虚拟环境，建议先激活虚拟环境${NC}"
    echo "   运行: source .venv/bin/activate"
    read -p "是否继续? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 安装 PyInstaller
echo -e "\n📦 安装打包工具..."
pip install pyinstaller pillow -q

# 创建资源目录
mkdir -p assets

# 生成图标（如果没有）
if [ ! -f "assets/icon.icns" ]; then
    echo -e "\n🎨 生成应用图标..."
    
    # 创建一个简单的图标（使用 Python）
    python3 << 'PYEOF'
from PIL import Image, ImageDraw, ImageFont
import os

# 创建 1024x1024 的图标
size = 1024
img = Image.new('RGBA', (size, size), (0, 120, 255, 255))
draw = ImageDraw.Draw(img)

# 绘制简单的播放按钮形状
margin = 200
center_x, center_y = size // 2, size // 2

# 绘制三角形（播放按钮）
triangle_size = 300
points = [
    (center_x - triangle_size//3, center_y - triangle_size//2),
    (center_x - triangle_size//3, center_y + triangle_size//2),
    (center_x + triangle_size//2, center_y)
]
draw.polygon(points, fill=(255, 255, 255, 255))

# 保存为 PNG
img.save('assets/icon_1024x1024.png')
print("✓ 图标已生成: assets/icon_1024x1024.png")
PYEOF

    # 转换为 .icns 格式
    echo "转换图标格式..."
    mkdir -p assets/icon.iconset
    
    # 生成不同尺寸的图标
    for size in 16 32 64 128 256 512 1024; do
        sips -z $size $size assets/icon_1024x1024.png --out assets/icon.iconset/icon_${size}x${size}.png 2>/dev/null || true
        if [ $size -le 512 ]; then
            sips -z $((size*2)) $((size*2)) assets/icon_1024x1024.png --out assets/icon.iconset/icon_${size}x${size}@2x.png 2>/dev/null || true
        fi
    done
    
    # 创建 .icns 文件
    iconutil -c icns assets/icon.iconset -o assets/icon.icns 2>/dev/null || {
        echo -e "${YELLOW}⚠️  iconutil 失败，使用 sips 替代${NC}"
        cp assets/icon_1024x1024.png assets/icon.icns
    }
    
    echo "✓ 图标已创建: assets/icon.icns"
fi

# 清理之前的构建
echo -e "\n🧹 清理之前的构建..."
rm -rf build dist

# 运行 PyInstaller
echo -e "\n🔨 开始打包..."
pyinstaller videomind.spec --clean

# 检查结果
if [ -d "dist/VideoMind Bridge.app" ]; then
    echo -e "\n${GREEN}✅ 打包成功!${NC}"
    echo ""
    echo "应用位置: dist/VideoMind Bridge.app"
    echo ""
    echo "应用信息:"
    ls -lh "dist/VideoMind Bridge.app/Contents/MacOS/" | head -5
    echo ""
    echo "📋 后续步骤:"
    echo "   1. 测试应用: open 'dist/VideoMind Bridge.app'"
    echo "   2. 移动到应用程序: mv 'dist/VideoMind Bridge.app' /Applications/"
    echo "   3. 创建 DMG: ./create_dmg.sh"
else
    echo -e "\n${RED}❌ 打包失败${NC}"
    exit 1
fi

echo ""
echo "🎉 完成!"
