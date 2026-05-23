# VideoMind Bridge API 使用文档

## 快速开始

### 1. 下载视频

```python
from src.services.download_service import DownloadService
from pathlib import Path

# 创建下载服务
download_service = DownloadService(output_dir=Path("./output"))

# 下载视频
result = download_service.download(
    url="https://www.bilibili.com/video/BV1xx411c7mD",
    download_video=True,
    video_quality="1080p"
)

print(f"视频路径: {result.video_path}")
print(f"音频路径: {result.audio_path}")
print(f"标题: {result.metadata.title}")
```

### 2. 语音转录

```python
from src.services.transcribe_service import TranscribeService

# 创建转录服务（使用 small 模型）
transcribe_service = TranscribeService(model_size="small")

# 转录音频
result = transcribe_service.transcribe(
    audio_path=result.audio_path,
    language="zh"
)

print(f"语言: {result.language}")
print(f"转录文本: {result.full_text[:200]}...")
```

### 3. AI 摘要生成

```python
from src.services.ai_service import AIService

# 创建 AI 服务
ai_service = AIService(
    engine="deepseek",
    model="deepseek-chat",
    api_key="your-api-key"
)

# 生成摘要
summary = ai_service.summarize(
    transcript=result.full_text,
    title="视频标题"
)

print(f"摘要: {summary.summary}")
print(f"要点数量: {len(summary.highlights)}")
```

### 4. 导出到 Obsidian

```python
from src.exporters.obsidian_exporter import ObsidianExporter
from src.models.task import ExportContext
from uuid import uuid4

# 创建导出器
exporter = ObsidianExporter(
    vault_path=Path("/path/to/vault"),
    subfolder="Inbox/Videos"
)

# 构建导出上下文
context = ExportContext(
    task_id=uuid4(),
    video_metadata=result.metadata,
    transcript_segments=transcript_result.segments,
    transcript_text=transcript_result.full_text,
    ai_summary=summary.summary
)

# 执行导出
export_result = exporter.export(context)

if export_result.success:
    print(f"导出成功: {export_result.output_path}")
```

## 配置管理

```python
from src.services.config_manager import get_config_manager

# 获取配置管理器
config_manager = get_config_manager()

# 读取配置
api_key = config_manager.get_api_key()
output_dir = config_manager.config.download.output_dir

# 修改配置
config_manager.config.ai.model = "deepseek-chat"
config_manager.save_config()
```

## 批量处理

```python
from src.services.export_orchestrator import ExportOrchestrator
from src.models.task import ExportTarget

# 创建导出编排器
orchestrator = ExportOrchestrator(
    targets=[ExportTarget.LOCAL, ExportTarget.OBSIDIAN],
    config={
        "local_output_path": Path("./output"),
        "obsidian_vault_path": Path("/path/to/vault")
    }
)

# 批量导出
results = orchestrator.export_all(context)

for result in results:
    print(f"{result.target.value}: {'成功' if result.success else '失败'}")
```

## 错误处理

```python
from src.utils.exceptions import DownloadError, TranscribeError, AIError

try:
    result = download_service.download(url)
except DownloadError as e:
    if e.error_code == "VIDEO_NOT_FOUND":
        print("视频不存在")
    elif e.error_code == "AGE_RESTRICTED":
        print("视频有年龄限制")
    else:
        print(f"下载失败: {e}")
```
