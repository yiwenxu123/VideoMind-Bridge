# 创作者主页与评论采集 API 设计

> 状态：Phase 2 已实现（creator feed + comments + MCP，均默认关闭）
> 日期：2026-10-20
> 范围：VMB 新增两个只读采集原语——创作者作品列表、评论采样
> 关联：内容运营 agent 的 ADR-002 采集层架构、[真实链接回归脚本](../scripts/check_real_links.py)

---

## 1. 背景与结论

内容运营 agent 已经有博主监控和评论洞察：

- `BenchmarkPatrolService`：拉 RSS → guid 游标去重 → 新作品入库；自动通道目前只支持 B站（RSSHub），小红书/公众号强制 manual。
- `BenchmarkService.commentInsight`：已有评论聚类与选题能力，但输入是人工粘贴的评论，明确不碰平台接口。

缺口在**平台采集**，不在下游算法。因此 VMB 只新增两个有边界的原语：

1. `creator_feed`：给定创作者主页，返回最新 N 条作品及互动数据。
2. `comments`：给定内容链接，返回限量评论样本，可选一层二级回复。

监控、去重、评分、选题、人工复核仍留在内容运营 agent。VMB 不做 watchlist、cron、LLM 聚类或用户画像。

### 1.1 已确认的约束

- 只采集公开内容与公开评论。
- 限量采样，不做全量翻页、不做递归回复。
- 不建立用户画像：默认不返回用户 ID、头像、主页；作者展示名可选。
- 保留人工复核：VMB 只提供样本，不自动发布、不自动做选题决策。

---

## 2. 职责边界

| 能力 | VMB | 内容运营 agent |
|---|---|---|
| 创作者作品列表 | 平台请求、登录态/签名、分页、结构化 metrics、限流、缓存 | 博主库、watchlist、cron、last_seen、去重、hit score |
| 评论样本 | 拉 top-N、可选一层回复、文本截断、限流、缓存 | 评论聚类、选题生成、人工复核、发布决策 |
| 错误处理 | 统一 `error_code`、`retry_after_seconds` | 根据错误码决定重试/跳过/通知 |
| 长期存储 | 不落库；仅进程内 TTL 缓存 | 作品、评论信号、选题、复盘数据的持久化 |

**边界原则**：VMB 不判断评论是否有价值，不做内容价值评估；这些属于消费端与评估层。

---

## 3. 通用约定

### 3.1 路径与鉴权

- 基址：`/api/v1`
- 鉴权：沿用现有 `Authorization: Bearer <token>`（`VIDEOMIND_API_TOKEN` / `VMB_CONSUMER_TOKENS`）。
- 请求/响应：`application/json`。
- 新端点默认**不注册**，通过环境变量显式开启；关闭时返回 404，不出现在 `/capabilities` 中。

快速启用与验证：

```bash
VMB_ENABLE_CREATOR_FEED=1 \
VMB_ENABLE_COMMENTS=1 \
VMB_BILIBILI_COOKIES_FILE=/path/to/bilibili-cookies.txt \
python main.py --api

curl -X POST http://127.0.0.1:8787/api/v1/creator/feed \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://space.bilibili.com/123456","limit":5}'

curl -X POST http://127.0.0.1:8787/api/v1/comments \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.bilibili.com/video/BVxxxx","limit":10,"sort":"hot","include_replies":true}'
```

MCP 模式下同样会按开关注册 `get_creator_feed` / `get_comments`。B站空间接口通常需要登录态；无 Cookie 时会返回 `risk_control`，评论接口实测可无登录采样，详见 §7。

