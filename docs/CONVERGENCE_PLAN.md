# VideoMind Bridge 架构收敛方案

> **状态**: 已实施 (2026-07-31, Phase 0/1/2 ✅, Phase 3 ✅)
> **战略方向**: 方向 A — AI-Agent 内容知识层
> **目标**: 将经历多次定位漂移的双系统收敛为单一核心，明确职责边界，消除维护双倍

---

## 一、定位声明

### 1.1 一句话定位

> **AI Agent 的视频内容知识层**: 把 `URL → 价值判断 → 文字提取 → 知识入库` 做成一条端到端能力，
> 面向 **AI Agent（Hermes / OpenClaw / Claude Code）与 Obsidian 知识工作者**。

### 1.2 差异化（唯一卖点）

| 能力 | 说明 | 竞品 |
|------|------|------|
| **零 Cookie 中文平台提取** | B站 WBI / 抖音 iesdouyin / 小红书页面解析 | 无直接替代 |
| **提取成本决策（预筛重定义）** | 规则快筛 → 决定"值不值得花成本提取" | 无（竞品无此概念） |
| **成本感知路由** | 免费→付费自动降级 | Vidscribe 等无 |
| **提取即归档 Obsidian** | v2 输出直接入库 | BiliNote/BiliSum 未深度集成 |

### 1.3 职责边界（三层分工，零重叠）

```
┌─ VideoMind Bridge（采集决策层）─────────────────────────────┐
│  负责: 获取 + 成本决策 + 归档                                │
│  prescreen: 提取成本分级（规则快筛，零网络零成本）            │
│  extract:   零 Cookie 高质量提取全文（9 提取器 + 成本路由）  │
│  export:    结构化内容 → Obsidian / 本地 / HTML              │
└──────────────────────────┬───────────────────────────────────┘
                           │  Hermes JSON（{title, content, segments, duration...}）
                           ▼
┌─ content-value-evaluator（理解层，独立 skill）────────────────┐
│  负责: 深度价值评估 + 学习建议（LLM）                        │
│  输入: VMB 的标准输出（无需改造，直接消费）                  │
└───────────────────────────────────────────────────────────────┘
```

**铁律**: VideoMind Bridge **不实现** LLM 内容价值评估——那是 `content-value-evaluator` 的职责。
VMB 的"分级"只回答一个问题:**提取这个链接要花多少钱**（成本决策），而非"内容好不好"。

---

## 二、现状差距清单

### 2.1 必须消除的混乱

| # | 问题 | 位置 | 收敛动作 |
|---|------|------|---------|
| 1 | 双系统语义冲突（v1 "提取"=下载+转录, v2 "提取"=文字） | `cli.py` 双模式 / MCP v1+v2 工具混列 | 合并为单一 v2 语义 |
| 2 | 预筛自称"内容质量"实为标题规则打分 | `prescreen_rules.py` | 重定义为成本决策 |
| 3 | v1 服务占约 60% 代码却定位"Legacy" | `services/` 全套 | 降级为可选扩展 |
| 4 | 假接口 `interfaces.py` 与实现不符 | `services/interfaces.py` | 删除或改为真实类型 |
| 5 | 6 入口都要感知双引擎 | CLI/MCP/API/GUI/扩展/skill | 收敛为 MCP+CLI 主入口 |
| 6 | 预筛→提取→归档三段割裂（需用户手动串） | `core` / `exporters` 分属两系统 | v2 链路内置归档 |

### 2.2 保留资产

- `src/core/*`：提取器注册表、成本路由、HermesFormatter —— **收敛为唯一核心**
- `src/exporters/{obsidian,local,html_player}_exporter.py`：归档能力 —— **迁入 v2 链路**
- `src/services/task_database.py`：任务历史（API/GUI 需要，保留）
- 浏览器扩展 + `src/api`：作为 GUI 的替代交互面，保留

---

## 三、目标架构

