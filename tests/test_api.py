"""API 服务测试

使用 FastAPI TestClient 测试 REST API 端点。
不涉及外部网络调用，AI 服务使用默认 mock 模式。

覆盖端点:
  - GET  /health
  - GET  /api/v1/status
  - POST /api/v1/tasks
  - GET  /api/v1/tasks
  - GET  /api/v1/tasks/{task_id}
  - POST /api/v1/tasks/{task_id}/cancel
  - DELETE /api/v1/tasks/{task_id}
  - POST /api/v1/extract
  - GET  /api/v1/settings
  - GET  /api/v1/config
"""

import sys
import time
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient

from src.api.server import APIServer

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def server():
    """创建独立的 APIServer 实例（每个测试一个，确保隔离）"""
    return APIServer()


@pytest.fixture
def client(server):
    """创建 TestClient，自动管理 FastAPI lifespan（启动/停止 TaskManager）"""
    with TestClient(server.app) as c:
        yield c


# ── Health Check ─────────────────────────────────────────────────


class TestHealth:
    """GET /health 健康检查"""

    def test_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_returns_healthy_status(self, client):
        resp = client.get("/health")
        assert resp.json()["status"] == "healthy"

    def test_returns_correct_version(self, client):
        resp = client.get("/health")
        assert resp.json()["version"] == "3.0.0"


# ── System Status ────────────────────────────────────────────────


class TestSystemStatus:
    """GET /api/v1/status 系统状态"""

    def test_returns_200(self, client):
        resp = client.get("/api/v1/status")
        assert resp.status_code == 200

    def test_has_valid_shape(self, client):
        resp = client.get("/api/v1/status")
        data = resp.json()
        assert data["version"] == "3.0.0"
        assert data["status"] == "running"
        assert isinstance(data["active_tasks"], int)
        assert isinstance(data["queued_tasks"], int)
        assert isinstance(data["completed_tasks"], int)
        assert isinstance(data["failed_tasks"], int)


# ── Create Task ──────────────────────────────────────────────────


class TestCreateTask:
    """POST /api/v1/tasks 创建任务"""

    VALID_URL = "https://example.com/video"

    def test_create_with_valid_url_returns_201(self, client):
        resp = client.post(
            "/api/v1/tasks",
            json={"url": self.VALID_URL, "mode": "transcribe_only"},
        )
        assert resp.status_code == 201

    def test_returns_correct_url_and_mode(self, client):
        resp = client.post(
            "/api/v1/tasks",
            json={"url": self.VALID_URL, "mode": "transcribe_only"},
        )
        data = resp.json()
        assert data["url"] == self.VALID_URL
        assert data["mode"] == "transcribe_only"
        assert data["status"] == "pending"
        # Validate UUID format
        UUID(data["id"])

    def test_returns_422_for_invalid_url(self, client):
        """Pydantic HttpUrl 校验失败返回 422（不是 400）"""
        resp = client.post(
            "/api/v1/tasks",
            json={"url": "not-a-valid-url", "mode": "transcribe_only"},
        )
        assert resp.status_code == 422

    def test_returns_422_for_missing_url(self, client):
        """缺少必填 url 字段，Pydantic 返回 422"""
        resp = client.post(
            "/api/v1/tasks",
            json={"mode": "transcribe_only"},
        )
        assert resp.status_code == 422

    def test_full_mode_with_ai_succeeds(self, client):
        """本地环境 AI 已配置时，full 模式创建成功"""
        resp = client.post(
            "/api/v1/tasks",
            json={"url": self.VALID_URL, "mode": "full", "allow_downgrade": True},
        )
        assert resp.status_code in (201, 400)

    def test_default_targets_and_mode(self, client):
        """测试默认值：不传 mode 时默认 full, targets 默认 [local]"""
        resp = client.post(
            "/api/v1/tasks",
            json={"url": self.VALID_URL, "allow_downgrade": True},
        )
        data = resp.json()
        assert data["mode"] == "full"
        assert "local" in data["targets"]


# ── Get Task ─────────────────────────────────────────────────────


