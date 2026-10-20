#!/usr/bin/env python3
"""真实链接回归检查（单条手动定位，不做批量抓取）

用法:
  cp benchmarks/real-links.example.yaml benchmarks/real-links.local.yaml
  # 填入真实链接（含 xsec_token，本地文件已被 gitignore）
  python scripts/check_real_links.py --manifest benchmarks/real-links.local.yaml

清单:
  - name: douyin-sample
    url: https://v.douyin.com/xxxx/
    min_completeness: full   # full | meta | none

退出码: 0=全部达标；1=有链接失败或完整性低于阈值。
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

RANK = {"none": 0, "unknown": 0, "meta": 1, "full": 2}


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


def check_one(
    client: httpx.Client,
    base_url: str,
    entry: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    row: dict[str, Any] = {
        "name": entry["name"],
        "ok": False,
        "completeness": "",
        "expected": entry["min_completeness"],
        "chars": 0,
        "method": "",
        "source": "",
        "request_id": "",
        "elapsed_seconds": None,
        "error": None,
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
            print(f"  ! {row['name']}: {str(row['error'])[:200]}")


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
    args = parser.parse_args(argv)

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

    return 0 if all(row["ok"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
