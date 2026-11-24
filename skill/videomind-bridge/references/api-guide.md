# HTTP API 参考（2026-11-25，A2 之后）

> 服务默认 `http://127.0.0.1:8787`。字段语义以仓库 `docs/CONTRACT.md` 为准，本文只给用法。
> **v1 已删除**：`/legacy`、`/ws`、`/api/v1/tasks*`（下载→转录→AI 摘要）不再存在。

## 公开端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 存活探针（无鉴权） |
| GET | `/api/v1/status` | 运行时状态（四个任务计数恒为 0，字段仅为兼容保留） |
| GET | `/api/v1/capabilities` | 提取器与 ASR 后端能力矩阵 |
| POST | `/api/v1/extract` | **主入口**：提取正文 |
| POST | `/api/v1/extract/archive` | 提取并归档（本地 / Obsidian / HTML） |
| POST | `/api/v1/parse` | 只解析元信息（快，含音频直链） |
| POST | `/api/v1/prescreen` | 零网络成本/价值预筛 |
| GET | `/api/v1/metrics` | 平台请求指标 + 熔断状态 + 提取命中分布 |
| POST | `/api/v1/comments` | 评论采样（需 `VMB_ENABLE_COMMENTS=1`） |
| POST | `/api/v1/creator/feed` | 创作者作品列表（需 `VMB_ENABLE_CREATOR_FEED=1`） |
| GET/PUT | `/api/v1/config`、`/api/v1/settings` | 配置（管理面，不承诺） |
| GET/PUT/DELETE | `/api/v1/keys*`、`/api/v1/sessions*` | 密钥与登录态（管理面，不承诺） |

鉴权：本机回环默认免鉴权；设了 `VIDEOMIND_API_TOKEN`（或 `VMB_CONSUMER_TOKENS`）后需
`Authorization: Bearer <token>`。建议带上 `X-Consumer-Id` 便于按调用方统计。

## 提取

```bash
curl -X POST http://127.0.0.1:8787/api/v1/extract \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.bilibili.com/video/BV1xx411c7mD", "cost_tier": "cheap"}'
```

响应关键字段：

| 字段 | 含义 |
|---|---|
| `success` | 是否拿到了东西（**不是**内容是否完整） |
| `completeness` | `full` / `meta` / `none` / `unknown` |
| `content` | 正文；`meta` 时可能只有标题/简介 |
| `platform` | 链接所属平台（永不是提取器名） |
| `method` | `subtitle` / `asr` / `page` / `desc` / `manual` |
| `attempts` | 失败时逐提取器明细（`extractor` / `error_code` / `error`） |
| `error_code` | 失败或部分成功的原因，`success=false` 时必非空 |

> **只有标题/文案时请判 `success=true` + `completeness=meta`**，不要当失败处理。

`cost_tier` 表示可接受的最高提取成本：`free` / `cheap`（默认）/ `paid` / `expensive` / `premium`。
非法值返回 400。

## 预筛（零网络）

```bash
curl -X POST http://127.0.0.1:8787/api/v1/prescreen \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.douyin.com/video/xxx", "mode": "quick"}'
```

返回内容分级（`grade` / `score`）与**提取成本决策**（`cost_grade` / `recommended_cost_tier` / `skip_reason`）。
它回答「提取这个链接要花多少钱」，不回答「这条内容值不值得运营」——后者属于调用方的职责。

## 归档

```bash
curl -X POST http://127.0.0.1:8787/api/v1/extract/archive \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.bilibili.com/video/BV1xx", "targets": ["local"], "local_output": "/tmp/vmb"}'
```

`targets` 可选 `local` / `obsidian` / `html_player`；Obsidian 需要 `obsidian_vault`。
失败时同样返回 `error_code`（`extract_failed` / `internal_error` 等）。

## 常见 error_code

| error_code | 含义 | 处理 |
|---|---|---|
| `unsupported_url` | 没有提取器认领这个链接 | 确认平台与链接形态 |
| `douyin_gateway_unavailable` | 本机 douyin-api(:8010) 没起 | `pm2 restart douyin-api` |
| `no_subtitle_no_asr` | 无字幕且 ASR 全部不可用 | 装 SenseVoice 或配 DashScope key |
| `risk_control` | 平台风控 | 配 cookie / 换 IP，不要重试轰炸 |
| `extract_failed` | 归档端提取失败 | 看 `attempts` 明细 |
| `internal_error` | 服务端异常 | 查服务日志 |
