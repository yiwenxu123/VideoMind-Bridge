"""内容提取器抽象基类

所有平台提取器继承此类，实现 is_available() + supports() + extract() 接口。
路由层通过 should_try() 自动决策是否尝试当前提取器。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from ..models import CostTier, ExtractResult


class ContentExtractor(ABC):
    """内容提取器抽象基类"""

    # 平台名称
    platform_name: str = "unknown"

    # 成本等级
    _cost_tier: CostTier = CostTier.FREE

    # URL 匹配正则 (子类覆写)
    url_pattern: re.Pattern = re.compile(r"^https?://")

    @abstractmethod
    def extract(self, url: str) -> ExtractResult:
        """从 URL 提取内容

        Args:
            url: 视频/内容链接

        Returns:
            ExtractResult: 提取结果
        """
        ...

    def is_available(self) -> bool:
        """当前提取器是否可用 (Token/Key 是否有效)

        子类可覆写以检查特定凭证。
        默认返回 True (无需凭证的提取器).
        """
        return True

    def supports(self, url: str) -> bool:
        """是否支持指定 URL

        默认使用 url_pattern 正则搜索匹配, 子类可覆写。
        """
        return bool(self.url_pattern.search(url))

    def should_try(self, url: str, max_cost: CostTier | None = None) -> bool:
        """是否应该尝试此提取器

        路由层调用此方法自动决策。
        检查顺序: 可用性 → URL 支持 → 成本限制.
        """
        if not self.is_available():
            return False
        if not self.supports(url):
            return False
        if max_cost is not None:
            cost_order = {
                CostTier.FREE: 0,
                CostTier.CHEAP: 1,
                CostTier.PAID: 2,
                CostTier.EXPENSIVE: 3,
                CostTier.PREMIUM: 4,
            }
            if cost_order.get(self.cost_tier(), 99) > cost_order.get(max_cost, 99):
                return False
        return True

    def cost_tier(self) -> CostTier:
        """获取此提取器的成本等级"""
        return self._cost_tier

    def _normalize_url(self, url: str) -> str:
        """标准化 URL (移除追踪参数等)"""
        return url.split("?")[0] if "?" in url else url

    def _resolve_api_key(self, key_name: str) -> str | None:
        """从配置系统获取 API Key: ConfigManager → 环境变量 → None

        子类在有 API Key 需求时调用此方法代替直接 os.getenv()。
        使用 ConfigManager 统一管理, 支持密钥环加密存储。
        """
        from ...services.config_manager import get_config_manager
        return get_config_manager().get_extractor_key(key_name)

    def _resolve_short_url(self, url: str, timeout: float = 10.0) -> str | None:
        """解析短链接为最终 URL（跟随重定向）

        使用子类构造的 self._client（httpx.Client）；无客户端时返回 None。
        """
        client = getattr(self, "_client", None)
        if client is None:
            return None
        try:
            resp = client.get(url, follow_redirects=True, timeout=timeout)
            return str(resp.url)
        except Exception:
            return None