### 3.2 通用响应字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `success` | bool | 是否成功返回可用数据；上游失败为 `false` 并带 `error_code` |
| `schema_version` | string | 与现有契约一致，当前 `1.0` |
| `request_id` | string | 服务端生成的 `uuid4().hex`，用于日志关联 |
| `platform` | string | `bilibili` 等 |
| `source` | string | 实际 provider，如 `bilibili_discovery` |
| `cost_tier` | string | `free / cheap / paid / expensive / premium` |
| `completeness` | string | `full / partial / none` |
| `sampled` | bool | 固定 `true`；明确这是采样结果 |
| `fetched_at` | string | ISO 8601，数据抓取时间；缓存命中时为原始抓取时间 |
| `cached` | bool | 是否来自缓存 |
| `warnings` | string[] | 部分成功时的说明，如 `replies_truncated` |
| `error` | string? | 失败时的人类可读信息 |
| `error_code` | string? | 失败时的机器可读错误码 |
| `retry_after_seconds` | int? | 限流/风控时建议等待秒数 |

### 3.3 HTTP 状态约定

| 场景 | HTTP | 说明 |
|---|---|---|
| 参数错误 | 400 | `detail` 说明具体字段 |
| 未授权 | 401 | 现有中间件 |
| 非法 Origin | 403 | 现有 CSRF 防护 |
| 功能未启用 | 404 | 路由未注册 |
| 网关/消费者限流 | 429 | 带 `Retry-After` |
| 上游风控、未找到、超时 | 200 | `success=false` + `error_code`，不改变现有契约习惯 |
| 成功 / 部分成功 | 200 | `success=true`；部分成功 `completeness=partial` + `warnings` |

---

## 4. 创作者作品列表

### 4.1 请求

`POST /api/v1/creator/feed`

```json
{
  "url": "https://space.bilibili.com/123456",
  "limit": 20,
  "max_cost": "cheap"
}
```

| 字段 | 类型 | 必填 | 默认 | 约束 |
|---|---|---|---|---|
| `url` | string | 是 | — | 创作者主页 URL；必须命中平台域名白名单 |
| `limit` | int | 否 | 20 | 1–30 |
| `max_cost` | string | 否 | `cheap` | 低于 provider 成本时返回 `cost_exceeded` |

v1 只接受主页 URL，不接受任意 `creator_id`，避免绕过平台域名白名单和 SSRF 防护。

### 4.2 响应

```json
{
  "success": true,
  "schema_version": "1.0",
  "request_id": "8f3c2a1b9d4e4f6a",
  "platform": "bilibili",
  "source": "bilibili_discovery",
  "cost_tier": "free",
  "completeness": "full",
  "sampled": true,
  "cached": false,
  "fetched_at": "2026-10-20T08:00:00+00:00",
  "creator": {
    "id": "123456",
    "name": "示例UP主",
    "url": "https://space.bilibili.com/123456"
  },
  "items": [
    {
      "id": "BV1xx411c7mD",
      "url": "https://www.bilibili.com/video/BV1xx411c7mD",
      "title": "示例视频标题",
      "published_at": "2026-10-19T10:00:00+00:00",
      "duration_seconds": 512,
      "metrics": {
        "views": 12000,
        "likes": 800,
        "comments": 60,
        "favorites": 300,
        "shares": 40,
        "coins": 50
      },
      "cover_url": "https://i0.hdslb.com/..."
    }
  ],
  "returned_count": 1,
  "has_more": true,
  "warnings": []
}
```

| 字段 | 说明 |
|---|---|
| `creator.id` | 平台侧公开 ID；仅用于标识创作者 |
| `items[].id` | 平台作品 ID，用于去重 |
| `items[].url` | 作品规范 URL |
| `items[].metrics` | 平台可提供的互动指标；缺失字段省略，不补 0 |
| `returned_count` | 实际返回条数 |
| `has_more` | 平台是否还有更早作品；v1 不提供翻页 |

### 4.3 规则

- 只取最新作品，按发布时间倒序。
- 默认 20 条，最多 30 条；不做历史全量归档。
- B站通过 `x/space/wbi/arc/search` 获取，复用现有 WBI 签名；可能需要 `buvid3`/`SESSDATA` cookie，缺失时返回 `auth_required` 或 `risk_control`。
- 互动数据是抓取时快照，不保证实时；消费端自行决定是否更新已有作品 metrics。
- 不返回创作者粉丝数、简介等画像字段，除非未来单独评审。

