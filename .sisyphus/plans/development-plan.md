# VideoMind Bridge v2 — 开发计划

> **之前**: 26 周, PySide6 桌面应用, Notion/Webhook/深色主题/多语言...
> **现在**: 4-6 周, 轻量内容引擎, CLI/MCP, Agent 优先

**策略转型**: 砍掉所有胖客户端功能。聚焦提取引擎+预筛+Agent接口。

---

## Phase 0: 核心提取引擎 (第 1-2 周)

**目标**: 多引擎提取, Coze 作为可选适配器保留, 新增零 Cookie 直接提取

### Week 1: 提取器基础设施

| 任务 | 内容 | 参考代码 |
|------|------|---------|
| 提取器基类 + 工厂 | `core/extractors/base.py` — 抽象基类, is_available()/should_try() | keepongo + Hermes 现有模式 |
| Bilibili 提取器 | `bilibili_extractor.py` — WBI 签名, 字幕下载 API | keepongo WBI 签名 + Hermes 短链接解析 |
| YouTube 提取器 | `youtube_extractor.py` — youtube-transcript-api / oembed | keepongo 实现 |
| Coze 提取器 | `coze_extractor.py` — 封装现有 Coze 代码为适配器 | Hermes coze-workflow.md (281 行, 直接复用) |
| yt-dlp 兜底 | `ytdlp_extractor.py` — 字幕→音频→Whisper 三级降级 | keepongo fallback chain |

**Week 1 验收标准**:
- [ ] `python -m src.core.extractors "B站URL" --json` 返回结构化内容 (直接 API)
- [ ] Coze 提取器: 有 Token 时走 Coze, 无 Token 时 is_available()=False 自动跳过
- [ ] 短链接自动解析 (b23.tv, xhslink.com, v.douyin.com)
- [ ] 提取失败时清晰错误信息 (不再静默失败)

### Week 2: 抖音 + 小红书 + 统一路由

| 任务 | 内容 | 参考代码 |
|------|------|---------|
| Douyin 提取器 | `douyin_extractor.py` — iesdouyin 移动端 API | keepongo `_douyin_share_api()` |
| Xiaohongshu 提取器 | `xiaohongshu_extractor.py` — `__SETUP_SERVER_STATE__` | keepongo `_parse_xhs_page()` |
| 内容路由 | `core/router.py` — 成本感知优先级列表, 自动遍历 | 新设计 (见架构图) |
| 缓存层 | 文件缓存提取结果 (TTL 7 天) | keepongo `_read_cache()` / `_write_cache()` |

**Week 2 验收标准**:
- [ ] `python -m src.core.extractors "抖音URL" --json` 返回结构化内容 (零 Cookie)
- [ ] `python -m src.core.extractors "小红书URL" --json` 返回结构化内容 (零 Cookie)
- [ ] 路由链: 直接API → Coze → yt-dlp字幕 → Whisper → 元信息, 自动跳过不可用
- [ ] 缓存: 相同 URL 第二次提取 < 1s
- [ ] Coze 401 时自动跳到 yt-dlp/Whisper, 不阻塞 (不会再降到 C 级)

---

## Phase 1: 预筛引擎 (第 3-3.5 周)

**目标**: 实现 learnvalue 轻量前置版, 提取前做内容价值评估

### Week 3: 预筛规则引擎

| 任务 | 内容 | 规则来源 |
|------|------|---------|
| 标题分析器 | SEO 关键词检测 (保姆级/存下吧/99%弯路...) | Hermes bilibili-evaluation-guide.md |
| 时长分析器 | <60s → 仅元信息; 聚合页检测 | Hermes 评估规则 |
| 营销/软文检测 | 工具推荐类是否披露利益; 夸张说法 | Hermes evaluation-criteria.md |
| 原创性验证 | "XX团队打造" 声明核实 (未来可扩展) | Hermes B站红黄牌 |
| 成本预估器 | 有字幕→免费通道; 无字幕→付费 (用户确认) | Hermes Coze 双工作流策略 |
| 评分输出 | 1-10 分, S/A/B/C/D 映射 (分级与 Hermes 一致) | learnvalue 方法论 |

**Week 3 验收标准**:
- [ ] `python -m src.core.prescreener "B站SEO聚合页URL" --json` → C级, 含原因
- [ ] `python -m src.core.prescreener "正常教程URL" --json` → B级或以上
- [ ] 预筛结果包含: grade, score, recommendation, reasons, flags
- [ ] CLI 支持 `--prescreen-only` 不执行提取

### Week 3.5: 预筛 + 提取联动

| 任务 | 内容 |
|------|------|
| 预筛→提取链路 | `prescreen()` → D/C 级直接返回; B/S/A 级自动提取 |
| `--smart` 模式 | CLI 参数: 自动预筛+提取, AI Agent 单命令完成 |
| 输出格式升级 | JSON 同时包含 prescreen + extract 结果 |

**Week 3.5 验收标准**:
- [ ] `uv run python -m src.cli "URL" --smart --json` 输出 {prescreen, extract} 完整结构
- [ ] D 级内容跳过提取 (省时间/省 ASR 费用)
- [ ] 输出格式与 Hermes content-value-evaluator 兼容

---

## Phase 2: Agent 接口升级 + Hermes 集成 (第 4 周)

**目标**: MCP Server 生产化, CLI 完善, 输出 Hermes 原生兼容

### Week 4: Agent 接口

