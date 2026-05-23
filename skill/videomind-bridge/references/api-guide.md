# API 服务使用指南

VideoMind Bridge 提供 FastAPI + WebSocket 的 API 服务模式，适合需要异步处理或集成的场景。

## 启动 API 服务

```bash
cd ~/.local/share/videomind-bridge
uv run python main.py --api --port 8787
```

## REST API 端点

### 系统信息

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | API 信息 |
| GET | `/health` | 健康检查 |
| GET | `/api/v1/status` | 系统状态（活跃/排队/完成/失败任务数） |
| GET | `/api/v1/config` | 系统配置（支持的平台、AI提供商等） |

### 任务管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/tasks` | 创建处理任务 |
| GET | `/api/v1/tasks` | 任务列表（支持分页和状态筛选） |
| GET | `/api/v1/tasks/{id}` | 任务详情 |
| POST | `/api/v1/tasks/{id}/cancel` | 取消任务 |
| DELETE | `/api/v1/tasks/{id}` | 删除任务 |

### 创建任务示例

```bash
curl -X POST http://127.0.0.1:8787/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.bilibili.com/video/BV1xx411c7mD",
    "mode": "full",
    "targets": ["local"],
    "ai_provider": "deepseek"
  }'
```

### 响应格式

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "url": "https://www.bilibili.com/video/BV1xx411c7mD",
  "status": "processing",
  "mode": "full",
  "targets": ["local"],
  "progress": 45.5,
  "current_step": "正在生成AI摘要...",
  "title": "视频标题",
  "author": "UP主",
  "platform": "bilibili"
}
```

## WebSocket 实时进度

连接 `ws://127.0.0.1:8787/ws`，发送订阅消息：

```json
{"action": "subscribe", "task_id": "任务ID"}
```

接收进度更新：

```json
{
  "task_id": "任务ID",
  "status": "downloading",
  "progress": 35.0,
  "current_step": "正在下载视频...",
  "message": "已下载 35MB / 100MB"
}
```

## Agent 使用 API 的典型流程

1. 启动 API 服务（后台运行）
2. POST 创建任务，获取 task_id
3. 轮询 GET `/api/v1/tasks/{id}` 或 WebSocket 订阅进度
4. 任务完成后读取结果

**注意**: CLI 模式（`--json`）通常更适合 Agent 一次性任务，API 模式适合需要管理多个任务的场景。