---

## 5. 评论采样

### 5.1 请求

`POST /api/v1/comments`

```json
{
  "url": "https://www.bilibili.com/video/BV1xx411c7mD",
  "limit": 20,
  "sort": "hot",
  "include_replies": true,
  "max_replies_per_thread": 3,
  "include_author": false,
  "max_cost": "cheap"
}
```

| 字段 | 类型 | 必填 | 默认 | 约束 |
|---|---|---|---|---|
| `url` | string | 是 | — | 内容 URL；支持 B站标准视频链接与 `b23.tv` 短链，最终域名必须在平台白名单内 |
| `limit` | int | 否 | 20 | 1–50；总数，包含回复 |
| `sort` | string | 否 | `hot` | `hot` / `recent` |
| `include_replies` | bool | 否 | false | 是否展开一层二级回复 |
| `max_replies_per_thread` | int | 否 | 3 | 1–10；仅 `include_replies=true` 时生效 |
| `include_author` | bool | 否 | false | 为 true 时只返回作者展示名，不返回用户 ID/头像/主页 |
| `max_cost` | string | 否 | `cheap` | 低于 provider 成本时返回 `cost_exceeded` |

### 5.2 响应

```json
{
  "success": true,
  "schema_version": "1.0",
  "request_id": "d2a9c7e1f0b34a6c",
  "platform": "bilibili",
  "source": "bilibili_discovery",
  "cost_tier": "free",
  "completeness": "full",
  "sampled": true,
  "cached": false,
  "fetched_at": "2026-10-20T08:00:00+00:00",
  "sort": "hot",
  "items": [
    {
      "id": "1234567890",
      "parent_id": null,
      "root_id": "1234567890",
      "text": "这个观点很有启发",
      "likes": 42,
      "created_at": "2026-10-19T12:00:00+00:00",
      "is_reply": false,
      "reply_count": 5
    },
    {
      "id": "1234567891",
      "parent_id": "1234567890",
      "root_id": "1234567890",
      "text": "同意，尤其是第二点",
      "likes": 3,
      "created_at": "2026-10-19T12:05:00+00:00",
      "is_reply": true
    }
  ],
  "returned_count": 2,
  "top_level_count": 1,
  "reply_count": 1,
  "has_more": true,
  "warnings": ["replies_truncated"]
}
```

| 字段 | 说明 |
|---|---|
| `items[].id` | 平台评论 ID |
| `items[].parent_id` | 二级回复的父评论 ID；一级评论为 `null` |
| `items[].root_id` | 所属根评论 ID |
| `items[].text` | 评论文本；超过 2000 字符截断 |
| `items[].truncated` | 文本是否被截断；未截断时省略 |
| `items[].likes` | 点赞数快照 |
| `items[].reply_count` | 平台提供的回复数，可选 |
| `items[].author` | 仅当 `include_author=true` 时出现，形如 `{"display_name": "..."}`；不含用户 ID |
| `returned_count` | 实际返回条数 |
| `has_more` | 平台是否还有更多评论；v1 不提供翻页 |

### 5.3 采样规则

- `limit` 是**总条数**上限，一级评论和二级回复共同占用。
- 默认按热度取一级评论；`sort=recent` 时按时间。
- `include_replies=true` 时，按一级评论顺序展开，最多 10 个 thread；每个 thread 最多 `max_replies_per_thread` 条回复；总数达到 `limit` 即停止。
- 短链解析最多 3 次跳转；解析失败或最终域名不是 B站时返回 `content_not_found`。
- 只展开一层，不递归二级以下回复。
- 不做全量翻页；`has_more=true` 只表示平台还有更多，客户端不能据此无限拉取。
- `limit` 是上限而非保证：当上游调用预算或总超时耗尽时，可能返回少于 `limit` 条，并置 `completeness=partial`、`has_more=true`。
- 同一评论按 `id` 去重。
- 上游回复抓取部分失败时，返回已取到的数据，`completeness=partial`，并在 `warnings` 中说明。

