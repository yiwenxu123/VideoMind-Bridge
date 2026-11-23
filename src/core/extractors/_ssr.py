"""SSR 数据提取共享工具（douyin/xiaohongshu 复用）"""

from __future__ import annotations

import json
import re
from typing import Any

# SSR 数据可能包含 JS 字面量 (undefined/NaN/Infinity), 非合法 JSON
_JS_LITERAL_RE = re.compile(r"([,\[{:])(undefined|NaN|Infinity)([,\]}])")
# 2026-10-31 小红书改版起，__INITIAL_STATE__ 里会混入 `new Map([...])` / `new Set([...])`。
# 只清洗 undefined/NaN/Infinity 的旧逻辑遇到它会让**整块** JSON 解析失败，
# 表现为"页面明明有数据却什么都取不到"。
_JS_COLLECTION_RE = re.compile(r"new\s+(?:Map|Set)\s*\(")


def _matching_paren(text: str, open_idx: int) -> int:
    """返回与 text[open_idx]（必须是 '('）配对的 ')' 下标；找不到返回 -1。

    扫描时跳过字符串字面量，避免把 URL、中文文案里的括号算进层级。
    """
    depth = 0
    quote: str | None = None
    i = open_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _strip_js_collections(text: str) -> str:
    """把 `new Map([...])` / `new Set([...])` 换成其内层数组。

    换掉包装器 JSON 才可解析。语义上是**安全降级**：
    - `new Map([])` → `[]`，调用方按 dict 取值只会拿到空（与"数据为空"等价）；
    - `new Map([["k","v"]])` → `[["k","v"]]`（数组而非对象），同样只是取值落空。
    这些字段原本只在有值时被使用，退化为空不会产生错误内容。

    单遍扫描并跳过字符串，保证正文里出现的 `new Map(` 字样不会被误替换。
    """
    out: list[str] = []
    i = 0
    n = len(text)
    quote: str | None = None
    while i < n:
        ch = text[i]
        if quote is not None:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
            i += 1
            continue
        match = _JS_COLLECTION_RE.match(text, i)
        if match:
            open_idx = match.end() - 1
            close_idx = _matching_paren(text, open_idx)
            if close_idx != -1:
                inner = text[open_idx + 1 : close_idx].strip()
                out.append(_strip_js_collections(inner))
                i = close_idx + 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)

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
    # 顺序：先拆 new Map/Set（内部含括号与字符串），再做字面量清洗
    cleaned = _JS_LITERAL_RE.sub(r"\1null\3", _strip_js_collections(text))
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
