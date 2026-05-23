# VideoMind Bridge v2 — 架构总览

> **战略定位**: AI-Agent-Ready Content Value Processing Engine
> **核心差异**: 内容预筛 → 成本感知提取 → Hermes 兼容输出
> **设计原则**: 轻量好用、可插拔、Agent 优先

---

## 一、系统架构 (三层模型)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         AI Agent 生态层                                 │
│                                                                         │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────┐   │
│  │  Claude Code  │   │    Hermes    │   │        OpenClaw          │   │
│  │  / Cursor     │   │    (Skill)   │   │    (Skill/Plugin)       │   │
│  └──────┬───────┘   └──────┬───────┘   └───────────┬──────────────┘   │
│         │                  │                        │                  │
│         └──────────────────┼────────────────────────┘                  │
│                            │  MCP / CLI / HTTP                         │
└────────────────────────────┼───────────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │   CLI 入口      │
                    │  (src/cli.py)   │
                    │  --json 标准输出 │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  MCP Server     │
                    │  (stdio JSON-RPC)│
                    └────────┬────────┘
                             │
╔════════════════════════════╪══════════════════════════════════════════╗
║                    VideoMind Bridge Core                             ║
╠════════════════════════════╪══════════════════════════════════════════╣
║                             │                                        ║
║  ┌──────────────────────────▼─────────────────────────────────────┐  ║
║  │  Layer 1: 内容预筛 (Prescreening)    ★ 唯⼀差异化              │  ║
║  │                                                               │  ║
║  │  URL ─→ 平台识别 ─→ 快速质量评估 ─→ 提取成本决策              │  ║
║  │                                                               │  ║
║  │  输入: URL / 文本                                              │  ║
║  │  输出: {recommendation, priority, estimated_cost, reason}     │  ║
║  │                                                               │  ║
║  │  检查项:                                                      │  ║
║  │  ├─ SEO 标题检测: 保姆级/存下吧/99%弯路 → 扣分                │  ║
║  │  ├─ 时长分析: <60s → 仅元信息; >60s → 完整提取                │  ║
║  │  ├─ 聚合页识别: B站推荐列表 > 描述 → C级上限                  │  ║
║  │  ├─ 原创性检测: "XX团队打造" 声明核实                         │  ║
║  │  ├─ 营销识别: 工具推荐类是否披露利益关系                      │  ║
║  │  └─ 成本路由: 有字幕→免费通道; 无字幕→付费ASR通道            │  ║
║  └────────────────────────────────────────────────────────────────┘  ║
║                             │                                        ║
║  ┌──────────────────────────▼─────────────────────────────────────┐  ║
║  │  Layer 2: 可插拔提取引擎 (Extraction Engine)                   │  ║
║  │                                                               │  ║
║  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │  ║
║  │  │ Bilibili    │  │ Douyin      │  │ Xiaohongshu         │   │  ║
║  │  │ (WBI签名)   │  │ (iesdouyin) │  │ (页面解析)          │   │  ║
║  │  │ 零Cookie    │  │ 零Cookie    │  │ 零Cookie            │   │  ║
║  │  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘   │  ║
║  │         │               │                     │               │  ║
║  │  ┌──────▼───────────────▼─────────────────────▼──────────┐   │  ║
║  │  │  Coze 工作流 (可选)                                    │   │  ║
║  │  │  ├─ 旧工作流 (免费, 有字幕视频)                       │   │  ║
║  │  │  └─ 新工作流 (付费ASR, 无字幕视频)                    │   │  ║
║  │  │  需配置 COZE_API_TOKEN, 可选依赖                      │   │  ║
║  │  └──────────────────────┬────────────────────────────────┘   │  ║
║  │                         │                                    │  ║
║  │  ┌──────▼───────────────▼─────────────────────▼──────────┐   │  ║
║  │  │  yt-dlp Fallback (1800+ sites)                        │   │  ║
║  │  │  字幕提取 → 音频下载 → Whisper ASR                    │   │  ║
║  │  └──────────────────────┬────────────────────────────────┘   │  ║
║  │                         │                                    │  ║
║  │  ┌──────────────────────▼────────────────────────────────┐   │  ║
║  │  │  商业 API 适配器 (可插拔)                              │   │  ║
║  │  │  ├─ tikhub.io (1000+ API, 16 平台)                   │   │  ║
║  │  │  ├─ 阿里百炼 (paraformer-v2 ASR)                     │   │  ║
║  │  │  └─ Apify (B站/抖音 Transcripts Scraper)             │   │  ║
║  │  └──────────────────────────────────────────────────────┘   │  ║
║  └────────────────────────────────────────────────────────────────┘  ║
║                             │                                        ║
║  ┌──────────────────────────▼─────────────────────────────────────┐  ║
║  │  Layer 3: 结构化输出 + Agent 接口                              │  ║
║  │                                                               │  ║
║  │  统一输出格式:                                                 │  ║
║  │  {                                                            │  ║
║  │    "success": true,                                           │  ║
║  │    "prescreen": {  // Layer 1 结果                            │  ║
║  │      "grade": "B",                                            │  ║
║  │      "recommendation": "速读提取",                             │  ║
║  │      "estimated_value": 6.5,                                   │  ║
║  │      "flags": ["seo_title", "short_duration"]                  │  ║
║  │    },                                                          │  ║
║  │    "platform": "bilibili",                                     │  ║
║  │    "title": "...",                                             │  ║
║  │    "content": "...",           // 完整提取结果                 │  ║
║  │    "source": "wbi_api",        // 提取方式                     │  ║
║  │    "cost_tier": "free",        // 免费/付费                    │  ║
║  │    "metadata": {duration, author, ...}                        │  ║
║  │  }                                                            │  ║
║  │                                                               │  ║
║  │  接口:                                                        │  ║
║  │  ├─ CLI: python -m src.cli <URL> --json (已有, 升级)          │  ║
║  │  ├─ MCP: configure → prescreen → extract (现有, 升级)         │  ║
║  │  └─ GUI: PySide6 (降级为可选, 不阻塞发布)                      │  ║
║  └────────────────────────────────────────────────────────────────┘  ║
╚════════════════════════════════════════════════════════════════════════╝
```

---

## 二、与 Hermes 生态的集成关系

```
Hermes 当前状态 (目前)             未来状态 (v2)
┌─────────────────────┐        ┌──────────────────────────────────┐
│ video-content-       │        │ VideoMind Bridge                │
│ extractor (仅 Coze)  │  ──→   │ (多引擎, Coze 是其中之一)     │
│ 不稳定, 401 频繁     │        │ 直接API → Coze → yt-dlp → ... │
│ 降级到 C 级          │        │ 一路不通自动跳下一路           │
└─────────┬───────────┘        └───────────────┬──────────────────┘
          │                                     │
          ▼                                     ▼
