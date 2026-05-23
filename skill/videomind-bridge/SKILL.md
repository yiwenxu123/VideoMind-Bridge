---
name: videomind-bridge
description: |
  视频知识提取工具 - 下载视频、语音转录、AI摘要生成、多格式导出。
  
  触发词："视频处理", "视频转录", "视频摘要", "视频下载", "视频笔记", "video transcript", "video summary", "视频转文字", "B站下载", "YouTube转录"
  
  触发场景：
  - 用户提供视频链接并希望获取文字内容或摘要
  - 用户需要将视频内容转为笔记或文档
  - 用户需要下载视频/音频文件
  - 用户需要生成视频字幕（SRT）
  - 用户需要将视频知识导出到 Obsidian
  
  不触发：
  - 纯文本摘要（不涉及视频）
  - 图片处理
  - 音频编辑（非转录）
  
  输出：结构化视频知识（转录文本、AI摘要、时间轴要点、导出文件路径）
version: 1.0.0
user-invocable: true
metadata: {"openclaw":{"requires":{"bins":["uv","yt-dlp"],"anyBins":["ffmpeg"],"env":[]},"primaryEnv":"DEEPSEEK_API_KEY","emoji":"🎬","os":["darwin","linux"],"install":[{"id":"uv","kind":"brew","formula":"uv","bins":["uv"],"label":"Install uv (brew)"},{"id":"yt-dlp","kind":"brew","formula":"yt-dlp","bins":["yt-dlp"],"label":"Install yt-dlp (brew)"},{"id":"ffmpeg","kind":"brew","formula":"ffmpeg","bins":["ffmpeg"],"label":"Install ffmpeg (brew, 可选，格式转换)"}]},"author":"VideoMind","category":"productivity","tags":["video","transcription","ai-summary","obsidian","download"]}
---

# VideoMind Bridge - 视频知识提取工具

将视频内容转化为结构化知识：下载 → 语音转录 → AI摘要 → 多格式导出。

## Instructions

### 步骤 1: 环境检查与安装

⛔ Gate: 执行任何操作前，先验证环境是否就绪。

```bash
# 检查必需工具
which uv && which yt-dlp && echo "核心依赖OK" || echo "缺少依赖"

# 检查可选工具
which ffmpeg && echo "ffmpeg已安装" || echo "ffmpeg未安装"
```

如果缺少依赖，执行安装：

```bash
# macOS (brew)
brew install uv yt-dlp
brew install ffmpeg  # 可选，用于格式转换

# 验证安装
uv --version && yt-dlp --version
```

### 步骤 2: 安装 VideoMind Bridge

```bash
# 克隆项目（如果尚未安装）
PROJECT_DIR="$HOME/.local/share/videomind-bridge"
if [ ! -d "$PROJECT_DIR" ]; then
  git clone https://github.com/your-org/VideoMind-Bridge.git "$PROJECT_DIR"
fi

# 安装依赖
cd "$PROJECT_DIR" && uv sync
```

### 步骤 3: 配置 API Key

AI摘要功能需要 LLM API Key。选择一个可用的提供商：

| 提供商 | 环境变量 | 获取地址 |
|--------|----------|----------|
| DeepSeek（推荐） | `DEEPSEEK_API_KEY` | https://platform.deepseek.com |
| 智谱AI | `ZHIPU_API_KEY` | https://open.bigmodel.cn |
| Moonshot | `MOONSHOT_API_KEY` | https://platform.moonshot.cn |

```bash
# 设置 API Key（选择一个）
export DEEPSEEK_API_KEY="sk-your-key-here"
```

### 步骤 4: 执行视频处理

根据用户需求选择处理模式：

**模式 A: 完整处理（推荐）** - 下载 + 转录 + AI摘要 + 导出

```bash
cd "$PROJECT_DIR"
uv run python -m src.cli "VIDEO_URL" --mode full --json
```

**模式 B: 仅转录** - 下载音频 + 语音转文字 + SRT字幕

```bash
uv run python -m src.cli "VIDEO_URL" --mode transcribe --json
```

**模式 C: 仅下载** - 下载视频/音频文件

```bash
uv run python -m src.cli "VIDEO_URL" --mode download --json
```

**常用参数组合：**

```bash
# 节省空间：不保留视频文件
uv run python -m src.cli "VIDEO_URL" --no-keep-video --json

# 指定 Whisper 模型（tiny最快，medium最准）
uv run python -m src.cli "VIDEO_URL" --model tiny --json

# 导出到 Obsidian
uv run python -m src.cli "VIDEO_URL" --targets obsidian --obsidian-vault /path/to/vault --json

# 多目标导出
uv run python -m src.cli "VIDEO_URL" --targets local,obsidian --json

# 指定输出目录
uv run python -m src.cli "VIDEO_URL" --output-dir ~/Documents/VideoNotes --json
```

