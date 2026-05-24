"""平台相关工具函数 - 处理跨平台操作"""

import logging
import platform
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class PlatformHelper:
    """平台辅助类"""

    @staticmethod
    def get_system() -> str:
        """获取操作系统类型"""
        return platform.system()

    @staticmethod
    def is_macos() -> bool:
        """是否为 macOS"""
        return platform.system() == "Darwin"

    @staticmethod
    def is_windows() -> bool:
        """是否为 Windows"""
        return platform.system() == "Windows"

    @staticmethod
    def is_linux() -> bool:
        """是否为 Linux"""
        return platform.system() == "Linux"

    @staticmethod
    def open_application(app_name: str) -> bool:
        """
        打开应用程序

        Args:
            app_name: 应用程序名称

        Returns:
            bool: 是否成功打开
        """
        system = PlatformHelper.get_system()
        try:
            if system == "Darwin":
                subprocess.run(["open", "-a", app_name], check=True)
            elif system == "Windows":
                subprocess.run(["start", app_name], shell=True, check=True)
            else:
                subprocess.run([app_name], check=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(f"打开应用失败 {app_name}: {e}")
            return False

    @staticmethod
    def open_path(path: Path) -> bool:
        """
        使用系统默认程序打开路径（文件或目录）

        Args:
            path: 要打开的路径

        Returns:
            bool: 是否成功打开
        """
        if not path.exists():
            logger.warning(f"路径不存在: {path}")
            return False

        system = PlatformHelper.get_system()
        try:
            if system == "Darwin":
                subprocess.run(["open", str(path)], check=True)
            elif system == "Windows":
                subprocess.run(["explorer", str(path)], check=True)
            else:
                subprocess.run(["xdg-open", str(path)], check=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(f"打开路径失败 {path}: {e}")
            return False

    @staticmethod
    def open_url(url: str) -> bool:
        """
        使用默认浏览器打开 URL

        Args:
            url: 要打开的 URL

        Returns:
            bool: 是否成功打开
        """
        import webbrowser
        try:
            webbrowser.open(url)
            return True
        except Exception as e:
            logger.warning(f"打开 URL 失败 {url}: {e}")
            return False

    @staticmethod
    def get_tray_location_hint() -> str:
        """
        获取托盘位置提示

        Returns:
            str: 托盘位置描述
        """
        if PlatformHelper.is_macos():
            return "屏幕右上角的菜单栏"
        elif PlatformHelper.is_windows():
            return "屏幕右下角的系统托盘区"
        else:
            return "系统托盘区"


class URLValidator:
    """URL 验证器"""

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """
        验证 URL 是否有效

        Args:
            url: 要验证的 URL

        Returns:
            bool: 是否有效
        """
        if not url or not isinstance(url, str):
            return False

        url = url.strip()
        if not url:
            return False

        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            # 检查是否有 scheme 和 netloc
            if not parsed.scheme or not parsed.netloc:
                return False

            # 检查 scheme 是否合法
            valid_schemes = ['http', 'https', 'ftp', 'ftps']
            if parsed.scheme.lower() not in valid_schemes:
                return False

            return True
        except Exception:
            return False

    @staticmethod
    def get_platform_from_url(url: str) -> str | None:
        """
        从 URL 识别视频平台

        Args:
            url: 视频 URL

        Returns:
            Optional[str]: 平台名称，无法识别返回 None
        """
        if not URLValidator.is_valid_url(url):
            return None

        url_lower = url.lower()

        platforms = {
            'bilibili': ['bilibili.com', 'b23.tv'],
            'youtube': ['youtube.com', 'youtu.be'],
            'douyin': ['douyin.com'],
            'tiktok': ['tiktok.com'],
            'xiaohongshu': ['xiaohongshu.com'],
        }

        for platform_name, domains in platforms.items():
            for domain in domains:
                if domain in url_lower:
                    return platform_name

        return None


class ProgressCalculator:
    """进度计算器"""

    @staticmethod
    def calculate_progress(
        current_step: int,
        total_steps: int,
        step_progress: float,
        start_percent: int,
        end_percent: int
    ) -> int:
        """
        计算整体进度

        Args:
            current_step: 当前步骤（从 0 开始）
            total_steps: 总步骤数
            step_progress: 当前步骤进度（0-100）
            start_percent: 整体起始百分比
            end_percent: 整体结束百分比

        Returns:
            int: 整体进度百分比
        """
        if total_steps <= 0:
            return start_percent

        # 每个步骤占的百分比
        step_range = (end_percent - start_percent) / total_steps

        # 当前步骤的基础进度
        base_progress = start_percent + (current_step * step_range)

        # 加上当前步骤的进度
        current_progress = (step_progress / 100) * step_range

        return int(base_progress + current_progress)
