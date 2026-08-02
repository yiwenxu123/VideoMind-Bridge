---
name: videomind-bridge
description: |
  视频知识提取工具 - v3 (提取成本决策 + 多引擎提取 + 提取即归档)。
  
  触发词："视频处理", "视频提取", "视频转文字", "视频摘要", "视频预筛", "内容评估", "视频笔记", "video extract", "video transcript", "video summary", "B站提取", "YouTube 转录", "内容提取", "视频归档", "归档到Obsidian"
  
  触发场景：
  - 用户提供视频链接并希望获取文字内容
  - 用户需要评估提取成本（预筛 cost_grade）
  - 用户需要提取视频字幕/文本
  - 用户需要将视频内容归档到 Obsidian/本地
  - 用户需要下载视频或转录音频
  
  不触发：
  - 纯文本摘要（不涉及视频）
  - 图片处理
  - 音频编辑（非转录）
  - 深度内容价值评估（交给 content-value-evaluator skill）
  
  输出：结构化视频内容（提取文本、成本分级、字幕、归档文件路径）
version: 3.0.0
user-invocable: true
metadata: {"openclaw":{"requires":{"bins":["uv","yt-dlp"],"anyBins":["ffmpeg"],"env":["DEEPSEEK_API_KEY"]},"primaryEnv":"DEEPSEEK_API_KEY","emoji":"🎬","os":["darwin","linux"],"install":[{"id":"uv","kind":"brew","formula":"uv","bins":["uv"],"label":"Install uv (brew)"},{"id":"yt-dlp","kind":"brew","formula":"yt-dlp","bins":["yt-dlp"],"label":"Install yt-dlp (brew)"},{"id":"ffmpeg","kind":"brew","formula":"ffmpeg","bins":["ffmpeg"],"label":"Install ffmpeg (brew, 可选)"}]},"author":"VideoMind","category":"productivity","tags":["video","transcription","extraction","prescreen","ai-summary","archive","mcp"]}
---
# VideoMind Bridge v3 - 视频内容提取 + 成本决策 + 归档工具

主链 (v2 Engine):
- **提取成本决策** → **多引擎提取** (B站/YouTube/抖音/小红书) → **结构化输出** → **提取即归档**
- 职责边界: VMB 只做采集与成本决策; 深度价值评估交给 content-value-evaluator

## Instructions

### 步骤 1: 环境检查与安装

```bash
which uv && which yt-dlp && echo "核心依赖OK" || echo "缺少依赖"
which ffmpeg && echo "ffmpeg已安装" || echo "ffmpeg未安装"

# 安装项目
PROJECT_DIR="$HOME/.local/share/videomind-bridge"
if [ ! -d "$PROJECT_DIR" ]; then
  git clone https://github.com/yiwenxu123/VideoMind-Bridge.git "$PROJECT_DIR"
fi
cd "$PROJECT_DIR" && uv sync
```

### 步骤 2: 配置 API Key

v2 提取引擎**无需任何 API Key** (零Cookie直接提取)。以下 Key 用于增强功能:

| 用途 | 环境变量 | 必需? |
|------|----------|-------|
| AI摘要 (v1) | `DEEPSEEK_API_KEY` | v1 必需, v2 可选 |
| DashScope ASR (无字幕兜底) | `ALI_API_KEY` | 可选 |
| 商业API (v2) | `TIKHUB_API_KEY` / `APIFY_API_KEY` / `ALIYUN_ACCESS_KEY_ID` + `ALIYUN_ACCESS_KEY_SECRET` + `ALIYUN_APPKEY` | 可选 |

```bash
# 最小配置（v2 零Cookie提取，不需要任何 Key）
# 可选：AI 摘要
export DEEPSEEK_API_KEY="sk-your-key-here"
# 可选：DashScope ASR (无字幕视频转写)
export ALI_API_KEY="sk-your_dashscope_key"
```

### 步骤 3: v2 提取模式 (推荐)

直接用 v2 引擎提取视频内容，无需下载/转码，速度快。

**模式 A: 直接提取** — 自动选择最佳提取器

```bash
cd "$PROJECT_DIR"
uv run python -m src.cli "URL" --json
```

**模式 B: 智能提取** — 预筛 + 成本感知提取

```bash
# 先FREE提取元信息 → 预筛评分 → C级以上自动提取
uv run python -m src.cli "URL" --smart --json
```

**模式 C: 仅预筛** — 评估内容价值，不提取

```bash
# 快速 (<2ms): 仅URL分析
uv run python -m src.cli "URL" --prescreen-only --json

# 完整: 先提取元信息再评分 (<10s)
uv run python -m src.cli "URL" --prescreen --json
```

