# Router 生命周期与平台会话加固方案

> 状态：阶段 1–5 已实施（2026-10-21）；阶段 5 的正式灰度未单独执行。
> 范围：第 1 项（Router 生命周期 + `/extract` 成本透传）与第 2 项（统一会话健康 + 平台级限流/退避）
> 目标：减少重复初始化与连接泄漏，让成本兜底真正可达，并降低 412/-352/429 的触发率。

---

## 1. 现状与问题

### 1.1 Router 每次请求重建

- `src/api/server.py:443`：`/extract` 每次 `ContentRouter()`。
- `src/api/server.py:478`：`/extract/archive` 每次 `ContentRouter()`。
- `src/mcp/server.py`：`_call_extract_video` / `_call_archive_extract` 也是每次新建。
- 结果：
  - 提取器实例、`httpx.Client`、WBI key、缓存全部重建；
  - `RouterConfig.cache` 是实例级 dict，跨请求基本失效；
  - 没有统一的 `close()` 生命周期，长期运行可能积累连接；
  - `capabilities` 也每次 `ContentRouter().list_extractors()`，会实例化全部提取器。

### 1.2 成本上限被写死

- `src/api/server.py:444`：`router.extract(url, max_cost=CostTier.CHEAP, ...)`。
- `/extract/archive` 同样写死 CHEAP。
- 结果：`tikhub` / `apify` 等 PREMIUM 兜底通过 HTTP API **永远不可达**，与 `capabilities` 宣称的能力不一致；MCP 的 `extract_video` 反而支持 `cost_tier`。

### 1.3 Router 缓存语义不安全

`ContentRouter` 的缓存目前以 URL 为 key，且只要 `success + content + 非占位` 就缓存：

- 不同 `asr_chain` / `asr_language` / `asr_max_cost` 的请求会命中同一份结果；
- 如果共享 Router，低质量结果可能挡住更高成本的补救路径；
- 缓存没有 TTL/容量上限。

### 1.4 会话与平台限流分散

- B站：`VMB_BILIBILI_COOKIES_FILE` / `VMB_BILIBILI_SESSDATA` / `VMB_BILIBILI_COOKIE`；
- 抖音：`DOUYIN_COOKIES_FILE`；
- yt-dlp：`VMB_COOKIES_FILE` / `VMB_COOKIES_BROWSER`；
- 没有统一的“是否配置、是否过期、来源是什么”的状态；
- 视频提取链路没有平台级最小间隔/退避；`PlatformThrottle` 只存在于 discovery，且 service 与 provider 会重复等待；
- 412/-352/429 没有统一的“是否重试”策略。

### 1.5 社区对照

- yt-dlp：extractor/plugin + lazy extractors、`--cookies-from-browser`、`--cache-dir`、`--download-archive`、`--sleep-requests`、`--retries`。
- gallery-dl：`cookies`/`cookies-update`、SQLite `archive`、`sleep-request`、`retries`、cache。
- Instaloader：跟踪 rate limit、遇到 429 按临时封禁时间重试、复用 session 文件。
- Google AIP-158：`page_size` 上限 + `next_page_token`，不允许无界分页。
- `bilibili-api` 2026-07 因 B站律师函永久关停：平台非公开接口适配存在现实法律风险，VMB 不应对外提供爬虫 SDK，也不应绕过风控。

---

## 2. 第 1 项：Router 生命周期 + 成本透传

### 2.1 目标

1. 每个进程只保留少量长生命周期 Router / 提取器 / HTTP 连接。
2. 缓存 key 能区分提取选项，且只缓存完整成功结果。
3. `/extract` 与 `/extract/archive` 支持请求级成本上限，默认 `cheap` 保持兼容。
4. API/MCP 使用同一套 Runtime，关闭时释放客户端。

### 2.2 新增 `RouterRuntime`

建议文件：`src/core/router_runtime.py`

```python
class RouterRuntime:
    def __init__(self, router: ContentRouter | None = None):
        self._router = router or ContentRouter()
        self._cache = TTLCache(max_entries=256)
        self._lock = threading.RLock()

    def extract(
        self,
        url: str,
        *,
        max_cost: CostTier | None,
        options: ExtractOptions | None,
    ) -> ExtractResult: ...

    def extractor_status(self) -> dict[str, bool]: ...

    def close(self) -> None: ...
```