---

## 6. 错误码

| `error_code` | 含义 | 消费端建议 |
|---|---|---|
| `invalid_request` | 参数/URL 非法 | 修正请求，不重试 |
| `not_supported` | 当前平台/功能不支持 | 跳过或走人工 |
| `auth_required` | 缺少或过期 cookie | 更新授权，不自动重试 |
| `risk_control` | 平台验证码/风控 | 停止并通知，不连续重试 |
| `creator_not_found` | 创作者不存在/不可见 | 标记失效，不重试 |
| `content_not_found` | 内容不存在/已删除 | 标记失效，不重试 |
| `rate_limited` | 平台或网关限流 | 按 `retry_after_seconds` 退避 |
| `cost_exceeded` | 没有符合 `max_cost` 的 provider | 提高成本上限或跳过 |
| `upstream_error` | 网络/5xx/超时 | 指数退避，最多 2–3 次 |
| `internal_error` | VMB 内部错误 | 上报，不盲目重试 |

- 失败响应示例：

```json
{
  "success": false,
  "schema_version": "1.0",
  "request_id": "a1b2c3d4",
  "platform": "bilibili",
  "source": "bilibili_discovery",
  "cost_tier": "free",
  "completeness": "none",
  "error": "平台触发风控，请稍后重试或更新 Cookie",
  "error_code": "risk_control",
  "retry_after_seconds": 60
}
```

- `rate_limited` 同时返回 HTTP 429 和 `Retry-After`；其余上游失败仍用 HTTP 200 + `success=false`，与现有 `/extract` 保持一致。

---

## 7. 平台支持与成本

| 平台 | creator_feed | comments | 认证/风控 | 成本档 | v1 |
|---|---|---|---|---|---|
| B站 | 支持：空间 API + WBI | 支持：官方 reply API | 可选 `buvid3` / `SESSDATA`；风控时返回错误码 | free/cheap | **是** |
| YouTube | 支持：频道 RSS | 可选：Data API（有配额） | API key | free/cheap | 后续 |
| 抖音 | 计划中 | 计划中 | `a_bogus` + cookie + 风控 | paid/premium | 后续 |
| 小红书 | 计划中 | 计划中 | `x-s` / `xsec_token` + cookie | paid/premium | 后续 |
| 公众号 | 不支持 | 不支持 | — | — | 否 |

> **B站实测（2026-10-20）**：空间接口在无登录态下会返回 HTTP 412 或 `code=-352`；请通过 `VMB_BILIBILI_COOKIES_FILE` / `VMB_BILIBILI_SESSDATA` / `VMB_BILIBILI_COOKIE` 提供有效登录态。评论接口 `/x/v2/reply` 实测可无登录采样（3 条一级 + 6 条二级）。另测：从 RSSHub 服务器导出的完整 cookie 在本机直连空间接口仍返回 `-352`，疑似与出口 IP/指纹绑定；遇到风控应停止重试，VMB 不会自动绕过验证码或切换账号。

- v1 每个平台/功能只配置**一个 provider**，不做多 provider 自动降级，避免风控时放大请求。
- 需要签名/cookie 的平台，先通过独立 provider 接入并单独评估维护成本，不把 Playwright 作为默认依赖。

---

## 8. 限额、缓存与限流

### 8.1 限额

| 项 | 默认 | 硬上限 |
|---|---|---|
| creator feed `limit` | 20 | 30 |
| comments `limit` | 20 | 50 |
| `max_replies_per_thread` | 3 | 10 |
| 评论展开 thread 数 | 10 | 10 |
| 单条评论文本 | 2000 字符 | 2000 字符 |
| 单次请求上游调用数 | 12 | 12 |
| 单次请求总超时 | 30s | 30s |

### 8.2 缓存

