#!/usr/bin/env python3
"""Discovery API 真实链接回归（creator feed / comments）

用法:
  cp benchmarks/discovery-links.example.yaml benchmarks/discovery-links.local.yaml
  # 填入真实链接
  python scripts/check_discovery_links.py --manifest benchmarks/discovery-links.local.yaml

清单:
  - name: bilibili-creator
    kind: creator_feed
    url: https://space.bilibili.com/123456
    limit: 5
  - name: bilibili-comments
    kind: comments
    url: https://www.bilibili.com/video/BVxxxx
    limit: 10
    sort: hot
    include_replies: true
    max_replies_per_thread: 2

退出码: 0=全部达标；1=有链接失败或返回条数低于 min_items。
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

ENDPOINTS = {
    "creator_feed": "/api/v1/creator/feed",
    "comments": "/api/v1/comments",
}


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        raise ValueError("manifest 必须是 YAML 数组")

    entries: list[dict[str, Any]] = []
    for index, raw in enumerate(data):
        if not isinstance(raw, dict) or not raw.get("url"):
            raise ValueError(f"第 {index + 1} 条缺少 url")
        kind = str(raw.get("kind") or "creator_feed").strip()
        if kind not in ENDPOINTS:
            raise ValueError(f"第 {index + 1} 条 kind 非法: {kind}")
        entry: dict[str, Any] = {
            "name": str(raw.get("name") or f"link-{index + 1}"),
            "kind": kind,
            "url": str(raw["url"]),
            "limit": int(raw.get("limit") or (5 if kind == "creator_feed" else 10)),
            "min_items": int(raw.get("min_items") or 1),
        }
        if kind == "comments":
            entry.update(
                {
                    "sort": str(raw.get("sort") or "hot"),
                    "include_replies": bool(raw.get("include_replies", False)),
                    "max_replies_per_thread": int(
                        raw.get("max_replies_per_thread") or 3
                    ),
                    "include_author": bool(raw.get("include_author", False)),
                }
            )
        entries.append(entry)
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
        "kind": entry["kind"],
        "ok": False,
        "success": False,
        "returned_count": 0,
        "top_level_count": 0,
        "reply_count": 0,
        "completeness": "",
        "has_more": False,
        "request_id": "",
        "error_code": "",
        "error": None,
        "elapsed_seconds": None,
    }
    payload: dict[str, Any] = {
        "url": entry["url"],
        "limit": entry["limit"],
    }
    if entry["kind"] == "comments":
        payload.update(
            {
                "sort": entry["sort"],
                "include_replies": entry["include_replies"],
                "max_replies_per_thread": entry["max_replies_per_thread"],
                "include_author": entry["include_author"],
            }
        )

    try:
        response = client.post(
            f"{base_url.rstrip('/')}{ENDPOINTS[entry['kind']]}",
            json=payload,
            timeout=timeout,
        )
        body = response.json()
        row["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        row["success"] = bool(body.get("success"))
        row["returned_count"] = int(body.get("returned_count") or 0)
        row["top_level_count"] = int(body.get("top_level_count") or 0)
        row["reply_count"] = int(body.get("reply_count") or 0)
        row["completeness"] = str(body.get("completeness") or "")
        row["has_more"] = bool(body.get("has_more"))
        row["request_id"] = str(body.get("request_id") or "")
        row["error_code"] = str(body.get("error_code") or "")
        row["error"] = body.get("error") or body.get("detail")
        row["ok"] = row["success"] and row["returned_count"] >= entry["min_items"]
    except Exception as exc:
        row["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def print_table(rows: list[dict[str, Any]]) -> None:
    headers = [
        "name", "kind", "ok", "count", "top", "replies",
        "completeness", "elapsed", "error",
    ]
    print(" | ".join(headers))
    print(" | ".join("---" for _ in headers))
    for row in rows:
        print(
            " | ".join(
                [
                    row["name"],
                    row["kind"],
                    "yes" if row["ok"] else "no",
                    str(row["returned_count"]),
                    str(row["top_level_count"]),
                    str(row["reply_count"]),
                    row["completeness"] or "-",
                    f"{row['elapsed_seconds']}s" if row["elapsed_seconds"] is not None else "-",
                    str(row["error"] or "-")[:160],
                ]
            )
        )
        if row["error_code"]:
            print(f"  ! {row['name']}: [{row['error_code']}]")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discovery API 真实链接回归")
    parser.add_argument("--manifest", required=True, help="YAML 清单路径")
    parser.add_argument(
        "--base-url",
        default=os.getenv("VMB_BASE_URL", "http://127.0.0.1:8787"),
    )
    parser.add_argument("--token", default=os.getenv("VMB_API_TOKEN", ""))
    parser.add_argument("--timeout", type=float, default=120.0)
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
