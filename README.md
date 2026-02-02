# VideoMind Bridge

智能视频处理工具，支持下载、转录、AI 摘要和导出。

## 功能特性

- **视频下载**: 支持 Bilibili、YouTube、抖音、小红书等平台
- **语音转录**: 自动生成字幕和时间轴
- **AI 摘要**: 使用 DeepSeek 等国内模型生成智能摘要
- **多格式导出**: 支持 Obsidian、本地文件夹、HTML 播放器
- **任务管理**: 队列管理、暂停/恢复、历史记录
- **系统托盘**: 最小化到托盘，任务完成通知

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
uv run python3 -m src.gui.app
```

### CLI 模式

```bash
# 处理单个视频
uv run python3 -m src.cli process <URL> --mode full

# 查看帮助
uv run python3 -m src.cli --help
```

## 配置

首次启动时会自动创建配置文件 `~/.config/VideoMind/config.yaml`。

### AI 引擎配置

支持以下国内模型：
- DeepSeek (deepseek-chat)
- 智谱 AI (glm-4)
- Moonshot (moonshot-v1-8k)
- MiniMax
- 豆包
- Ollama (本地)

### 导出配置

- **Obsidian**: 设置 Vault 路径和子文件夹
- **本地文件夹**: 设置输出目录和组织方式

## 开发

### 项目结构

```
src/
├── gui/           # GUI 界面
├── services/      # 核心服务
├── exporters/     # 导出器
├── models/        # 数据模型
└── utils/         # 工具函数
```

### 运行测试

```bash
uv run python3 tests/test_ai_service.py
```

## 版本历史

### v1.0.0 (2025-02-02)

- 初始版本发布
- 支持视频下载、转录、AI 摘要
- 支持多种导出格式
- 实现任务队列和历史记录
- 系统托盘支持
- 自动重试机制

## 许可证

MIT License
