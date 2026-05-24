"""平台检测工具 - 统一视频平台 URL 检测

从 URL 中检测视频来源平台，支持主流视频平台。
纯规则引擎，无网络请求，适合单元测试。

合并了 download_service、downloader base、prescreener 三处的平台规则。
"""


def detect_platform(url: str) -> str:
    """从 URL 检测视频平台 (纯规则, 无网络 IO)

    通过域名/子串匹配判断 URL 对应的视频平台。
    支持 13 个平台: bilibili, youtube, douyin, tiktok, xiaohongshu,
    kuaishou, weibo, zhihu, twitter, instagram, facebook, vimeo, reddit。

    Args:
        url: 视频 URL

    Returns:
        平台名称 (小写)，如果无法识别则返回 "unknown"

    Examples:
        >>> detect_platform("https://www.bilibili.com/video/BV1xx")
        'bilibili'
        >>> detect_platform("https://www.youtube.com/watch?v=xxx")
        'youtube'
        >>> detect_platform("https://v.douyin.com/xxxxx/")
        'douyin'
        >>> detect_platform("https://example.com/video")
        'unknown'
    """
    url_lower = url.lower()

    platform_patterns: dict[str, list[str]] = {
        "bilibili": ["bilibili.com", "b23.tv"],
        "youtube": ["youtube.com", "youtu.be"],
        "douyin": ["douyin.com", "iesdouyin.com", "v.douyin.com"],
        "tiktok": ["tiktok.com", "vm.tiktok.com"],
        "xiaohongshu": ["xiaohongshu.com", "xhs.link", "xhslink.com"],
        "kuaishou": ["kuaishou.com", "gifshow.com"],
        "weibo": ["weibo.com", "weibo.cn"],
        "zhihu": ["zhihu.com"],
        "twitter": ["twitter.com", "x.com"],
        "instagram": ["instagram.com"],
        "facebook": ["facebook.com", "fb.watch"],
        "vimeo": ["vimeo.com"],
        "reddit": ["reddit.com"],
    }

    for platform, patterns in platform_patterns.items():
        if any(pattern in url_lower for pattern in patterns):
            return platform

    return "unknown"
