"""API 阶段 2：能力发现、请求级 ASR 覆盖与响应契约。"""

from __future__ import annotations

from unittest import mock

import pytest
from fastapi.testclient import TestClient

from src.api.server import APIServer
from src.core.models import CostTier, ExtractResult
from src.models.config import AsrConfig


@pytest.fixture
def server():
    return APIServer()


@pytest.fixture
def client(server):
    with TestClient(server.app) as c:
        yield c


def _fake_result() -> ExtractResult:
    return ExtractResult(
        success=True,
        platform="bilibili",
        title="测试",
        content="转写内容",
        source="bilibili_asr",
        url="https://www.bilibili.com/video/BV1xx",
        cost_tier=CostTier.FREE,
        duration_seconds=60,
        language="zh",
        segments=[{"start": 0.0, "end": 1.0, "text": "转写内容"}],
        completeness="full",
        method="asr",
        asr_provider="sensevoice",
        asr_model="sensevoice-small",
    )


class TestCapabilities:
    def test_returns_asr_backends_and_extractors(self, client):
        resp = client.get("/api/v1/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert data["schema_version"] == "1.0"
        names = [b["name"] for b in data["asr"]["backends"]]
        for expected in ("faster_whisper", "dashscope", "aliyun", "sensevoice"):
            assert expected in names
        assert "bilibili" in data["extractors"]

    def test_backends_expose_capability_shape(self, client):
        data = client.get("/api/v1/capabilities").json()
        for backend in data["asr"]["backends"]:
            assert {"name", "available", "languages", "timestamps", "cost_tier"} <= set(backend)


class TestExtractContract:
    def test_unsupported_url_returns_contract_fields(self, client):
        resp = client.post(
            "/api/v1/extract",
            json={"url": "https://unsupported-example.com/video"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["schema_version"] == "1.0"
        assert data["request_id"]
        assert data["error_code"] == "unsupported_url"


class TestAsrOverride:
    @mock.patch("src.services.config_manager.ConfigManager.get_asr_config")
    @mock.patch("src.core.ContentRouter")
    def test_asr_preferred_backend_is_chain_head(self, MockRouter, mock_cfg, client):
        mock_cfg.return_value = AsrConfig(chain=["faster_whisper", "dashscope"])
        router = MockRouter.return_value
        router.extract = mock.Mock(return_value=_fake_result())

        resp = client.post(
            "/api/v1/extract",
            json={
                "url": "https://www.bilibili.com/video/BV1xx",
                "asr": "sensevoice",
                "asr_options": {"language": "zh"},
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["asr"]["provider"] == "sensevoice"
        assert data["completeness"] == "full"
        assert data["method"] == "asr"

        options = router.extract.call_args.kwargs["options"]
        assert options.asr_chain == ["sensevoice", "faster_whisper", "dashscope"]
        assert options.asr_language == "zh"
        assert options.request_id == data["request_id"]

    @mock.patch("src.core.ContentRouter")
    def test_asr_chain_is_exact(self, MockRouter, client):
        router = MockRouter.return_value
        router.extract = mock.Mock(return_value=_fake_result())

        resp = client.post(
            "/api/v1/extract",
            json={
                "url": "https://www.bilibili.com/video/BV1xx",
                "asr_chain": ["sensevoice", "faster_whisper"],
            },
        )

        assert resp.status_code == 200
        options = router.extract.call_args.kwargs["options"]
        assert options.asr_chain == ["sensevoice", "faster_whisper"]

    @pytest.mark.parametrize(
        "payload",
        [
            {"url": "https://example.com/v", "asr": "no_such_backend"},
            {"url": "https://example.com/v", "asr_chain": []},
            {"url": "https://example.com/v", "asr_chain": ["ghost"]},
            {"url": "https://example.com/v", "asr_options": "bad"},
        ],
    )
    def test_invalid_asr_params_return_400(self, client, payload):
        resp = client.post("/api/v1/extract", json=payload)
        assert resp.status_code == 400