- 进程内 TTL LRU，不落库；多进程部署时各自缓存。
- creator feed：默认 300 秒。
- comments：默认 900 秒。
- 只缓存 `success=true` 且 `completeness=full` 的结果；空结果可短缓存 60 秒。
- 缓存 key 不包含消费者身份（公开数据），但限流仍按消费者计算。
- 风控/鉴权失败不缓存。

### 8.3 限流

- 沿用现有 `VMB_RATE_LIMIT_PER_MIN` 每消费者限流。
- 平台级节流：同一平台上游请求最小间隔默认 1000ms；最多等待 2 秒，否则返回 429 `rate_limited`。
- 评论展开回复时，每次上游请求都计入节流和单次调用上限；达到调用上限时提前返回，不再继续翻页。
- 超时：单次上游 10 秒；总调用 30 秒；部分成功返回 `partial`。

### 8.4 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `VMB_ENABLE_CREATOR_FEED` | `0` | 开启 creator feed 路由 |
| `VMB_ENABLE_COMMENTS` | `0` | 开启评论路由（更敏感，单独开关） |
| `VMB_CREATOR_FEED_CACHE_TTL` | `300` | 秒 |
| `VMB_COMMENTS_CACHE_TTL` | `900` | 秒 |
| `VMB_DISCOVERY_HTTP_TIMEOUT` | `10` | 单次上游超时（秒） |
| `VMB_DISCOVERY_TOTAL_TIMEOUT` | `30` | 单次 API 调用总超时（秒） |
| `VMB_BILIBILI_MIN_INTERVAL_MS` | `1000` | B站上游最小间隔 |
| `VMB_BILIBILI_COOKIES_FILE` | 空 | Netscape cookies.txt；为空时回退 `VMB_COOKIES_FILE` |
| `VMB_BILIBILI_SESSDATA` | 空 | 直接提供 SESSDATA 值；适合从其他系统导出单条凭证 |
| `VMB_BILIBILI_COOKIE` | 空 | 完整 Cookie header；优先级最高，适合提供带 `buvid3` 等字段的完整 cookie |

---

## 9. 隐私与安全

### 9.1 数据最小化

- 只采公开评论和公开作品元信息。
- 默认不返回用户 ID、头像、主页链接；`include_author=true` 时只返回公开展示名。
- 不建立用户画像，不做跨内容作者聚合，不提供“某用户还评论过什么”。
- 评论仅用于选题信号与人工复核，不用于自动化发布。
- VMB 不持久化评论；仅进程内 TTL 缓存，重启即失效。
- 评论正文、作者展示名不写日志；日志只记录 `request_id`、平台、数量、耗时、`error_code`。

### 9.2 防滥用与 SSRF

- URL 必须命中平台域名白名单；只接受 `http/https`。
- 短链解析最多 3 次跳转，最终 host 仍须在白名单内。
- 不访问私网/回环地址；平台 API host 固定。
- 不支持任意关键词搜索、任意用户 ID 查询、批量导入 URL 列表。
- 所有新端点继承 Bearer 鉴权、Origin 防护和消费者限流。
- 功能默认关闭，开启后才注册路由并在 `/capabilities` 中暴露。

### 9.3 合规

- 仅采集公开内容；不绕过登录、付费墙、验证码或访问控制。
- 遇到 `risk_control` 立即停止，不连续重试、不切换账号规避。
- 控制采样频率和数量；遵循平台条款与合理使用原则。
- 内容运营 agent 保留人工复核；VMB 不提供自动发布能力。

---

## 10. 实现结构

```text
src/core/discovery/
  __init__.py
  models.py              # CreatorFeedItem / CommentItem / 结果模型
  base.py                # DiscoveryProvider 协议
  registry.py            # 平台 provider 注册
  service.py             # 限额、成本、缓存、节流、错误归一化
  cache.py               # TTL LRU
  providers/
    __init__.py
    bilibili.py          # B站 provider（I/O + 解析）

src/core/platforms/
  bilibili_client.py     # 共享 WBI/cookie/HTTP，供 extractor 与 discovery 复用

src/api/
  discovery_routes.py    # 两个新路由；按开关注册
  models.py              # Pydantic 请求/响应模型

src/mcp/server.py        # 新增 get_creator_feed / get_comments
src/core/capabilities.py # 开启时声明 discovery 能力
```

