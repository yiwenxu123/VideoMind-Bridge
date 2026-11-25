# 对外契约（CONTRACT）

> 版本：`schema_version=1.0`｜最近修订：2026-11-25（A2 之后）
> 本文是**唯一权威**的对外契约说明。改字段语义前先读 §5。

---

## 1. 这个服务是谁

VideoMind Bridge 是**内容获取能力**：给一条视频/笔记链接，返回它的文字内容。

```
L2  内容运营agent  ──HTTP(:8787)──┐
L3  DSH MCP 工具（videomind）     ├──► 本服务 ──HTTP──► douyin-api(:8010) 平台网关
L3  video-content-extractor Skill ┘                    └──► yt-dlp / 本地 SenseVoice 转写
```

**消费者清单见 [`CONSUMERS.md`](./CONSUMERS.md)。改动前必须核对。**

> **上游是 L0，不是我的内部模块**：图里的 `douyin-api(:8010)` 按《项目分层与协作架构》§2.4 归
> **L0「平台取数网关」**（panorama 注册表 `layer: L0`，端口探活），VideoMind 只做编排。
> 抖音提取失败最常见的原因是它没起（`error_code=douyin_gateway_unavailable` → `pm2 restart douyin-api`）。
> 2026-11-25 之前它**完全不在注册表里**，所以运维视图上看不见这条硬依赖。
>
> **上游契约**：`~/Projects/ai-agents/douyin-api/docs/CONTRACT.md`（服务版本 V4.1.2）。
> 它只承诺一条路径 —— `GET /api/douyin/web/fetch_one_video?aweme_id=` —— 以及本服务读取的那几个字段。
> 上游升级/改写时先跑 `python scripts/check_douyin_gateway_contract.py`（读上游 `/openapi.json`，
> 路径或参数不见了就退非零，网关没起退 2）。

---

## 2. 端点

| 端点 | 用途 | 稳定性 |
|---|---|---|
| `GET /health` | 存活探针（无鉴权） | 稳定 |
| `GET /api/v1/status` | 运行时状态 | 稳定 |
| `GET /api/v1/capabilities` | 提取器与 ASR 后端能力矩阵 | 稳定 |
| `POST /api/v1/extract` | **主入口**：提取内容（有 response_model，形状见 §3） | 稳定 |
| `POST /api/v1/extract/archive` | 提取并归档 | 稳定 |
| `POST /api/v1/parse` | 仅解析元信息（快，含音频直链） | 稳定 |
| `POST /api/v1/prescreen` | 零网络成本/价值预筛（不下载） | 稳定 |
| `POST /api/v1/comments` | 评论采集 | 稳定 |
| `POST /api/v1/creator/feed` | 创作者作品列表 | **默认关闭**（`VMB_ENABLE_CREATOR_FEED=0` 时不注册） |
| `GET /api/v1/metrics` | 平台请求指标 + 熔断状态 + 提取命中分布 | 稳定 |
| `POST /api/v1/sessions*`、`/api/v1/settings`、`/api/v1/keys*` | 管理面（登录态 / 归档目录 / Obsidian 导出 / 提取器 Key） | 内部，不承诺 |

> **2026-11-25（A2）：`/legacy`、`/ws`、`/api/v1/tasks*` 已删除**（v1 下载→转录→AI 摘要流水线）。
> 请求这些路径返回 405。`GET /api/v1/status` 仍保留 `active_tasks/queued_tasks/completed_tasks/failed_tasks`
> 四个字段但恒为 0 —— 字段保留是为了不破坏已按这四列写代码的调用方，不是因为还有任务在跑。

鉴权：本机回环默认免鉴权；设了 `VIDEOMIND_API_TOKEN` / `VMB_CONSUMER_TOKENS` 后需 `Authorization: Bearer`。

> **token 环境变量只有一个规范名：`VIDEOMIND_API_TOKEN`**（服务端只读它，见 `src/api/auth.py`）。
> 回归脚本 `scripts/check_real_links.py` / `scripts/check_discovery_links.py` 现在也读这个名字；
> 历史错名 `VMB_API_TOKEN` 仅保留一个版本的兼容回退并打印弃用提示——**用旧名不会有任何报错，只会静默变成匿名请求**。