┌─────────────────────┐        ┌───────────────────────────┐
│ content-value-       │        │ content-value-            │
│ evaluator (v6.0)     │  ←←    │ evaluator (v6.0)          │
│ 评估 + Obsidian      │ JSON   │ 不变, 保持独立            │
│ 完全不需要改          │        │ 输入质量因 VMB 大幅提升   │
└─────────────────────┘        └───────────────────────────┘
```

**关键集成点**:
- VideoMind Bridge **扩展而非替换** `video-content-extractor` 的能力
- Coze 保留为可选适配器: 有 Token 就优先用它(免费+快), 没配或过期就自动跳其他方案
- `content-value-evaluator` skill **完全不动**，直接消费 VMB 的标准输出
- 格式兼容: VMB 输出 `{success, platform, title, content, source, url}` 与 Hermes 现有接口一致
- **容错提升**: Coze 失败 = 当前 Hermes 直接降到 C 级; VMB 中 Coze 失败 = 自动切到 yt-dlp/Whisper, 仍有内容

---

## 三、提取引擎策略模式

```python
# 核心接口
class ContentExtractor(ABC):
    """提取器基类"""
    platform: str                    # 平台标识
    cost_tier: str                   # "free" | "api" | "asr"
    requires_cookie: bool = False
    
    @abstractmethod
    def extract(self, url: str) -> ExtractResult: ...
    
    @abstractmethod
    def prescreen(self, url: str) -> PrescreenResult: ...

# 成本感知优先级列表 (按成本 + 速度排序)
# 每个提取器都有 is_available() → Token/Key 有效? 
# 每个提取器都有 should_try(url) → 这个URL适合我吗?
EXTRACTOR_PRIORITY = [
    #  级别  | 提取器              | 成本   | 速度   | 依赖
    # ───────┼─────────────────────┼────────┼────────┼──────────
    BilibiliExtractor(),            # 免费   秒级   无      (WBI 签名)
    DouyinExtractor(),              # 免费   秒级   无      (iesdouyin)
    XiaohongshuExtractor(),         # 免费   秒级   无      (页面解析)
    YouTubeExtractor(),             # 免费   秒级   pip     (transcript-api)
    CozeExtractor(free=True),       # 免费   10-30s Token  (旧工作流, 有字幕)
    YtdlpSubsExtractor(),           # 免费   秒级   pip     (yt-dlp 字幕)
    CozeExtractor(paid=True),       # 付费   30s    +ALI   (新工作流, ASR)
    WhisperExtractor(),             # 免费   分钟级 GPU     (本地 Whisper)
    CommercialAPIExtractor(),       # 付费   秒级   API Key (tikhub/Apify/百炼)
]

