# 消费者清单（CONSUMERS）

> 最近核对：2026-11-23
> **改任何对外字段前先看这里。** 找不到你的改动所影响的人，说明存在未登记消费者——先补登记再改。

---

## C1. 内容运营agent（L2，Node.js）— 主要消费者

| 项 | 内容 |
|---|---|
| 代码位置 | `~/Projects/ai-agents/内容运营agent/api-server/services/VideoMindClient.js` |
| 接入方式 | HTTP `VMB_BASE_URL`（默认 `http://127.0.0.1:8787`） |
| 调用的端点 | `GET /api/v1/capabilities`、`POST /api/v1/extract`、`POST /api/v1/creator/feed`（默认关闭）、`POST /api/v1/comments` |
| 依赖的字段 | `success`、`error_code`、`completeness`、`content`、`title`、`duration_seconds` |
| 错误映射 | `success !== true` → `unsupported_url` 映射 422，其余一律 **502** |
| 自有护栏 | ① content 以 title 开头则剥前缀；② `completeness=full` 但字数 < max(50, 时长×1.5) 时自行降级为 `partial` |

**它对契约的隐含假设（改动时必须保住）：**

1. `success=true` 才继续处理；`success!==true` 视为致命错误。
   → **部分内容必须 `success=true` + `completeness=meta`**。
2. 小红书正文是 `title + "\n\n" + 正文`，它靠这个剥标题前缀；形状变了会重复拼接。
3. 它**不信任**我们的 `completeness=full`，会用自己的密度规则再降级——所以
   我们不需要为"它可能误判"而收紧 `success`。

**已知待改（对方侧）**：把"内容不完整"映射成 502 语义不对（502 = 网关收到无效响应）。
建议改为业务降级。见 `docs/issues/2026-11-23-downstream-502-mapping.md`。

---

## C2. DSH MCP 工具 `videomind`（L3）— Agent 通道

| 项 | 内容 |
|---|---|
| 代码位置 | 本仓库 `src/mcp/`（`server.py` 旧实现 / `modern_server.py` 现行） |
| 注册位置 | `~/.dsh/profiles/{desktop,web}/cordis.patch.yml` → `mcp-videomind` |
| 形态 | **薄适配器**：工具把请求转给 REST :8787（不自带引擎），标识 `X-Consumer-Id: dsh-mcp` |
| 工具面（3 个） | `extract` / `capabilities` / `comments` |
| 依赖的字段 | 与 §3 相同的响应对象（工具结果原样透出） |

> 2026-11-23 从 12 个工具收敛到 3 个：其余 10 个**没有已知消费者**（详见审查报告 §问题 3）。
> 2026-11-24 改为薄适配器：此前 MCP 在进程内跑整套引擎，导致 Agent 流量在 `/metrics` 里
> 完全不可见（实测 MCP 提取后 REST 的 `total` 不变）。现在统一走 REST，指标自然可见。
> 代价：本服务没起时 MCP 不可用（会返回 `pm2 start videomind-api` 的提示）；
> 没有离线兜底：`VMB_MCP_EMBEDDED=1` 已于 2026-11-25 删除，服务必须在跑。

---

## C3. `video-content-extractor` Skill（L3）

| 项 | 内容 |
|---|---|
| 代码位置 | `panorama/skills/shared/video-content-extractor/SKILL.md`（v7.7） |
| 接入方式 | 直接调 REST `127.0.0.1:8787`（主路径）；MCP 为可选加速 |
| 依赖的字段 | `success`、`completeness`、`content`、`source`、`error_code`、`duration_seconds`、`attempts` |
| 依赖的端点 | `/health`、`/api/v1/extract`、`/api/v1/metrics`（诊断用） |

它把 `error_code` 的语义写进了文档（错误码对照表），**改错误码等于改 Skill 的行为**。

---

## C4. 潜在消费者（未登记，发现即补）

- 其它 DSH 会话里的 Agent 可能直接用 `curl 127.0.0.1:8787`（无 consumer 标识，无法枚举）
- `benchmark-decompose-assist` 等 Skill 走 `agent-reach` CLI，**不走本服务**（无重叠）

**如何发现新消费者**：给本服务加调用日志（`X-Consumer-Id` 请求头，缺省记 `unknown`），
跑一周即可得到真实清单。这是 P1 的第一项动作。
