"""HermesFormatter 测试"""
from unittest import mock

from src.core.formatter import HermesFormatter
from src.core.models import ExtractResult, PrescreenResult, ContentGrade, CostTier


def make_extract_result(**overrides) -> ExtractResult:
    defaults = {
        "success": True, "platform": "bilibili", "title": "测试视频",
        "content": "这是内容", "source": "bilibili_extractor",
        "url": "https://bilibili.com/video/BV1xx",         "cost_tier": CostTier.FREE,
        "duration_seconds": 300.0, "language": "zh",
    }
    defaults.update(overrides)
    return ExtractResult(**defaults)


def test_format_extract_result():
    result = make_extract_result()
    d = HermesFormatter.format_extract_result(result)
    assert d["success"] is True
    assert d["platform"] == "bilibili"


def test_format_extract_result_full_adds_fields():
    result = make_extract_result()
    d = HermesFormatter.format_extract_result_full(result)
    assert d["source_type"] == "video_content"
    assert d["version"] == "2.0"
    assert "extracted_at" in d


def test_format_extract_result_full_with_prescreen():
    result = make_extract_result()
    prescreen = PrescreenResult(
        url="https://bilibili.com/video/BV1xx",
        platform="bilibili", title="测试视频", duration_seconds=300.0,
        grade=ContentGrade.A, score=75, reasons=["内容丰富"], metadata={},
    )
    d = HermesFormatter.format_extract_result_full(result, prescreen=prescreen)
    assert "prescreen" in d
    assert d["prescreen"]["grade"] == "A"


def test_format_extract_result_full_without_prescreen():
    result = make_extract_result()
    d = HermesFormatter.format_extract_result_full(result)
    assert "prescreen" not in d


def test_to_json():
    result = make_extract_result()
    json_str = HermesFormatter.to_json(result)
    assert '"success": true' in json_str
    assert '"version": "2.0"' in json_str


def test_to_json_with_extra_kwargs():
    result = make_extract_result()
    json_str = HermesFormatter.to_json(result, custom_field="hello")
    assert '"custom_field": "hello"' in json_str


def test_format_prescreen_result():
    prescreen = PrescreenResult(
        url="https://x.com", platform="youtube", title="Test",
        duration_seconds=120.0, grade=ContentGrade.B, score=60,
        reasons=["ok"], metadata={"key": "val"},
    )
    d = HermesFormatter.format_prescreen_result(prescreen)
    assert d["url"] == "https://x.com"
    assert d["grade"] == "B"
    assert d["score"] == 60
    assert d["metadata"] == {"key": "val"}