```
┌───────────────────────────────────────────────────────────────┐
│  AI Agent 生态 (Hermes / OpenClaw / Claude Code / Cursor)      │
│  ┌──────────┐   ┌──────────┐   ┌─────────────────────────┐    │
│  │ MCP Server│   │   CLI    │   │   API (扩展专用, 保留)  │    │
│  └─────┬────┘   └────┬─────┘   └──────────┬──────────────┘    │
└────────┼─────────────┼────────────────────┼────────────────────┘
         └─────────────┼────────────────────┘
                        ▼
╔═══════════════════════════════════════════════════════════════╗
║  VideoMind 核心 (v2 收敛后)                                     ║
║                                                                 ║
║  Layer 1  prescreener（成本决策，重定义）                        ║
║    └─ 规则快筛: 平台支持 / 字幕可得 / 时长期望 / 标题信号         ║
║    └─ 输出: {cost_grade, recommended_cost_tier, skip_reason}    ║
║                                                                 ║
║  Layer 2  router（成本感知路由，保留）                           ║
║    └─ 遍历优先级 → 失败降级 → 缓存成功结果                       ║
║                                                                 ║
║  Layer 3  extractors（9 提取器，保留 + 稳定性投入）              ║
║    └─ coze/bilibili/youtube/douyin/xiaohongshu/ytdlp/ytdlp_asr/ ║
║       tikhub/apify                                              ║
║                                                                 ║
║  Layer 4  archiver（新增: 提取即归档）                           ║
║    └─ 复用 v1 导出器(Obsidian/本地/HTML), 适配 ExtractResult    ║
║                                                                 ║
║  Layer 5  formatter（Hermes 输出，保留）                         ║
╚═════════════════════════════════════════════════════════════════╝

可选扩展（v1 瘦身保留，不在主链）:
  ┌─ 下载/转录 (DownloadService/TranscribeService) → --mode full 使用
  ├─ GUI (PySide6) → 薄壳, 仅对接 API
  ├─ 任务队列/历史 (TaskManager/TaskDatabase) → API 专用
  └─ 浏览器扩展 → 对接 API
```

---

## 四、关键设计

### 4.1 预筛引擎重定义（成本决策）

**现状问题**: `prescreen_rules.py` 的 S/A/B/C/D 声称评估"内容质量"，实际是 SEO 词表 + 时长区间打分。
既无法回答"值不值得看"（需要 LLM），也误导用户以为能评估内容。

**重定义**:

```
新语义: prescreen 回答"提取这个链接的成本价值"
        高分级 = 提取性价比高（免费字幕 + 中等以上时长）
        低分级 = 提取性价比低（付费 ASR 才能取到 / 超短片段 / 平台不支持）

新输出 PrescreenResult:
  {
    "url": ...,
    "platform": "bilibili",
    "cost_grade": "B",              # 提取成本分级 (S/A/B/C/D)
    "score": 65.0,
    "recommended_cost_tier": "free", # → router 直接消费
    "skip_reason": "无字幕且平台不支持零Cookie提取, 需付费ASR",  # C/D 级
    "reasons": ["平台: bilibili", "预期有官方字幕(免费)"],
    "metadata": {"has_subtitle_evidence": true, ...}
  }
```

**规则集调整方向**（`prescreen_rules.py` 重构）:

| 规则 | 现在（质量语义） | 改为（成本语义） |
|------|----------------|----------------|
| 平台支持度 | 无 | **核心**: 平台是否在零Cookie提取器覆盖内 |
| 字幕可得性 | 无 | **核心**: 该平台/URL 预期有官方字幕（免费）还是需 ASR（付费） |
| 时长 | 越接近"最佳区间"越加分 | 过短(<30s)不划算 → 降级; 超长无字幕 → 成本上升 → 降级 |
| 标题 SEO | 扣分 | 保留（作为辅助信号, 不主导） |
| 营销词 | 扣分 | 保留（辅助信号） |

**关键: 分级结果直接作为 router 的 `max_cost` 输入**, 让 `--smart` 的推荐成本与预筛语义自洽:
```
prescreen → recommended_cost_tier → router.extract(url, max_cost=recommended)
```

**与 content-value-evaluator 的衔接**（明确不重叠）:
- VMB 输出 `cost_grade`（提取成本决策）+ 提取到的全文
- content-value-evaluator 消费全文做深度价值评估 + 学习建议
- 二者通过 Hermes JSON 衔接, VMB **不**引入内容价值 LLM 调用