**调用方标识**：请在请求头带 `X-Consumer-Id`（如 `content-ops`、`dsh-mcp`）。
缺省记 `anonymous`。该标识进日志与 `/api/v1/metrics` 的 `api.by_consumer`，
是"按实际使用收敛端点数/工具面"的唯一依据。

**MCP 是薄适配器**：`videomind` MCP 工具（`extract`/`capabilities`/`comments`）不带引擎，
而是把请求转给本服务，因此**本服务必须在跑**；指标/缓存/熔断由此天然统一。
服务不可用时 MCP 会返回可执行提示（`pm2 start videomind-api`）。**没有离线兜底**：
> `VMB_MCP_EMBEDDED=1` 的进程内引擎已于 2026-11-25 删除 —— 它让 L3 适配器持有整套业务引擎。

---

## 3. `/api/v1/extract` 响应字段

> 2026-11-24：该端点有了 response_model（`src/api/models.py` 的 `ExtractResponse`），字段在 `GET /openapi.json` 里可见。
> 模型显式 `extra="allow"` + `response_model_exclude_unset=True` —— 加模型是为了文档化与校验，**不是**为了过滤：
> 进什么键出什么键，既不丢字段，也不会给未出现的字段补 `null`（补 null 同样算改形状）。

### 3.1 字段表

| 字段 | 类型 | 含义 |
|---|---|---|
| `success` | bool | **是否拿到了东西**（不是"是否完整"） |
| `completeness` | `full` \| `meta` \| `none` \| `unknown` | **内容的完整程度** |
| `platform` | string | 链接所属平台（`douyin`/`bilibili`/`xiaohongshu`/`youtube`）。**永远不会是提取器名** |
| `source` | string | 实际产出它的链路（`douyin_asr`/`bilibili_api`/`ytdlp_asr_local`…） |
| `method` | `subtitle` \| `asr` \| `page` \| `desc` \| `manual` \| `""` | 文字是怎么拿到的 |
| `title` / `content` | string | 标题 / 正文 |
| `duration_seconds` | float | 视频时长；图文笔记为 0 |
| `language` | string \| null | 语言 |
| `segments` | array（可选） | 时间轴分段 `{start,end,text}` |
| `asr` | object（可选） | `{provider, model, model_version}` |
| `error_code` | string \| null | 可机读的失败/部分原因 |
| `error` | string（可选） | 人类可读说明（失败时含各链路尝试摘要） |
| `attempts` | array（可选，失败时） | `[{extractor, error_code, error}]` 逐提取器明细 |
| `url` / `request_id` / `schema_version` / `cost_tier` | — | 回显与追踪 |
| `cost_tier_source` | `request` \| `default` | 成本档从哪来：调用方显式传了，还是服务端按默认档（cheap）处理。**看到 `default` 就说明你没管花钱上限** |

### 3.2 关键：`success` 与 `completeness` 是**正交**的两条轴

这是本契约最容易踩错的地方，也是真实事故来源：

| | `completeness=full` | `completeness=meta` | `completeness=none` |
|---|---|---|---|
| `success=true` | 拿到全文 | **拿到部分内容**（如只有标题/文案） | ⚠️ 不允许（见不变式） |
| `success=false` | 不存在 | 不存在 | 什么也没拿到 |

**语义约定：**

- `success=true` 只表示"有可用的东西返回"，**不代表内容完整**；
- 判断能否直接用，看 `completeness`（以及你自己对内容质量的校验）；
- "内容不完整"**不**通过 `success=false` 或 5xx 表达。

> 2026-11-23 曾把"只有标题"改成 `success=false`，理由是"不谎报成功"。
> 结果下游（以 `success!==true` 为致命错误）把唯一可用内容当成了 502。
> 正确做法是 `success=true` + `completeness=meta`。**不要重复这个错误。**

---

