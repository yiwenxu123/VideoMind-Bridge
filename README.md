# VideoMind Bridge

**AI Agent 的视频内容知识层** — 把 `URL → 价值判断 → 文字提取 → 知识入库` 做成一条端到端能力。
支持零Cookie提取 B站/YouTube/抖音/小红书等平台内容，提取即归档 Obsidian。

面向 AI Agent（Hermes / OpenClaw / Claude Code）与 Obsidian 知识工作者。

## 功能特性

### v2 Engine（主链，推荐）
- **多引擎提取**：8 个提取器自动降级（B站/YouTube/抖音/小红书/yt-dlp/yt-dlp+ASR/TikHub/Apify）
- **零Cookie提取**：B站 WBI 签名、抖音 iesdouyin、小红书页面解析，无需浏览器 Cookie
- **提取成本决策**：预筛回答"提取这个链接要花多少钱"（cost_grade + recommended_cost_tier），S/A 免费、B 便宜、C 需付费、D 建议跳过
- **成本感知路由**: 免费 > 付费自动选择，失败自动降级下一级
- **提取即归档**: `--archive obsidian,local` 一条命令把全文写入 Obsidian/本地，无需下载视频
- **结构化输出**: Hermes 兼容 JSON 格式
- **MCP Server**: AI Agent 直接调用（`extract` / `capabilities` / `comments` 三个工具，薄适配器，经 HTTP 调本服务）

> 职责边界: VideoMind Bridge 负责**采集与成本决策**；内容价值的深度评估交给 content-value-evaluator skill

> **2026-11-25（A2）：v1 流水线已删除**（下载 → 转录 → AI 摘要 → 任务队列/WebSocket）。
> 现在只剩两条能力：**链接提取**（v2 引擎）与**本地文件转写**（走同一条 ASR 降级链）。

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

旧版 v1 工作站（`/legacy`）、WebSocket（`/ws`）与任务接口（`/api/v1/tasks*`）已于 2026-11-25 删除。

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

MCP 工具列表（3 个，2026-11-23 从 12 个收敛；2026-11-25 删除全部 v1 工具）:
| 工具 | 说明 |
|------|------|
| `extract` | 提取正文；`mode=prescreen` 时改走零网络成本预筛 |
| `capabilities` | 提取器与 ASR 后端能力矩阵 |
| `comments` | 评论采样（需 `VMB_ENABLE_COMMENTS=1`） |

MCP 是**薄适配器**：把请求转给本机 REST(8787)，自己不跑引擎（服务没起会明确报错）。

### 本地文件转写（手动下载的视频）

平台拿不到直链时（如视频号），可以先手动下载，再让本服务转写。这条路径**只做转写**，
没有下载、没有 AI 摘要 —— 走的是同一套 ASR 降级链：

```bash
uv run python -m src.cli ~/Downloads/manual.mp4 --json
uv run python -m src.cli ~/Downloads/manual.mp4 --asr-chain sensevoice,faster_whisper
```

### API 服务模式

```bash
python main.py --api
python main.py --api --port 9000
# Gateway Console: http://127.0.0.1:8787/console
# API 文档:        http://127.0.0.1:8787/docs
```

## 配置

首次启动时会自动创建配置文件 `~/.config/VideoMind/config.yaml`。

### AI 引擎配置

> **2026-11-25（A2）**：AI 摘要（DeepSeek / 智谱 / Moonshot / …）随 v1 流水线删除。
> `config.yaml` 的 `ai` 段与 `/api/v1/settings` 的 AI 字段仍在（读旧配置不报错），
> 但**已无执行者**；下一次整理配置 schema 时一并去掉。

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
│   ├── asr/              # ASR 统一层（降级链 + 4 个后端适配器）
│   ├── media/            # yt-dlp/HTTP 取媒体 + ffmpeg 转码
│   ├── platforms/        # 登录态 / 限流 / 熔断
│   ├── discovery/        # 评论 / 创作者作品列表
│   └── extractors/       # 8 个提取器
│       ├── bilibili_extractor.py
│       ├── youtube_extractor.py
│       ├── douyin_extractor.py
│       ├── xiaohongshu_extractor.py
│       ├── ytdlp_extractor.py
│       ├── ytdlp_asr_extractor.py   # yt-dlp + 阿里云 ASR
│       ├── tikhub_extractor.py      # 商业API
│       └── apify_extractor.py       # 商业爬虫
├── api/                  # API 服务（FastAPI）
├── cli.py                # CLI 入口（v2 单一路径；本地文件只转写）
├── mcp/                  # MCP：server.py=入口，modern_server.py=3 工具薄适配器
├── config/               # 配置常量
├── exporters/            # 导出器
├── models/               # 数据模型
├── services/             # 配置管理 / 本地路径白名单 / 导出编排
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