| 任务 | 内容 | 当前状态 |
|------|------|---------|
| MCP prescreen 工具 | 新增 `prescreen_video` 工具 | ❌ 不存在 |
| MCP extract 工具 | 现有 `process_video` → 升级为完整提取 | ✅ 已有, 需升级 |
| MCP smart 工具 | 合并预筛+提取为一步 | ❌ 不存在 |
| MCP 配置接口 | 新增 `configure` 工具 (API Key, 商业API配置) | ❌ 不存在 |
| MCP 成本告知 | 响应中包含 cost_tier 字段, Agent 可决策是否继续 | ❌ 不存在 |
| CLI --prescreen | 新增预筛参数 | ❌ 不存在 |
| CLI --smart | 新增智能模式 | ❌ 不存在 |
| CLI --cost-tier | 强制指定付费/免费通道 | ❌ 不存在 |
| 输出格式对齐 | 确保与 Hermes skill 的 `{success, platform, title, content, source}` 一致 | ✅ 基本一致, 需验证 |

**Week 4 验收标准**:
- [ ] MCP 三个工具 (prescreen / extract / smart) 可用
- [ ] MCP 响应包含 cost_tier, Agent 可据此决策
- [ ] CLI --smart 模式端到端工作
- [ ] Hermes `content-value-evaluator` skill 可直接消费 VMB 输出 (实测)
- [ ] OpenClaw `videomind-bridge` skill 配置更新

---

## Phase 3: 商业 API 适配 + 收尾 (第 5-6 周)

**目标**: 可选的商业 API 集成, 文档, OpenClaw skill 更新

### Week 5: 商业 API 适配器

| 任务 | 内容 | 成本 |
|------|------|------|
| tikhub.io 适配器 | 可选集成, 1000+ API, 16 平台支持 | ~$0.001/请求 |
| 阿里百炼 ASR 适配器 | paraformer-v2 模型, 用于无字幕视频 | 按量计费 |
| Apify 适配器 | B站/抖音 Transcripts Scraper | $4.99/1000次 |
| API Key 管理 | 配置文件管理多个 API Key, 优先级排序 | - |

**Week 5 验收标准**:
- [ ] 配置商业 API Key 后, 提取质量提升 (尤其无字幕视频)
- [ ] 路由自动选择: 免费 > 付费, 不会硬编码
- [ ] 无 API Key 时优雅降级 (不影响核心功能)

### Week 6: Hermes + OpenClaw 集成

| 任务 | 内容 |
|------|------|
| OpenClaw skill 更新 | `skill/videomind-bridge/SKILL.md` 升级到 v2, 新增 prescreen/smart 指令 |
| Hermes 兼容测试 | 用真实 Hermes content-value-evaluator skill 测试端到端 |
| 文档 | CLI 指南, MCP 指南, 预筛规则说明 |
| 清理 | 删除未使用的 GUI 组件, 简化项目结构 |

**Week 6 验收标准**:
- [ ] OpenClaw/Hermes 可通过 skill 直接调用 VMB 预筛+提取
- [ ] 从 URL 到 Obsidian 保存的全链路 < 2 分钟
- [ ] README 更新为 v2 定位

---

## 项目文件变更清单

### 新增文件
```
src/core/
├── __init__.py
├── models.py              # PrescreenResult, ExtractResult, ContentGrade
├── prescreener.py         # 预筛引擎
├── prescreen_rules.py     # SEO/时长/营销/原创性规则
├── router.py              # 成本感知路由 (遍历优先级列表)
├── formatter.py           # Hermes 兼容输出格式化
└── extractors/
    ├── __init__.py
    ├── base.py            # ContentExtractor 抽象基类
    ├── bilibili_extractor.py   # WBI 签名, 零 Cookie
    ├── douyin_extractor.py     # iesdouyin 移动端
    ├── xiaohongshu_extractor.py
    ├── youtube_extractor.py
    ├── coze_extractor.py       # Coze 工作流 (可选, 复用现有代码)
    ├── ytdlp_extractor.py      # yt-dlp 字幕
    └── whisper_extractor.py    # 本地 Whisper ASR
```

### 修改文件
```
src/cli.py           # 新增 --prescreen, --smart, --cost-tier 参数
src/mcp/server.py    # 新增 prescreen, smart 工具, 升级 extract
skill/videomind-bridge/SKILL.md   # 更新为 v2
```

### 保留不动
```
src/services/        # download/transcribe/ai 服务 (核心处理链)
src/exporters/       # Obsidian/本地/HTML 导出
src/gui/             # 保留但降级, 不阻塞发布
src/models/          # 数据模型 (可能简化)
```

---

## 为什么是这个节奏?

| 阶段 | 周期 | 核心理由 |
|------|------|---------|
| Phase 0 | 2 周 | **奠基**: 多引擎 + Coze 保留, 解决 401 不再掉到 C 级 |
| Phase 1 | 1.5 周 | **差异化**: 预筛 + 成本路由, 唯一竞品没有的能力 |
| Phase 2 | 1 周 | **集成**: MCP 升级 + 输出对齐, 让 Hermes 直接消费 |
| Phase 3 | 2 周 | **增强**: 商业 API 可选, 提升无字幕视频提取质量 |

**总计: 6.5 周** (vs 原计划 26 周)

核心交付 (Phase 0-2) 只需 **4.5 周**: 预筛+提取+MCP, 即可上线让 Hermes 使用。