- `RouterRuntime` 负责缓存、锁、request_id 传递和 close。
- 默认单实例；如果后续并发升高，可在 Runtime 内切换为小 Router 池（2–4 个），接口不变。
- `ContentRouter` 保留为纯路由/降级逻辑，不持有跨请求缓存（或只保留测试用 cache）。

### 2.3 生命周期接线

- `APIServer`：
  - 在 `APIServer.__init__` 或 `_create_app` 创建 `self._router_runtime`；
  - `/extract`、`/extract/archive` 使用 `self._router_runtime.extract(...)`；
  - `lifespan` 的 `finally` 中 `await self.task_manager.stop()` 后调用 `router_runtime.close()`。
- `MCPServer`：
  - 通过 `self._get_service("router_runtime", RouterRuntime)` 复用；
  - 在 MCP `main` 的 `finally` 中关闭；
  - `_call_extract_video` / `_call_archive_extract` / `_call_smart_extract` 改用 Runtime。
- 测试：
  - 用计数 fake extractor 验证两次请求只初始化一次；
  - 触发 app shutdown 后 `close()` 被调用；
  - 不关闭的 Runtime 会在测试中显式 close，避免连接泄漏。

### 2.4 缓存设计

- 使用通用 `TTLCache`（建议从 `src/core/discovery/cache.py` 抽到 `src/core/cache.py`，discovery 复用）。
- Key：
  - canonical URL（去 fragment；保留必要 query，如 B站 p 参数）；
  - `max_cost`；
  - `asr_chain`、`asr_language`、`asr_max_cost`；
  - 其他会影响提取结果的请求级选项（未来新增字段需加入 key）。
- Value：`ExtractResult`。
- TTL：默认 600 秒；容量 256；可配 `VMB_EXTRACT_CACHE_TTL`、`VMB_EXTRACT_CACHE_MAX_ENTRIES`。
- 只缓存：`success=True` 且 `completeness="full"` 且非 placeholder。
- 不缓存：失败、meta、partial、risk_control、auth_required。
- 线程安全：TTLCache 内置锁；`RouterRuntime.extract` 在 cache miss 时不持有全局锁，避免串行化所有提取。
- 可选：对 `max_cost` 更高的请求，可以复用更低成本但 `completeness="full"` 的结果（成本不高于上限即可）；meta 不复用。

### 2.5 成本透传

请求字段（`/extract` 与 `/extract/archive`）：

```json
{
  "url": "https://www.bilibili.com/video/BV...",
  "cost_tier": "cheap",
  "asr": "sensevoice",
  "asr_max_cost": "premium"
}
```

- `cost_tier`：free / cheap / paid / expensive / premium，默认 `cheap`。
- 语义：**Router 可接受的最高提取器成本**；与 `asr_max_cost`（ASR 后端成本）分开。
- 非法值 → HTTP 400；未知字段保持忽略（兼容现有调用方）。
- `/extract/archive` 同步支持。
- MCP `extract_video` 已有 `cost_tier`，改用 Runtime 后行为一致。
- 消费端（内容运营 agent）可在 `VideoMindClient.extract` 增加可选 `costTier`，默认 cheap；这是后续小改动。

### 2.6 Extractor close

- `ContentExtractor` 基类新增 `close() -> None`（默认 no-op）。
- 覆写持有 HTTP client 的提取器：
  - Bilibili：`BilibiliClient.close()`；
  - Douyin / XHS / YouTube / Tikhub / Apify：关闭 `self._client`；
  - yt-dlp 类：释放临时资源（若有）。
- `ContentRouter.close()` 遍历已实例化的提取器并调用 close。
- `RouterRuntime.close()` 调用 router.close，并清空缓存。

### 2.7 能力探测

- `capabilities_payload` 改用 `RouterRuntime.extractor_status()`，结果缓存 60 秒；
- 首次调用仍会实例化提取器，但只发生一次；不再每次请求全量实例化。
- 若担心启动开销，可后续改为“类级静态可用性 + 懒加载”，本方案不强制。

