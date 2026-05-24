# VideoMind Bridge — Agent Guide

## Project Overview

智能视频处理工具，支持下载、转录、AI 摘要和导出。  
Python 3.11+ monorepo。uv 驱动。

## Quick Start

```bash
uv sync                         # 安装依赖
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
**v2 (New Engine):** Extract ×6 → Cost-aware Route → Prescreen → Hermes Output

| Layer | Path | Technology |
|-------|------|-----------|
| Entrypoint | `main.py` | argparse → GUI / API (FastAPI) / MCP |
| CLI | `src/cli.py` | rich, argparse (v1+v2 dual mode) |
| v2 Engine | `src/core/` | 6 extractors + router + prescreener + Hermes formatter |
| v1 Services | `src/services/` | download, transcribe (faster-whisper), AI, export |
| API | `src/api/` | FastAPI + WebSocket |
| MCP | `src/mcp/server.py` | stdio JSON-RPC (Model Context Protocol) |
| GUI | `src/gui/` | PySide6 |

## v2 Engine (`src/core/`)

### Extractors (`src/core/extractors/`)

6 个提取器通过注册表模式自动注册 (`register_extractor()`)，在 `__init__.py` 中延迟导入触发。

默认优先级 (成本排序):
```
bilibili → youtube → douyin → xiaohongshu → coze → ytdlp
FREE        FREE       FREE      FREE           CHEAP   FREE
```

提取器接口: `extract()`, `is_available()`, `supports()`, `should_try()`

### Router (`router.py`)

`ContentRouter.extract(url, max_cost=None)` — 遍历优先级列表，失败自动降级。  
成本等级: FREE < CHEAP < PAID < EXPENSIVE < PREMIUM

### Prescreener (`prescreener.py` + `prescreen_rules.py`)

纯规则引擎（零网络）。评分基准 50/100，范围 0-100。  
等级阈值: S≥85 / A≥70 / B≥55 / C≥40 / D<40

两条重点:
1. `prescreen()` 方法**不发起网络请求** — 需要外部传入 title + duration
2. `is_extraction_worthwhile(grade, min_grade=ContentGrade.C)` — 默认 C 级以上值得提取

### CLI v2 模式 (`src/cli.py` v2 section)

```
--prescreen       # 提取一次 → 评分 → 复用结果（单次提取，不重复）
--smart           # FREE 提取取元信息 → 预筛 → 低于 C 级跳过
--prescreen-only  # 仅 URL 分析，无网络，默认 B 级
--cost-tier       # 限制最大提取成本
--list-extractors # 列出可用提取器
```

### Hermes Formatter (`formatter.py`)

输出结构: `{success, platform, title, content, source, url, cost_tier, duration_seconds, ...}`  
`format_extract_result_full()` 加 `source_type`, `extracted_at`, `version` 字段。

## Known Quirks & Gotchas

- **sys.path 动态注入**: `main.py` 和 `cli.py` 都会将 `src/` 插入 sys.path。`cli.py` 用 try/except 做双模式导入兜底
- **两种 TranscriptSegment 类型**: `src.models.task.TranscriptSegment` vs `src.services.transcribe_service.TranscriptSegment` — 已有类型冲突（预存问题，不影响运行）
- **Bilibili API**: URL 必须全小写 `/x/web-interface/view`，大写 `I` 会 404
- **Extractor 注册**: 通过 import 时跑的模块级代码自动注册，无需手动配置
- **Coze 提取器**: 401 时不阻塞，自动跳到下一个提取器
- **`--prescreen` 复用提取**: 在 CLI 层面用 `prescreen_meta["extract_result"]` 缓存，不会被二次提取
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
3. Type check (`mypy src/` — 允许失败)
4. Build (`python -m build`)

## Build & Release

```
uv sync                         # 开发安装
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
- GUI 的 `main_window.py.bak` 文件需要手动删除（一次性遗留）
- MCP 通过 stdio 通信，不支持 HTTP — 仅适用 MCP 兼容的 AI Agent