## 4. 不变式（有测试保护：`tests/test_consumer_contract.py`、`tests/test_api.py::TestArchiveFailureContract`）

1. `success=false` ⇒ `error_code` 非空（失败必须可机读归因）
2. `success=true` ⇒ `completeness ∈ {full, meta}`（不允许 `none`）
3. `completeness="full"` ⇒ `content` 非空
4. `completeness="meta"` ⇒ `content` 可非空但**不是全文**；`metadata.partial=true`（MCP 路径）
5. 失败时 `attempts` 列出每个尝试过的提取器及其原因
6. `platform` 恒为链接所属平台，即便最终由兜底提取器返回

---

## 5. 变更规则（改任何字段前必须回答三问）

**① 谁会坏？** 查 [`CONSUMERS.md`](./CONSUMERS.md)。找不到就说明存在未登记消费者 → 先补登记。

**② 能不能同一天把消费者一起改完？**
- 能 → 允许直接改语义，但必须同一天两边一起提交，并在本节记一行。
- 不能 → **先加新字段，不改旧语义**；旧字段保留到消费者迁移完。

**③ 是新增还是修改？**
- 新增字段：安全，直接发（`schema_version` 不变）。
- 修改/删除字段或改变其语义：**属破坏性变更**，必须 bump `schema_version` 并在下面记一行。

### 变更记录

| 日期 | 变更 | 影响 | 处理 |
|---|---|---|---|
| 2026-11-23 | 曾把 meta 结果改为 `success=false` | 下游会抛 502 | 同日回滚为 `success=true`（`5f2924f`） |
| 2026-11-23 | 失败结果的 `platform` 由提取器名改为链接所属平台 | 按平台聚合的统计更准 | 视为修正，无消费者依赖旧值 |
| 2026-11-24 | `/extract` 新增 response_model（`extra="allow"` + `exclude_unset`） | OpenAPI 可见字段；键集合与值均不变 | 纯新增（只文档化，不过滤字段、不补 null） |
| 2026-11-24 | `/extract/archive` 失败补 `error_code`（`extract_failed` / `internal_error`） | 该端点此前违反不变式 1 | 纯新增 |
| 2026-11-25 | `/api/v1/settings`、`/api/v1/config` 删除无执行者的 AI / 下载 / 转录字段 | 内部端点，控制台未使用；删后不再误导「改了有用」 | 删除（**配置存储 schema 未动**，旧 config.yaml 仍可读） |
| 2026-11-25 | `/extract`、`/extract/archive` 新增 `cost_tier_source`（`request` / `default`） | 纯新增；让「服务端替你用了默认成本档」可见 | 纯新增（默认档位仍是 cheap，未改行为） |
| 2026-11-22 | `/extract` 新增 `attempts` | 纯新增 | — |
| 2026-11-22 | `/metrics` 新增 `circuits`、`extraction` | 纯新增 | — |

---

## 6. 错误码

| `error_code` | 含义 | 建议动作 |
|---|---|---|
| `douyin_gateway_unavailable` | 本机 douyin-api 网关没起 | `pm2 restart douyin-api` |
| `douyin_gateway_no_detail` | 网关通了但无详情 | 多半视频不可见，请用户确认 |
| `douyin_risk_control` | 真被风控（含 200 壳页） | 配 cookie / 等冷却 |
| `douyin_no_content` | 页面正常但无文字 | 提高成本档走 ASR |
| `xhs_token_invalid` | 分享参数失效 | 让用户重新分享 |
| `xhs_note_unavailable` | 笔记不可见 | 确认笔记状态 |
| `xhs_login_required` | 需要登录态 | 配 `VMB_XHS_COOKIE` |
| `xhs_risk_control` | 触发风控 | 稍后重试 |
| `xhs_no_content` | 笔记无正文 | 纯图片 |
| `extract_failed` | 全部链路失败且无更具体归因 | 看 `attempts` |

**HTTP 状态映射建议**：传输失败/超时 → 502/503；内容不完整或不可见 → **业务降级，不要 502**。