### 10.1 Provider 接口

```python
class DiscoveryProvider(Protocol):
    platform: str
    cost_tier: CostTier

    def supports_creator_feed(self) -> bool: ...
    def supports_comments(self) -> bool: ...

    def fetch_creator_feed(self, url: str, limit: int) -> CreatorFeedResult: ...
    def fetch_comments(
        self,
        url: str,
        limit: int,
        sort: str,
        include_replies: bool,
        max_replies_per_thread: int,
        include_author: bool,
    ) -> CommentsResult: ...
```

- `DiscoveryService` 负责参数校验、限额、成本过滤、缓存、节流和错误映射。
- Provider 只负责平台请求与解析，不处理鉴权中间件、限流策略或消费者身份。
- API 与 MCP 共用同一个 `DiscoveryService`，避免两套逻辑漂移。

### 10.2 B站复用

- 从现有 `bilibili_extractor.py` 抽出 WBI 签名、mixin key、cookie 加载为共享 `bilibili_client.py`，extractor 与 discovery 都使用它。
- 先补 characterization test，确保抽取后原有 B站提取行为不变。
- 空间作品接口：`x/space/wbi/arc/search`（需要 WBI + 可能的 cookie）。
- 评论接口：官方 `x/v2/reply` 与 `x/v2/reply/reply`；只取一层回复。
- 具体参数与字段以真实链接验证为准，不把浏览器自动化作为默认路径。

---

## 11. 与内容运营 agent 的对接

### 11.1 创作者作品

现有 `BenchmarkPatrolService._discoverBlogger` 的输入是 RSS item，输出是 `addPost`。VMB 接入后：

1. 博主记录使用 `homepage_url` 调用 `creator_feed`（B站）。
2. 将 `items[].url/title/published_at` 映射到 `addPost`，`discovery_source` 记为 `vmb`。
3. 将 `items[].metrics` 映射到现有 `updateMetrics`，补齐 hit score 所需的互动数据。
4. `last_seen_guids` 继续使用作品 URL/ID，不需要改库结构。
5. 消费者增加 `BENCHMARK_DISCOVERY_SOURCE=rss|vmb|auto`；VMB 失败时回退 RSS/manual。

### 11.2 评论

现有 `BenchmarkService.commentInsight` 接受 `{text, likes}` 数组。VMB 的评论项可直接映射：

```js
comments = result.items.map((c) => ({ text: c.text, likes: c.likes }));
```

- 触发时机：某条作品被判定为爆款/值得拆解后，再拉评论样本；不要对每条作品都拉评论。
- 消费者保留人工复核；`commentInsight` 的 LLM 聚类与选题逻辑不变。
- 建议在消费者侧增加 `BENCHMARK_COMMENTS_SOURCE=manual|vmb`，便于回滚。

### 11.3 不建议的接法

- 不在 VMB 内实现 cron/watchlist/博主库。
- 不在 VMB 内做评论聚类、选题生成、爆款判定。
- 不让 VMB 直接写内容运营 agent 的 `benchmark_posts` 或 `signals` 集合。

---

## 12. 测试与验收

### 12.1 单元测试

- 请求校验：缺 URL、非法 limit、非法 sort、未知平台。
- 限额：默认值、上限、`max_replies_per_thread` 边界。
- 成本：`max_cost=free` 时过滤 paid provider，返回 `cost_exceeded`。
- 开关：关闭时路由 404；开启时出现在 capabilities。
- URL 白名单：非平台域名、私网地址、短链跳转越界。
- 缓存：TTL、key 区分 sort/limit/include_replies、失败不缓存。
- 错误映射：风控、限流、部分成功。
- 隐私：默认响应不含用户 ID/头像/主页；日志不含评论正文。

