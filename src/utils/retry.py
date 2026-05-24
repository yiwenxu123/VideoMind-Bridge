"""重试机制 - 自动重试装饰器和策略"""

import random
import time
from collections.abc import Callable
from enum import Enum
from functools import wraps
from typing import Any

from . import get_logger
from .exceptions import (
    AIError,
    DownloadError,
    NetworkError,
    RetryableError,
    ServiceUnavailableError,
    TimeoutError,
    TranscribeError,
)

logger = get_logger(__name__)


class RetryStrategy(Enum):
    """重试策略"""
    FIXED = "fixed"           # 固定间隔
    EXPONENTIAL = "exponential"  # 指数退避
    LINEAR = "linear"         # 线性增长


class RetryConfig:
    """重试配置"""

    # 默认配置
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_BASE_DELAY = 1.0  # 秒
    DEFAULT_MAX_DELAY = 60.0  # 秒
    DEFAULT_JITTER = 0.1      # 抖动范围（10%）

    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        jitter: float = DEFAULT_JITTER,
        retryable_exceptions: tuple[type[Exception], ...] = (RetryableError,),
        on_retry: Callable[[Exception, int, float], None] | None = None
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.strategy = strategy
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions
        self.on_retry = on_retry

    def calculate_delay(self, attempt: int) -> float:
        """计算重试延迟"""
        if self.strategy == RetryStrategy.FIXED:
            delay = self.base_delay
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.base_delay * attempt
        else:  # EXPONENTIAL
            delay = self.base_delay * (2 ** (attempt - 1))

        # 应用最大延迟限制
        delay = min(delay, self.max_delay)

        # 添加抖动（避免惊群效应）
        if self.jitter > 0:
            jitter_amount = delay * self.jitter
            delay += random.uniform(-jitter_amount, jitter_amount)

        return max(0.1, delay)  # 最小延迟 0.1 秒


# 针对不同错误类型的默认配置
DOWNLOAD_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=2.0,
    max_delay=30.0,
    strategy=RetryStrategy.EXPONENTIAL,
    retryable_exceptions=(
        NetworkError, TimeoutError, ServiceUnavailableError,
        DownloadError  # 某些下载错误也可重试
    )
)

TRANSCRIBE_RETRY_CONFIG = RetryConfig(
    max_retries=2,
    base_delay=1.0,
    max_delay=10.0,
    strategy=RetryStrategy.EXPONENTIAL,
    retryable_exceptions=(
        NetworkError, TimeoutError, ServiceUnavailableError,
        TranscribeError
    )
)

AI_RETRY_CONFIG = RetryConfig(
    max_retries=3,
    base_delay=1.0,
    max_delay=30.0,
    strategy=RetryStrategy.EXPONENTIAL,
    retryable_exceptions=(
        NetworkError, TimeoutError, ServiceUnavailableError,
        AIError
    )
)


def retry_with_config(config: RetryConfig):
    """
    重试装饰器工厂

    Args:
        config: 重试配置

    Usage:
        @retry_with_config(DOWNLOAD_RETRY_CONFIG)
        def download_video(url: str) -> DownloadResult:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(1, config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt >= config.max_retries:
                        logger.warning(
                            f"{func.__name__} 在 {config.max_retries} 次尝试后仍然失败: {e}"
                        )
                        raise

                    delay = config.calculate_delay(attempt)
                    logger.info(
                        f"{func.__name__} 第 {attempt} 次尝试失败: {e}，"
                        f"{delay:.1f} 秒后重试..."
                    )

                    # 调用重试回调（如果有）
                    if config.on_retry:
                        config.on_retry(e, attempt, delay)

                    time.sleep(delay)

            # 不应该到达这里，但为了类型检查
            raise last_exception if last_exception else RuntimeError("重试逻辑异常")

        return wrapper
    return decorator


def retry(
    max_retries: int = RetryConfig.DEFAULT_MAX_RETRIES,
    base_delay: float = RetryConfig.DEFAULT_BASE_DELAY,
    max_delay: float = RetryConfig.DEFAULT_MAX_DELAY,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
    retryable_exceptions: tuple[type[Exception], ...] = (RetryableError,),
    on_retry: Callable[[Exception, int, float], None] | None = None
):
    """
    简化版重试装饰器

    Usage:
        @retry(max_retries=3, base_delay=1.0)
        def my_function():
            ...
    """
    config = RetryConfig(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=max_delay,
        strategy=strategy,
        retryable_exceptions=retryable_exceptions,
        on_retry=on_retry
    )
    return retry_with_config(config)


class RetryableOperation:
    """
    可重试操作类 - 用于更复杂的重试场景

    支持：
    - 动态修改重试配置
    - 手动触发重试
    - 重试状态跟踪
    """

    def __init__(
        self,
        operation: Callable,
        config: RetryConfig,
        name: str | None = None
    ):
        self.operation = operation
        self.config = config
        self.name = name or operation.__name__
        self.attempt_count = 0
        self.last_exception = None
        self.is_successful = False

    def execute(self, *args, **kwargs) -> Any:
        """执行操作（带重试）"""
        self.attempt_count = 0
        self.last_exception = None
        self.is_successful = False

        for attempt in range(1, self.config.max_retries + 1):
            self.attempt_count = attempt

            try:
                result = self.operation(*args, **kwargs)
                self.is_successful = True
                logger.info(f"{self.name} 在第 {attempt} 次尝试成功")
                return result

            except self.config.retryable_exceptions as e:
                self.last_exception = e

                if attempt >= self.config.max_retries:
                    logger.error(
                        f"{self.name} 在 {self.config.max_retries} 次尝试后失败: {e}"
                    )
                    raise

                delay = self.config.calculate_delay(attempt)
                logger.warning(
                    f"{self.name} 第 {attempt} 次尝试失败: {e}，"
                    f"{delay:.1f} 秒后重试..."
                )

                if self.config.on_retry:
                    self.config.on_retry(e, attempt, delay)

                time.sleep(delay)

        raise self.last_exception if self.last_exception else RuntimeError("重试逻辑异常")

    def can_retry(self) -> bool:
        """检查是否还可以重试"""
        return self.attempt_count < self.config.max_retries and not self.is_successful

    def get_status(self) -> dict:
        """获取重试状态"""
        return {
            "name": self.name,
            "attempt_count": self.attempt_count,
            "max_retries": self.config.max_retries,
            "is_successful": self.is_successful,
            "last_exception": str(self.last_exception) if self.last_exception else None,
            "can_retry": self.can_retry()
        }


def is_retryable_error(error: Exception) -> bool:
    """
    检查错误是否可重试

    Args:
        error: 异常对象

    Returns:
        bool: 是否可重试
    """
    # 可重试错误类型
    retryable_types = (
        RetryableError,
        NetworkError,
        ServiceUnavailableError,
        TimeoutError,
    )

    if isinstance(error, retryable_types):
        return True

    # 检查特定错误代码
    if hasattr(error, 'error_code'):
        retryable_codes = {
            # 下载错误
            'NETWORK_ERROR', 'RATE_LIMITED', 'DOWNLOAD_FAILED',
            # 转录错误
            'MODEL_LOAD_FAILED', 'TRANSCRIBE_FAILED',
            # AI 错误
            'RATE_LIMIT_EXCEEDED', 'TIMEOUT', 'GENERATION_FAILED'
        }
        if error.error_code in retryable_codes:
            return True

    return False
