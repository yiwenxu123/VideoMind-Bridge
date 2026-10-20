#!/usr/bin/env python3
"""真实链接回归检查（单条手动定位，不做批量抓取）

用法:
  cp benchmarks/real-links.example.yaml benchmarks/real-links.local.yaml
  # 填入真实链接（含 xsec_token，本地文件已被 gitignore）
  python scripts/check_real_links.py --manifest benchmarks/real-links.local.yaml
  python scripts/check_real_links.py --manifest benchmarks/real-links.local.yaml --html

清单:
  - name: douyin-sample
    url: https://v.douyin.com/xxxx/
    min_completeness: full   # full | meta | none

退出码: 0=全部达标；1=有链接失败或完整性低于阈值。
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
import yaml

RANK = {"none": 0, "unknown": 0, "meta": 1, "full": 2}
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT_DIR = PROJECT_ROOT / "benchmarks" / "reports"
_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_URL_TRAILING = ".,;:!?)]}，。；！？"


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        raise ValueError("manifest 必须是 YAML 数组")
    entries: list[dict[str, Any]] = []
    for index, raw in enumerate(data):
        if not isinstance(raw, dict) or not raw.get("url"):
            raise ValueError(f"第 {index + 1} 条缺少 url")
        minimum = str(raw.get("min_completeness") or "full").lower()
        if minimum not in RANK:
            raise ValueError(f"第 {index + 1} 条 min_completeness 非法: {minimum}")
        entries.append(
            {
                "name": str(raw.get("name") or f"link-{index + 1}"),
                "url": str(raw["url"]),
                "min_completeness": minimum,
                "asr": raw.get("asr") or "sensevoice",
            }
        )
    return entries


def redact_url(url: str) -> str:
    """去掉查询参数、片段和 userinfo，避免报告泄露 xsec_token 等时效凭证。"""
    url = url.strip()
    if not url:
        return url
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url
    if not parsed.scheme or not parsed.netloc:
        return url
    netloc = parsed.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def redact_text(text: str) -> str:
    """替换文本中的 URL，保留原句其余内容。"""

    def _replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        trailing = ""
        while raw and raw[-1] in _URL_TRAILING:
            trailing = raw[-1] + trailing
            raw = raw[:-1]
        return redact_url(raw) + trailing

    return _URL_RE.sub(_replace, text)


def _escape(value: Any, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    return html.escape(str(value))


_REPORT_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 32px;
  background: #f6f7f9;
  color: #1f2937;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
}
main { max-width: 1440px; margin: 0 auto; }
h1 { margin: 0 0 8px; font-size: 24px; }
.subtitle { margin: 0 0 24px; color: #6b7280; font-size: 14px; }
.summary { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
.stat {
  min-width: 112px; padding: 14px 18px; background: #fff;
  border: 1px solid #e5e7eb; border-radius: 10px;
}
.stat .num { display: block; font-size: 24px; font-weight: 700; }
.stat.pass .num { color: #047857; }
.stat.fail .num { color: #b91c1c; }
.meta {
  display: grid; gap: 6px; margin-bottom: 20px; padding: 14px 18px;
  background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
  font-size: 13px;
}
.meta span { color: #6b7280; margin-right: 6px; }
.table-wrap { overflow-x: auto; border-radius: 10px; }
table {
  width: 100%; min-width: 1100px; border-collapse: collapse; background: #fff;
  border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden;
}
th, td {
  padding: 10px 12px; border-bottom: 1px solid #eef0f3;
  text-align: left; vertical-align: top; font-size: 13px;
}
th { background: #f9fafb; color: #4b5563; font-weight: 600; white-space: nowrap; }
tr:last-child td { border-bottom: none; }
tr.fail-row td { background: #fff7f7; }
.name { font-weight: 600; }
.badge {
  display: inline-block; padding: 2px 8px; border-radius: 999px;
  font-size: 12px; font-weight: 600; white-space: nowrap;
}
.badge.pass { background: #d1fae5; color: #065f46; }
.badge.fail { background: #fee2e2; color: #991b1b; }
.muted { margin-top: 3px; color: #6b7280; font-size: 12px; word-break: break-all; }
code { padding: 1px 5px; background: #f3f4f6; border-radius: 4px; font-size: 12px; }
.empty { padding: 24px; text-align: center; color: #6b7280; }
footer { margin-top: 16px; color: #6b7280; font-size: 12px; }
@media (max-width: 700px) { body { padding: 16px; } }
"""