### 2.8 验收

- [x] `/extract` 默认 `cost_tier=cheap`，行为与当前一致。
- [x] `cost_tier=premium` 能命中 fake premium extractor；cheap 时跳过（API 透传 + Router 成本过滤测试）。
- [x] 同一 Runtime 命中缓存时不再进入 Router/提取器。
- [x] 不同 ASR 选项不会命中同一缓存；meta/失败不缓存。
- [x] app shutdown / MCP shutdown 调用 close；测试无未关闭 client 警告。
- [x] 全量 pytest、ruff、mypy 通过。

---

## 3. 第 2 项：统一会话健康 + 平台限流/退避

### 3.1 目标

1. 每个平台有统一的会话来源、配置状态、过期时间和错误码。
2. 所有平台 HTTP 请求经过同一套“最小间隔 + 并发上限 + 退避 + 熔断”。
3. 412/-352 不重试、不绕过；429 按 `Retry-After`/退避；401 返回 auth_required。
4. 不改变 `/extract` 的 HTTP 200 + error_code 契约。

### 3.2 SessionManager

建议文件：`src/core/platforms/session.py`

```python
@dataclass(frozen=True)
class SessionStatus:
    platform: str
    configured: bool
    source: str            # env | file | browser | config | none
    cookie_count: int
    expires_at: str | None
    valid: bool | None     # None=unknown；不做网络探测
    last_checked: str | None
    error_code: str | None

class SessionProvider(Protocol):
    platform: str
    def headers(self) -> dict[str, str]: ...
    def status(self) -> SessionStatus: ...
    def check(self) -> SessionStatus: ...   # 可选，显式调用才发网络
```

- `BilibiliSessionProvider`：
  - 来源优先级：显式请求覆盖（若未来支持）> `VMB_BILIBILI_COOKIE` > `VMB_BILIBILI_SESSDATA` > `VMB_BILIBILI_COOKIES_FILE` > `VMB_COOKIES_FILE` > none。
  - 解析 Netscape，按 `bilibili.com` 域过滤，计算最近过期时间。
  - `check()` 调用 `/x/web-interface/nav`，`isLogin` 判断；-101/-401 → expired，-352 → risk_control；超时 → unknown。
- `DouyinSessionProvider`：
  - `DOUYIN_COOKIES_FILE`；按 `douyin.com` 域过滤，`DouyinExtractor` 直接复用该 Cookie header。
  - 默认只做 `status()`，`check()` 不发起网络探测。
- `XiaohongshuSessionProvider`：
  - `VMB_XHS_COOKIE` > `VMB_XHS_COOKIES_FILE` > `VMB_COOKIES_FILE`；按 `xiaohongshu.com` 域过滤。
  - 不配置时保持零 Cookie；`check()` 不发起网络探测。
- `YtDlpSessionProvider`：
  - `VMB_COOKIES_FILE` / `VMB_COOKIES_BROWSER`；`cookie_args()` 是 yt-dlp `--cookies` / `--cookies-from-browser` 的唯一来源。
- `NoneSessionProvider`：
  - `youtube` 等当前无需登录态的提取器返回 `configured=False, source="none"`。YouTube 的登录态由 yt-dlp 自行管理，不新增直连 Cookie provider。

**安全约束**
- API/日志永不返回 cookie 值；只返回来源、数量、过期时间、状态。
- 路径只显示 basename 或 `<configured>`，不返回完整本地路径。
- 文件权限非 600 时在状态中给 warning（不修改权限）。
- 不自动刷新 cookie、不扫码登录、不绕过验证码。

**API**
- `GET /api/v1/sessions`（Bearer 鉴权）：
  ```json
  {
    "schema_version": "1.0",
    "sessions": [
      {
        "platform": "bilibili",
        "configured": true,
        "source": "file",
        "cookie_count": 29,
        "expires_at": "2027-04-08T00:00:00+08:00",
        "valid": null,
        "last_checked": null,
        "error_code": null
      }
    ]
  }
  ```
- `POST /api/v1/sessions/{platform}/check`：显式网络检查，限流；B站 nav，不支持平台返回 422。
- 不在 `capabilities` 中做网络检查；保持 capabilities 无网络承诺。

