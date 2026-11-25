# VideoMind Bridge — Agent Guide

## Project Overview

多平台内容采集引擎：给一条链接，返回它的文字内容（无字幕由 ASR 兜底）。  
Python 3.11+ monorepo。uv 驱动。

## Quick Start

```bash
uv sync --extra dev             # 服务端/CLI/MCP 依赖（含 dev: ruff/mypy/pytest）
uv run python -m src.cli <url>  # CLI 模式
uv run python -m src.cli /path/to/video.mp4 --json  # 本地文件：只转写（无下载/摘要）
python main.py --api            # API 服务 (端口 8787; 控制台 /console)；GUI 已下线
python main.py --mcp            # MCP Server (stdio JSON-RPC)
./scripts/install_sensevoice.sh --check  # SenseVoice（默认 ASR 第一级）体检；去掉 --check 即安装
pm2 start ecosystem.config.cjs  # 本机 PM2 常驻 API 服务
pytest tests/ -v                # 运行测试
ruff check src/                 # 代码风格检查
mypy src/ --ignore-missing-imports  # 类型检查
```

## Architecture (Dual System)

**v1 已删除（2026-11-25 A2）:** 原 Download → Transcribe → AI Summary → Export 流水线；现在只有 v2 引擎 + 本地文件转写。
**v2 (Only Engine):** Prescreen → Cost-aware Route → Extract ×8 → ASR 兜底 → Hermes Output / 归档

| Layer | Path | Technology |
|-------|------|-----------|
| Entrypoint | `main.py` | argparse → API (FastAPI) / MCP |
| CLI | `src/cli.py` | rich, argparse（v2 单一路径；本地文件只转写） |
| v2 Engine | `src/core/` | 8 extractors + ASR 链 + router + prescreener + archiver + Hermes formatter |
| Services | `src/services/` | config_manager（配置/密钥）、local_media（本地路径白名单）、export_orchestrator（并发导出） |
| API | `src/api/` | FastAPI（无 WebSocket，A2 已删） |
| MCP | `src/mcp/server.py` | stdio 入口 → `modern_server.py`（3 工具薄适配器，转 HTTP） |

## v2 Engine (`src/core/`)

### Extractors (`src/core/extractors/`)

8 个提取器通过注册表模式自动注册 (`register_extractor()`)，在 `__init__.py` 中延迟导入触发。

默认优先级 (成本排序):
```
bilibili → youtube → douyin → xiaohongshu → ytdlp → ytdlp_asr → tikhub → apify
FREE       FREE       FREE      FREE           FREE    CHEAP      PREMIUM   PREMIUM
```

抖音在本地/云 IP 常被验证码风控，可通过 `DOUYIN_COOKIES_FILE` 指定 cookies.txt (Netscape 格式) 绕过。

抖音链**唯一跨仓硬依赖**是 L0 网关 `douyin-api(:8010)`（注册表 `layer: L0`）。它有自己的对外契约
（`~/Projects/ai-agents/douyin-api/docs/CONTRACT.md`，V4.1.2，承诺 `GET /api/douyin/web/fetch_one_video?aweme_id=`），
消费方自检：`python scripts/check_douyin_gateway_contract.py`（读上游 `/openapi.json`）。网关没起时提取报
`douyin_gateway_unavailable`。

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
- CLI: `--archive obsidian,local --obsidian-vault <path>`; API: `POST /api/v1/extract/archive`（MCP 不暴露归档工具）
- 无真实内容 (占位/失败) 时拒绝归档

### Hermes Formatter (`formatter.py`)

输出结构: `{success, platform, title, content, source, url, cost_tier, duration_seconds, ...}`  
`format_extract_result_full()` 加 `source_type`, `extracted_at`, `version` 字段。

## Known Quirks & Gotchas