def render_html_report(
    rows: list[dict[str, Any]],
    *,
    manifest_name: str = "",
    base_url: str = "",
    generated_at: datetime | None = None,
) -> str:
    generated = (generated_at or datetime.now().astimezone()).isoformat(timespec="seconds")
    passed = sum(1 for row in rows if row.get("ok"))
    failed = len(rows) - passed

    table_rows: list[str] = []
    for row in rows:
        name = _escape(row.get("name"))
        url = html.escape(redact_url(str(row.get("url") or "")))
        request_id = _escape(row.get("request_id"), "")
        status = (
            '<span class="badge pass">通过</span>'
            if row.get("ok")
            else '<span class="badge fail">未达标</span>'
        )
        completeness = _escape(row.get("completeness"))
        expected = _escape(row.get("expected"))
        method = _escape(row.get("method"))
        chars = row.get("chars")
        chars_text = "—" if chars is None else html.escape(str(chars))
        elapsed = row.get("elapsed_seconds")
        elapsed_text = "—" if elapsed is None else html.escape(f"{elapsed}s")
        source = _escape(row.get("source"))

        asr_provider = str(row.get("asr_provider") or "")
        asr_model = str(row.get("asr_model") or "")
        asr_text = ""
        if asr_provider:
            asr_text = f"ASR: {html.escape(asr_provider)}"
            if asr_model:
                asr_text += f" / {html.escape(asr_model)}"
        asr_html = f'<div class="muted">{asr_text}</div>' if asr_text else ""

        error_code = str(row.get("error_code") or "")
        error_text = redact_text(str(row.get("error") or ""))
        error_parts: list[str] = []
        if error_code:
            error_parts.append(f"<code>{html.escape(error_code)}</code>")
        if error_text:
            error_parts.append(html.escape(error_text))
        error_html = " ".join(error_parts) or '<span class="muted">—</span>'

        url_html = f'<div class="muted">{url}</div>' if url else ""
        request_html = f'<div class="muted">request_id: {request_id}</div>' if request_id else ""

        row_class = "" if row.get("ok") else ' class="fail-row"'
        table_rows.append(
            f"<tr{row_class}>"
            f'<td><div class="name">{name}</div>{url_html}{request_html}</td>'
            f"<td>{status}</td>"
            f'<td>{completeness} <span class="muted">(&gt;= {expected})</span></td>'
            f"<td>{method}{asr_html}</td>"
            f"<td>{chars_text}</td>"
            f"<td>{elapsed_text}</td>"
            f"<td>{source}</td>"
            f"<td>{error_html}</td>"
            "</tr>"
        )

    if not table_rows:
        table_rows.append('<tr><td colspan="8" class="empty">清单为空</td></tr>')

    summary = (
        '<div class="summary">'
        f'<div class="stat"><span class="num">{len(rows)}</span><span>总数</span></div>'
        f'<div class="stat pass"><span class="num">{passed}</span><span>通过</span></div>'
        f'<div class="stat fail"><span class="num">{failed}</span><span>未达标</span></div>'
        "</div>"
    )
    meta = (
        '<div class="meta">'
        f'<div><span>清单</span>{html.escape(manifest_name or "—")}</div>'
        f'<div><span>目标服务</span>{html.escape(redact_url(base_url) if base_url else "—")}</div>'
        f'<div><span>生成时间</span>{html.escape(generated)}</div>'
        "</div>"
    )
    rows_html = "\n".join(table_rows)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>VideoMind Bridge 真实链接回归报告</title>