**接线**
- `BilibiliClient` 构造时从 `SessionManager` 取 cookie/headers；提取器与 discovery 共用。
- `DouyinExtractor` 改用 `DouyinSessionProvider`。
- `ytdlp` 提取器读取 `YtDlpSessionProvider` 的配置，生成 yt-dlp options。
- 现有 env 保持兼容，不要求用户迁移。

### 3.3 PlatformRateLimiter

建议文件：`src/core/platforms/rate_limit.py`

```python
class PlatformRateLimiter:
    def acquire(self, platform: str, *, deadline: float | None = None) -> None: ...
    def execute(self, platform: str, fn, *, deadline: float | None = None): ...
    def record_failure(self, platform: str, error_code: str) -> None: ...
    def circuit_state(self, platform: str) -> str: ...
```

- 每平台：
  - 最小间隔（默认 B站 1000ms、抖音 2000ms、小红书 1500ms、YouTube 500ms）；
  - 最大并发（默认 1）；
  - 最大重试（默认 2）；
  - 指数退避 + jitter（500ms base，×2，0–250ms jitter）；
  - 熔断：连续 3 次 risk_control/429 触发，冷却 60s；
  - `max_wait`：等待超过 2s 返回 `rate_limited` + `retry_after_seconds`。
- 失败映射：
  - 412 / -352 / -412：`risk_control`，**不重试**，记录熔断；
  - 429：`rate_limited`，按 `Retry-After` 或退避重试；
  - 5xx / timeout：`upstream_error`，对 GET 重试；
  - 401：`auth_required`，不重试；
  - 4xx 参数/内容不存在：不重试。
- 与总超时：
  - `execute(..., deadline=...)` 每次请求/退避前检查剩余时间；
  - 评论 discovery 继续使用 `VMB_DISCOVERY_TOTAL_TIMEOUT`，重试/等待都算在预算内。
- 观测：
  - 结构化日志：`platform_request`（outcome/status/latency/retries/error_code）、`platform_request_retry`、`platform_risk_signal`、`platform_circuit_open`、`platform_circuit_rejected`。
  - 不记录 URL、cookie、请求头或响应正文；`VMB_LOG_JSON=1` 可切换为单行 JSON 日志。
  - `GET /api/v1/metrics`：每平台请求、成功/失败、重试、风控、限流、熔断与延迟计数；进程内计数，重启清零。

**接线**
- Bilibili：`BilibiliClient` 的所有请求（nav/view/playurl/reply/space）走 limiter；删除 discovery 中重复的 `PlatformThrottle`（service 与 provider 不再双重等待）。
- Douyin：`iesdouyin.com` / `www.douyin.com` 页面和 detail API 走 limiter；本地 `douyin-api` 网关不套 limiter。
- Xiaohongshu：`xhslink` 短链和 `xiaohongshu.com` 页面走 limiter。
- YouTube：`oembed`、watch 页和字幕轨道走 limiter；`youtubetranscript.com` 第三方服务不套平台 limiter。
- yt-dlp/yt-dlp+ASR：注入 `--sleep-requests`、`--retries`、`--extractor-retries`、`--socket-timeout`，不使用 HTTP limiter 包整个子进程；平台熔断打开时跳过 yt-dlp 兜底。
- TikHub/Apify：付费第三方 API 不套平台 limiter，保留各自配额与重试。
- 配置：
  - `VMB_PLATFORM_RATE_LIMIT_ENABLED=1`
  - `VMB_PLATFORM_INTERVALS_MS='{"bilibili":1000,"douyin":2000,"xiaohongshu":1500,"youtube":500}'`
  - `VMB_PLATFORM_MAX_CONCURRENCY=1`
  - `VMB_PLATFORM_MAX_RETRIES=2`
  - `VMB_PLATFORM_BACKOFF_BASE_MS=500`
  - `VMB_PLATFORM_CIRCUIT_COOLDOWN_SEC=60`
  - `VMB_XHS_COOKIE` / `VMB_XHS_COOKIES_FILE`（可选登录态）
  - `VMB_YTDLP_SLEEP_REQUESTS` / `VMB_YTDLP_RETRIES` / `VMB_YTDLP_EXTRACTOR_RETRIES` / `VMB_YTDLP_SOCKET_TIMEOUT` / `VMB_YTDLP_SLEEP_INTERVAL`
