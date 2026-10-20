"""API 鉴权与限流（阶段 4）

配置（全部可选）：
- VIDEOMIND_API_TOKEN: 管理员 token（兼容旧行为）
- VMB_CONSUMER_TOKENS: JSON 对象，例如 {"content-ops":"tok-a","n8n":"tok-b"}
- VMB_RATE_LIMIT_PER_MIN: 每个消费者每分钟请求上限，0 或未设置 = 关闭

未配置任何 token 时保持本地无鉴权模式（127.0.0.1 默认绑定）。
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _token_matches(expected: str, actual: str) -> bool:
    return hmac.compare_digest(expected.encode(), actual.encode())


@dataclass
class AuthConfig:
    """从环境变量解析出的鉴权配置"""

    admin_token: str = ""
    consumer_tokens: dict[str, str] = field(default_factory=dict)
    rate_limit_per_min: int = 0

    @classmethod
    def from_env(cls) -> AuthConfig:
        raw_consumers = os.getenv("VMB_CONSUMER_TOKENS", "").strip()
        consumers: dict[str, str] = {}
        if raw_consumers:
            try:
                data = json.loads(raw_consumers)
                if isinstance(data, dict):
                    consumers = {
                        str(name): str(token)
                        for name, token in data.items()
                        if name and token
                    }
                else:
                    logger.warning("VMB_CONSUMER_TOKENS 必须是 JSON 对象，已忽略")
            except json.JSONDecodeError:
                logger.warning("VMB_CONSUMER_TOKENS 不是合法 JSON，已忽略")

        try:
            limit = int(os.getenv("VMB_RATE_LIMIT_PER_MIN", "0") or 0)
        except ValueError:
            limit = 0

        return cls(
            admin_token=os.getenv("VIDEOMIND_API_TOKEN", "").strip(),
            consumer_tokens=consumers,
            rate_limit_per_min=max(0, limit),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.admin_token or self.consumer_tokens)

    def authenticate(self, authorization: str) -> str | None:
        """返回消费者名；无效 token 返回 None。"""
        if not authorization.startswith("Bearer "):
            return None
        token = authorization[7:].strip()
        if not token:
            return None

        if self.admin_token and _token_matches(self.admin_token, token):
            return "admin"
        for name, expected in self.consumer_tokens.items():
            if _token_matches(expected, token):
                return name
        return None


class RateLimiter:
    """进程内滑动窗口限流（单实例；多副本部署需换共享存储）"""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, consumer: str) -> tuple[bool, float]:
        """返回 (是否放行, 建议 Retry-After 秒数)。"""
        if self.per_minute <= 0:
            return True, 0.0
        now = time.monotonic()
        cutoff = now - 60.0
        with self._lock:
            events = self._events.setdefault(consumer, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.per_minute:
                retry_after = max(0.0, 60.0 - (now - events[0]))
                return False, retry_after
            events.append(now)
            return True, 0.0
