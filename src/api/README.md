# VideoMind Bridge API 服务

本地API服务，提供REST API和WebSocket接口，支持外部工具集成。

## 快速开始

### 启动API服务器

```bash
# 默认启动 (127.0.0.1:8787)
python -m src.api

# 指定主机和端口
python -m src.api --host 0.0.0.0 --port 8080
```

### API文档

启动服务器后，访问自动生成的API文档：
- Swagger UI: http://127.0.0.1:8787/docs
- ReDoc: http://127.0.0.1:8787/redoc

## API端点

### 系统状态

```http
GET /api/v1/status
```

返回系统状态统计信息：

```json
{
  "version": "1.0.0",
  "status": "running",
  "active_tasks": 2,
  "queued_tasks": 1,
  "completed_tasks": 10,
  "failed_tasks": 0
}
```

### 系统配置

```http
GET /api/v1/config
```

返回系统配置信息：

```json
{
  "default_output_dir": "/Users/username/.VideoMind/output",
  "supported_platforms": ["bilibili", "youtube", "douyin", "xiaohongshu"],
  "supported_ai_providers": ["deepseek", "openai", "anthropic"],
  "supported_export_targets": ["local", "obsidian", "notion"]
}
```

### 创建任务

```http
POST /api/v1/tasks
Content-Type: application/json

{
  "url": "https://www.bilibili.com/video/BV1xx411c7mD",
  "mode": "full",
  "targets": ["local", "obsidian"],
  "ai_provider": "deepseek"
}
```

响应：

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "url": "https://www.bilibili.com/video/BV1xx411c7mD",
  "status": "pending",
  "mode": "full",
  "targets": ["local", "obsidian"],
  "progress": 0.0,
  "current_step": "等待中",
  "title": "视频标题",
  "author": "UP主名称",
  "platform": "bilibili",
  "created_at": "2026-02-02T10:00:00",
  "updated_at": "2026-02-02T10:00:00"
}
```

### 获取任务列表

```http
GET /api/v1/tasks?status=processing&limit=20&offset=0
```

### 获取单个任务

```http
GET /api/v1/tasks/{task_id}
```

### 取消任务

```http
POST /api/v1/tasks/{task_id}/cancel
```

### 删除任务

```http
DELETE /api/v1/tasks/{task_id}
```

## WebSocket 实时进度

连接WebSocket以接收实时任务进度更新：

```javascript
const ws = new WebSocket('ws://127.0.0.1:8787/ws');

ws.onopen = () => {
  console.log('WebSocket连接已建立');

  // 订阅特定任务的进度更新
  ws.send(JSON.stringify({
    action: 'subscribe',
    task_id: '550e8400-e29b-41d4-a716-446655440000'
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('进度更新:', data);
  // {
  //   "task_id": "550e8400-e29b-41d4-a716-446655440000",
  //   "status": "downloading",
  //   "progress": 35.5,
  //   "current_step": "正在下载视频...",
  //   "message": "已下载 35MB / 100MB",
  //   "timestamp": "2026-02-02T10:01:30"
  // }
};

ws.onclose = () => {
  console.log('WebSocket连接已关闭');
};
```

## 使用示例

### cURL 示例

```bash
# 创建任务
curl -X POST http://127.0.0.1:8787/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.bilibili.com/video/BV1xx411c7mD",
    "mode": "full",
    "targets": ["local"]
  }'

# 获取任务列表
curl http://127.0.0.1:8787/api/v1/tasks

# 获取单个任务
curl http://127.0.0.1:8787/api/v1/tasks/{task_id}

# 取消任务
curl -X POST http://127.0.0.1:8787/api/v1/tasks/{task_id}/cancel

# 删除任务
curl -X DELETE http://127.0.0.1:8787/api/v1/tasks/{task_id}
```

### Python 示例

```python
import httpx
import asyncio

async def main():
    async with httpx.AsyncClient() as client:
        # 创建任务
        response = await client.post(
            "http://127.0.0.1:8787/api/v1/tasks",
            json={
                "url": "https://www.bilibili.com/video/BV1xx411c7mD",
                "mode": "full",
                "targets": ["local"]
            }
        )
        task = response.json()
        print(f"任务已创建: {task['id']}")

        # 获取任务状态
        response = await client.get(
            f"http://127.0.0.1:8787/api/v1/tasks/{task['id']}"
        )
        print(f"任务状态: {response.json()}")

asyncio.run(main())
```

## 应用场景

### 1. Alfred Workflow

创建Alfred Workflow，通过快捷键快速提交视频链接进行处理：

```bash
# Alfred Workflow 脚本
curl -X POST http://127.0.0.1:8787/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"{query}\", \"mode\": \"full\"}"
```

### 2. 浏览器扩展

开发浏览器扩展，在视频页面添加"处理此视频"按钮，调用API服务。

### 3. 命令行工具

创建CLI工具批量处理视频：

```bash
# videomind-cli
videomind process https://www.bilibili.com/video/BV1xx411c7mD
```

### 4. 自动化脚本

配合定时任务，自动处理收藏夹中的视频。

## 数据模型

### ProcessingMode (处理模式)

- `full`: 完整处理（下载 → 转录 → AI摘要 → 导出）
- `download_only`: 仅下载
- `transcribe_only`: 下载并转录，不生成AI摘要

### ExportTarget (导出目标)

- `local`: 本地文件
- `obsidian`: Obsidian笔记
- `notion`: Notion页面

### TaskStatus (任务状态)

- `pending`: 等待中
- `downloading`: 下载中
- `transcribing`: 转录中
- `ai_processing`: AI处理中
- `exporting`: 导出中
- `completed`: 已完成
- `failed`: 失败
- `cancelled`: 已取消
