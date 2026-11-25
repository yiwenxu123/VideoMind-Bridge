#!/usr/bin/env python3
"""校验 douyin-api 网关的对外契约（L0 上游）是否还成立。

背景：抖音链是 VideoMind 唯一跨仓的硬依赖（`VideoMind → douyin-api:8010`）。
2026-11-25 起上游有了显式契约（`douyin-api/docs/CONTRACT.md`，服务版本 V4.1.2）：
只承诺一条路径 —— `GET /api/douyin/web/fetch_one_video?aweme_id=`。

这个脚本读上游的 `/openapi.json`（机读事实源），校验那条路径与参数还在。
网关升级/被换掉时它会先红，而不是等到提取失败才发现。

用法:
    python scripts/check_douyin_gateway_contract.py
    DOUYIN_API_URL=http://127.0.0.1:8010 python scripts/check_douyin_gateway_contract.py --json

退出码:
    0  契约成立
    1  契约被破坏（路径/参数不见了）
    2  网关不可达（先 pm2 restart douyin-api）
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

PATH = "/api/douyin/web/fetch_one_video"
EXPECTED_PARAM = "aweme_id"
# 消费方契约里写明的服务版本；上游升版本时这里会提示，但不自动判失败。
EXPECTED_VERSION = "V4.1.2"


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 douyin-api 对外契约")
    parser.add_argument("--json", dest="json_output", action="store_true", help="以 JSON 输出")
    parser.add_argument("--timeout", type=float, default=10.0, help="单次请求超时秒数")
    args = parser.parse_args()

    base = os.getenv("DOUYIN_API_URL", "http://127.0.0.1:8010").rstrip("/")
    try:
        resp = httpx.get(f"{base}/openapi.json", timeout=args.timeout)
        resp.raise_for_status()
        spec = resp.json()
    except Exception as exc:  # noqa: BLE001 - CLI 边界，统一给人能读的原因
        msg = f"网关不可达: {base}（{type(exc).__name__}: {exc}）→ pm2 list | grep douyin-api"
        print(json.dumps({"ok": False, "error": "unreachable", "message": msg}, ensure_ascii=False)
              if args.json_output else msg, file=sys.stdout if args.json_output else sys.stderr)
        return 2

    version = str((spec.get("info") or {}).get("version", "?"))
    path_item = (spec.get("paths") or {}).get(PATH)
    problems: list[str] = []

    if not isinstance(path_item, dict):
        problems.append(f"路径不见了: GET {PATH}")
    else:
        get_op = path_item.get("get")
        if not isinstance(get_op, dict):
            problems.append(f"方法变了: {PATH} 不再有 GET")
        else:
            params = {p.get("name") for p in get_op.get("parameters") or [] if isinstance(p, dict)}
            if EXPECTED_PARAM not in params:
                problems.append(f"参数不见了: {EXPECTED_PARAM}（现有 {sorted(p for p in params if p)}）")

    result = {
        "ok": not problems,
        "base": base,
        "version": version,
        "version_expected": EXPECTED_VERSION,
        "version_changed": version != EXPECTED_VERSION,
        "path": PATH,
        "paths_total": len(spec.get("paths") or {}),
        "problems": problems,
    }

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif problems:
        print(f"✗ douyin-api 契约被破坏（服务版本 {version}）:", file=sys.stderr)
        for p in problems:
            print(f"   - {p}", file=sys.stderr)
        print("   对照 douyin-api/docs/CONTRACT.md 确认是升级还是改名。", file=sys.stderr)
    else:
        print(f"✅ douyin-api 契约成立：GET {PATH}?{EXPECTED_PARAM}= （服务版本 {version}，共 {result['paths_total']} 条路径）")
        if result["version_changed"]:
            print(f"   注：版本与契约记录的 {EXPECTED_VERSION} 不同，若有字段调整请同步更新两份 CONTRACT.md")

    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