- 默认开启对 B站/抖音/小红书/YouTube 的平台直连节流；提供一键关闭开关以便回滚。

### 3.4 验收

- [x] `GET /api/v1/sessions` 只返回脱敏状态；cookie 值不出现在 API/日志。
- [x] B站 cookie 文件/ SESSDATA / 完整 header 的优先级正确；过期时间可读。
- [x] 412/-352 不重试，返回 `risk_control`，并触发熔断。
- [x] 429 按 `Retry-After` 重试，最终失败返回 `rate_limited` + `retry_after_seconds`。
- [x] 同平台请求满足最小间隔/并发上限；测试用 fake clock，不真实 sleep。
- [x] 评论总超时仍生效，重试不突破总预算。
- [x] yt-dlp options 包含 sleep/retries；现有提取测试通过。
- [x] 全量 pytest、ruff、mypy 通过。

---

## 4. 文件改动清单

| 文件 | 改动 |
|---|---|
| `src/core/router.py` | 移除/弱化实例缓存；新增 `close()`；与 Runtime 解耦 |
| `src/core/router_runtime.py` | 新增：Runtime、TTL 缓存、锁、close |
| `src/core/cache.py` | 新增/迁移通用 TTLCache（discovery 复用） |
| `src/core/extractors/base.py` | 新增 `close()` 默认实现 |
| `src/core/extractors/*.py` | 关闭各自 HTTP client |
| `src/core/platforms/session.py` | 新增：SessionProvider/SessionStatus/SessionManager |
| `src/core/platforms/rate_limit.py` | 新增：PlatformRateLimiter/熔断/退避 |
| `src/core/platforms/bilibili_client.py` | 注入 session + limiter；移除重复 cookie 解析 |
| `src/core/discovery/*` | 复用 SessionManager/RateLimiter；删除重复 throttle |
| `src/api/server.py` | Runtime 生命周期；`cost_tier` 解析；sessions 路由 |
| `src/api/models.py` | `ExtractRequest`/`cost_tier`/`SessionStatusResponse` |
| `src/mcp/server.py` | 共享 Runtime；shutdown close |
| `src/core/capabilities.py` | 使用 Runtime 缓存提取器状态（可选） |
| `tests/*` | Runtime/缓存/成本/会话/限流/熔断/脱敏测试 |
| `docs/API_USAGE.md` | 补充 `cost_tier` 与 `/sessions` |

---

## 5. 分阶段实施

| 阶段 | 内容 | 状态 |
|---|---|---|
| 1 | RouterRuntime + 缓存 + close + cost_tier 透传 + 测试 | 已完成 |
| 2 | SessionManager + B站接入 + `/sessions` 状态 + 测试 | 已完成 |
| 3 | PlatformRateLimiter + B站接入 + 删除 discovery 重复 throttle + 测试 | 已完成 |
| 4 | 抖音/小红书/YouTube 直连接入 + yt-dlp 网络参数/会话 + 测试 | 已完成（2026-10-21） |
| 5 | 观测、灰度、文档、全量回归 | 观测/文档/回归已完成；正式灰度按需 |

**回滚**
- `cost_tier` 默认 cheap，旧调用方无感。
- Rate limiter 有 `VMB_PLATFORM_RATE_LIMIT_ENABLED=0` 开关。
- SessionManager 只读，不影响现有 cookie 优先级。
- 提取缓存可用 `VMB_EXTRACT_CACHE_TTL=0` 关闭；如需完全退回每请求新建 Router，需回滚代码（当前未提供运行时开关）。

---

## 6. 非目标

- 不做扫码登录、自动 cookie 刷新、验证码打码、代理池、浏览器指纹伪装。
- 不做公开爬虫 SDK 或大规模采集。
- 不改 ASR 端口/模型链。
- 不引入 Redis/Celery/完整 APM；先做轻量进程内实现。
- 不扩展 creator feed；B站同 IP 实测仍 -352，保持关闭。

