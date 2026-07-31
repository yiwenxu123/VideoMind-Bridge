"""WebhookExporter 测试"""
import json
from unittest import mock
from uuid import uuid4

import httpx
import pytest

from src.exporters.webhook_exporter import WebhookExporter
from src.models.task import ExportContext, ExportTarget, TranscriptSegment, VideoMetadata


@pytest.fixture
def sample_context():
    return ExportContext(
        task_id=uuid4(),
        video_metadata=VideoMetadata(
            title="测试标题", author="UP主", duration=180,
            platform="bilibili", url="https://test.com/video",
        ),
        transcript_segments=[
            TranscriptSegment(start=0, end=5, text="第一句", confidence=0.95),
            TranscriptSegment(start=5, end=10, text="第二句", confidence=0.90),
        ],
        transcript_text="[00:00:00] 第一句\n[00:00:05] 第二句",
        ai_summary="测试摘要",
        config={"highlights": [{"time": "00:01:30", "seconds": 90, "content": "亮点"}],
                "prompt_template_id": "v2", "processing_mode": "smart"},
        video_path=None, audio_path=None, transcript_path=None,
    )


class TestValidateConfig:
    def test_empty_url(self):
        exporter = WebhookExporter(url="")
        valid, msg = exporter.validate_config()
        assert not valid
        assert "未配置" in msg

    def test_invalid_scheme(self):
        exporter = WebhookExporter(url="ftp://example.com/hook")
        valid, msg = exporter.validate_config()
        assert not valid
        assert "http" in msg

    def test_valid_url(self):
        exporter = WebhookExporter(url="https://hooks.example.com/notify")
        valid, msg = exporter.validate_config()
        assert valid
        assert msg == ""


class TestExport:
    def test_export_validate_fails(self, sample_context):
        exporter = WebhookExporter(url="")
        result = exporter.export(sample_context)
        assert not result.success
        assert result.target == ExportTarget.WEBHOOK

    def test_export_success(self, sample_context):
        exporter = WebhookExporter(url="https://hooks.example.com/notify")
        with mock.patch.object(exporter, "_send_with_retry") as mock_send:
            mock_send.return_value = (True, "", {"id": "ack-123"})
            result = exporter.export(sample_context)
        assert result.success
        assert result.target == ExportTarget.WEBHOOK
        assert result.metadata["response"] == {"id": "ack-123"}

    def test_export_failure(self, sample_context):
        exporter = WebhookExporter(url="https://hooks.example.com/notify")
        with mock.patch.object(exporter, "_send_with_retry") as mock_send:
            mock_send.return_value = (False, "connection refused", None)
            result = exporter.export(sample_context)
        assert not result.success
        assert "connection refused" in result.error_msg


class TestBuildPayload:
    def test_build_payload_full(self, sample_context):
        exporter = WebhookExporter(url="https://hooks.example.com/notify")
        payload = exporter._build_payload(sample_context)
        assert payload["event"] == "video.processed"
        assert payload["data"]["task_id"] == str(sample_context.task_id)
        assert payload["data"]["metadata"]["title"] == "测试标题"
        assert payload["data"]["summary"] == "测试摘要"
        assert len(payload["data"]["transcript_segments"]) == 2
        assert payload["data"]["config"]["prompt_template_id"] == "v2"
        assert payload["data"]["config"]["processing_mode"] == "smart"

    def test_build_payload_no_highlights(self, sample_context):
        ctx = sample_context
        ctx.config = {}
        exporter = WebhookExporter(url="https://hooks.example.com/notify")
        payload = exporter._build_payload(ctx)
        assert payload["data"]["highlights"] == []

    def test_build_payload_with_video_paths(self, sample_context):
        ctx = sample_context
        ctx.video_path = "/tmp/video.mp4"
        ctx.audio_path = "/tmp/audio.mp3"
        ctx.transcript_path = "/tmp/transcript.json"
        exporter = WebhookExporter(url="https://hooks.example.com/notify")
        payload = exporter._build_payload(ctx)
        assert payload["data"]["output_files"]["video"] == "/tmp/video.mp4"
        assert payload["data"]["output_files"]["audio"] == "/tmp/audio.mp3"
        assert payload["data"]["output_files"]["transcript"] == "/tmp/transcript.json"

    def test_build_payload_no_segments(self, sample_context):
        ctx = sample_context
        ctx.transcript_segments = []
        exporter = WebhookExporter(url="https://hooks.example.com/notify")
        payload = exporter._build_payload(ctx)
        assert payload["data"]["transcript_segments"] == []