### 4.2 CLI 单一化

**现状**: 一个 `cli.py` 承载 v1 模式（`--mode full/download/transcribe`）+ v2 模式（`--smart/--prescreen/--cost-tier`）20+ 参数。

**收敛目标**:

```bash
# 主命令（v2 语义, 唯一入口）
uv run python -m src.cli <URL>                    # 提取全文（自动路由）
uv run python -m src.cli <URL> --smart            # 成本决策 → 提取
uv run python -m src.cli <URL> --prescreen        # 仅成本决策（零网络）
uv run python -m src.cli <URL> --archive obsidian # 提取即归档 Obsidian
uv run python -m src.cli <URL> --mode full        # 可选扩展: 下载+转录+摘要

# 旧 v1 参数收敛到 --mode 子命令下, 不再与 v2 参数平级混排
```

**拆分建议**:
- `src/cli.py` → `src/cli/` 包: `main.py`（参数解析）/ `v2.py`（主链）/ `full.py`（可选扩展模式）
- 参数分组: v2 参数为主, v1 的 `--mode full` 明确标注"扩展模式"

### 4.3 入口收敛

| 入口 | 现状 | 收敛策略 | 优先级 |
|------|------|---------|--------|
| **MCP** | v1 工具(process/download/transcribe) + v2 工具(prescreen/extract) 混列 | **主入口**: v1 工具标 deprecated, 聚焦 prescreen_video/smart_extract/extract_video/list_extractors; 补 download 工具(对齐竞品) | P1 |
| **CLI** | v1+v2 双模式 | 主入口（见 4.2） | P1 |
| **API** | v1 任务系统 + v2 extract 端点 | 保留（浏览器扩展依赖）; v2 端点保持现状 | P2 |
| **GUI** | 1160 行 MainWindow + v1 worker | 降级为薄壳（对接 API）, 不再直接调 v1 服务 | P2 |
| **浏览器扩展** | 接 API | 保留 | 无 |
| **OpenClaw skill** | v1+v2 双引擎描述 | 更新为 v2 主链描述 | P2 |

### 4.4 归档链迁移（提取即归档）

**新增 `src/core/archiver.py`**: 将 v1 导出器适配到 v2 链路。

```python
# 目标接口
def archive_extract_result(
    result: ExtractResult,
    targets: list[str],          # ["obsidian", "local", "html_player"]
    config: ArchiverConfig,
) -> list[ExportResult]:
    """把提取结果直接归档, 无需经过 v1 下载/转录"""

# 适配: v1 BaseExporter.export(ExportContext) 期望 video_path/audio_path
#       但 v2 ExtractResult 只有文本 → 导出器需支持"纯文本归档"模式:
#       ExportContext.transcript_segments / ai_summary 已存在, 补 transcript_text 即可
```

**各导出器适配点**:
- `obsidian_exporter.py`: 纯文本（transcript + 时间轴）即可生成笔记 —— **主要适配**
- `local_exporter.py`: 无视频文件时保存 Markdown/SRT —— 适配
- `html_player_exporter.py`: 无本地视频时降级为"纯字幕播放器"或跳过 —— 适配
- `webhook_exporter.py`: 直接可用（POST JSON）—— 无需改

**效果**: 用户给 Agent 一个链接 → `smart_extract --archive obsidian` → Obsidian 出现笔记。
这补上了"预筛→提取→归档"的组合拳, 是竞品(BiliNote/BiliSum)未做好的链路。

### 4.5 v1 服务瘦身路线

| 模块 | 处置 | 理由 |
|------|------|------|
| `DownloadService` / `TranscribeService` | 保留为可选扩展（`--mode full`） | 完整处理仍有价值 |
| `AIService` | 保留（`--mode full` 的摘要）; 从主链剥离 | 深度评估交给 content-value-evaluator |
| `ExportOrchestrator` | 复用（归档链） | 见 4.4 |
| `TaskManager` / `TaskDatabase` | 保留（API/GUI 用） | 任务历史有价值 |
| `interfaces.py` | **删除**, 改用具体类型 | 假接口是最大债务 |
| `duplicate_detector` | 保留（GUI/API 用） | — |
| `prompt_template` | 保留（--mode full 用） | — |

