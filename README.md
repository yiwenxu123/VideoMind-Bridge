# VideoMind Bridge

智能视频处理工具，支持下载、转录、AI 摘要和导出。

## 功能特性

- **视频下载**：支持 Bilibili、YouTube、抖音、小红书等平台
- **语音转录**：自动生成字幕和时间轴
- **AI 摘要**：使用 DeepSeek 等国内模型生成智能摘要
- **多格式导出**：支持 Obsidian、本地文件夹、HTML 播放器
- **任务管理**：队列管理、暂停、恢复、历史记录
- **系统托盘**：最小化到托盘，任务完成通知
- **本地 API 服务**：提供 REST API 和 WebSocket，支持浏览器扩展集成
- **浏览器扩展**：支持 Chrome、Edge、Firefox，一键提交视频处理任务

## 安装

### 环境要求

- Python 3.11+
- macOS / Windows / Linux

### 安装步骤

```bash
# 克隆仓库
git clone <repository-url>
cd VideoMindBridge

# 使用 uv 安装依赖
uv sync

# 或使用 pip
pip install -r requirements.txt
```

## 使用

### GUI 模式

```bash
# 方式一：使用 main.py 入口（推荐）
python main.py

# 方式二：使用虚拟环境直接运行
.venv/bin/python3 -m src.gui.app
```

### API 服务模式

```bash
# 方式一：使用 main.py 入口（推荐）
python main.py --api

# 方式二：指定端口
python main.py --api --port 9000

# 方式三：直接运行模块
.venv/bin/python3 -m src.api

# API 服务运行于 http://127.0.0.1:8787
# 文档地址：http://127.0.0.1:8787/docs
```

API 服务提供以下功能：
- 创建、查询、取消视频处理任务
- WebSocket 实时推送任务进度
- 支持浏览器扩展集成
- 共享 GUI 配置的 AI 服务

## 浏览器扩展

### 安装方式

**Chrome / Edge（Chromium 内核）**：

1. 打开浏览器，地址栏输入 `chrome://extensions/` 或 `edge://extensions/`
2. 开启右上角的「开发者模式」
3. 点击「加载已解压的扩展程序」
4. 选择 `browser-extension` 文件夹

**Firefox**：

1. 打开浏览器，地址栏输入 `about:debugging`
2. 点击「此 Firefox」
3. 点击「临时载入附加组件」
4. 选择 `browser-extension/manifest.json`

### 使用方法

1. 安装扩展后，访问任意支持的视频页面
2. 点击浏览器工具栏中的扩展图标
3. 选择处理模式（完整模式、仅下载、仅转录）
4. 点击「开始处理」提交任务
5. 实时查看处理进度和结果

### 功能特性

- 视频页面自动检测
- 一键提交处理任务
- 三种处理模式可选
- WebSocket 实时进度更新
- 与 GUI 共享任务历史

## 配置

首次启动时会自动创建配置文件 `~/.config/VideoMind/config.yaml`。

### AI 引擎配置

支持以下模型：
- DeepSeek（deepseek-chat）
- 智谱 AI（glm-4）
- Moonshot（moonshot-v1-8k）
- MiniMax
- 豆包
- Ollama（本地）
- OpenAI（GPT-4o、GPT-4）
- Anthropic（Claude 3.5）

### 导出配置

- **Obsidian**：设置 Vault 路径和子文件夹
- **本地文件夹**：设置输出目录和组织方式

## 开发

### 项目结构

```
src/
├── api/                  # API 服务（FastAPI + WebSocket）
│   ├── __main__.py       # 服务入口
│   ├── server.py         # API 服务器
│   ├── task_manager.py   # 任务管理器
│   └── models.py         # 数据模型
├── config/               # 配置常量
│   └── constants.py      # 常量定义
├── gui/                  # GUI 界面
│   ├── app.py            # 应用入口
│   ├── main_window.py    # 主窗口
│   ├── components/       # GUI 组件
│   │   ├── menu_manager.py
│   │   └── tray_manager.py
│   ├── widgets/          # GUI 控件
│   │   ├── ai_config.py
│   │   ├── mode_selector.py
│   │   ├── settings_dialog.py
│   │   ├── task_history_sidebar.py
│   │   ├── task_queue.py
│   │   └── url_input.py
│   └── workers/          # 后台工作者
│       └── processing_worker.py
├── exporters/            # 导出器
│   ├── base.py
│   ├── html_player_exporter.py
│   ├── local_exporter.py
│   └── obsidian_exporter.py
├── models/               # 数据模型
│   ├── config.py
│   └── task.py
├── services/             # 核心服务
│   ├── ai_service.py
│   ├── config_manager.py
│   ├── download_service.py
│   ├── duplicate_detector.py
│   ├── export_orchestrator.py
│   ├── task_database.py
│   └── transcribe_service.py
├── ui/                   # UI 资源
└── utils/                # 工具函数
    ├── config.py
    ├── credential_manager.py
    ├── file_utils.py
    ├── logger.py
    ├── media_utils.py
    ├── platform_utils.py
    └── retry.py

browser-extension/        # 浏览器扩展
├── manifest.json         # 扩展清单
├── background.js         # 背景脚本
├── content.js            # 内容脚本
├── content.css           # 样式
├── popup.html            # 弹窗页面
└── popup.js              # 弹窗脚本

tests/                    # 测试文件
└── test_ai_service.py    # AI 服务测试
```

### 运行测试

```bash
# 安装测试依赖
pip install -e ".[dev]"

# 运行所有测试
pytest tests/ -v

# 运行测试并查看覆盖率
pytest tests/ -v --cov=src --cov-report=term-missing
```

## 版本历史

### v1.0.0（2026-02-02）

- 初始版本发布
- 支持视频下载、转录、AI 摘要
- 支持多种导出格式
- 实现任务队列和历史记录
- 系统托盘支持
- 自动重试机制
- 新增本地 API 服务
- 新增浏览器扩展支持

## 许可证

MIT License
