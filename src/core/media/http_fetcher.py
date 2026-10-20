"""HTTP 媒体下载器（阶段 3）

替代各平台提取器里重复的 httpx 流式下载：统一的超时、大小上限、
防盗链请求头、失败清理与错误语义。
"""

from __future__ import annotations

import httpx

from .types import (
    FetchedMedia,
    MediaFetchFailed,
    MediaFetchRequest,
    MediaTooLarge,
)


class HttpMediaFetcher:
    """基于 httpx 的直链下载器

    client 可注入（测试或复用连接池）；缺省每次请求创建短连接客户端。
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, request: MediaFetchRequest) -> FetchedMedia:
        request.dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if self._client is not None:
                return self._stream(self._client, request)
            with httpx.Client(follow_redirects=True, timeout=request.timeout) as client:
                return self._stream(client, request)
        except (MediaTooLarge, MediaFetchFailed):
            request.dest.unlink(missing_ok=True)
            raise
        except Exception as exc:
            request.dest.unlink(missing_ok=True)
            raise MediaFetchFailed(f"下载失败: {exc}") from exc

    @staticmethod
    def _stream(client: httpx.Client, request: MediaFetchRequest) -> FetchedMedia:
        total = 0
        with client.stream("GET", request.url, headers=request.headers) as resp:
            resp.raise_for_status()
            with open(request.dest, "wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    total += len(chunk)
                    if total > request.max_bytes:
                        raise MediaTooLarge(
                            f"媒体超过上限 {request.max_bytes} 字节（已下载 {total}）"
                        )
                    fh.write(chunk)
            if total < request.min_bytes:
                raise MediaFetchFailed(f"媒体过小（{total} 字节 < {request.min_bytes}）")
            return FetchedMedia(
                path=request.dest,
                size=total,
                content_type=resp.headers.get("content-type", ""),
                source="http",
            )