**GUI 薄壳化**: `main_window.py`(1160行) + worker(637行) 不再直接调 v1 服务, 改为 WebSocket 消费 API 进度。长期可替换为 web/ 前端（已存在）。

---

## 五、分阶段实施计划

> 实施状态: **Phase 0 ✅ / Phase 1 ✅ / Phase 2 ✅ / Phase 3 ✅**

### Phase 0 — 预筛重定义（基础, 0.5~1 周）✅

- [x] 重构 `prescreen_rules.py`: 新增平台/字幕/时长成本规则, 弱化 SEO 词表
- [x] 扩展 `PrescreenResult`: 新增 `recommended_cost_tier` / `skip_reason` 字段
- [x] `router.extract(max_cost)` 消费 prescreen 输出, `--smart` 语义自洽
- [x] 更新 `tests/test_core.py` 预筛测试到新语义
- [x] 更新 SKILL.md / AGENTS.md 预筛描述

### Phase 1 — v2 主链打通（核心, 1~2 周）✅

- [x] 新增 `src/core/archiver.py`（提取即归档）
- [x] 适配 obsidian/local 导出器支持纯文本归档
- [x] CLI 增加 `--archive` 参数（拆分推迟到 Phase 3 入口统一）
- [x] MCP 新增 `archive_extract` 工具 + v1 工具标 [DEPRECATED]
- [x] CLI/MCP 增加 `--archive` / `archive_extract` 能力

### Phase 2 — v1 瘦身（1~2 周）✅

- [x] 删除 `services/interfaces.py`, 全部改具体类型
- [x] GUI 清理未使用 import/属性（完整薄壳化推迟至 web 前端成熟后）
- [x] API 补 v2 归档端点 `/api/v1/extract/archive`
- [x] 清理 6 个 `__main__` 调试块 + 死代码

### Phase 3 — 入口统一与文档（0.5 周）✅

- [x] OpenClaw skill / README 更新为 v2 主链叙事
- [x] 版本号升 3.0.0（语义: 定位收敛）
- [x] 文档归档: 本方案 + 新架构图

**总工期约 3.5~5.5 周**（可并行 Phase 1 的 CLI/MCP 与 Phase 2 的 interfaces 清理）

---

## 六、风险与回退

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 预筛重定义破坏现有 Agent 契约（S/A/B/C/D 语义变化） | 中 | 中 | 字段向后兼容: `grade` 保留, 新增 `cost_grade` 字段过渡; SKILL.md 同步 |
| 导出器纯文本适配回归 | 中 | 中 | 逐导出器测试; 无视频时降级而非报错 |
| 抖音/小红书平台接口变化 | 高 | 高 | 成本路由自动降级（已实现）; 商业 API 兜底 |
| GUI 薄壳化期间用户功能缺失 | 中 | 低 | 阶段内保留旧 GUI 并行, 验证后切换 |
| v1 `--mode full` 用户流失 | 低 | 低 | 保留该模式, 仅降优先级 |

**回退原则**: 每个 Phase 独立可回退（git 提交分阶段）; 预筛重定义保留旧字段兼容。

---

## 七、验收标准

实施结果:
1. ✅ **预筛语义自洽**: `prescreen` 输出的 `recommended_cost_tier` 可直接驱动 `router.extract`，`--smart` 行为与文档一致
2. ✅ **提取即归档**: `smart_extract --archive obsidian` / MCP `archive_extract` 一条命令完成"决策→提取→入库"
3. ⏳ **CLI 单一化**: v2 参数为主已达成；`src/cli/` 包拆分推迟（当前 900+ 行单文件可维护）
4. ✅ **MCP 聚焦**: v2 工具为主入口 + `archive_extract`；v1 工具标 [DEPRECATED]
5. ✅ **interfaces.py 删除**: 全部改具体类型, mypy 错误 328 → 317
6. ✅ **职责边界**: VMB 无内容价值评估逻辑（归 content-value-evaluator）
7. ✅ **全部测试通过**: 987 passed, 覆盖率 73%+

**遗留长期项**: GUI 完整薄壳化（对接 API）、CLI 包拆分、`data/tasks.db` 解除 git 跟踪
