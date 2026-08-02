# VideoMind Bridge — Agent Guide

## Project Overview

智能视频处理工具，支持下载、转录、AI 摘要和导出。  
Python 3.11+ monorepo。uv 驱动。

## Quick Start

```bash
uv sync --extra dev             # 安装依赖（含 dev: ruff/mypy/pytest）
uv run python -m src.cli <url>  # CLI 模式
python main.py                  # GUI 模式
python main.py --api            # API 服务 (端口 8787)
python main.py --mcp            # MCP Server (stdio JSON-RPC)
pytest tests/ -v                # 运行测试
ruff check src/                 # 代码风格检查
mypy src/ --ignore-missing-imports  # 类型检查
```

## Architecture (Dual System)

**v1 (Legacy):** Download → Transcribe (Whisper) → AI Summary → Export  
**v2 (New Engine):** Extract ×10 → Cost-aware Route → Prescreen → Hermes Output

| Layer | Path | Technology |
|-------|------|-----------|
| Entrypoint | `main.py` | argparse → GUI / API (FastAPI) / MCP |
| CLI | `src/cli.py` | rich, argparse (v1+v2 dual mode) |
| v2 Engine | `src/core/` | 10 extractors + router + prescreener + archiver + Hermes formatter |
| v1 Services | `src/services/` | download, transcribe (faster-whisper), AI, export |
| API | `src/api/` | FastAPI + WebSocket |
| MCP | `src/mcp/server.py` | stdio JSON-RPC (Model Context Protocol) |
| GUI | `src/gui/` | PySide6 |

## v2 Engine (`src/core/`)

### Extractors (`src/core/extractors/`)

10 个提取器通过注册表模式自动注册 (`register_extractor()`)，在 `__init__.py` 中延迟导入触发。

默认优先级 (成本排序):
```
bilibili → youtube → douyin → xiaohongshu → ytdlp → ytdlp_asr → tikhub → apify
FREE       FREE       FREE      FREE           FREE    CHEAP      PREMIUM   PREMIUM
```

抖音在本地/云 IP 常被验证码风控，可通过 `DOUYIN_COOKIES_FILE` 指定 cookies.txt (Netscape 格式) 绕过。

提取器接口: `extract()`, `is_available()`, `supports()`, `should_try()`

### DashScope ASR (`_dashscope_asr.py` + `dashscope_key`)

无字幕视频兜底转写:
- `ytdlp_asr` 提取器: yt-dlp 下载音频 → DashScope paraformer-v2 转写
- 配置 `dashscope_key` (env: `ALI_API_KEY`) 即可启用，无需 Coze

所有 Key 通过 `ConfigManager` 统一管理: 系统密钥环(持久化) → 环境变量(兜底)。

### Router (`router.py`)

`ContentRouter.extract(url, max_cost=None)` — 遍历优先级列表，失败自动降级。  
成本等级: FREE < CHEAP < PAID < EXPENSIVE < PREMIUM

### Prescreener (`prescreener.py` + `prescreen_rules.py`)

两套分级语义:
1. **内容基本面** (`grade`/`score`): SEO/时长/营销规则，评分基准 50/100，等级阈值 S≥85/A≥70/B≥55/C≥40/D<40
2. **提取成本决策** (`cost_grade`/`recommended_cost_tier`/`skip_reason`): 回答"提取这个链接要花多少钱"——平台可达性/字幕可得性/时长期望。`recommended_cost_tier` 直接供 router 消费

两条重点:
1. `prescreen()` 方法**不发起网络请求** — 需要外部传入 title + duration
2. `is_extraction_worthwhile(grade, min_grade=ContentGrade.C)` — 默认 C 级以上值得提取；MCP/CLI 基于 `effective_cost_grade()` 判断
3. `effective_cost_grade()` — 返回成本分级（未设置时回退基本面分级）；`cost_grade` 的 S/A/B → 免费/便宜提取，C/D → 需付费或建议跳过（含 `skip_reason`）
4. **职责边界**: VMB 不实现内容价值评估（那是 content-value-evaluator 的职责），只做提取成本决策

### CLI v2 模式 (`src/cli.py` v2 section)

```
--prescreen       # 提取一次 → 评分 → 复用结果（单次提取，不重复）
--smart           # FREE 提取取元信息 → 预筛 → 低于 C 级跳过
--prescreen-only  # 仅 URL 分析，无网络，默认 B 级
--cost-tier       # 限制最大提取成本
--list-extractors # 列出可用提取器
--archive         # 提取即归档 (obsidian,local,html_player 逗号分隔)
```

### Archiver (`archiver.py`)

