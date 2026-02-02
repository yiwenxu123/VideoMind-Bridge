---

# 产品需求文档 (PRD) - v1.0

**项目名称**：VideoMind Bridge (视频知识处理工作站)  
**版本**：v1.0  
**文档状态**：终稿  
**目标**：构建单用户桌面级视频知识处理 All-in-One 工具，实现"采集→解析→理解→归档→分发"一体化，具备强扩展性。

---

## 1. 产品概述

### 1.1 核心定位
一个**绿色免安装的桌面级视频处理工作站**，用户通过**单一界面**完成视频下载、语音转录、AI 摘要生成，并可按需求选择**输出到多个目标**（Obsidian/本地/Notion 等）。支持**三种处理深度**（完整处理/仅下载/仅转录），通过**可视化卡片**一键切换。

### 1.2 用户场景
- **场景 A（完整学习）**：看到 B站教程 → 粘贴链接 → 选择"完整处理" → 5 分钟后在 Obsidian 看到带时间轴的 AI 笔记，同时本地文件夹保存原始 MP4 备份
- **场景 B（素材收藏）**：发现优质访谈 → 选择"仅下载" → AI 区域自动隐藏 → 仅获取原始视频到本地
- **场景 C（字幕提取）**：需要某视频字幕 → 选择"转录存档" → 仅生成 SRT 文件，不调 LLM API 节省成本

---

## 2. 核心功能需求 (Functional Requirements)

### 2.1 多渠道视频采集
- **FR-001.1**：主输入框支持粘贴单个 URL（自动识别剪贴板内容，含有 URL 时自动填入）
- **FR-001.2**：支持批量模式（换行分隔多个链接），队列化处理，可配置并发数
- **FR-001.3**：支持主流平台（Bilibili、YouTube、小红书、小宇宙、Twitter/X 等 yt-dlp 支持站点）
- **FR-001.4**：[扩展] 预留本地 HTTP API 接口（端口 59696），供 Alfred/Raycast/浏览器插件远程推送链接

### 2.2 三级处理模式（核心交互）
**必须通过卡片式单选组件呈现，视觉上明确区分**：

| 模式 | 图标 | 说明 | 后续流程 |
|------|------|------|----------|
| **Mode A: 完整处理** | 🧠 | 下载→转录→AI摘要→生成笔记 | 执行完整 pipeline |
| **Mode B: 仅下载** | 💾 | 仅下载原始视频+音频 | 跳过转录和 AI，直接保存文件 |
| **Mode C: 转录存档** | 📝 | 下载→生成 SRT 字幕文件 | 执行转录，但不调 LLM API |

**交互逻辑**：
- **动态 UI**：选择"仅下载"时，**AI 引擎配置区域自动折叠/隐藏**，输出目标自动取消"Obsidian"勾选（因为没有笔记生成），仅保留"本地文件夹"
- **模式记忆**：记住用户上次选择，下次启动时恢复

### 2.3 灵活 AI 配置中心
- **FR-003.1**：支持多厂商 LLM 配置（OpenAI、DeepSeek、Anthropic、Azure、本地 Ollama）
- **FR-003.2**：处理时可实时切换模型（下拉选择），支持为不同模型配置独立 API Key
- **FR-003.3**：Prompt 模板外置化（YAML/JSON 格式），支持变量注入：
  - `{{title}}` - 视频标题
  - `{{transcript}}` - 转录文本（自动截断至模型上下文长度）
  - `{{url}}` - 原始链接
  - `{{duration}}` - 视频时长
- **FR-003.4**：内置预设角色（学术总结/速览/提取行动项/翻译），用户可自定义新增

### 2.4 多输出目标支持（关键扩展性设计）
**必须支持多选（Checkbox），允许多处同时归档**：

- **Target A: Obsidian** (内置)
  - 可配置 Vault 路径和子文件夹（如 `Inbox/Videos/`）
  - 生成标准 Markdown，包含 YAML Frontmatter（title、source、date、tags、ai_model）
  - 支持模板自定义（Jinja2 语法），支持 [[双链]] 语法自动提取
  
