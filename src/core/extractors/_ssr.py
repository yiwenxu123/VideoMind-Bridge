"""SSR 数据提取共享工具（douyin/xiaohongshu 复用）"""

from __future__ import annotations

import json
import re
from typing import Any

_SSR_PATTERNS = [
    re.compile(r"<script>window\.__INITIAL_STATE__\s*=\s*({.*?});</script>", re.DOTALL),
    re.compile(
        r'<script id="__NEXT_DATA__"\s*type="application/json">({.*?})</script>',
        re.DOTALL,
    ),
]


def find_ssr_payload(html: str) -> dict[str, Any] | None:
    """在 HTML 中查找 SSR 数据块（__INITIAL_STATE__ / __NEXT_DATA__）并解析为 dict。

    返回第一个可解析为 dict 的负载；找不到返回 None。
    """
    for pattern in _SSR_PATTERNS:
        m = pattern.search(html)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None
