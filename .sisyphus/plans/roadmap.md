# VideoMind Bridge v2 — 开发路线图

> 总计: ~6.5 周, 4 个 Phase

```
    第1周          第2周          第3周         第4周         第5周         第6周
  ┌──────────────┬──────────────┬─────────────┬─────────────┬─────────────┬─────────────┐
  │                              │                             │                          │
  │  Phase 0:                     Phase 1:       Phase 2:      Phase 3:                 │
  │  提取引擎                      预筛引擎        Agent接口     商业API+集成               │
  │                              │                             │                          │
  │  ┌────────────────────┐  ┌────────────────┐  ┌────────────┐  ┌────────────────────┐  │
  │  │ Bilibili           │  │ 标题/SEO/时长   │  │ MCP 升级   │  │ tikhub.io          │  │
  │  │ YouTube            │  │ 分析器          │  │ CLI升级     │  │ 阿里百炼           │  │
  │  │ Douyin (零Cookie)  │  │ 营销检测        │  │ 输出对齐    │  │ Apify              │  │
  │  │ 小红书 (零Cookie)  │  │ 成本预估        │  │ Hermes集成  │  │ OpenClaw Skill更新 │  │
  │  │ Coze (可选,保留)   │  │ D/C/B/S/A分级   │  │            │  │ 文档               │  │
  │  │ yt-dlp 兜底        │  │ 预筛→提取联动   │  │            │  │                    │  │
  │  │ 缓存层             │  │                │  │            │  │                    │  │
  │  └────────┬───────────┘  └───────┬────────┘  └─────┬──────┘  └─────────┬──────────┘  │
  │           │                      │                 │                   │              │
  │           ▼                      ▼                 ▼                   ▼              │
  │  ┌────────────────────┐  ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐  │
  │  │ 多引擎就绪         │  │ 预筛引擎完成    │  │ MCP 3工具就绪   │  │ 全链路可运行       │  │
  │  │ Coze 可选 + 零Cookie│  │ --smart 模式   │  │ Hermes 可消费  │  │ OpenClaw 可调用   │  │
  │  │ Coze 失败不降级    │  │                │  │               │  │                    │  │
  │  └────────────────────┘  └────────────────┘  └────────────────┘  └────────────────────┘  │
  │                                                                                         │
  │  ✅可交付 Hermes 使用                                                                   │
  │     (Phase 0 完成即可替换 video-content-extractor)                                      │
  └──────────────────────────────────────────────────────────────────────────────────────┘
```

## 里程碑

| 时间 | 里程碑 | 交付物 | 对 Hermes 的价值 |
|------|--------|--------|-----------------|
| **第 2 周** | Phase 0 ✅ | 提取引擎, CLI --json | ✅ 多引擎就绪, Coze 可选保留, 401 不再降 C 级 |
| **第 3.5 周** | Phase 1 ✅ | 预筛引擎, --smart 模式 | ✅ 提取前知道内容价值 |
| **第 4 周** | Phase 2 ✅ | MCP 升级, Hermes 输出对齐 | ✅ 直接集成, 无需适配 |
| **第 6 周** | Phase 3 ✅ | 商业 API, OpenClaw 更新 | ✅ 无字幕视频也能提取 |

## Phase 0 交付就够了?

**是的。** 即使只完成 Phase 0, 对 Hermes 已经是巨大的提升:

**当前 (仅 Coze)** | **Phase 0 后 (VMB 多引擎)**
---|---
401 Token 过期 → 降级 C 级 | Coze 可选, 有 Token 就用; 过期自动跳到直接 API/yt-dlp
无字幕视频 → 旧工作流空结果 | yt-dlp + Whisper 兜底, 无字幕也能提取
120 秒超时 → 失败 | 多引擎并行, 一个超时另一个接上
没有 Coze 就用不了 | CLI 一行命令, 零外部依赖也能用; Coze 只是加速选项
短链接解析失败 | 4 种方法解析短链接

**Coze 在 VMB 中的位置变了**: 从"唯一依赖" → "可选加速器"。有 Token 时优先用(免费+快), 没有或坏了自动跳其他路。

## 快速开始 (Phase 0 完成后)

```bash
# 1. 预筛 + 提取 (一步完成)
uv run python -m src.cli "https://bilibili.com/video/BVxxx" --smart --json

# 2. 仅预筛 (不下载)
uv run python -m src.cli "https://bilibili.com/video/BVxxx" --prescreen-only --json

# 3. 强制指定提取成本
uv run python -m src.cli "https://douyin.com/video/xxx" --cost-tier free --json

# 4. MCP 方式 (AI Agent 调用)
# → prescreen_video("URL") → 返回 {grade, score, recommendation}
# → extract_video("URL")   → 返回 {content, source, cost_tier}
```

## 风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| 抖音反爬升级, iesdouyin 接口变 | 中 | 高 | 降级到 yt-dlp + Cookie, 商业 API 备用 |
| B站 WBI 签名算法变更 | 低 | 高 | yt-dlp 兜底, 检测到 403 自动切换 |
| 小红书页面结构变更 | 中 | 中 | CSS 选择器改为正则匹配, 自修复 |
| 用户不习惯 CLI | 中 | 低 | Agent 封装了 CLI, 用户不直接接触 |
| 与 Hermes skill 集成冲突 | 低 | 中 | 输出格式已对齐, SKILL.md 只需小改 |
| **Coze Token 过期** | **高** | **低** | **Coze→路由器自动跳过, 不影响提取, 不再是灾难** |