**模式 D: 指定成本等级**

```bash
# 仅免费提取器
uv run python -m src.cli "URL" --cost-tier free --json
# 允许付费 API
uv run python -m src.cli "URL" --cost-tier paid --json
# 允许所有 (含 ASR)
uv run python -m src.cli "URL" --cost-tier premium --json
```

**模式 E: 列出可用提取器**

```bash
uv run python -m src.cli --list-extractors
```

**模式 F: 提取即归档 (一条命令入库)**

```bash
# 提取全文 → 写入 Obsidian + 本地
uv run python -m src.cli "URL" --archive obsidian,local --obsidian-vault /path/to/vault --json

# 仅归档到本地
uv run python -m src.cli "URL" --archive local --json
```

### 步骤 4: v1 处理模式 (视频下载 + 转录 + 摘要)

当需要完整处理（含 AI 摘要和文件导出）时使用:

```bash
# 完整处理 (下载+转录+AI摘要)
uv run python -m src.cli "URL" --mode full --json

# 仅转录
uv run python -m src.cli "URL" --mode transcribe --json

# 仅下载
uv run python -m src.cli "URL" --mode download --json

# 导出到 Obsidian
uv run python -m src.cli "URL" --targets obsidian --obsidian-vault /path/to/vault --json
```

### 步骤 5: MCP 模式 (AI Agent 直接调用)

MCP Server 提供工具，Agent 可直接调用:

```json
// 预筛视频质量
{
  "tool": "prescreen_video",
  "args": { "url": "https://...", "mode": "quick" }
}
// 返回: { "grade": "B", "score": 72.5, "reasons": [...] }

// 智能提取 (预筛+提取一步完成)
{
  "tool": "smart_extract",
  "args": { "url": "https://..." }
}
// 返回: { "prescreen": {...}, "extraction_performed": true, "result": {...} }

// 直接提取
{
  "tool": "extract_video",
  "args": { "url": "https://...", "cost_tier": "free" }
}

// 提取并归档 (写入 Obsidian/本地)
{
  "tool": "archive_extract",
  "args": { "url": "https://...", "targets": ["obsidian", "local"], "obsidian_vault": "/path/to/vault" }
}

// 列出提取器
{
  "tool": "list_extractors"
}
```

### 步骤 6: 解析 v2 输出

**预筛结果 (prescreen_video):**

```json
{
  "grade": "B",
  "cost_grade": "A",
  "score": 72.5,
  "platform": "bilibili",
  "reasons": ["评分 72/100 → A 级", "平台 bilibili: 零 Cookie 免费提取", "平台 bilibili: 预期有官方字幕 (免费完整内容)"],
  "recommended_cost_tier": "free",
  "skip_reason": null
}
```

两套分级含义 (注意区分):
- **grade** (内容基本面, 兼容保留): SEO/时长/营销规则评分
- **cost_grade** (提取成本决策, v3 主用): 回答"提取要花多少钱"
  - **S/A**: 免费可及 (零 Cookie + 官方字幕) → 推荐 `free`
  - **B**: 免费但内容有限 → 推荐 `cheap` (ASR 兜底)
  - **C**: 需付费通道 (无字幕需 ASR) → 推荐 `paid`
  - **D**: 提取性价比低 → `skip_reason` 说明, 建议跳过
- **recommended_cost_tier**: 直接作为 router 的 `max_cost` 输入
- 深度内容价值评估**不在此处** — 交给 content-value-evaluator skill

**提取结果 (extract_video):**

```json
{
  "success": true,
  "platform": "bilibili",
  "title": "视频标题",
  "content": "完整文字内容...",
  "source": "bilibili_api",
  "cost_tier": "free",
  "duration_seconds": 750.0
}
```

**智能提取 (smart_extract):**

```json
{
  "prescreen": {
    "grade": "A",
    "score": 78.0,
    "extraction_recommended": true
  },
  "extraction_performed": true,
  "result": {
    "success": true,
    "platform": "bilibili",
    "title": "视频标题",
    "content": "完整文字内容...",
    "source": "bilibili_api"
  }
}
```

`prescreen` 内含 `cost_grade`（成本分级）与 `recommended_cost_tier`（推荐成本），Agent 可直接据此决策是否升级提取成本。

### 步骤 7: 向用户呈现 v2 结果

```
📹 视频标题 (bilibili | 12分30秒)
📊 成本分级: A级 (推荐免费提取)
📝 内容预览: [前200字...]
```

对于 v1 完整处理结果，还包含摘要和时间轴。

## Extractors (9)

