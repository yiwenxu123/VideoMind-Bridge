"""真实网络集成测试（默认跳过，需显式开启）。

## 为什么要有这个文件

本项目此前的"实测通过"只存在于手工运行的 ``scripts/check_real_links.py``，
而它既不在 CI、也不在 pytest 里。后果是：**抖音链路可以坏上几个月而单元测试全绿**——
因为单元测试全部 mock，还有两条把 bug 写成了断言。

这个文件补上的就是那一层：真的发网络请求、真的跑降级链、真的断言拿到了全文。

## 怎么跑

```bash
# 只跑抖音这一条（约 40 秒）
VMB_RUN_INTEGRATION=1 .venv/bin/python -m pytest tests/test_real_network.py -v

# 跑清单里全部条目（较慢，逐条真打网络）
VMB_RUN_INTEGRATION=1 .venv/bin/python -m pytest tests/test_real_network.py -v -k "manifest"
```

## 前提

1. ``benchmarks/real-links.local.yaml`` 存在（含真实链接与时效 token，已被 gitignore）；
   缺失时自动 skip，不会把别人的机器跑红。
2. 本机服务在线：``127.0.0.1:8787``（videomind-api）与 ``127.0.0.1:8010``（douyin-api 网关）。
   抖音那条依赖网关——这正是要测出来的东西：网关挂了就该红，而不是静默返回"无字幕"。

## 断言口径

与 SKILL.md 的 Verification 一致：``success`` 为真、``completeness`` 不低于清单要求的
``min_completeness``、``content`` 长度 > 100。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.core.models import CostTier, ExtractOptions
from src.core.router_runtime import RouterRuntime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = PROJECT_ROOT / "benchmarks" / "real-links.local.yaml"

# none < meta < full
_RANK = {"none": 0, "unknown": 0, "meta": 1, "full": 2}

_RUN = os.getenv("VMB_RUN_INTEGRATION", "").strip() not in {"", "0", "false", "False"}

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _RUN,
        reason="真实网络测试默认跳过；设置 VMB_RUN_INTEGRATION=1 开启",
    ),
]


def _load_entries() -> list[dict[str, Any]]:
    if not MANIFEST.exists():
        return []
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        return []
    entries: list[dict[str, Any]] = []
    for index, raw in enumerate(data):
        if not isinstance(raw, dict) or not raw.get("url"):
            continue
        entries.append(
            {
                "name": str(raw.get("name") or f"link-{index + 1}"),
                "url": str(raw["url"]),
                "min_completeness": str(raw.get("min_completeness") or "full").lower(),
            }
        )
    return entries


def _extract(url: str):
    """走真实降级链提取一条链接，用完即关（提取器持有 httpx 连接）。"""
    runtime = RouterRuntime()
    try:
        return runtime.extract(
            url,
            max_cost=CostTier.CHEAP,
            options=ExtractOptions(request_id="integration-test"),
        )
    finally:
        runtime.close()


def _assert_meets(result, entry: dict[str, Any], label: str) -> None:
    assert result.success, (
        f"{label} 提取失败\n"
        f"  error_code : {result.error_code}\n"
        f"  error      : {result.error}\n"
        f"  platform   : {result.platform}\n"
        f"  提示: douyin_gateway_unavailable → pm2 restart douyin-api；"
        f"douyin_gateway_no_detail → 视频多半不可见，换一条链接"
    )
    assert len(result.content or "") > 100, f"{label} 正文过短: {len(result.content or '')} 字符"
    want = _RANK.get(entry["min_completeness"], 2)
    got = _RANK.get(result.completeness, 0)
    assert got >= want, (
        f"{label} completeness 未达标: 实际 {result.completeness!r}，要求 {entry['min_completeness']!r}"
        f"（source={result.source}）"
    )


# ── 抖音：曾经"静默失效"的那条链路，单独锁住 ────────────────────────────


def test_douyin_gateway_is_reachable():
    """抖音唯一可用的获取链路是本机 douyin-api 网关；它挂了必须显式暴露。"""
    import httpx

    base = os.getenv("DOUYIN_API_URL", "http://127.0.0.1:8010").rstrip("/")
    try:
        resp = httpx.get(f"{base}/docs", timeout=5.0)
    except Exception as exc:  # noqa: BLE001 - 这里就是要捕获任何连接失败
        pytest.fail(
            f"抖音网关不可达 ({base}): {exc}\n"
            f"这是抖音提取的必要前提，请先: pm2 list | grep douyin-api; pm2 restart douyin-api"
        )
    assert resp.status_code == 200, f"抖音网关 {base}/docs 返回 {resp.status_code}"


def test_douyin_link_reaches_full_completeness():
    """抖音链接必须拿到完整正文（不是只有标题的 meta 占位）。

    这是"技能不可用"的原始现场：此前同一条链接会返回占位文本并报"可能被验证码风控"，
    而真实原因是网关没起或视频本身不可见。
    """
    entry = next((e for e in _load_entries() if e["name"].startswith("douyin")), None)
    if entry is None:
        pytest.skip(f"未在 {MANIFEST.name} 找到 douyin 条目")

    result = _extract(entry["url"])

    _assert_meets(result, entry, f"douyin({entry['name']})")
    assert result.completeness == "full", (
        f"抖音只拿到 {result.completeness!r}（source={result.source}），"
        f"没有走到 ASR；检查网关与 ASR 链"
    )
    assert result.language in {None, "zh"}, f"语言识别异常: {result.language}"


# ── 整份清单（可选，较慢）──────────────────────────────────────────────


@pytest.mark.parametrize(
    "entry",
    _load_entries(),
    ids=[e["name"] for e in _load_entries()] or ["empty-manifest"],
)
def test_manifest_entry_meets_declared_completeness(entry: dict[str, Any]):
    """清单里每条链接都达到自己声明的 min_completeness。"""
    if not _load_entries():
        pytest.skip(f"{MANIFEST.name} 不存在或为空")

    result = _extract(entry["url"])
    _assert_meets(result, entry, entry["name"])