def extract_with_fallback(url: str) -> ExtractResult:
    """
    遍历提取器列表, 找到第一个可用的提取
    - is_available(): Token/Key 有效?
    - should_try():  这个 URL 适合用这个提取器?
    任何一个失败都会自动跳到下一个
    """
    for extractor in EXTRACTOR_PRIORITY:
        if not extractor.is_available():
            continue                    # Token 过期? 跳过
        if not extractor.should_try(url):
            continue                    # 无字幕视频? 跳过旧工作流
        result = extractor.extract(url)
        if result.success and result.content:
            return result
    return metadata_only(url)           # 全失败 → 返回元信息
```

---

## 四、数据流 (完整链路)

```
用户 / Agent
    │
    │  1. URL / 文本
    ▼
┌─────────────────────┐
│  Prescreener        │←── learnvalue 轻量规则
│                     │
│  • 标题分析         │
│  • 时长检测         │
│  • SEO识别          │
│  • 成本预估         │
│  • 优先级打分       │
│                     │
│  输出: prescreen.json│
└─────────┬───────────┘
          │
          │  2. 预筛通过？ 
          ├── D/C 级 → 直接返回 prescreen, 不提取
          │
          │  3. B/S/A 级 → 继续
          ▼
┌───────────────────────┐
│  ContentRouter        │←── 遍历优先级列表
│                       │
│  ① 直接API (免费/秒级)│
│  ② Coze旧工作流(免费) │
│  ③ yt-dlp字幕 (免费) │
│  ④ Coze新工作流(付费)│
│  ⑤ Whisper本地(免费) │
│  ⑥ 商业API (付费)    │
│                       │
│  自动跳过不可用/不适配 │
└──────────┬────────────┘
           │
           │  4. 执行提取
           ▼
┌───────────────────────┐
│  Extractor Pool       │
│                       │
│  Direct API → WBI/ies │
│  Coze       → API调用 │
│  yt-dlp     → 字幕/ASR│
│  Whisper    → 本地转录│
│  Commercial → tikhub  │
│                       │
│  一路不通自动跳下一路  │
└──────────┬────────────┘
          │
          │  5. 结构化输出
          ▼
┌─────────────────────┐
│  OutputFormatter    │──→ Hermes content-value-evaluator
│                     │──→ CLI stdout --json
│  统一 JSON Schema   │──→ MCP Server response
└─────────────────────┘
```

---

## 五、文件结构规划 (新增/修改)

```
src/
├── core/                          ★ 新增核心模块
│   ├── __init__.py
│   ├── prescreener.py             ← 内容预筛引擎 (learnvalue light)
│   ├── prescreen_rules.py         ← 规则集: SEO检测/时长/营销
│   ├── extractors/                ← 可插拔提取器
│   │   ├── __init__.py
│   │   ├── base.py                ← 提取器抽象基类
│   │   ├── bilibili_extractor.py  ← WBI 签名, 零 Cookie
│   │   ├── douyin_extractor.py    ← iesdouyin 移动端页面
│   │   ├── xiaohongshu_extractor.py
│   │   ├── youtube_extractor.py
│   │   ├── coze_extractor.py      ← Coze 工作流 (可选, 需 Token)
│   │   ├── ytdlp_extractor.py     ← yt-dlp 字幕/音频
│   │   └── whisper_extractor.py   ← 本地 Whisper ASR
│   ├── router.py                  ← 成本感知路由
│   ├── formatter.py               ← Hermes 兼容输出
│   └── models.py                  ← 数据模型
│
├── mcp/
│   └── server.py                  ← ★ 升级: 新增 prescreen 工具等
│
├── cli.py                         ← ★ 升级: 新增 --prescreen 参数
│
├── services/                      ← 保留, 但可能简化
│
└── gui/                           ← 保留, 降级为可选
```

---

## 六、与竞品的差异化总结

| 维度 | keepongo/v-s | douyin-mcp | social-post-mcp | VideoTranscriptAPI | **VideoMind Bridge v2** |
|------|-------------|------------|-----------------|-------------------|------------------------|
| 预筛引擎 | ❌ | ❌ | ❌ | ❌ | **✅ learnvalue light** |
| 零Cookie提取 | ✅ 3平台 | ✅ 抖音 | ✅ 2平台 | ❌ (需Tikhub Key) | **✅ 4平台** |
| Coze 集成 | ❌ | ❌ | ❌ | ❌ | **✅ 可选, 有Token优先用** |
| 成本感知路由 | ❌ | ❌ | ❌ | ❌ | **✅ 自动选择免费/付费** |
| MCP接口 | ❌ | ✅ | ✅ | ❌ | **✅ (已有, 升级)** |
| Hermes生态 | ❌ | ❌ | ❌ | ❌ | **✅ 原生兼容** |
| 价值评估 | ❌ | ❌ | ❌ | ❌ | **✅ 集成 Hermes skill** |
| 安装复杂度 | pip install | uv run | pip + 百炼Key | Docker | **uv run** |
