"""URL 归一化：把同一视频的不同链接写法收敛成各平台的标准形式。

## 为什么需要

抖音同一个视频有多种 URL 写法，但 **yt-dlp 只认 `/video/<id>`**：

| 写法 | yt-dlp |
|---|---|
| `douyin.com/video/<id>` | ✅ 支持 |
| `douyin.com/jingxuan?modal_id=<id>` | ❌ `Unsupported URL` |
| `douyin.com/user/xxx?modal_id=<id>` | ❌ `Unsupported URL` |
| `iesdouyin.com/share/video/<id>/` | ⚠️ 部分支持 |

这正是"抖音提取不可用"的第一现场：报错是 `Unsupported URL`，却被上层合并进
"可能被验证码风控"，于是所有人都在查风控，而真正的问题是 URL 形式没归一化。

## 边界

纯规则、**无网络请求**。短链（`v.douyin.com/<code>`、`b23.tv/<code>`、`xhslink.*`）
需要一次 302 才知道目标地址，由各提取器在请求时解析，这里不处理——归一化必须是
纯函数，否则它会变成一个新的网络故障点。

只重写能**静态确定**目标的形式；无法确定时原样返回，绝不猜测。
"""

from __future__ import annotations

import re

# 抖音视频 ID：纯数字。各写法都把它放在不同位置，统一抽出来再重建标准 URL。
_DOUYIN_ID_RE = re.compile(
    r"(?:[?&]modal_id=|/video/|/share/video/|/note/)(\d{8,})"
)
_DOUYIN_HOSTS = ("douyin.com", "iesdouyin.com")
_CANONICAL_DOUYIN = "https://www.douyin.com/video/{video_id}"


def _is_douyin(url: str) -> bool:
    lowered = url.lower()
    return any(host in lowered for host in _DOUYIN_HOSTS)


def normalize_video_url(url: str) -> str:
    """返回归一化后的 URL；无法确定时原样返回（幂等）。

    Examples:
        >>> normalize_video_url("https://www.douyin.com/jingxuan?modal_id=7640637984061484998")
        'https://www.douyin.com/video/7640637984061484998'
        >>> normalize_video_url("https://www.douyin.com/video/123?previous_page=app_code_link")
        'https://www.douyin.com/video/123'
        >>> normalize_video_url("https://v.douyin.com/kDF2hXSzlHw/")
        'https://v.douyin.com/kDF2hXSzlHw/'
    """
    text = (url or "").strip()
    if not text:
        return text

    # 片段标识对平台无意义，且会污染缓存键
    text = text.split("#", 1)[0]

    if _is_douyin(text):
        match = _DOUYIN_ID_RE.search(text)
        if match:
            return _CANONICAL_DOUYIN.format(video_id=match.group(1))

    return text
