# VideoMind Bridge macOS 应用打包指南

本文档介绍如何将 VideoMind Bridge 打包为独立的 macOS 应用程序。

## 当前状态

```
当前: Python 脚本 🐍
     python3 main.py

目标: macOS 应用 📱
     VideoMind Bridge.app
```

## 打包方案

### 方案 1: PyInstaller（推荐）

**优点**:
- 简单易用，一键打包
- 支持代码签名
- 社区活跃，文档完善

**缺点**:
- 应用体积较大（约 300-500MB）
- 启动速度稍慢

### 方案 2: PySide6 Deploy

**优点**:
- 专为 Qt 应用优化
- 体积可能更小

**缺点**:
- 工具较新，文档较少
- 配置较复杂

## 快速开始

### 1. 准备工作

```bash
# 确保在虚拟环境中
source .venv/bin/activate

# 安装打包工具
pip install pyinstaller pillow
```

### 2. 准备应用图标

将您的应用图标（1024x1024 PNG）放入 `assets/` 目录：

```bash
mkdir -p assets
cp your-icon.png assets/icon_1024x1024.png
```

或者使用脚本自动生成简单图标：

```bash
./build_macos_app.sh
```

### 3. 打包应用

```bash
# 方法 1: 使用打包脚本（推荐）
./build_macos_app.sh

# 方法 2: 手动打包
pyinstaller videomind.spec --clean
```

### 4. 测试应用

```bash
# 运行应用
open 'dist/VideoMind Bridge.app'

# 查看日志（调试用）
'./dist/VideoMind Bridge.app/Contents/MacOS/VideoMind Bridge'
```

### 5. 创建 DMG 安装包

```bash
./create_dmg.sh
```

输出: `VideoMind-Bridge-1.0.0.dmg`

## 应用签名（可选但推荐）

### 使用开发者证书签名

```bash
# 1. 在 Apple Developer 网站申请证书
# 2. 安装证书到钥匙串

# 3. 修改 videomind.spec
codesign_identity='Developer ID Application: Your Name (TEAM_ID)'

# 4. 重新打包
pyinstaller videomind.spec --clean

# 5. 验证签名
codesign -dv --verbose=4 'dist/VideoMind Bridge.app'
```

### 公证（Notarization）

```bash
# 1. 创建 zip
zip -r 'VideoMind Bridge.zip' 'dist/VideoMind Bridge.app'

# 2. 提交公证
xcrun altool --notarize-app \
    --primary-bundle-id "dev.videomind.bridge" \
    --username "your@email.com" \
    --password "@keychain:AC_PASSWORD" \
    --file "VideoMind Bridge.zip"

# 3. 等待邮件通知后， staple 公证信息
xcrun stapler staple 'dist/VideoMind Bridge.app'
```

## 常见问题

### Q: 应用显示"无法打开，因为无法验证开发者"

**A**: 右键点击应用，选择"打开"，或禁用 Gatekeeper:

```bash
sudo spctl --master-disable
# 使用完毕后重新启用
sudo spctl --master-enable
```

### Q: 应用图标不显示

**A**: 确保:
1. `assets/icon.icns` 存在
2. 图标尺寸包含所有必要尺寸（16, 32, 64, 128, 256, 512, 1024）
3. 重新打包: `rm -rf build dist && ./build_macos_app.sh`

### Q: 应用体积太大

**A**: 可以尝试:
1. 使用 UPX 压缩（已启用）
2. 排除不必要的模块（修改 videomind.spec 中的 excludes）
3. 使用 PySide6 Deploy 替代 PyInstaller

### Q: 启动速度慢

**A**: 
1. 首次启动需要解压，后续会快很多
2. 考虑使用 `--onedir` 模式（默认）而非 `--onefile`
3. 禁用不必要的导入

## 文件说明

| 文件 | 说明 |
|------|------|
| `videomind.spec` | PyInstaller 配置文件 |
| `build_macos_app.sh` | 一键打包脚本 |
| `create_dmg.sh` | DMG 创建脚本 |
| `assets/icon.icns` | 应用图标 |
| `dist/VideoMind Bridge.app` | 打包后的应用 |

## 发布流程

```
1. 更新版本号
   - pyproject.toml
   - videomind.spec
   - create_dmg.sh

2. 测试功能
   - 下载视频
   - 转录
   - AI 摘要
   - 导出

3. 打包
   ./build_macos_app.sh

4. 签名（可选）
   codesign -s "Developer ID" 'dist/VideoMind Bridge.app'

5. 创建 DMG
   ./create_dmg.sh

6. 测试安装
   - 卸载旧版本
   - 安装新版本
   - 验证功能

7. 发布
   - 上传到 GitHub Releases
   - 更新下载链接
```

## 高级配置

### 自定义 Info.plist

修改 `videomind.spec` 中的 `info_plist` 字典：

```python
info_plist={
    'CFBundleShortVersionString': '1.1.0',
    'CFBundleVersion': '1.1.0',
    'LSMinimumSystemVersion': '11.0',  # 要求 macOS 11+
    # ... 其他配置
}
```

### 添加文件关联

```python
info_plist={
    # ... 其他配置
    'CFBundleDocumentTypes': [
        {
            'CFBundleTypeName': 'VideoMind Playlist',
            'CFBundleTypeExtensions': ['vmplaylist'],
            'CFBundleTypeRole': 'Editor',
        }
    ]
}
```

## 参考资源

- [PyInstaller 文档](https://pyinstaller.readthedocs.io/)
- [Apple 代码签名指南](https://developer.apple.com/documentation/xcode/creating-distribution-signed-code-for-the-mac)
- [macOS 应用公证](https://developer.apple.com/documentation/xcode/notarizing_macos_software_before_distribution)
