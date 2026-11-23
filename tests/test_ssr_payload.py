"""SSR 负载解析测试（2026-11-23）。

背景：2026-10-31 小红书改版起，`__INITIAL_STATE__` 里会混入 JS 集合字面量
（如 `"noteDetailMap":new Map([])`）。旧清洗器只处理 `undefined/NaN/Infinity`，
遇到 `new Map(` 会让**整块 JSON 解析失败**——表现是"页面明明有数据却什么都取不到"。

社区的同类故障有完整 PR 记录（Diana #1419）。本地 4 条真实页面上该字面量计数为 0，
所以这是**前瞻性修复**：一旦上游铺开，不会立刻失效。

替换策略是安全降级（`new Map([])` → `[]`，取值落空而非报错），
且必须**跳过字符串**，否则正文里出现 "new Map(" 字样会被误改。
"""

from __future__ import annotations

import pytest

from src.core.extractors._ssr import _strip_js_collections, find_ssr_payload


def _wrap(payload: str) -> str:
    """模拟页面里内联 SSR 数据的样子。"""
    return f"<html><script>window.__INITIAL_STATE__ = {payload};</script></html>"


@pytest.mark.parametrize(
    ("raw", "expect"),
    [
        ('{"a":new Map([])}', {"a": []}),
        ('{"a":new Set([])}', {"a": []}),
        ('{"a":new Set([1,2])}', {"a": [1, 2]}),
        ('{"a":new Map([["k","v"]])}', {"a": [["k", "v"]]}),
        ('{"a":new Map([new Set([1])])}', {"a": [[1]]}),
        # 与既有的字面量清洗共存
        ('{"a":new Map([]),"b":undefined}', {"a": [], "b": None}),
    ],
)
def test_js_collections_are_parsed(raw: str, expect: dict) -> None:
    assert find_ssr_payload(_wrap(raw)) == expect


def test_realistic_xhs_shape():
    """真实形态：笔记详情表在新版里被表达成 new Map([])。"""
    payload = '{"note":{"noteDetailMap":new Map([]),"currentNoteId":"abc"}}'
    data = find_ssr_payload(_wrap(payload))
    assert data is not None
    assert data["note"]["noteDetailMap"] == []
    assert data["note"]["currentNoteId"] == "abc"


def test_strings_containing_js_literals_are_untouched():
    """字符串里的 "new Map(" 必须原样保留，不能被当成代码替换掉。"""
    text = '{"desc":"正文里提到 new Map(x) 这个词","ok":1}'
    assert find_ssr_payload(_wrap(text)) == {
        "desc": "正文里提到 new Map(x) 这个词",
        "ok": 1,
    }


def test_strip_helper_is_idempotent():
    once = _strip_js_collections('{"a":new Map([])}')
    assert once == '{"a":[]}'
    assert _strip_js_collections(once) == once


def test_malformed_collection_falls_back_without_crashing():
    """括号不配对时不能抛异常，只是解析失败（返回 None）。"""
    assert find_ssr_payload(_wrap('{"a":new Map([')) is None


def test_plain_json_still_works():
    assert find_ssr_payload(_wrap('{"a":{"b":1}}')) == {"a": {"b": 1}}