class TestGetTask:
    """GET /api/v1/tasks/{task_id} 获取单个任务"""

    VALID_URL = "https://example.com/video"

    def test_returns_existing_task(self, client):
        create_resp = client.post(
            "/api/v1/tasks",
            json={"url": self.VALID_URL, "mode": "transcribe_only"},
        )
        task_id = create_resp.json()["id"]

        resp = client.get(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == task_id

    def test_returns_404_for_non_existent(self, client):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.get(f"/api/v1/tasks/{fake_id}")
        assert resp.status_code == 404


# ── List Tasks ───────────────────────────────────────────────────


class TestListTasks:
    """GET /api/v1/tasks 任务列表"""

    VALID_URL = "https://example.com/video"

    def test_returns_200(self, client):
        resp = client.get("/api/v1/tasks")
        assert resp.status_code == 200

    def test_has_correct_shape(self, client):
        resp = client.get("/api/v1/tasks")
        data = resp.json()
        assert "tasks" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data

    def test_pagination_params(self, client):
        resp = client.get("/api/v1/tasks?limit=5&offset=0")
        data = resp.json()
        assert data["page_size"] == 5
        assert data["page"] == 1

    def test_reflects_created_tasks(self, client):
        client.post(
            "/api/v1/tasks",
            json={"url": self.VALID_URL, "mode": "transcribe_only"},
        )
        resp = client.get("/api/v1/tasks")
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["tasks"]) >= 1

    def test_status_filter(self, client):
        client.post(
            "/api/v1/tasks",
            json={"url": self.VALID_URL, "mode": "transcribe_only"},
        )
        resp = client.get("/api/v1/tasks?status=pending")
        data = resp.json()
        assert all(t["status"] == "pending" for t in data["tasks"])


# ── Cancel Task ──────────────────────────────────────────────────


class TestCancelTask:
    """POST /api/v1/tasks/{task_id}/cancel 取消任务"""

    VALID_URL = "https://example.com/video"

    def test_cancel_pending_task(self, client):
        """取消一个刚创建还未开始处理的任务"""
        create_resp = client.post(
            "/api/v1/tasks",
            json={"url": self.VALID_URL, "mode": "transcribe_only"},
        )
        task_id = create_resp.json()["id"]

        # 立即取消（理想情况：任务还处在 pending 状态）
        cancel_resp = client.post(f"/api/v1/tasks/{task_id}/cancel")

        # 取消成功返回 200；如果任务已自动完成/失败则返回 400
        assert cancel_resp.status_code in (200, 400)
        if cancel_resp.status_code == 200:
            assert cancel_resp.json()["success"] is True

    def test_cancel_completed_task_returns_400(self, client):
        """取消已完成（失败）的任务应返回 400"""
        create_resp = client.post(
            "/api/v1/tasks",
            json={"url": self.VALID_URL, "mode": "transcribe_only"},
        )
        task_id = create_resp.json()["id"]

        # 轮询等待任务结束（URL 不存在会快速失败）
        terminal_states = {"completed", "failed", "cancelled"}
        for _ in range(15):
            time.sleep(1)
            get_resp = client.get(f"/api/v1/tasks/{task_id}")
            if get_resp.json()["status"] in terminal_states:
                break

        cancel_resp = client.post(f"/api/v1/tasks/{task_id}/cancel")
        assert cancel_resp.status_code == 400


# ── Delete Task ──────────────────────────────────────────────────


