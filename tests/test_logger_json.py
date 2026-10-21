"""JSON 结构化日志格式测试。"""

from __future__ import annotations

import json
import logging
import sys

from src.utils.logger import JsonFormatter


def test_json_formatter_includes_extra_fields():
    record = logging.LogRecord(
        "src.core.platforms.rate_limit",
        logging.INFO,
        __file__,
        10,
        "platform_request platform=%s outcome=success",
        ("bilibili",),
        None,
    )
    record.platform = "bilibili"
    record.outcome = "success"
    record.latency_ms = 12.5

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "src.core.platforms.rate_limit"
    assert payload["message"] == "platform_request platform=bilibili outcome=success"
    assert payload["platform"] == "bilibili"
    assert payload["outcome"] == "success"
    assert payload["latency_ms"] == 12.5
    assert "args" not in payload


def test_json_formatter_includes_exception():
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record = logging.LogRecord(
            "test",
            logging.ERROR,
            __file__,
            20,
            "failed",
            (),
            sys.exc_info(),
        )
        payload = json.loads(JsonFormatter().format(record))

    assert "RuntimeError: boom" in payload["exception"]