- **Target B: 本地文件夹** (内置)
  - 保存原始视频、音频、SRT、Markdown 到用户指定目录
  - 自动按日期或视频标题创建子文件夹结构
  
- **Target C: Notion** (插件化)
  - 通过 Notion API 创建 Page，将 Markdown 转换为 Notion Blocks
  - 支持配置 Database ID，自动填充属性字段
  
- **Target D: 自定义 Webhook** (扩展接口)
  - POST 结构化 JSON 到用户指定的 HTTP Endpoint，供对接 Zapier/Make 等平台

**并发写入**：各目标独立执行，一个失败不影响其他（失败时标记状态，支持重试）。

### 2.5 本地处理引擎
- **FR-005.1**：视频下载使用 yt-dlp 核心（Python 库调用），显示实时速度（MB/s）和进度百分比
- **FR-005.2**：语音转录使用 faster-whisper（支持 GPU 加速），模型可选（tiny/base/small/medium），本地离线运行
- **FR-005.3**：音频预处理：自动提取音轨、标准化比特率、超长视频自动分段（避免显存不足）
- **FR-005.4**：支持断点续传（下载中断后可恢复）

### 2.6 任务队列与状态管理
- **FR-006.1**：可视化任务队列（ListView），显示：
  - 视频标题（缩略图）
  - 当前步骤（下载中/转录中/AI思考中/已完成）
  - 进度条（百分比）
  - 操作按钮（取消/删除/重试）
- **FR-006.2**：支持任务暂停/恢复/彻底删除
- **FR-006.3**：系统托盘常驻，后台处理时显示迷你进度图标

---

## 3. 用户界面与交互 (UI/UX)

### 3.1 主界面布局（基于线框图）

```
┌──────────────────────────────────────────────────────────────┐
│ [Logo] VideoMind Bridge v1.0                        [_][口][X]│
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  📥 视频源 URL                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ https://www.bilibili.com/video/...    [粘贴] [+ 批量]  │ │
│  └────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────┤
│  ⚙️ 处理模式（单选卡片）                                      │
│  ┌──────────────┬──────────────┬──────────────┐             │
│  │ [◉] 🧠       │ [○] 💾       │ [○] 📝       │             │
│  │   完整处理   │   仅下载     │   转录存档   │             │
│  │   AI摘要生成 │   原始视频   │   生成SRT    │             │
│  └──────────────┴──────────────┴──────────────┘             │
├──────────────────────────────────────────────────────────────┤
│  🤖 AI 引擎配置（仅 Mode A 显示，Mode B 隐藏，Mode C 禁用）  │
│  └─ 引擎: [DeepSeek-V3 ▼]  [⚙️ 配置 Prompt]                  │
├──────────────────────────────────────────────────────────────┤
│  📤 输出目标（可多选）                                        │
│  ┌──────────────┬──────────────┬──────────────┐             │
│  │ ☑️ Obsidian  │ ☑️ 本地文件  │ ☐ Notion     │             │
│  │   Vault/Inbox│   /Downloads │   (需配置)   │             │
│  └──────────────┴──────────────┴──────────────┘             │
├──────────────────────────────────────────────────────────────┤
│  📋 任务队列 (2 个待处理)                                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ ▶️ 知识管理方法论...       [转录中 45%]        [取消] │ │
│  │ ⏸️ Python入门...            [等待中]          [🗑️]  │ │
│  └────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────┤
│  ▶ 开始处理          📂 打开Obsidian           ⏷ 最小化托盘 │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 关键交互细节

**动态界面规则**：
1. **选择 Mode B (仅下载)**：
   - AI 引擎区域**隐藏**（节省空间）
   - 输出目标自动**取消勾选** Obsidian/Notion（仅保留本地文件夹可选）
   
2. **选择 Mode C (转录存档)**：
   - AI 引擎区域**显示但禁用**（不调用 API，仅做转录）
   - 提示文本："此模式仅生成字幕，不消耗 AI Token"

3. **输出目标多选逻辑**：
   - 勾选 Notion 但未配置 Token 时，显示红色提示"点击配置 API"
   - 每个目标可点击展开详细设置（如 Obsidian 的子文件夹路径）

### 3.3 配置对话框 (Settings Dialog)
四标签页设计：
- **通用**：下载路径、并发数、是否保留原始视频、系统启动项
- **AI 引擎**：表格管理多厂商 Key（支持加密存储）
- **输出模板**：Monaco Editor 编辑 Markdown/Jinja2 模板，实时预览
- **插件管理**：安装/manage Notion/Logseq 等扩展插件

---

## 4. 技术架构 (Technical Architecture)

### 4.1 推荐技术栈
- **框架**：Python 3.10+ + PySide6 (Qt6)
- **下载**：yt-dlp (Python 库)
- **转录**：faster-whisper (支持 CTranslate2 加速)
- **HTTP**：httpx (异步调用 LLM API)
- **打包**：PyInstaller (单文件 exe) 或 Nuitka (编译加速)

### 4.2 核心架构分层

```python
# 分层架构确保可扩展性
├─ UI Layer (PySide6)
│   ├─ MainWindow (主界面，含动态显隐逻辑)
│   ├─ ModeSelector (处理模式卡片组件)
│   ├─ TargetSelector (多选输出目标组件)
│   └─ TaskQueueWidget (任务队列可视化)
│
├─ Application Layer (Services)
│   ├─ DownloadService (yt-dlp 封装，带进度回调)
│   ├─ TranscriptionService (faster-whisper 封装)
│   ├─ AIService (多厂商 LLM 适配器，支持 Failover)
│   └─ ExportOrchestrator (导出编排器，并发管理多目标)
│
├─ Domain Layer (Models)
│   ├─ VideoTask (任务实体：url/mode/targets/status)
│   ├─ ProcessingMode (Enum: FULL/DOWNLOAD/TRANSCRIBE)
│   └─ ExportTarget (Enum: OBSIDIAN/LOCAL/NOTION/WEBHOOK)
│
└─ Infrastructure Layer
    ├─ Exporter Plugins (插件目录)
    │   ├─ obsidian_exporter.py (内置)
    │   ├─ local_exporter.py (内置)
    │   ├─ notion_exporter.py (插件)
    │   └─ webhook_exporter.py (插件)
    ├─ ConfigManager (YAML 配置持久化)
    ├─ KeychainManager (API Key 加密存储)
    └─ APIServer (可选启动的本地 HTTP 服务，供外部调用)