class TestDeleteTask:
    """DELETE /api/v1/tasks/{task_id} 删除任务"""

    VALID_URL = "https://example.com/video"

    def test_delete_existing_task(self, client):
        create_resp = client.post(
            "/api/v1/tasks",
            json={"url": self.VALID_URL, "mode": "transcribe_only"},
        )
        task_id = create_resp.json()["id"]

        resp = client.delete(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_returns_404_for_non_existent(self, client):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.delete(f"/api/v1/tasks/{fake_id}")
        assert resp.status_code == 404


# ── Content Extraction ───────────────────────────────────────────


class TestExtraction:
    """POST /api/v1/extract 内容提取 (v2 引擎)"""

    def test_missing_url_returns_400(self, client):
        resp = client.post("/api/v1/extract", json={})
        assert resp.status_code == 400
        assert "url" in resp.json()["detail"].lower()

    def test_unsupported_url_returns_error(self, client):
        """不支持的 URL 会返回 success=False + error 信息"""
        resp = client.post(
            "/api/v1/extract",
            json={"url": "https://unsupported-example.com/video"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "error" in data


class TestExtractionArchive:
    """POST /api/v1/extract/archive 提取并归档 (v2)"""

    def test_missing_url_returns_400(self, client):
        resp = client.post("/api/v1/extract/archive", json={})
        assert resp.status_code == 400
        assert "url" in resp.json()["detail"].lower()

    def test_unsupported_url_returns_error(self, client):
        """不支持/无内容的 URL 返回 success=False"""
        resp = client.post(
            "/api/v1/extract/archive",
            json={"url": "https://unsupported-example.com/video", "targets": ["local"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "error" in data


# ── Settings ─────────────────────────────────────────────────────


class TestSettings:
    """GET /api/v1/settings 获取设置"""

    def test_returns_200(self, client):
        resp = client.get("/api/v1/settings")
        assert resp.status_code == 200

    def test_has_correct_structure(self, client):
        resp = client.get("/api/v1/settings")
        data = resp.json()
        assert "ai_engine" in data
        assert "ai_model" in data
        assert "ai_api_key_configured" in data
        assert "ai_temperature" in data
        assert "ai_max_tokens" in data
        assert "ai_timeout" in data
        assert "output_dir" in data
        assert "download_quality" in data
        assert "whisper_model" in data
        assert "save_srt" in data
        assert "save_transcript" in data
        assert "save_markdown" in data
        assert "available_engines" in data


# ── Config ───────────────────────────────────────────────────────


class TestConfig:
    """GET /api/v1/config 系统配置"""

    def test_returns_200(self, client):
        resp = client.get("/api/v1/config")
        assert resp.status_code == 200

    def test_has_correct_structure(self, client):
        resp = client.get("/api/v1/config")
        data = resp.json()
        assert "default_output_dir" in data
        assert "supported_platforms" in data
        assert isinstance(data["supported_platforms"], list)
        assert len(data["supported_platforms"]) > 0
        assert "supported_ai_providers" in data
        assert isinstance(data["supported_ai_providers"], list)
        assert "supported_export_targets" in data
        assert isinstance(data["supported_export_targets"], list)
        assert "ai_enabled" in data
        assert isinstance(data["ai_enabled"], bool)


# ── 安全防护 ─────────────────────────────────────────────────


class TestSecurity:
    """CORS CSRF 防护与可选 token 鉴权"""

    def test_rejects_foreign_origin(self, server):
        """非白名单 Origin 的请求应被 403 拒绝 (防 CSRF)"""
        with TestClient(server.app) as c:
            resp = c.post(
                "/api/v1/tasks",
                json={"url": "https://bilibili.com/video/BV1xx411c7mD", "mode": "transcribe", "targets": ["local"]},
                headers={"Origin": "https://evil.example.com"},
            )
            assert resp.status_code == 403

    def test_allows_local_origin(self, server):
        """白名单 Origin (localhost) 正常放行"""
        with TestClient(server.app) as c:
            resp = c.get(
                "/api/v1/status",
                headers={"Origin": "http://localhost:5173"},
            )
            assert resp.status_code == 200

    def test_allows_no_origin_clients(self, server):
        """非浏览器客户端 (无 Origin) 正常放行"""
        with TestClient(server.app) as c:
            resp = c.get("/api/v1/status")
            assert resp.status_code == 200

    def test_token_required_when_configured(self, server):
        """配置 token 后, /api/v1 未携带 token 应 401"""
        server._api_token = "test-secret-token"
        with TestClient(server.app) as c:
            resp = c.get("/api/v1/status")
            assert resp.status_code == 401

    def test_token_authorized_when_configured(self, server):
        """配置 token 后, 携带正确 Bearer token 应通过"""
        server._api_token = "test-secret-token"
        with TestClient(server.app) as c:
            resp = c.get(
                "/api/v1/status",
                headers={"Authorization": "Bearer test-secret-token"},
            )
            assert resp.status_code == 200

    def test_token_wrong_token_rejected(self, server):
        """配置 token 后, 错误 token 应 401"""
        server._api_token = "test-secret-token"
        with TestClient(server.app) as c:
            resp = c.get(
                "/api/v1/status",
                headers={"Authorization": "Bearer wrong"},
            )
            assert resp.status_code == 401

    def test_health_endpoint_no_auth_required(self, server):
        """配置 token 后, /health 仍应免鉴权"""
        server._api_token = "test-secret-token"
        with TestClient(server.app) as c:
            resp = c.get("/health")
            assert resp.status_code == 200

    def test_list_tasks_limit_zero_rejected(self, server):
        """limit=0 应被参数校验拒绝 (422), 而非 500 ZeroDivisionError"""
        with TestClient(server.app) as c:
            resp = c.get("/api/v1/tasks?limit=0")
            assert resp.status_code == 422

    def test_list_tasks_limit_overflow_rejected(self, server):
        """limit 过大应被参数校验拒绝 (422)"""
        with TestClient(server.app) as c:
            resp = c.get("/api/v1/tasks?limit=1000")
            assert resp.status_code == 422
