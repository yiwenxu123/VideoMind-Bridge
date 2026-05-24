"""统一日志模块"""

import logging
import os
import sys
from pathlib import Path

LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_LOG_LEVEL_NAME = os.getenv("VIDEOMIND_LOG_LEVEL", "INFO").upper()
_LOG_LEVEL = LOG_LEVELS.get(_LOG_LEVEL_NAME, logging.INFO)

_initialized = False


def setup_logging(
    level: int = logging.INFO,
    log_file: Path | None = None,
    format_string: str | None = None
) -> None:
    """
    配置全局日志系统

    Args:
        level: 日志级别 (默认 INFO)
        log_file: 日志文件路径 (默认 None，不写入文件)
        format_string: 自定义格式字符串
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    formatter = logging.Formatter(format_string)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def _ensure_initialized() -> None:
    """确保日志系统已初始化"""
    global _initialized
    if not _initialized:
        setup_logging(level=_LOG_LEVEL)
        _initialized = True


def get_logger(name: str) -> logging.Logger:
    """
    获取命名日志记录器

    Args:
        name: 日志记录器名称，建议使用 __name__

    Returns:
        logging.Logger: 配置好的日志记录器
    """
    _ensure_initialized()
    return logging.getLogger(name)


def set_log_level(level_name: str) -> None:
    """设置全局日志级别"""
    level = LOG_LEVELS.get(level_name.upper(), logging.INFO)
    logging.getLogger().setLevel(level)


_ensure_initialized()
