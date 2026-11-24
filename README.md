# VideoMind Bridge

**AI Agent 的视频内容知识层** — 把 `URL → 价值判断 → 文字提取 → 知识入库` 做成一条端到端能力。
支持零Cookie提取 B站/YouTube/抖音/小红书等平台内容，提取即归档 Obsidian。

面向 AI Agent（Hermes / OpenClaw / Claude Code）与 Obsidian 知识工作者。

## 功能特性

### v2 Engine（主链，推荐）
- **多引擎提取**：9 个提取器自动降级（B站/YouTube/抖音/小红书/yt-dlp/tikhub/Apify/阿里云ASR）
- **零Cookie提取**：B站 WBI 签名、抖音 iesdouyin、小红书页面解析，无需浏览器 Cookie
- **提取成本决策**：预筛回答"提取这个链接要花多少钱"（cost_grade + recommended_cost_tier），S/A 免费、B 便宜、C 需付费、D 建议跳过
- **成本感知路由**: 免费 > 付费自动选择，失败自动降级下一级
- **提取即归档**: `--archive obsidian,local` 一条命令把全文写入 Obsidian/本地，无需下载视频
- **结构化输出**: Hermes 兼容 JSON 格式
- **MCP Server**: AI Agent 直接调用（prescreen_video / smart_extract / extract_video / archive_extract）

> 职责边界: VideoMind Bridge 负责**采集与成本决策**；内容价值的深度评估交给 content-value-evaluator skill

### v1 (Legacy 扩展模式)

> 状态：Legacy / 冻结。仅保留兼容性，不再作为新功能的默认入口；新工作流请使用 v2 Engine、MCP 或 Gateway Console。

- **视频下载**：支持 Bilibili、YouTube、抖音、小红书等平台
- **语音转录**：自动生成字幕和时间轴
- **AI 摘要**：使用 DeepSeek 等国内模型生成智能摘要
- **多格式导出**：支持 Obsidian、本地文件夹、HTML 播放器
- **任务管理**：队列管理、暂停、恢复、历史记录
- **本地 API 服务**：提供 REST API 和 WebSocket

## 安装

### 环境要求

- Python 3.11+
- macOS / Windows / Linux

### 安装步骤

```bash
# 克隆仓库
git clone <repository-url>
cd VideoMindBridge

# 使用 uv 安装依赖（推荐）
uv sync                 # 服务端 / CLI / MCP（2026-11-24 起桌面 GUI 已下线）
uv sync --extra dev     # 开发（ruff/mypy/pytest）

# 或使用 pip
pip install .
```

### ASR 后端（可选，默认链第一级 SenseVoice）

无字幕视频靠 ASR 兜底，默认链是 `sensevoice → faster_whisper → dashscope`
（单一常量定义在 `src/models/config.py` 的 `DEFAULT_ASR_CHAIN`）。
其中 SenseVoice 的依赖**故意不进主 venv**（sherpa-onnx 体积大），要单独准备解释器与模型：

```bash
./scripts/install_sensevoice.sh --check   # 先体检：只读，不下载不安装
./scripts/install_sensevoice.sh           # 安装/补全（幂等，已就绪直接跳过）
```

它做三件事：建 `~/.cache/sensevoice/venv` 并装 `sherpa-onnx + soundfile`、
把模型下到 `~/.cache/sherpa-onnx/sense-voice/`（约 230MB）、用 1 秒静音 wav 真跑一次转写自检。
国内网络可加 `--index-url https://pypi.tuna.tsinghua.edu.cn/simple`。

不装也能跑：`/api/v1/capabilities` 会把 sensevoice 标成 `available=false` 并写明缺什么，
提取链自动落到下一级 `faster_whisper`。自 2026-11-24 起这个判断是**真探测**
（起子进程试 `import sherpa_onnx, soundfile`），不再只看文件是否存在。

### Docker 部署（服务端）

```bash
docker compose up -d --build
curl http://127.0.0.1:8787/health
```

默认只绑定 `127.0.0.1:8787`；远程消费者请设置 `VMB_BIND_ADDR=0.0.0.0`，
并按需配置 `VIDEOMIND_API_TOKEN` / `VMB_CONSUMER_TOKENS` / `VMB_RATE_LIMIT_PER_MIN`。

本机常驻（PM2）：

```bash
pm2 start ecosystem.config.cjs
pm2 save
```

### Gateway Console

启动 API 后打开：

```text
http://127.0.0.1:8787/console
```

控制台包含：概览、平台健康、提取/归档、公开评论采样、会话状态、指标和能力探测。
如果配置了 `VIDEOMIND_API_TOKEN` / `VMB_CONSUMER_TOKENS`，在右上角「设置 Token」填入即可。

旧版 v1 工作站仍保留在 `http://127.0.0.1:8787/legacy`，用于过渡；新操作请使用 Gateway Console。

## 使用

### v2 Engine (CLI, 主入口)

```bash
# 直接提取内容（自动选择最佳提取器）
uv run python -m src.cli "URL" --json

# 智能模式：成本决策 + 自动提取
uv run python -m src.cli "URL" --smart --json

# 提取即归档 Obsidian + 本地（一条命令完成）
uv run python -m src.cli "URL" --archive obsidian,local --obsidian-vault /path/to/vault --json

# 仅成本决策（快速评估，零网络）
uv run python -m src.cli "URL" --prescreen-only --json

# 列出可用提取器
uv run python -m src.cli --list-extractors

# 指定成本等级
uv run python -m src.cli "URL" --cost-tier paid --json
```