提取即归档: 把 `ExtractResult` 直接写入 Obsidian/本地/HTML, 无需 v1 下载/转录。
- `archive_extract_result(result, targets, config)` — 复用 v1 导出器做纯文本归档
- `build_export_context(result)` — ExtractResult → ExportContext (无媒体文件, 导出器自动降级为纯文本笔记)
- CLI: `--archive obsidian,local --obsidian-vault <path>`; MCP: `archive_extract` 工具
- 无真实内容 (占位/失败) 时拒绝归档

### Hermes Formatter (`formatter.py`)

输出结构: `{success, platform, title, content, source, url, cost_tier, duration_seconds, ...}`  
`format_extract_result_full()` 加 `source_type`, `extracted_at`, `version` 字段。

## Known Quirks & Gotchas

- **sys.path 动态注入**: `main.py` 会将 `src/` 插入 sys.path。`cli.py` 使用 `from src.*` 导入，需以 `python -m src.cli`（项目根）方式运行
- **Bilibili API**: URL 必须全小写 `/x/web-interface/view`，大写 `I` 会 404
- **Extractor 注册**: 通过 import 时跑的模块级代码自动注册，无需手动配置
- **占位结果语义**: `ExtractResult.is_placeholder=True` 表示仅元信息/说明文本（无真实内容）。router 对占位结果不缓存、继续降级链；真正成功才缓存并返回
- **`--smart`/MCP smart_extract**: FREE 提取到完整内容时直接复用（不二次提取）；仅当 FREE 失败/占位时才按推荐成本升级提取
- **`--prescreen` 复用提取**: 仅真成功（有内容、非占位）结果被复用；失败/占位时允许二次高成本提取
- **API 鉴权**: 默认绑定 127.0.0.1。设置环境变量 `VIDEOMIND_API_TOKEN` 后，`/api/v1/*` 需携带 `Authorization: Bearer <token>`；带非白名单 Origin 的浏览器请求被 403 拒绝（防 CSRF）
- **GUI 使用 PySide6**: 依赖较重，macOS 需提前安装 Qt 运行时
- **Build 工具**: PyInstaller (`videomind.spec`，已被 gitignore)
- **配置存储**: `~/.config/VideoMind/config.yaml` (首次启动自动生成)
- **v2 引擎完全独立**: 不依赖 `src/services/` 中的任何模块，可单独导入 `from src.core import ContentRouter`

## Testing

```bash
pytest tests/ -v                                # 全部测试
pytest tests/test_models.py -v                  # 单文件
pytest tests/ -k "test_prescreen" -v            # 关键词筛选
pytest tests/ --cov=src --cov-report=term       # 覆盖率
```

覆盖配置: `tests/` 下 `test_*.py` 匹配。pytest-asyncio 已启用 (`asyncio_mode = auto`)。

## CI Pipeline (`.github/workflows/ci.yml`)

1. Lint (`ruff check .`)
2. Test (pytest + coverage, `--cov-fail-under=40`)
3. Type check (`mypy src/` — 全量 0 错误，失败即 CI 失败)
4. Build (`python -m build`)

## Build & Release

```
uv sync --extra dev             # 开发安装（含 dev 依赖）
pip install -e ".[dev]"         # 含 dev 依赖
pyinstaller videomind.spec      # macOS 应用打包
```

Release workflow 自动构建 macOS DMG + Windows ZIP，标签推送 `v*` 触发。

## 非标准文件

| 文件 | 说明 |
|------|------|
| `main.py` | 入口：GUI/API/MCP 三模式 |
| `build_macos_app.sh` | macOS 构建脚本 |
| `create_dmg.sh` | DMG 包创建 |
| `.python-version` | Python 3.11 (仅供 pyenv) |
| `skill/` | OpenClaw 集成 skill 定义 |
| `.sisyphus/` | 历史开发计划 (仅保留供参考) |
| `docs/` | API 使用 / 架构 / macOS 构建文档 |

## 常见陷阱

- 不要在 `prescreener.prescreen()` 内部调用提取器 — 该方法承诺纯规则
- 修改提取器优先级列表时，同步更新 `src/core/router.py` 的 `_DEFAULT_PRIORITY`
- 添加新提取器时: 继承 `ContentExtractor` → 调用 `register_extractor()` → 在 `__init__.py` 中 import
- MCP 通过 stdio 通信，不支持 HTTP — 仅适用 MCP 兼容的 AI Agent
- **钥匙串弹窗**: macOS keyring 弹窗「python 想要使用钥匙串中的机密信息」是因为 ConfigManager 访问了系统钥匙串。解决：(1) 设置环境变量（优先级高于钥匙串），无需钥匙串；或 (2) 在 `~/.zshrc` 添加 `export ALI_API_KEY=xxx` 等；测试已通过 `tests/conftest.py` 全局 mock keyring 避免弹窗
