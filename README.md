# VideoMind Bridge

智能视频内容处理引擎 — v2 多引擎提取 + 内容预筛 + 结构化输出。
支持零Cookie提取 B站/YouTube/抖音/小红书等平台内容。

## 功能特性

### v2 Engine (推荐)
- **多引擎提取**：9 个提取器自动降级（B站/YouTube/抖音/小红书/Coze/yt-dlp/tikhub/Apify/阿里云ASR）
- **零Cookie提取**：B站 WBI 签名、抖音 iesdouyin、小红书页面解析，无需浏览器 Cookie
- **内容预筛**: 纯规则引擎评估内容价值，S/A/B/C/D 分级，提取前知道值不值得
- **成本感知路由**: 免费 > 付费自动选择，失败自动降级下一级
- **结构化输出**: Hermes 兼容 JSON 格式
- **MCP Server**: AI Agent 直接调用（prescreen_video / smart_extract / extract_video）

### v1 (Legacy)
- **视频下载**：支持 Bilibili、YouTube、抖音、小红书等平台
- **语音转录**：自动生成字幕和时间轴
- **AI 摘要**：使用 DeepSeek 等国内模型生成智能摘要
- **多格式导出**：支持 Obsidian、本地文件夹、HTML 播放器
- **任务管理**：队列管理、暂停、恢复、历史记录
- **系统托盘**：最小化到托盘，任务完成通知
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

### v2 Engine (CLI)

```bash
# 直接提取内容（自动选择最佳提取器）
uv run python -m src.cli "URL" --json

# 智能模式：预筛 + 自动提取
uv run python -m src.cli "URL" --smart --json

# 仅预筛（快速评估）
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
| `prescreen_video` | 预筛内容质量（纯规则，零网络） |
| `smart_extract` | 智能提取：预筛 → 评分 → 自动提取 |
| `extract_video` | 直接提取内容 |
| `list_extractors` | 列出所有提取器及状态 |
| `configure` | 获取/设置配置 |

### v1 (Legacy)

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
│   ├── prescreener.py    # 内容预筛引擎
│   ├── prescreen_rules.py# 预筛规则集
│   ├── router.py         # 成本感知路由
│   ├── formatter.py      # Hermes 输出格式化
│   ├── models.py         # 数据模型
│   └── extractors/       # 9 个提取器
│       ├── bilibili_extractor.py
│       ├── youtube_extractor.py
│       ├── douyin_extractor.py
│       ├── xiaohongshu_extractor.py
│       ├── coze_extractor.py
│       ├── ytdlp_extractor.py
│       ├── tikhub_extractor.py      # ★ 商业API
│       ├── apify_extractor.py       # ★ 商业爬虫
│       └── aliyun_asr_extractor.py  # ★ 阿里云ASR
├── api/                  # API 服务（FastAPI + WebSocket）
├── cli.py                # CLI 入口（v1+v2 双模式）
├── mcp/                  # MCP Server（stdio JSON-RPC, 9 工具）
├── config/               # 配置常量
├── gui/                  # GUI 界面（PySide6, 降级）
├── exporters/            # 导出器
├── models/               # 数据模型
├── services/             # v1 核心服务
├── utils/                # 工具函数
│   └── platform_detector.py  # ★ 统一平台检测（13 平台）
├── ... (GUI, services, exporters, etc.)
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

### v2.0.0（2026-05-24）

- **v2 核心引擎**：9 个提取器 + 内容预筛 + 成本感知路由
- **零Cookie提取**：B站/YouTube/抖音/小红书 无需浏览器 Cookie
- **内容预筛引擎**：纯规则评分（S/A/B/C/D），提取前知价值
- **MCP 升级**：prescreen_video + smart_extract + configure 工具
- **商业 API 适配器**：tikhub.io / Apify / 阿里云 ASR
- **CLI v2 模式**：--smart / --prescreen / --prescreen-only / --cost-tier
- **Hermes 兼容**：统一结构输出，AI Agent 原生可消费
- **代码重构**：统一平台检测、移除 sys.path hack、配置常量解耦

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
