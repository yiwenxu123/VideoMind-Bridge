"""熔断作用域回归测试（2026-11-20 P1）。

背景 bug：熔断键曾经**等于平台名**。抖音页面直抓（iesdouyin / www detail）被风控 3 次后
`"douyin"` 键打开，而 yt-dlp 与本地 ASR 两个兜底提取器也检查同一个键——于是它们被
"平台熔断中"直接跳过 60 秒。结果是最需要兜底的时候兜底被关掉：配了 cookie 的 yt-dlp
本来能拿到内容，却因为抖音直抓失败而完全不被尝试。

修复：把"限速主体"和"熔断主体"拆开。`platform` 继续决定限速策略/并发/指标归属，
新增 `circuit_key` 决定熔断归属，取值为 `平台:链路`（如 douyin:crawl）。

这两个测试锁住三件事：
1. 作用域熔断不会外溢到同平台的其它键，也不会打开裸平台键；
2. 省略 circuit_key 时仍按平台熔断（向后兼容，bilibili 等在用）；
3. 抖音直抓熔断后，yt-dlp / ASR 兜底仍会被真正执行。
"""

from __future__ import annotations

from src.core.extractors.ytdlp_asr_extractor import YtDlpASRExtractor
from src.core.extractors.ytdlp_extractor import YtDlpExtractor
from src.core.platforms import rate_limit
from src.core.platforms.rate_limit import PlatformPolicy, PlatformRateLimiter

_DOUYIN_URL = "https://www.douyin.com/video/7400000000000000000"


def _limiter() -> PlatformRateLimiter:
    """threshold=2 便于构造；cooldown 给足 60s，避免时钟推进造成偶发通过。"""
    policy = PlatformPolicy(circuit_threshold=2, circuit_cooldown_seconds=60.0)
    return PlatformRateLimiter({"douyin": policy}, enabled=True)


def _open_douyin_crawl(limiter: PlatformRateLimiter) -> None:
    limiter.notify_risk_control("douyin", circuit_key="douyin:crawl")
    limiter.notify_risk_control("douyin", circuit_key="douyin:crawl")
    assert limiter.circuit_state("douyin:crawl") == "open"


def test_scoped_circuit_does_not_leak_to_platform_or_other_scopes():
    limiter = _limiter()
    _open_douyin_crawl(limiter)

    # 兜底链路与裸平台键都必须保持关闭
    assert limiter.circuit_state("douyin") == "closed"
    assert limiter.circuit_state("douyin:ytdlp") == "closed"
    assert limiter.circuit_state("douyin:ytdlp_asr") == "closed"


def test_omitting_circuit_key_keeps_legacy_platform_behaviour():
    limiter = _limiter()
    for _ in range(2):
        limiter.notify_risk_control("douyin")
    assert limiter.circuit_state("douyin") == "open"


def test_circuits_snapshot_exposes_scope_state():
    limiter = _limiter()
    _open_douyin_crawl(limiter)

    snapshot = limiter.circuits_snapshot()
    assert snapshot["douyin:crawl"]["state"] == "open"
    assert snapshot["douyin:crawl"]["failure_streak"] == 2
    assert snapshot["douyin:crawl"]["cooldown_remaining_s"] > 0


def test_douyin_crawl_circuit_does_not_block_ytdlp_fallback(monkeypatch):
    limiter = _limiter()
    _open_douyin_crawl(limiter)
    monkeypatch.setattr(rate_limit, "_limiter", limiter)

    extractor = YtDlpExtractor()
    monkeypatch.setattr(extractor, "is_available", lambda: True)
    monkeypatch.setattr(
        extractor,
        "_try_extract",
        lambda url: ("这是兜底拿到的正文内容", [], "zh", {"title": "兜底标题"}),
    )

    result = extractor.extract(_DOUYIN_URL)

    assert "熔断" not in (result.error or ""), f"兜底被熔断误伤: {result.error}"
    assert result.success is True
    assert "兜底拿到的正文" in result.content


def test_douyin_crawl_circuit_does_not_block_ytdlp_asr_fallback(monkeypatch):
    limiter = _limiter()
    _open_douyin_crawl(limiter)
    monkeypatch.setattr(rate_limit, "_limiter", limiter)

    extractor = YtDlpASRExtractor()
    monkeypatch.setattr(extractor, "is_available", lambda: True)
    # 让它走到"下载失败"这一步：能走到这里就证明熔断闸门已放行
    monkeypatch.setattr(extractor, "_download_audio", lambda url, dest: None)

    result = extractor.extract(_DOUYIN_URL)

    assert "熔断" not in (result.error or ""), f"ASR 兜底被熔断误伤: {result.error}"
    assert "下载音频失败" in (result.error or "")


# ── 壳页计入熔断（2026-11-21 P0-5）──────────────────────────────────────────
# 修复前：抖音返回 HTTP 200 验证码壳页时被 platform_get 记成 success，
# 每轮都先把失败计数清零，于是 douyin:crawl 的 failure_streak 永远停在 1，熔断打不开。
# 修复后：壳页由 validator 转成 risk_control 错误，计入失败。

_SHELL_PAGE = (
    "<html><head><title>安全验证</title></head><body>"
    '<div id="captcha_container">请完成滑块验证</div>'
    "<script>window.__secsdk_verify__ = 1; argus.init()</script>"
    "</body></html>"
)


def _douyin_extractor_with_shell(limiter):
    import httpx

    from src.core.extractors.douyin_extractor import DouyinExtractor

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_SHELL_PAGE)

    client = httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=True
    )
    return DouyinExtractor(client=client, limiter=limiter)


def test_repeated_shell_pages_open_the_crawl_circuit():
    """连续 3 次壳页必须把 douyin:crawl 熔断打开（此前永远打不开）。"""
    policy = PlatformPolicy(circuit_threshold=3, circuit_cooldown_seconds=60.0)
    limiter = PlatformRateLimiter({"douyin": policy}, enabled=True)
    extractor = _douyin_extractor_with_shell(limiter)

    for _ in range(3):
        title, content, segments, failure = extractor._fetch_video_data("7400000000000000000")
        assert failure == "risk_control"
        assert content == ""

    assert limiter.circuit_state("douyin:crawl") == "open"
    # 仍然不污染裸平台键与兜底作用域
    assert limiter.circuit_state("douyin") == "closed"
    assert limiter.circuit_state("douyin:ytdlp") == "closed"

    snapshot = limiter.circuits_snapshot()
    assert snapshot["douyin:crawl"]["failure_streak"] >= 3
