# VideoMind Bridge 架构文档

> 2026-11-25（A2）重写：v1 流水线（下载 → 转录 → AI 摘要 → 任务队列）已删除，
> 本文只描述现存结构。历史结构见 `docs/AUDIT-2026-11-24.md` 第八章。

## 1. 分层与职责

```
L3  接口层   REST /api/v1/*(:8787) · MCP（stdio，薄适配器）· 控制台 /console
                │  只做参数翻译、鉴权、错误翻译；不含业务逻辑
L1  编排层   src/core/router.py       成本感知路由 + 降级链 + 缓存
             src/core/extractors/     8 个平台提取器
             src/core/asr/            ASR 降级链（4 个后端适配器）
             src/core/archiver.py     提取即归档（复用导出器，纯文本）
             src/core/formatter.py    Hermes 输出格式
                │  消费
外部  平台  douyin-api(:8010) 平台网关（**待收编为 L0**，见分层文档 §2.4）
     模型/ASR  SenseVoice(本地) · DashScope · 阿里云 · faster-whisper
```

定位（与《项目分层与协作架构》一致）：**L1 采集编排 + L3 接口**。
承诺的是「采到内容，并能证明采到了什么/有多完整」；不判断内容价值——那是 L2 调用方的职责。

## 2. 目录

| 路径 | 内容 |
|---|---|
| `src/core/extractors/` | 8 个提取器（bilibili / youtube / xiaohongshu / douyin / ytdlp / ytdlp_asr / tikhub / apify），注册表模式自动注册 |
| `src/core/asr/` | ASR 统一层：`chain.py` 降级链、`registry.py` 后端注册、`adapters/` 4 个后端、`normalizer.py` 结果映射 |
| `src/core/media/` | yt-dlp 与 HTTP 媒体获取、ffmpeg 转码（`to_16k_mono_wav` / `transcode_to_mp3`） |
| `src/core/platforms/` | 平台登录态、限流器、熔断、共享 HTTP（`platform_get`） |
| `src/core/discovery/` | 评论采样、创作者作品列表（默认关闭，需显式开启） |
| `src/core/router.py` | 成本感知路由：按优先级尝试提取器，失败自动降级；只缓存 `completeness=full` |
| `src/core/prescreener.py` | 零网络预筛：内容分级 + **提取成本决策**（不做内容价值评估） |
| `src/core/archiver.py` | 提取即归档（Obsidian / 本地 / HTML 播放器），复用 `src/exporters/` |
| `src/api/` | FastAPI：`server.py`（路由）/ `auth.py`（token + 限流）/ `models.py`（响应模型） |
| `src/mcp/` | `server.py` = 入口（`-m src.mcp.server`）；`modern_server.py` = 3 个工具的薄适配器 |
| `src/services/` | `config_manager`（配置与密钥）、`local_media`（本地路径白名单）、`export_orchestrator`（并发导出） |
| `src/exporters/` | local / obsidian / webhook / html_player 四个导出器 |
| `src/models/` | `config.py`（配置 schema）、`task.py`（导出上下文与结果模型） |

## 3. 数据流

```
URL（或本地文件）
  │
  ├─► /api/v1/prescreen   零网络：内容分级 + 推荐成本档（不下载）
  │
  └─► /api/v1/extract     ContentRouter.extract(url, max_cost)
        │
        ├─ 逐提取器尝试（按成本档排序，失败降级，记 attempts 明细）
        │     · 有字幕 → 直接取字幕/正文
        │     · 无字幕 → 下载音频 → ASR 链（SenseVoice → DashScope → 阿里云 → faster-whisper）
        │
        └─► ExtractResult（success ⊥ completeness，见 docs/CONTRACT.md）
              ├─► formatter：Hermes 输出
              └─► archiver：纯文本归档到 Obsidian / 本地 / HTML
```

## 4. 契约与消费者

- 对外字段与不变式：`docs/CONTRACT.md`（唯一权威，含变更记录）。
- 谁在调用：`docs/CONSUMERS.md`。改字段前必须核对，找不到影响面说明有未登记消费者。
- 双轴：`success`（拿没拿到）与 `completeness`（有多完整，`full/meta/none/unknown`）正交。
  「只有标题/文案」必须是 `success=true` + `completeness=meta`，不能是失败。

## 5. 扩展点

### 加一个提取器

1. 继承 `ContentExtractor`（`src/core/extractors/base.py`）；
2. 调 `register_extractor()` 注册；
3. 在 `src/core/extractors/__init__.py` 里 import 触发注册；
4. 需要调优先级就改 `src/core/router.py` 的 `_DEFAULT_PRIORITY`；
5. `capabilities()` 会自动反映（`is_available()` 决定 `available`）。

### 加一个 ASR 后端

1. 在 `src/core/asr/adapters/` 实现 `Transcriber`（`capabilities()` + `transcribe()`）；
2. `register_transcriber()` 注册；
3. 默认链顺序在 `src/models/config.py` 的 `DEFAULT_ASR_CHAIN`（单一常量）。

### 加一个导出目标

1. 继承 `BaseExporter`，实现 `validate_config()` / `export()`；
2. 在 `ExportTarget` 枚举加值；
3. 在 `ExportOrchestrator` 注册。

## 6. 治理与可观测

- **缓存**：进程内短时缓存，只缓存 `completeness=full`；key 区分成本档与 ASR 选项。
- **限流与熔断**：平台自有请求走 `PlatformRateLimiter`；熔断时跳过 yt-dlp 兜底。
- **指标**：`GET /api/v1/metrics` 按平台/提取器/消费者计数，是「按实际使用收敛接口」的唯一依据。
- **鉴权**：默认回环免鉴权；设 `VIDEOMIND_API_TOKEN` 后需 Bearer；可配多消费者与限流。
- **日志**：`VMB_LOG_JSON=1` 输出结构化日志。