### 12.2 夹具测试

- 录制脱敏后的 B站空间作品 JSON、评论 JSON、二级回复 JSON。
- 覆盖：空列表、缺失 metrics、折叠回复、长评论截断、平台错误码。

### 12.3 接口/MCP 集成

- FastAPI TestClient + mock provider。
- MCP `get_creator_feed` / `get_comments` 与 API 返回同一结构。
- capabilities 在开关开启/关闭时的差异。

### 12.4 真实链接回归

- 新增 `benchmarks/discovery-links.example.yaml`：
  - 1 个 B站创作者主页。
  - 1 条有热评的 B站视频。
- 已实现 `scripts/check_discovery_links.py`（清单：`benchmarks/discovery-links.example.yaml`）：
  - 检查 `success`、`returned_count`、是否包含 metrics/replies、耗时、`error_code`。
  - 输出表格或 `--json`；本地清单 `benchmarks/discovery-links.local.yaml` 已 gitignore。
- 不建议把 creator/comments 混进现有 `check_real_links.py` 的单条提取清单，避免语义混乱。

### 12.5 验收标准

- [ ] B站 creator feed 返回 ≥1 条作品，包含可用 metrics。
- [ ] B站 comments 返回一级评论；`include_replies=true` 时返回一层回复。
- [ ] `limit` 在两个端点都被严格执行；没有全量翻页。
- [ ] 默认响应不含用户 ID/头像/主页；`include_author=true` 只多展示名。
- [ ] 风控/鉴权失败返回正确 `error_code`，不连续重试。
- [ ] 关闭开关时两个端点均 404。
- [ ] 内容运营 agent 可直接消费结果，无需改 `commentInsight` / `addPost` 契约。
- [ ] 日志中无评论正文、作者展示名、带 token 的 URL。

---

## 13. 分阶段落地

| 阶段 | 内容 | 预计 |
|---|---|---|
| 0 | 本设计评审，确认默认值与开关 | 0.5 天 |
| 1 | 共享 B站 client + `DiscoveryService` + creator feed + API（默认关闭）+ 单测/夹具 | 1–2 天 |
| 2 | comments 采样 + MCP + capabilities + 真实链接脚本 | 1–2 天 |
| 3 | 内容运营 agent 接入 B站 patrol 与 commentInsight；观察 1–2 周 | 1 天 |
| 4 | 评估抖音/小红书；仅在 B站证明价值且合规边界确认后启动 | 待定 |

**回滚**：关闭 `VMB_ENABLE_CREATOR_FEED` / `VMB_ENABLE_COMMENTS`；消费者回退 RSS/manual。VMB 不保存数据，无需数据迁移。

---

## 14. 待确认项（已给推荐默认值）

| 事项 | 推荐默认 | 备选 |
|---|---|---|
| 作者展示名 | 默认不返回；`include_author=true` 才返回展示名 | 永远不返回作者信息 |
| 评论排序 | 默认 `hot` | 默认 `recent` |
| 回复深度 | 只一层 | 不做回复 |
| 翻页 | 不提供，`has_more` 仅提示 | 未来加 cursor |
| 缓存 TTL | feed 5 分钟 / comments 15 分钟 | 更短或更长 |
| 功能开关 | 两个端点默认关闭 | 默认开启 creator feed |
| v1 平台 | 仅 B站 | 同时做 YouTube |
| 评论存储 | 不落库，仅内存缓存 | 落 SQLite 供审计 |
| 成本默认 | `cheap` | `premium` |

---

## 15. 非目标

- 关键词搜索、话题发现、批量 URL 导入。
- 全量评论翻页、递归回复、评论按用户聚合。
- 用户画像、跨平台身份合并、作者主页抓取。
- 多账号池、代理池、验证码打码、浏览器自动化默认路径。
- VMB 内置 cron/watchlist/通知/UI。
- VMB 内做 LLM 评论聚类、选题生成、内容价值评估。
- 自动发布或自动决策。
