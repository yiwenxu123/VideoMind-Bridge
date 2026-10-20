"""真实链接回归脚本的 HTML 报告与脱敏测试。"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_real_links.py"
_SPEC = importlib.util.spec_from_file_location("_vmb_check_real_links", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
check_real_links = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(check_real_links)


def _row(entry: dict[str, Any], *, ok: bool = True) -> dict[str, Any]:
    return {
        "name": entry["name"],
        "url": entry["url"],
        "ok": ok,
        "completeness": "full" if ok else "meta",
        "expected": entry["min_completeness"],
        "chars": 12 if ok else 0,
        "method": "asr" if ok else "html",
        "source": "douyin" if ok else "xiaohongshu",
        "request_id": "req-1",
        "elapsed_seconds": 1.5,
        "error": None if ok else "boom https://example.com/error?token=secret, retry",
        "error_code": "" if ok else "extract_failed",
        "asr_provider": "sensevoice" if ok else "",
        "asr_model": "sensevoice-small" if ok else "",
    }


def test_redact_url_strips_query_fragment_and_userinfo():
    raw = "https://user:pass@example.com/path?a=1&token=secret#frag"
    assert check_real_links.redact_url(raw) == "https://example.com/path"


def test_redact_text_preserves_surrounding_text():
    text = "failed: https://example.com/a?token=secret, retry later"
    assert check_real_links.redact_text(text) == "failed: https://example.com/a, retry later"


def test_check_one_captures_diagnostics_and_redacts_url():
    entry = {
        "name": "demo",
        "url": "https://example.com/v?token=secret",
        "min_completeness": "full",
        "asr": "sensevoice",
    }

    class _Response:
        def json(self):
            return {
                "success": True,
                "completeness": "full",
                "content": "hello",
                "method": "asr",
                "source": "douyin",
                "request_id": "req-1",
                "asr": {"provider": "sensevoice", "model": "small"},
            }

    class _Client:
        def post(self, *args, **kwargs):
            return _Response()

    row = check_real_links.check_one(_Client(), "http://127.0.0.1:8787", entry, 10)

    assert row["ok"] is True
    assert row["url"] == "https://example.com/v"
    assert row["asr_provider"] == "sensevoice"
    assert row["asr_model"] == "small"
    assert row["error_code"] == ""


def test_render_html_report_escapes_and_redacts():
    row = _row(
        {
            "name": '<img src=x onerror="alert(1)">',
            "url": "https://example.com/note?xsec_token=secret",
            "min_completeness": "full",
        },
        ok=False,
    )
    row["error"] = "boom <script>alert(1)</script> https://example.com/error?token=secret, retry"

    report = check_real_links.render_html_report(
        [row],
        manifest_name="real-links.local.yaml",
        base_url="http://127.0.0.1:8787/?token=base-secret",
        generated_at=datetime(2026, 10, 20, 12, 0, tzinfo=UTC),
    )

    assert "token=secret" not in report
    assert "xsec_token=secret" not in report
    assert "base-secret" not in report
    assert "<script>alert" not in report
    assert "<img src=x" not in report
    assert "&lt;script&gt;" in report
    assert "https://example.com/note" in report
    assert "https://example.com/error" in report
    assert "extract_failed" in report
    assert "未达标" in report
    assert "2026-10-20T12:00:00+00:00" in report


def test_main_writes_html_report(monkeypatch, tmp_path, capsys):
    manifest = tmp_path / "manifest.yaml"
    report = tmp_path / "report.html"
    entry = {
        "name": "demo",
        "url": "https://example.com/v?token=secret",
        "min_completeness": "full",
        "asr": "sensevoice",
    }
    monkeypatch.setattr(check_real_links, "load_manifest", lambda path: [entry])
    monkeypatch.setattr(
        check_real_links,
        "check_one",
        lambda client, base_url, row_entry, timeout: _row(row_entry),
    )

    code = check_real_links.main(
        ["--manifest", str(manifest), "--html", "--html-output", str(report)]
    )

    assert code == 0
    content = report.read_text(encoding="utf-8")
    assert "demo" in content
    assert "通过" in content
    assert "token=secret" not in content
    assert "sensevoice" in content
    captured = capsys.readouterr()
    assert "HTML 报告" in captured.out
    assert str(report) in captured.out


def test_main_html_uses_default_report_dir(monkeypatch, tmp_path):
    manifest = tmp_path / "manifest.yaml"
    entry = {
        "name": "demo",
        "url": "https://example.com/v?token=secret",
        "min_completeness": "full",
        "asr": "sensevoice",
    }
    monkeypatch.setattr(check_real_links, "load_manifest", lambda path: [entry])
    monkeypatch.setattr(
        check_real_links,
        "check_one",
        lambda client, base_url, row_entry, timeout: _row(row_entry),
    )
    monkeypatch.setattr(check_real_links, "DEFAULT_REPORT_DIR", tmp_path / "reports")

    code = check_real_links.main(["--manifest", str(manifest), "--html"])

    assert code == 0
    reports = list((tmp_path / "reports").glob("real-links-*.html"))
    assert len(reports) == 1
    assert "demo" in reports[0].read_text(encoding="utf-8")


def test_main_json_stdout_stays_machine_readable(monkeypatch, tmp_path, capsys):
    manifest = tmp_path / "manifest.yaml"
    report = tmp_path / "report.html"
    entry = {
        "name": "demo",
        "url": "https://example.com/v?token=secret",
        "min_completeness": "full",
        "asr": "sensevoice",
    }
    monkeypatch.setattr(check_real_links, "load_manifest", lambda path: [entry])
    monkeypatch.setattr(
        check_real_links,
        "check_one",
        lambda client, base_url, row_entry, timeout: _row(row_entry, ok=False),
    )

    code = check_real_links.main(
        ["--manifest", str(manifest), "--json", "--html-output", str(report)]
    )

    assert code == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload[0]["name"] == "demo"
    assert "HTML 报告" in captured.err
    assert report.is_file()
    assert "token=secret" not in report.read_text(encoding="utf-8")