```

### 4.3 Exporter 插件接口规范
所有输出目标必须实现：

```python
class BaseExporter(ABC):
    name: str  # 显示名称
    icon: str  # Emoji 图标
    
    @abstractmethod
    def validate_config(self) -> tuple[bool, str]:
        """检查配置是否有效，返回 (是否可用, 错误信息)"""
        pass
    
    @abstractmethod
    def export(self, context: ExportContext) -> ExportResult:
        """
        context 包含:
        - video_path: 本地视频路径
        - audio_path: 音频路径
        - transcript: 转录文本
        - ai_summary: AI 生成的摘要
        - metadata: 标题/作者/URL/时长等
        """
        pass
```

---

## 5. 数据与配置 (Configuration)

**配置文件**：`~/.config/VideoMind/config.yaml`

```yaml
app:
  theme: "system"  # light/dark/system
  auto_start: false
  minimize_to_tray: true
  
processing:
  default_mode: "full"  # full/download/transcribe
  concurrent_downloads: 2
  concurrent_ai: 1
  whisper_model: "small"  # tiny/base/small/medium
  keep_original_video: true  # 是否保留下载的视频文件
  
ai_providers:
  - name: "DeepSeek-V3"
    type: "openai_compatible"
    base_url: "https://api.deepseek.com/v1"
    api_key: "sk-..."  # 实际存储经加密
    model: "deepseek-chat"
    default_prompt: "academic_summary"
    
  - name: "Claude-3.5"
    type: "anthropic"
    api_key: "sk-ant-..."
    model: "claude-3-5-sonnet-20241022"

prompts:
  academic_summary: "请总结以下学术内容..."
  quick_overview: "三句话概括要点..."
  
