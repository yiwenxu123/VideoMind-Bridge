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
- **视频下载**：支持 Bilibili、YouTube、抖音、小红书等平台
- **语音转录**：自动生成字幕和时间轴
- **AI 摘要**：使用 DeepSeek 等国内模型生成智能摘要
- **多格式导出**：支持 Obsidian、本地文件夹、HTML 播放器
- **任务管理**：队列管理、暂停、恢复、历史记录
- **本地 API 服务**：提供 REST API 和 WebSocket
- **浏览器扩展**：支持 Chrome、Edge、Firefox

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
uv sync

# 或使用 pip
pip install -r requirements.txt
```

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

#### GUI 模式

```bash
python main.py
# 或
.venv/bin/python3 -m src.gui.app
```

#### API 服务模式

```bash
python main.py --api
# 或指定端口
python main.py --api --port 9000
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

## 浏览器扩展

### 安装方式

**Chrome / Edge（Chromium 内核）**：

1. 打开浏览器，地址栏输入 `chrome://extensions/` 或 `edge://extensions/`
2. 开启右上角的「开发者模式」
3. 点击「加载已解压的扩展程序」
4. 选择 `browser-extension` 文件夹

**Firefox**：

1. 打开浏览器，地址栏输入 `about:debugging`
2. 点击「此 Firefox」
3. 点击「临时载入附加组件」
4. 选择 `browser-extension/manifest.json`

### 使用方法

1. 安装扩展后，访问任意支持的视频页面
2. 点击浏览器工具栏中的扩展图标
3. 选择处理模式（完整模式、仅下载、仅转录）
4. 点击「开始处理」提交任务
5. 实时查看处理进度和结果

### 功能特性

- 视频页面自动检测
- 一键提交处理任务
- 三种处理模式可选
- WebSocket 实时进度更新
- 与 GUI 共享任务历史

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
├── gui/                  # GUI（PySide6, v1 扩展, 降级）
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