---

## 7. 待确认

1. Router 采用单例还是小池？推荐先用单例 + 线程安全缓存，压测后再池化。
2. 成本字段命名 `cost_tier`（与 MCP 一致）还是 `max_cost`（与 discovery 一致）？推荐 `cost_tier`，默认 cheap。
3. 会话检查默认只读状态，还是允许 `POST check` 网络探测？推荐只读状态 + 显式 check。
4. 平台限流默认值是否按推荐值开启？推荐 B站 1s、抖音 2s、小红书 1.5s、并发 1。
5. 5xx/timeout 是否重试？推荐只对幂等 GET 重试 2 次，412/-352 永不重试。

---

## 8. 实施记录与差异（阶段 1–3）

**已落地**
- `RouterRuntime`（`src/core/router_runtime.py`）+ 通用 `TTLCache`（`src/core/cache.py`）：API/MCP 共用长生命周期 Router；缓存 key 含 URL、`cost_tier`、ASR 链/语言/上限；只缓存 full 成功结果；关闭时释放提取器。
- `/extract`、`/extract/archive` 支持 `cost_tier`，默认 `cheap`，非法值 400；MCP 继续使用既有 `cost_tier`。
- `SessionManager`（`src/core/platforms/session.py`）+ `GET /api/v1/sessions`、`POST /api/v1/sessions/{platform}/check`；B站状态只返回来源、数量、过期时间和错误码，永不返回 cookie 值；仅 B站支持显式 check，其他平台 422。
- `PlatformRateLimiter`（`src/core/platforms/rate_limit.py`）：B站 `BilibiliClient` 全部请求接入；412/-352 不重试并熔断，429/5xx/超时退避重试，401 直接 `auth_required`；HTTP 200 响应体内的 -352/-412/-799 也会登记风控。
- 删除 discovery 的 `PlatformThrottle`，避免 service/provider 双重等待；评论总超时预算继续生效。
- 阶段 4：新增 `platform_get()`（`src/core/platforms/http.py`）；抖音 `iesdouyin`/`douyin.com` 直连、小红书短链/笔记页、YouTube oembed/watch/字幕轨道接入 limiter；本地 `douyin-api`、`youtubetranscript.com`、TikHub/Apify 不接平台 limiter。
- 阶段 4：`XiaohongshuSessionProvider`（`VMB_XHS_COOKIE` / `VMB_XHS_COOKIES_FILE` / `VMB_COOKIES_FILE`）；抖音改用 SessionManager 的 Cookie；`YtDlpSessionProvider.cookie_args()` 成为 yt-dlp cookies 参数唯一来源。
- 阶段 4：yt-dlp 命令注入 `--sleep-requests`、`--retries`、`--extractor-retries`、`--socket-timeout`；平台熔断打开时 yt-dlp/yt-dlp+ASR 直接跳过。
- 阶段 4：平台最大等待按间隔自动放大（`max(2s, interval+1s)`），避免抖音 2s 间隔在并发请求下误报 `rate_limited`。
- 阶段 5：`PlatformRateLimiter` 内置平台计数（请求/成功/失败/重试/风控/限流/超时/熔断/延迟），新增 `GET /api/v1/metrics`；新增 `platform_request*` 结构化日志与可选 `VMB_LOG_JSON=1` JSON 格式；日志不包含 URL、cookie、请求头或响应正文。

**与草案的差异**
- 限流器公开接口为 `execute()` + `notify_risk_control()`，没有单独的 `acquire()`/`record_failure()`。
- `SessionStatus` 为普通 dataclass；B站 `check()` 的错误码为 `auth_required` / `risk_control` / `upstream_error`。
- 提取缓存默认 TTL 600 秒、容量 256，可由 `VMB_EXTRACT_CACHE_TTL` / `VMB_EXTRACT_CACHE_MAX_ENTRIES` 调整。
- 阶段 5 的正式灰度未单独执行；指标为进程内计数，重启清零，不引入 Prometheus/Redis。
- `docs/API_USAGE.md` 已补 `cost_tier`、`/sessions`、`/metrics` 与阶段 4 环境变量。