| 提取器 | 成本 | 依赖 | 说明 |
|--------|------|------|------|
| bilibili | 免费 | 无 | WBI签名，零Cookie |
| youtube | 免费 | pip | youtube-transcript-api |
| douyin | 免费 | 无 | iesdouyin 移动端API |
| xiaohongshu | 免费 | 无 | 页面解析 |
| dashscope_key | 便宜 | ALI_API_KEY | 无字幕视频 ASR 转写 |
| ytdlp | 免费 | yt-dlp | 1800+ 平台兜底 |
| tikhub | 商业 | TIKHUB_API_KEY | 1000+ API |
| apify | 商业 | APIFY_API_KEY | 预构建爬虫 |
| aliyun_asr | 付费 | 阿里云Key | 无字幕视频ASR |

## Examples

### 成功案例 1: 智能提取 B站视频

**Input**: "帮我提取这个B站视频的内容" https://bilibili.com/video/BV1xx411c7mD

**Action**:
```bash
cd ~/.local/share/videomind-bridge
uv run python -m src.cli "https://bilibili.com/video/BV1xx411c7mD" --smart --json
```

**Output**: 解析 JSON 呈现：
> 📹 **视频标题** - bilibili | 12分30秒
> 📊 预筛: A级 (78/100) - 值得提取
> 🔍 提取: bilibili_api (免费)
> 📝 内容: [转录文本/字幕...]

### 成功案例 2: 预筛评估内容价值

**Input**: "评估这个视频值不值得看" https://bilibili.com/video/BV1xx

**Action**:
```bash
uv run python -m src.cli "URL" --prescreen --json
```

**Output**:
> 📊 内容预筛结果: **C级** (45/100)
> ⚠ 低价值内容 (SEO标题 + 短时长)
> 建议: 跳过提取

### 成功案例 3: MCP Agent 调用

Agent 直接通过 MCP 调用:
```
用户: "这个视频讲的是什么？"
Agent: 调用 prescreen_video → smart_extract → 返回内容摘要
```

### 边界案例: 配置商业 API 提升质量

配置 TIKHUB_API_KEY 后提取器自动启用，无需修改命令:
```bash
export TIKHUB_API_KEY="your-key"
uv run python -m src.cli "URL" --cost-tier premium --json
```

### 边界案例: 无字幕视频 (ASR 兜底)

```bash
# 使用阿里云 ASR 转写
export ALIYUN_ACCESS_KEY_ID="..."
export ALIYUN_ACCESS_KEY_SECRET="..."
export ALIYUN_APPKEY="..."
uv run python -m src.cli "URL" --cost-tier expensive --json
```

## Output Formats

### v2 提取输出
```json
{
  "success": true,
  "platform": "bilibili",
  "title": "视频标题",
  "content": "完整文字内容...",
  "source": "bilibili_api",
  "url": "https://...",
  "cost_tier": "free",
  "duration_seconds": 750.0,
  "language": "zh",
  "segments": [...]
}
```

### v2 智能模式输出 (含预筛)
```json
{
  "success": true,
  "platform": "bilibili",
  "title": "...",
  "content": "...",
  "source": "bilibili_api",
  "cost_tier": "free",
  "prescreen": {
    "url": "https://...",
    "platform": "bilibili",
    "grade": "A",
    "score": 78.0,
    "reasons": [...],
    "extraction_recommended": true
  }
}
```

### v2 提取失败时
```json
{
  "success": false,
  "platform": "unknown",
  "error": "所有提取器均不可用",
  "cost_tier": "free"
}
```

### v1 完整处理输出 (含摘要)
参见 references/cli-guide.md。

## Troubleshooting

| 症状 | 原因 | 修复方式 |
|------|------|----------|
| v2 提取失败 | 平台API变更 | 自动降级到 yt-dlp 兜底 |
| 抖音/小红书失败 | 反爬升级 | 使用 `--cost-tier premium` 启用商业API |
| 平台风控 (验证码/403) | 本地 IP 受限 | 配置 cookies.txt (DOUYIN_COOKIES_FILE) |
| yt-dlp 下载失败 | 版本过旧 | `brew upgrade yt-dlp` |
| Whisper 模型下载慢 | HuggingFace网络 | `HF_ENDPOINT=https://hf-mirror.com` |
| AI摘要为空 | API Key 无效 | 检查 Key 和余额 |
| 无字幕视频 | 本身没字幕 | 用 `--cost-tier expensive` 启动 ASR |

## References
- CLI 完整参数 → `{skillDir}/references/cli-guide.md`
- API 服务指南 → `{skillDir}/references/api-guide.md`
- 配置与环境变量 → `{skillDir}/references/config-guide.md`
- 支持平台与提取器 → `{skillDir}/references/platforms-guide.md`