- **sys.path 动态注入**: `main.py` 会将 `src/` 插入 sys.path。`cli.py` 使用 `from src.*` 导入，需以 `python -m src.cli`（项目根）方式运行
- **Bilibili API**: URL 必须全小写 `/x/web-interface/view`，大写 `I` 会 404
- **Extractor 注册**: 通过 import 时跑的模块级代码自动注册，无需手动配置
- **占位结果语义**: `ExtractResult.is_placeholder=True` 表示仅元信息/说明文本（无真实内容）。router 对占位结果不缓存、继续降级链；真正成功才缓存并返回
- **`--smart`**: FREE 提取到完整内容时直接复用（不二次提取）；仅当 FREE 失败/占位时才按推荐成本升级提取（MCP 侧的 smart_extract 已于 2026-11-25 删除，预筛用 `extract mode=prescreen`）
- **`--prescreen` 复用提取**: 仅真成功（有内容、非占位）结果被复用；失败/占位时允许二次高成本提取
- **API 鉴权**: 默认绑定 127.0.0.1。设置 `VIDEOMIND_API_TOKEN`（admin）或 `VMB_CONSUMER_TOKENS`（JSON 多消费者）后，`/api/v1/*` 需携带 `Authorization: Bearer <token>`；`VMB_RATE_LIMIT_PER_MIN` 可开启每消费者每分钟限流（0=关闭）。**token 规范名只有 `VIDEOMIND_API_TOKEN`**；`VMB_API_TOKEN` 是历史错名（服务端从不读），回归脚本仅为兼容保留回退并打印弃用提示。带非白名单 Origin 的浏览器请求被 403 拒绝（防 CSRF）。**Origin 校验为精确主机名匹配**（urlsplit 后 host ∈ {127.0.0.1, localhost, ::1}，扩展按 scheme 放行）——不要改回前缀匹配，`http://127.0.0.1.evil.com` 类仿冒源曾可绕过。多消费者模式下 settings/keys/sessions 写端点仅 admin 可用（consumer 返回 403）
- **Discovery API**: `VMB_ENABLE_CREATOR_FEED=1` 开启 `/api/v1/creator/feed`，`VMB_ENABLE_COMMENTS=1` 开启 `/api/v1/comments`（默认都不注册路由）；MCP 侧只有 `comments` 工具（创作者列表走 REST）。B站空间接口对无登录态请求常返回 HTTP 412 / `code=-352`，可用 `VMB_BILIBILI_COOKIES_FILE`（Netscape cookies.txt）或 `VMB_BILIBILI_SESSDATA` / `VMB_BILIBILI_COOKIE` 提供登录态；评论接口实测可无登录采样。cookie 可能绑定出口 IP/指纹，换机器仍可能 `risk_control`；VMB 不绕过验证码。回归脚本：`scripts/check_discovery_links.py`
- **本地文件只剩转写（2026-11-25 A2）**: `uv run python -m src.cli <本地文件>` 会 ffmpeg 转 16k 单声道 wav 后走 ASR 降级链，**没有下载、没有 AI 摘要**。API `POST /api/v1/parse` 仍接受本地路径（受 `VMB_LOCAL_MEDIA_DIRS` 白名单约束）；`/api/v1/extract` 只接受 URL。
- **登录态统一管理**: 所有平台登录态经 `SessionManager.resolve(platform)` 统一解析，优先级：**平台专用 env → 密钥环 session 设置 → 通用 env（`VMB_COOKIES_FILE` / `VMB_COOKIES_BROWSER`）**。密钥环键见 `ConfigManager.SESSION_KEYS`（如 `bilibili:cookies_file`、`ytdlp:browser`），管理入口：API `PUT/DELETE /api/v1/sessions/settings/{key}`（admin）——MCP 的 `configure` 工具已于 2026-11-25 删除。`/api/v1/parse` **不接受**请求体 cookies_file 路径（安全），登录态只来自服务端解析。新平台接入时在 `session.py` 加 Provider，勿在业务代码直读 cookie env
- **平台请求治理**: 平台自有 HTTP 请求走 `PlatformRateLimiter`（B站/抖音/小红书/YouTube），本地网关、第三方 API 和 CDN 下载不套平台 limiter；yt-dlp 通过 `VMB_YTDLP_SLEEP_REQUESTS`、`VMB_YTDLP_RETRIES` 等参数节流，平台熔断时跳过 yt-dlp 兜底。小红书可选 `VMB_XHS_COOKIE` / `VMB_XHS_COOKIES_FILE`；抖音用 `DOUYIN_COOKIES_FILE`。`GET /api/v1/metrics` 返回进程内平台计数，`VMB_LOG_JSON=1` 开启 JSON 日志。
- **GUI 与 v1 都没了（2026-11-24 / 11-25）**: `src/gui/`、`browser-extension/`、`/legacy`、`/ws`、`/api/v1/tasks*`、任务队列与 AI 摘要全部删除；`python main.py` / `python -m src.cli` 不带参数都是「打印用法 + 退出码 2」。`GET /api/v1/status` 的四个任务计数恒为 0（字段保留仅为不破坏调用方）。MCP 的 `VMB_MCP_LEGACY` / `VMB_MCP_EMBEDDED` 两个兜底开关也一并删除
- **SenseVoice 依赖仓库外资产**: 默认 ASR 第一级需要 `~/.cache/sensevoice/venv`（sherpa-onnx + soundfile）与 `~/.cache/sherpa-onnx/sense-voice/`（`model.int8.onnx` + `tokens.txt`）。2026-11-24 起 `capabilities()` 会真起子进程探测 `import sherpa_onnx, soundfile`（按解释器缓存，超时 10s），**文件齐但解释器缺依赖时 `available=false`**——别再把「文件存在」当成「能用」。安装/体检：`scripts/install_sensevoice.sh [--check]`
- **Build 工具**: 只剩 `python -m build`（sdist/wheel）。PyInstaller 打包随 GUI 一起在 2026-11-24 移除
- **配置存储**: `~/.config/VideoMind/config.yaml`（首次启动自动生成；**格式 v2**）
  - 只写四段：`version` / `archive.output_dir` / `asr` / `export.obsidian`
  - `ai` / `download` / `transcribe` / `ui` / `performance` 是 v1 遗留段：**仍能读**（`AppConfig.from_dict` 兼容，`DownloadConfig.output_dir` 会升级为 `archive.output_dir`），**不再写盘**
  - 含遗留段的旧文件在首次加载时自动迁移：先备份 `config.yaml.bak-<时间戳>`，再写 v2；`VMB_CONFIG_NO_MIGRATE=1` 只提示不改文件
  - `VMB_CONFIG_DIR=/some/dir` 可把配置目录整体挪走（测试隔离 / 多实例并存）；测试已用 autouse fixture 隔离，**跑 pytest 不会改真实配置**
