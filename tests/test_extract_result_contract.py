"""ExtractResult 对外契约测试（阶段 2）。"""

from __future__ import annotations

from src.core.models import CostTier, ExtractResult


def _result(**overrides) -> ExtractResult:
    data = {
        "success": True,
        "platform": "bilibili",
        "title": "标题",
        "content": "内容",
        "source": "bilibili_asr",
        "url": "https://example.com/v",
        "cost_tier": CostTier.FREE,
    }
    data.update(overrides)
    return ExtractResult(**data)


def test_contract_fields_are_always_present():
    data = _result().to_dict()
    assert data["schema_version"] == "1.0"
    assert data["completeness"] == "unknown"
    assert data["method"] == ""


def test_asr_and_request_fields_are_optional():
    data = _result().to_dict()
    for key in ("asr_provider", "asr_model", "asr_model_version", "request_id", "error_code"):
        assert key not in data

    enriched = _result(
        completeness="full",
        method="asr",
        asr_provider="sensevoice",
        asr_model="sensevoice-small",
        asr_model_version="abc123",
        request_id="req-1",
        error_code="asr_failed",
    ).to_dict()
    assert enriched["asr_provider"] == "sensevoice"
    assert enriched["asr_model"] == "sensevoice-small"
    assert enriched["asr_model_version"] == "abc123"
    assert enriched["request_id"] == "req-1"
    assert enriched["error_code"] == "asr_failed"


def test_completeness_and_method_are_not_dropped():
    data = _result(completeness="meta", method="page").to_dict()
    assert data["completeness"] == "meta"
    assert data["method"] == "page"
