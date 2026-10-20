"""对外契约黄金测试（阶段 3）：锁定响应 key 集合与版本。"""

from __future__ import annotations

from unittest import mock

from src.api.server import _extract_response
from src.core.asr import Capabilities
from src.core.capabilities import capabilities_payload
from src.core.models import SCHEMA_VERSION, CostTier, ExtractResult
from src.models.config import AsrConfig


def test_extract_success_contract_keys():
    result = ExtractResult(
        success=True,
        platform="bilibili",
        title="标题",
        content="内容",
        source="bilibili_asr",
        url="https://example.com/v",
        cost_tier=CostTier.FREE,
        duration_seconds=60,
        language="zh",
        segments=[{"start": 0.0, "end": 1.0, "text": "内容"}],
        completeness="full",
        method="asr",
        asr_provider="sensevoice",
        asr_model="sensevoice-small",
    )

    payload = _extract_response(result, "req-1")

    assert set(payload) == {
        "success", "schema_version", "platform", "title", "content", "language",
        "duration_seconds", "cost_tier", "source", "url", "completeness",
        "method", "request_id", "segments", "asr",
    }
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["request_id"] == "req-1"
    assert payload["asr"]["provider"] == "sensevoice"


def test_extract_failure_contract_keys():
    result = ExtractResult(
        success=False,
        platform="unknown",
        title="",
        content="",
        source="router",
        url="https://example.com/v",
        cost_tier=CostTier.FREE,
        error="不支持的平台",
        error_code="unsupported_url",
    )

    payload = _extract_response(result, "req-2")

    assert set(payload) == {
        "success", "schema_version", "platform", "title", "content", "language",
        "duration_seconds", "cost_tier", "source", "url", "completeness",
        "method", "request_id", "error", "error_code",
    }
    assert payload["success"] is False
    assert payload["error_code"] == "unsupported_url"


@mock.patch("src.core.router.ContentRouter")
@mock.patch("src.core.asr.available_transcribers")
@mock.patch("src.services.config_manager.ConfigManager.get_asr_config")
def test_capabilities_contract_shape(mock_cfg, mock_backends, MockRouter):
    mock_cfg.return_value = AsrConfig(chain=["faster_whisper"], max_cost="premium")
    mock_backends.return_value = [
        Capabilities(
            name="faster_whisper",
            available=True,
            languages=["auto", "zh"],
            timestamps=True,
            cost_tier=CostTier.CHEAP,
            model="base",
        )
    ]
    MockRouter.return_value.list_extractors.return_value = {"bilibili": True}

    payload = capabilities_payload()

    assert set(payload) == {"schema_version", "asr", "extractors", "platforms"}
    assert payload["schema_version"] == SCHEMA_VERSION
    assert set(payload["asr"]) == {"default_chain", "language", "max_cost", "backends"}
    assert payload["asr"]["default_chain"] == ["faster_whisper"]
    assert payload["asr"]["backends"][0]["name"] == "faster_whisper"
    assert payload["extractors"] == {"bilibili": True}


def test_extract_result_default_schema_version_matches_constant():
    result = ExtractResult(
        success=True,
        platform="p",
        title="t",
        content="c",
        source="s",
        url="u",
        cost_tier=CostTier.FREE,
    )
    assert result.schema_version == SCHEMA_VERSION