- **v2 引擎可独立导入**: `from src.core import ContentRouter` 不依赖 GUI；ASR 适配器在需要时通过 `src/services/config_manager` 读取密钥

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
2. Test (pytest + coverage, `--cov-fail-under=75`；实际约 80.6%，门槛留 5 个点缓冲)
3. Type check (`mypy src/` — 全量 0 错误，失败即 CI 失败)
4. Build (`python -m build`)

## Build & Release

```
uv sync --extra dev             # 开发安装（服务端）
pip install -e ".[dev]"         # 含 dev 依赖
python -m build                 # 产出 sdist/wheel（CI 的 build job 也跑这条）
```

**桌面打包流水线已于 2026-11-24 删除**（GUI 下线）：`.github/workflows/build.yml`、`build_macos_app.sh`、`create_dmg.sh` 均已移除，标签推送 `v*` 不再触发任何打包。`docs/MACOS_BUILD.md` 仅作历史参考。

## 非标准文件

| 文件 | 说明 |
|------|------|
| `main.py` | 入口：API / MCP 两模式（GUI 已下线） |
| `.python-version` | Python 3.11 (仅供 pyenv) |
| `skill/` | OpenClaw 集成 skill 定义 |
| `.sisyphus/` | 历史开发计划 (仅保留供参考) |
| `docs/` | API 使用 / 架构 / 审计报告 / 契约 |
| `docs/issues/` | 跨项目问题记录（下游 502 映射等，供对方仓库引用） |

## 常见陷阱

- 不要在 `prescreener.prescreen()` 内部调用提取器 — 该方法承诺纯规则
- 修改提取器优先级列表时，同步更新 `src/core/router.py` 的 `_DEFAULT_PRIORITY`
- 添加新提取器时: 继承 `ContentExtractor` → 调用 `register_extractor()` → 在 `__init__.py` 中 import
- MCP 通过 stdio 通信，不支持 HTTP — 仅适用 MCP 兼容的 AI Agent
- **钥匙串弹窗**: macOS keyring 弹窗「python 想要使用钥匙串中的机密信息」是因为 ConfigManager 访问了系统钥匙串。解决：(1) 设置环境变量（优先级高于钥匙串），无需钥匙串；或 (2) 在 `~/.zshrc` 添加 `export ALI_API_KEY=xxx` 等；测试已通过 `tests/conftest.py` 全局 mock keyring 避免弹窗