export_targets:
  obsidian:
    enabled: true
    vault_path: "/Users/xxx/Documents/Obsidian"
    subfolder: "Inbox/Videos"
    template: "templates/video_note.md"
    
  local:
    enabled: true
    output_path: "~/Downloads/VideoMind"
    organize_by: "date"  # date/title
    
  notion:
    enabled: false
    token: "secret_..."  # 加密存储
    database_id: "..."
```

---

## 6. 非功能需求 (Non-Functional Requirements)

### 6.1 离线优先 (Offline First)
- 除 AI 总结环节外（必须联网），下载和转录必须支持完全离线运行
- 网络中断时，本地队列保留，恢复后自动重试（指数退避）

### 6.2 容错与恢复 (Resilience)
- **分级错误处理**：
  - 下载失败（网络错误）：自动重试 3 次，失败后标记为"失败"但不阻塞其他任务
  - AI 失败（API 限流/故障）：自动切换到备用模型（DeepSeek → Claude），都失败则保留转录文本供用户手动处理
  - 导出失败（如 Notion 网络错误）：标记为"待重试"，本地保存已成功，不阻塞流程
- **临时文件管理**：应用崩溃或取消时，自动清理未完成下载的临时文件

### 6.3 性能指标
- **启动时间**：冷启动 < 3 秒（Windows 10/i5 级别）
- **内存占用**：常规运行 < 300MB，转录时峰值 < 1GB（medium 模型）
- **UI 响应**：所有耗时操作（下载/转录/AI）必须异步，界面不卡顿，实时进度更新

### 6.4 隐私与安全
- **零遥测**：不上传任何使用数据
- **API Key 加密**：使用系统 Keyring（Windows Credential / macOS Keychain / Linux Secret Service）存储，配置文件仅存储加密后的 token
- **本地优先**：转录完全本地进行，原始视频保存在用户指定位置，不上传至任何云服务（除非用户选择导出到 Notion）

---

## 7. 扩展性设计 (Extensibility)

### 7.1 本地 HTTP API 服务（可选启动）
监听 `localhost:59696`，供外部工具调用：

```bash
# 示例：从 Alfred/Raycast 推送链接
POST /api/process
Content-Type: application/json

{
  "url": "https://bilibili.com/...",
  "mode": "full",
  "targets": ["obsidian", "local"],
  "ai_model": "deepseek-chat"
}

# 返回: { "task_id": "uuid", "status": "queued" }

# WebSocket 实时进度
WS /api/stream/{task_id}
```

### 7.2 浏览器扩展配套（未来）
开发 Chrome/Edge 插件，右键菜单"发送到 VideoMind"，调用本地 API 实现一键收藏。

### 7.3 插件市场（远期）
支持从 GitHub URL 安装社区插件（如飞书导出、钉钉机器人推送等）。

---

## 8. 验收标准 (Acceptance Criteria)

1. **场景验证**：用户复制 B站链接 → 粘贴 → 选择"完整处理" → 勾选"Obsidian + 本地" → 点击开始 → 5 分钟后在 Obsidian 看到带 AI 摘要的笔记，同时本地文件夹存在 MP4 和 SRT 文件
2. **模式切换验证**：选择"仅下载"模式后，AI 配置区域自动隐藏，处理完成后仅本地有文件，无笔记生成
3. **多目标验证**：同时勾选 Obsidian 和 Notion，断网导致 Notion 失败时，Obsidian 保存成功，Notion 显示"待重试"状态
4. **容错验证**：处理 10 个视频队列时，第 5 个视频下载失败，其余 9 个继续处理，失败项可单独重试
5. **扩展验证**：按照文档实现的 `notion_exporter.py` 放入 plugins 目录，重启后在输出目标中可见 Notion 选项

---

## 9. 交付物要求 (Deliverables)

1. **应用程序**：单文件可执行程序（Windows: `.exe`, macOS: `.app`, Linux: `AppImage`）
2. **配置文件示例**：`config.example.yaml`（包含注释说明）
3. **Prompt 模板库**：内置 5 个常用模板（学术/速览/行动项/翻译/问答）
4. **开发文档**：README 包含如何编写自定义 Exporter 插件的接口说明

---