### MCP Server (AI Agent 调用)

```bash
# 启动 MCP Server (stdio JSON-RPC)
python main.py --mcp
# 或
uv run python -m src.mcp.server
```

MCP 工具列表:
| 工具 | 说明 |
|------|------|
| `prescreen_video` | 成本决策（纯规则，零网络），输出 cost_grade + recommended_cost_tier |
| `smart_extract` | 智能提取：成本决策 → 评分 → 自动提取 |
| `extract_video` | 直接提取内容 |
| `archive_extract` | 提取并归档（Obsidian/本地） |
| `list_extractors` | 列出所有提取器及状态 |
| `configure` | 获取/设置配置 |

### v1 (Legacy 扩展模式)

> **2026-11-24：桌面 GUI 与浏览器扩展已下线**（PySide6 依赖一并移除；`python main.py` 不带参数会打印用法并退出）。
> v1 的下载 / 转录 / AI 摘要能力仍在：用下面的 API 模式 + `/legacy` 页面，或 CLI 的 `--mode`。

#### API 服务模式

```bash
python main.py --api
# 或指定端口
python main.py --api --port 9000
# Gateway Console: http://127.0.0.1:8787/console
# 旧版工作站: http://127.0.0.1:8787/legacy
# API 文档: http://127.0.0.1:8787/docs
```

#### CLI 完整处理

```bash
# 完整处理（下载 + 转录 + AI摘要 + 导出）
uv run python -m src.cli "URL" --mode full --json

# 仅转录
uv run python -m src.cli "URL" --mode transcribe --json

# 仅下载
uv run python -m src.cli "URL" --mode download --json
```

## 配置

首次启动时会自动创建配置文件 `~/.config/VideoMind/config.yaml`。

### AI 引擎配置

支持以下模型：
- DeepSeek（deepseek-chat）
- 智谱 AI（glm-4）
- Moonshot（moonshot-v1-8k）
- MiniMax
- 豆包
- Ollama（本地）
- OpenAI（GPT-4o、GPT-4）
- Anthropic（Claude 3.5）

### 导出配置

- **Obsidian**：设置 Vault 路径和子文件夹
- **本地文件夹**：设置输出目录和组织方式

## 开发

### 项目结构

```
src/
├── core/                 # ★ v2 核心引擎
│   ├── prescreener.py    # 提取成本决策引擎 (cost_grade)
│   ├── prescreen_rules.py# 规则集: 成本/平台/字幕/时长
│   ├── router.py         # 成本感知路由
│   ├── archiver.py       # 提取即归档 (Obsidian/本地/HTML)
│   ├── formatter.py      # Hermes 输出格式化
│   ├── models.py         # 数据模型
│   └── extractors/       # 9 个提取器
│       ├── bilibili_extractor.py
│       ├── youtube_extractor.py
│       ├── douyin_extractor.py
│       ├── xiaohongshu_extractor.py
│       ├── ytdlp_extractor.py
│       ├── ytdlp_asr_extractor.py   # yt-dlp + 阿里云 ASR
│       ├── tikhub_extractor.py      # 商业API
│       └── apify_extractor.py       # 商业爬虫
├── api/                  # API 服务（FastAPI + WebSocket, v1 扩展）
├── cli.py                # CLI 入口（v2 主链 + v1 --mode full 扩展）
├── mcp/                  # MCP Server（stdio JSON-RPC, v2 工具为主）
├── config/               # 配置常量
├── exporters/            # 导出器
├── models/               # 数据模型
├── services/             # v1 服务（扩展模式）
└── utils/                # 工具函数
    └── platform_detector.py  # 统一平台检测（13 平台）
```

### 运行测试

```bash
# 安装测试依赖
pip install -e ".[dev]"

# 运行所有测试
pytest tests/ -v

# 运行测试并查看覆盖率
pytest tests/ -v --cov=src --cov-report=term-missing
```

## 版本历史

### v3.0.0（定位收敛）

- **定位**: AI Agent 的视频内容知识层（URL → 价值判断 → 提取 → 知识入库）
- **预筛重定义**: 从"内容质量评分"改为"提取成本决策"（cost_grade + recommended_cost_tier），直接驱动路由
- **提取即归档**: 新增 `archiver.py`，`--archive obsidian,local` 一条命令入库
- **MCP 升级**: 新增 `archive_extract` 工具；v1 工具标 [DEPRECATED]
- **架构收敛**: 删除假接口 `interfaces.py`、清理 6 个调试块、API 补 v2 归档端点
- **职责边界**: VMB 只做采集与成本决策，内容价值评估交给 content-value-evaluator

### v2.0.0（2026-05-24）

- **v2 核心引擎**：9 个提取器 + 内容预筛 + 成本感知路由
- **零Cookie提取**：B站/YouTube/抖音/小红书 无需浏览器 Cookie
- **MCP 升级**：prescreen_video + smart_extract + configure 工具
- **商业 API 适配器**：tikhub.io / Apify / 阿里云 ASR
- **CLI v2 模式**：--smart / --prescreen / --prescreen-only / --cost-tier
- **Hermes 兼容**：统一结构输出，AI Agent 原生可消费

### v1.0.0（2026-02-02）

- 初始版本发布
- 支持视频下载、转录、AI 摘要
- 支持多种导出格式
- 实现任务队列和历史记录
- 系统托盘支持
- 自动重试机制
- 本地 API 服务 + 浏览器扩展

## 许可证

MIT License
