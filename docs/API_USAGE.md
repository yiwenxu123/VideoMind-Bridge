# VideoMind Bridge API 使用文档

> 创作者作品列表 / 评论采样接口见 [DISCOVERY_API.md](DISCOVERY_API.md)；默认关闭，需显式开启。

## HTTP API 要点

### 提取：请求级成本上限

`POST /api/v1/extract` 与 `POST /api/v1/extract/archive` 支持 `cost_tier`，表示 Router 可接受的最高提取器成本：

```json
{
  "url": "https://www.bilibili.com/video/BV...",
  "cost_tier": "cheap"
}
```

- 取值：`free` / `cheap` / `paid` / `expensive` / `premium`；默认 `cheap`。
- 只有显式提高 `cost_tier` 才会走到付费兜底提取器；非法值返回 400。
- 同一进程内完整成功结果会短时缓存（默认 600 秒），缓存 key 区分成本与 ASR 选项。

### 登录态状态

- `GET /api/v1/sessions`：列出各平台登录态来源、cookie 数量、最近过期时间和健康状态。
- `POST /api/v1/sessions/bilibili/check`：显式检查 B站登录态；其他平台返回 422。
- 响应只含脱敏信息，永不返回 cookie 值。

配置方式：
- B站：`VMB_BILIBILI_COOKIE` > `VMB_BILIBILI_SESSDATA` > `VMB_BILIBILI_COOKIES_FILE` > `VMB_COOKIES_FILE`。
- 抖音：`DOUYIN_COOKIES_FILE`。
- 小红书：`VMB_XHS_COOKIE` > `VMB_XHS_COOKIES_FILE` > `VMB_COOKIES_FILE`（只取 `xiaohongshu.com` 域）。
- yt-dlp：`VMB_COOKIES_FILE` / `VMB_COOKIES_BROWSER`。

### yt-dlp 网络参数

需要限制 yt-dlp 子进程的请求频率时，可设置：

- `VMB_YTDLP_SLEEP_REQUESTS`：默认按平台（B站 1s、抖音 2s、小红书 1.5s、YouTube 0.5s）。
- `VMB_YTDLP_RETRIES`：默认 3。
- `VMB_YTDLP_EXTRACTOR_RETRIES`：默认 2。
- `VMB_YTDLP_SOCKET_TIMEOUT`：默认 30 秒。
- `VMB_YTDLP_SLEEP_INTERVAL`：默认 0（不额外等待）。

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