<style>{_REPORT_CSS}</style>
</head>
<body>
<main>
<h1>VideoMind Bridge 真实链接回归报告</h1>
<p class="subtitle">完整性、方法、耗时与错误一目了然；URL 已去除查询参数与片段。</p>
{summary}
{meta}
<div class="table-wrap">
<table>
<thead>
<tr><th>名称 / 链接</th><th>结果</th><th>完整性</th><th>方法 / ASR</th><th>字数</th><th>耗时</th><th>来源</th><th>错误</th></tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</div>
<footer>由 scripts/check_real_links.py 生成 · 报告为本地文件，请勿提交包含真实链接的清单或报告</footer>
</main>
</body>
</html>
"""


def write_html_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def check_one(
    client: httpx.Client,
    base_url: str,
    entry: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    row: dict[str, Any] = {
        "name": entry["name"],
        "url": redact_url(entry["url"]),
        "ok": False,
        "completeness": "",
        "expected": entry["min_completeness"],
        "chars": 0,
        "method": "",
        "source": "",
        "request_id": "",
        "elapsed_seconds": None,
        "error": None,
        "error_code": "",
        "asr_provider": "",
        "asr_model": "",
    }
    try:
        resp = client.post(
            f"{base_url.rstrip('/')}/api/v1/extract",
            json={"url": entry["url"], "asr": entry["asr"]},
            timeout=timeout,
        )
        body = resp.json()
        row["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        row["completeness"] = body.get("completeness") or ""
        row["chars"] = len(body.get("content") or "")
        row["method"] = body.get("method") or ""
        row["source"] = body.get("source") or ""
        row["request_id"] = body.get("request_id") or ""
        row["error"] = body.get("error")
        row["error_code"] = body.get("error_code") or ""
        asr = body.get("asr")
        if isinstance(asr, dict):
            row["asr_provider"] = str(asr.get("provider") or "")
            row["asr_model"] = str(asr.get("model") or "")
        rank = RANK.get(str(row["completeness"]).lower(), 0)
        row["ok"] = bool(body.get("success")) and rank >= RANK[entry["min_completeness"]]
    except Exception as exc:
        row["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def print_table(rows: list[dict[str, Any]]) -> None:
    headers = ["name", "ok", "completeness", "method", "chars", "elapsed", "source"]
    print(" | ".join(headers))
    print(" | ".join("---" for _ in headers))
    for row in rows:
        print(
            " | ".join(
                [
                    row["name"],
                    "yes" if row["ok"] else "no",
                    f"{row['completeness'] or '-'} (>= {row['expected']})",
                    row["method"] or "-",
                    str(row["chars"]),
                    f"{row['elapsed_seconds']}s" if row["elapsed_seconds"] is not None else "-",
                    row["source"] or "-",
                ]
            )
        )
        if row["error"]:
            code = f"[{row['error_code']}] " if row.get("error_code") else ""
            print(f"  ! {row['name']}: {code}{str(row['error'])[:200]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="真实链接完整性回归检查")
    parser.add_argument("--manifest", required=True, help="YAML 清单路径")
    parser.add_argument(
        "--base-url",
        default=os.getenv("VMB_BASE_URL", "http://127.0.0.1:8787"),
    )
    parser.add_argument("--token", default=os.getenv("VMB_API_TOKEN", ""))
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--html",
        action="store_true",
        help="生成自包含 HTML 回归报告（默认写入 benchmarks/reports/）",
    )
    parser.add_argument(
        "--html-output",
        default=None,
        help="HTML 报告输出路径（指定后隐含 --html）",
    )
    args = parser.parse_args(argv)
    if args.html_output is not None and not args.html_output.strip():
        parser.error("--html-output 不能为空")

    entries = load_manifest(Path(args.manifest).expanduser())
    headers = {"Content-Type": "application/json"}
    token = args.token.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    with httpx.Client(headers=headers) as client:
        rows = [
            check_one(client, args.base_url, entry, args.timeout)
            for entry in entries
        ]

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print_table(rows)

    report_path: Path | None = None
    if args.html or args.html_output:
        if args.html_output:
            report_path = Path(args.html_output).expanduser()
        else:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            report_path = DEFAULT_REPORT_DIR / f"real-links-{stamp}.html"
        write_html_report(
            report_path,
            render_html_report(
                rows,
                manifest_name=Path(args.manifest).name,
                base_url=args.base_url,
            ),
        )
        print(
            f"\nHTML 报告: {report_path}",
            file=sys.stderr if args.json else sys.stdout,
        )

    return 0 if all(row["ok"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
