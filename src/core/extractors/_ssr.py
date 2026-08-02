"""SSR 数据提取共享工具（douyin/xiaohongshu 复用）"""

from __future__ import annotations

import json
import re
from typing import Any

# SSR 数据可能包含 JS 字面量 (undefined/NaN/Infinity), 非合法 JSON
_JS_LITERAL_RE = re.compile(r"([,\[{:])(undefined|NaN|Infinity)([,\]}])")
_SSR_MARKERS = ("window.__INITIAL_STATE__", "__NEXT_DATA__")


def find_ssr_payload(html: str) -> dict[str, Any] | None:
    """在 HTML 中查找 SSR 数据块（__INITIAL_STATE__ / __NEXT_DATA__）并解析为 dict。

    - 使用 JSONDecoder.raw_decode 括号平衡解析，避免非贪婪正则截断
    - 清洗 JS 字面量 (undefined/NaN/Infinity → null)

    返回第一个可解析为 dict 的负载；找不到返回 None。
    """
    for marker in _SSR_MARKERS:
        idx = html.find(marker)
        while idx != -1:
            brace = html.find("{", idx)
            if brace == -1:
                break
            data = _parse_payload(html[brace:])
            if data is not None:
                return data
            idx = html.find(marker, idx + 1)
    return None


def _parse_payload(text: str) -> dict[str, Any] | None:
    """从文本开头尝试解析一个完整 JSON 对象（容忍 JS 字面量）。"""
    cleaned = _JS_LITERAL_RE.sub(r"\1null\3", text)
    try:
        data, _end = json.JSONDecoder().raw_decode(cleaned)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        return data
    return None


def find_first_meta(html: str, patterns: list[str]) -> str:
    """按顺序在 HTML 中匹配正则，返回第一个捕获组（去首尾空白）。

    常用于提取 og:title / og:description 等 meta 字段。
    """
    for p in patterns:
        m = re.search(p, html)
        if m:
            return m.group(1).strip()
    return ""
