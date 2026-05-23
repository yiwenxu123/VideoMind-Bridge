#!/bin/bash
# 创建 VideoMind Bridge DMG 安装包

set -e

APP_NAME="VideoMind Bridge"
DMG_NAME="VideoMind-Bridge-1.0.0.dmg"
VOLUME_NAME="VideoMind Bridge Installer"

echo "🎯 创建 DMG 安装包..."

# 检查应用是否存在
if [ ! -d "dist/${APP_NAME}.app" ]; then
    echo "❌ 错误: 未找到 dist/${APP_NAME}.app"
    echo "   请先运行 ./build_macos_app.sh"
    exit 1
fi

# 创建临时目录
TMP_DIR=$(mktemp -d)
mkdir -p "${TMP_DIR}/${APP_NAME}"

# 复制应用
cp -r "dist/${APP_NAME}.app" "${TMP_DIR}/${APP_NAME}/"

# 创建 Applications 快捷链接
ln -s /Applications "${TMP_DIR}/${APP_NAME}/Applications"

# 创建 .DS_Store 设置窗口样式（可选）
# 可以添加背景图片和布局

# 创建 DMG
echo "📦 打包 DMG..."
hdiutil create \
    -volname "${VOLUME_NAME}" \
    -srcfolder "${TMP_DIR}/${APP_NAME}" \
    -ov \
    -format UDZO \
    "${DMG_NAME}"

# 清理
rm -rf "${TMP_DIR}"

echo "✅ DMG 创建成功: ${DMG_NAME}"
echo ""
echo "📋 文件信息:"
ls -lh "${DMG_NAME}"
