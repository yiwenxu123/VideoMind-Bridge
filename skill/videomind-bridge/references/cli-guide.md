# CLI 完整参数说明

## 基本用法

```bash
cd ~/.local/share/videomind-bridge
uv run python -m src.cli <URL> [选项]
```

## 参数详解

### 位置参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `url` | 视频链接（必需） | `"https://bilibili.com/video/BV1xx"` |

### 处理模式

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--mode full` | ✅ | 完整处理：下载 → 转录 → AI摘要 → 导出 |
| `--mode download` | | 仅下载视频/音频文件 |
| `--mode transcribe` | | 下载音频 + 转录生成 SRT/TXT |

### Whisper 转录模型

| 参数 | 模型大小 | 速度 | 精度 | 适用场景 |
|------|----------|------|------|----------|
| `--model tiny` | ~75MB | ⚡⚡⚡⚡⚡ | ★★ | 快速预览 |
| `--model base` | ~145MB | ⚡⚡⚡⚡ | ★★★ | 日常使用 |
| `--model small` | ~488MB | ⚡⚡⚡ | ★★★★ | 默认，平衡选择 |
| `--model medium` | ~1.5GB | ⚡⚡ | ★★★★★ | 高精度需求 |

### 导出选项

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--targets local` | ✅ | 导出到本地目录 |
| `--targets obsidian` | | 导出到 Obsidian Vault |
| `--targets local,obsidian` | | 多目标导出（逗号分隔） |
| `--obsidian-vault <path>` | | Obsidian Vault 路径 |
| `--output-dir <path>` | `~/Downloads/VideoMind` | 输出目录 |

### 视频控制

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--keep-video` | ✅ | 保留视频文件 |
| `--no-keep-video` | | 不保留视频，仅下载音频（节省空间） |
| `--video-quality best` | ✅ | 最佳质量 |
| `--video-quality 1080p` | | 指定分辨率 |
| `--video-quality 720p` | | 720p |
| `--video-quality 480p` | | 480p |

### 输出控制

| 参数 | 说明 |
|------|------|
| `--json` | JSON 格式输出（Agent/脚本调用时必用） |
| `--quiet` | 静默模式，仅输出最终结果 |
| `--mock` | 测试模式，使用模拟 AI 数据 |

## 使用示例

```bash
# 最常用：完整处理 + JSON 输出
uv run python -m src.cli "https://bilibili.com/video/BV1xx" --json

# 快速转录（节省时间和空间）
uv run python -m src.cli "URL" --mode transcribe --model tiny --no-keep-video --json

# 高精度转录
uv run python -m src.cli "URL" --mode transcribe --model medium --json

# 导出到 Obsidian
uv run python -m src.cli "URL" --targets obsidian --obsidian-vault ~/MyVault --json

# 仅下载视频
uv run python -m src.cli "URL" --mode download --video-quality 1080p --json

# 测试模式（无需 API Key）
uv run python -m src.cli "URL" --mock --json
```