class TestExtractHighlights:
    def test_extract_highlights_with_data(self, sample_context):
        exporter = WebhookExporter(url="https://hooks.example.com/notify")
        h = exporter._extract_highlights(sample_context)
        assert len(h) == 1
        assert h[0]["time"] == "00:01:30"
        assert h[0]["seconds"] == 90

    def test_extract_highlights_empty_config(self, sample_context):
        ctx = sample_context
        ctx.config = {}
        exporter = WebhookExporter(url="https://hooks.example.com/notify")
        h = exporter._extract_highlights(ctx)
        assert h == []

    def test_extract_highlights_no_config(self, sample_context):
        ctx = sample_context
        del ctx.config
        exporter = WebhookExporter(url="https://hooks.example.com/notify")
        h = exporter._extract_highlights(ctx)
        assert h == []


class TestSendWithRetry:
    def test_send_success(self, sample_context):
        exporter = WebhookExporter(url="https://hooks.example.com/notify", max_retries=1)
        payload = exporter._build_payload(sample_context)
        with mock.patch("httpx.post") as mock_post:
            mock_response = mock.Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_post.return_value = mock_response

            success, error, data = exporter._send_with_retry(payload)
        assert success
        assert data == {"ok": True}

    def test_send_http_error_with_retry(self, sample_context):
        exporter = WebhookExporter(url="https://hooks.example.com/notify", max_retries=2, retry_delay=0)
        payload = exporter._build_payload(sample_context)
        with mock.patch("httpx.post") as mock_post:
            mock_response = mock.Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.return_value = mock_response

            success, error, data = exporter._send_with_retry(payload)
        assert not success
        assert "500" in error

    def test_send_timeout_with_retry(self, sample_context):
        exporter = WebhookExporter(url="https://hooks.example.com/notify", max_retries=2, retry_delay=0)
        payload = exporter._build_payload(sample_context)
        with mock.patch("httpx.post") as mock_post:
            mock_post.side_effect = httpx.TimeoutException("timed out")
            success, error, data = exporter._send_with_retry(payload)
        assert not success
        assert "超时" in error

    def test_send_connect_error_with_retry(self, sample_context):
        exporter = WebhookExporter(url="https://hooks.example.com/notify", max_retries=2, retry_delay=0)
        payload = exporter._build_payload(sample_context)
        with mock.patch("httpx.post") as mock_post:
            mock_post.side_effect = httpx.ConnectError("connection refused")
            success, error, data = exporter._send_with_retry(payload)
        assert not success
        assert "连接错误" in error

    def test_send_generic_exception_with_retry(self, sample_context):
        exporter = WebhookExporter(url="https://hooks.example.com/notify", max_retries=2, retry_delay=0)
        payload = exporter._build_payload(sample_context)
        with mock.patch("httpx.post") as mock_post:
            mock_post.side_effect = RuntimeError("unexpected")
            success, error, data = exporter._send_with_retry(payload)
        assert not success
        assert "异常" in error

    def test_send_success_on_retry(self, sample_context):
        exporter = WebhookExporter(url="https://hooks.example.com/notify", max_retries=3, retry_delay=0)
        payload = exporter._build_payload(sample_context)
        with mock.patch("httpx.post") as mock_post:
            fail_response = mock.Mock()
            fail_response.status_code = 503
            fail_response.text = "Service Unavailable"

            ok_response = mock.Mock()
            ok_response.status_code = 200
            ok_response.json.return_value = {"ok": True}

            mock_post.side_effect = [fail_response, ok_response]
            success, error, data = exporter._send_with_retry(payload)
        assert success
        assert data == {"ok": True}

    def test_send_non_json_response(self, sample_context):
        exporter = WebhookExporter(url="https://hooks.example.com/notify", max_retries=1)
        payload = exporter._build_payload(sample_context)
        with mock.patch("httpx.post") as mock_post:
            mock_response = mock.Mock()
            mock_response.status_code = 200
            mock_response.json.side_effect = json.JSONDecodeError("not json", "", 0)
            mock_response.text = "plain text response"
            mock_post.return_value = mock_response

            success, error, data = exporter._send_with_retry(payload)
        assert success
        assert data["text"] == "plain text response"


class TestShouldTrigger:
    def test_should_trigger_matching(self):
        exporter = WebhookExporter(url="https://hooks.example.com/notify", events=["on_completed", "on_failed"])
        assert exporter.should_trigger("on_completed") is True
        assert exporter.should_trigger("on_failed") is True

    def test_should_trigger_non_matching(self):
        exporter = WebhookExporter(url="https://hooks.example.com/notify", events=["on_completed"])
        assert exporter.should_trigger("on_started") is False