### 步骤 5: 解析结果并呈现

`--json` 标志输出结构化 JSON，解析关键字段呈现给用户：

- `result.success` → 是否成功
- `result.metadata.title` → 视频标题
- `result.metadata.platform` → 视频平台
- `result.summary.text` → AI摘要文本
- `result.summary.highlights` → 时间轴要点列表
- `result.transcript.full_text` → 完整转录文本
- `result.exports[].output_path` → 导出文件路径
- `result.error` → 错误信息（如果失败）

### 步骤 6: 向用户展示结果

将结果以清晰格式呈现：
1. 视频标题和作者
2. AI摘要（一句话总结）
3. 关键时间轴要点
4. 导出文件路径列表

## Examples

### 成功案例 1: 完整处理 B站视频

**Input**: "帮我处理这个B站视频 https://www.bilibili.com/video/BV1xx411c7mD"

**Action**:
```bash
cd ~/.local/share/videomind-bridge
uv run python -m src.cli "https://www.bilibili.com/video/BV1xx411c7mD" --mode full --json
```

**Output**: 解析 JSON 后呈现：
> 📹 **视频标题** - 作者名 | bilibili | 12分30秒
> 
> **AI摘要**: 本视频介绍了...
> 
> **关键要点**:
> - [02:15] 第一个要点内容
> - [05:30] 第二个要点内容
> - [09:45] 第三个要点内容
> 
> 📁 文件已导出至: ~/Downloads/VideoMind/...

### 成功案例 2: 仅转录 YouTube 视频

**Input**: "把这个 YouTube 视频转成文字 https://youtube.com/watch?v=xxx"

**Action**:
```bash
uv run python -m src.cli "https://youtube.com/watch?v=xxx" --mode transcribe --no-keep-video --json
```

### 边界案例: 缺少 API Key

**Input**: "帮我摘要这个视频"

**Action**: 检查环境变量，如果无 API Key：
1. 告知用户需要配置 API Key
2. 提供获取链接
3. 建议使用 `--mode transcribe` 模式（无需 API Key）作为替代

### 边界案例: 不支持的平台

**Input**: "处理这个 Vimeo 视频"

**Action**: 告知用户当前支持的平台列表（bilibili、youtube、douyin、xiaohongshu、kuaishou、tiktok、twitter、weibo、zhihu），建议尝试 `--mode download` 看 yt-dlp 是否支持。

## Output Format

成功时 JSON 结构：

```json
{
  "success": true,
  "url": "https://...",
  "mode": "full",
  "elapsed_seconds": 125.3,
  "metadata": {
    "title": "视频标题",
    "author": "作者",
    "duration": 750,
    "platform": "bilibili"
  },
  "video_path": "/path/to/video.mp4",
  "audio_path": "/path/to/audio.m4a",
  "transcript": {
    "language": "zh",
    "segments_count": 156,
    "full_text": "完整转录文本...",
    "srt_path": "/path/to/subtitle.srt"
  },
  "summary": {
    "text": "AI摘要内容...",
    "highlights": [
      {"time": "02:15", "seconds": 135, "content": "要点内容"}
    ]
  },
  "exports": [
    {"target": "local", "success": true, "output_path": "/path/to/output"}
  ]
}
```

失败时 JSON 结构：

```json
{
  "success": false,
  "url": "https://...",
  "mode": "full",
  "elapsed_seconds": 12.5,
  "error": "错误描述",
  "error_step": "download|transcribe|ai_summary|export"
}
```

## Troubleshooting

| 症状 | 原因 | 修复方式 |
|------|------|----------|
| `yt-dlp` 下载失败 | 版本过旧或平台限制 | `brew upgrade yt-dlp` |
| 抖音/小红书下载失败 | 需要 Cookie | 使用 `--cookies-from-browser chrome` 或导出 Cookie |
| Whisper 模型下载慢 | HuggingFace 网络问题 | 设置 `HF_ENDPOINT=https://hf-mirror.com` |
| AI摘要返回空 | API Key 无效或余额不足 | 检查 API Key 和账户余额 |
| `faster-whisper` 安装失败 | 缺少 CTranslate2 依赖 | `brew install cmake` 后重试 |
| 转录质量差 | Whisper 模型太小 | 使用 `--model medium` 提高精度 |
| 磁盘空间不足 | 视频文件较大 | 使用 `--no-keep-video` 仅保留音频 |
| JSON 输出为空 | 命令执行中途崩溃 | 去掉 `--json` 查看详细错误信息 |

## References

- CLI 完整参数说明 → `{skillDir}/references/cli-guide.md`
- API 服务使用指南 → `{skillDir}/references/api-guide.md`
- 配置与环境变量 → `{skillDir}/references/config-guide.md`
- 支持平台与下载器 → `{skillDir}/references/platforms-guide.md`
