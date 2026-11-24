"""提取链路命中分布指标（2026-11-23）。

## 解决什么问题

没有这套指标时，只能回答"提取成功了没有"，回答不了这些关键问题：

- 抖音这几百条里，**多少走了 ASR、多少走了字幕**？
- 失败主要卡在哪一环（网关不可达？视频不可见？真风控？）
- 哪条链路实际上从没被用到（白白维护）

而这些恰恰决定了"该修哪里""值不值得继续维护某条链路"。

## 口径

以 `ExtractResult` 的既有字段为准，不新造语义：

| 维度 | 来源 | 回答的问题 |
|---|---|---|
| `method` | `subtitle` / `asr` / `page` / `desc` / `manual` | **文字是怎么拿到的**（字幕 vs 转写 vs 文案） |
| `source` | `douyin_asr` / `bilibili_api` / `ytdlp_asr_local` … | 具体是哪条链路干的 |
| `platform` | `douyin` / `bilibili` … | 分平台看 |
| `completeness` | `full` / `meta` / `none` / `unknown` | 拿到全文还是只有占位 |
| `error_code` | `douyin_gateway_unavailable` … | 失败归因分布 |

缓存命中单独计：否则"ASR 命中率"会被缓存放大成虚假繁荣。

## 边界

- 进程内计数，重启清零（与 `platforms/rate_limit` 的指标一致）；
- 键空间有上限（超过就归入 `other`），避免错误码/来源意外爆炸导致内存增长；
- 只读快照，不影响提取路径。
"""

from __future__ import annotations

import threading
from collections import Counter
from typing import Any

# 每个维度最多保留多少个不同取值，超出归入 "other"
_MAX_KEYS_PER_DIMENSION = 40


class ExtractionMetrics:
    """线程安全的提取命中分布计数器。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total = 0
        self._cache_hits = 0
        self._dims: dict[str, Counter[str]] = {
            "method": Counter(),
            "source": Counter(),
            "platform": Counter(),
            "completeness": Counter(),
            "error_code": Counter(),
        }

    # ── 写入 ────────────────────────────────────────────────────────

    def record(self, result: Any, *, cache_hit: bool = False) -> None:
        """记录一次提取结果。``result`` 为 ExtractResult。"""
        with self._lock:
            self._total += 1
            if cache_hit:
                # 缓存命中只计总量：它没有"用哪条链路拿到文字"这件事，
                # 混进 method 分布会让 ASR/字幕占比失真。
                self._cache_hits += 1
                return
            values = {
                "method": result.method or "unknown",
                "source": result.source or "unknown",
                "platform": result.platform or "unknown",
                "completeness": result.completeness or "unknown",
            }
            # 成功时错误码通常为空，不计入，避免把 None 堆成最大桶
            if not result.success and result.error_code:
                values["error_code"] = result.error_code
            for dim, value in values.items():
                self._bump(dim, value)

    def _bump(self, dim: str, value: str) -> None:
        counter = self._dims[dim]
        key = value if len(counter) < _MAX_KEYS_PER_DIMENSION or value in counter else "other"
        counter[key] += 1

    # ── 读取 ────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """返回可 JSON 序列化的快照。

        ``asr_share`` 是最常用的派生值：转写（asr）在所有成功结果中的占比，
        直接回答"这条平台到底靠字幕还是靠转写"。
        """
        with self._lock:
            method = dict(self._dims["method"])
            total = self._total
            cache_hits = self._cache_hits
            payload = {
                "total": total,
                "cache_hits": cache_hits,
                # 真正走了提取链路的次数 = 总量 - 缓存命中
                "extracted": total - cache_hits,
                "method": method,
                "source": dict(self._dims["source"]),
                "platform": dict(self._dims["platform"]),
                "completeness": dict(self._dims["completeness"]),
                "error_code": dict(self._dims["error_code"]),
            }
        extracted = sum(v for k, v in method.items() if k not in {"unknown"})
        asr = method.get("asr", 0)
        subtitle = method.get("subtitle", 0)
        payload["method_share"] = {
            "total_classified": extracted,
            "asr": round(asr / extracted, 4) if extracted else 0.0,
            "subtitle": round(subtitle / extracted, 4) if extracted else 0.0,
        }
        return payload

    def reset(self) -> None:
        with self._lock:
            self._total = 0
            self._cache_hits = 0
            for counter in self._dims.values():
                counter.clear()


class ApiCallMetrics:
    """按调用方统计 API 调用（2026-11-23）。

    作用只有一个：**回答"到底谁在调我"**。
    此前中间件只在启用鉴权时记日志，而本机默认不启用鉴权——于是没有任何调用记录，
    想收敛工具面/端点数全凭猜。有了这个计数，跑一周就能拿到真实清单。

    `X-Consumer-Id` 请求头缺省记 `anonymous`（Agent 直连时就是它）。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._total = 0
        self._by_consumer: Counter[str] = Counter()
        self._by_endpoint: Counter[str] = Counter()

    def record(self, consumer: str, method: str, path: str, status: int) -> None:
        with self._lock:
            self._total += 1
            self._bump(self._by_consumer, consumer or "anonymous")
            # 只统计 2xx/4xx/5xx 的类别，不把每条路径都展开
            self._bump(self._by_endpoint, f"{method} {path} {status // 100}xx")

    @staticmethod
    def _bump(counter: Counter[str], key: str) -> None:
        if len(counter) >= _MAX_KEYS_PER_DIMENSION and key not in counter:
            key = "other"
        counter[key] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total": self._total,
                "by_consumer": dict(self._by_consumer),
                "by_endpoint": dict(self._by_endpoint),
            }


_metrics: ExtractionMetrics | None = None
_metrics_lock = threading.Lock()


def get_extraction_metrics() -> ExtractionMetrics:
    global _metrics
    with _metrics_lock:
        if _metrics is None:
            _metrics = ExtractionMetrics()
        return _metrics


def reset_extraction_metrics() -> None:
    """清空单例（测试用）。"""
    global _metrics
    with _metrics_lock:
        _metrics = None


_api_metrics: ApiCallMetrics | None = None


def get_api_metrics() -> ApiCallMetrics:
    global _api_metrics
    with _metrics_lock:
        if _api_metrics is None:
            _api_metrics = ApiCallMetrics()
        return _api_metrics


def reset_api_metrics() -> None:
    global _api_metrics
    with _metrics_lock:
        _api_metrics = None
