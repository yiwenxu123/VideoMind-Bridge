"""系统托盘管理组件"""


from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ...utils import get_logger
from ...utils.platform_utils import PlatformHelper

logger = get_logger(__name__)


class TrayManager(QObject):
    """系统托盘图标管理器"""

    # 信号
    show_window_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._parent = parent
        self._tray_icon: QSystemTrayIcon | None = None

    def setup(self) -> bool:
        """
        设置系统托盘图标

        Returns:
            bool: 是否成功创建托盘图标
        """
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("系统不支持托盘图标，无法创建托盘图标")
            return False

        logger.info("正在创建托盘图标...")

        # 创建托盘图标
        self._tray_icon = QSystemTrayIcon(self._parent)
        self._tray_icon.setToolTip("VideoMind Bridge")

        # 加载图标
        self._load_icon()

        # 创建托盘菜单
        self._setup_menu()

        # 连接点击信号
        self._tray_icon.activated.connect(self._on_tray_activated)

        # 显示托盘图标
        self._tray_icon.show()

        # 验证托盘图标是否成功显示
        if self._tray_icon.isVisible():
            logger.info("托盘图标已显示")
            return True
        else:
            logger.warning("托盘图标创建但未显示（可能在 macOS 菜单栏被隐藏）")
            return False

    def _load_icon(self) -> None:
        """加载托盘图标"""
        from pathlib import Path

        if self._tray_icon is None:
            return

        # 尝试加载自定义图标
        icon_path = Path(__file__).parent.parent.parent / "assets" / "icon.svg"
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            logger.info(f"使用自定义图标: {icon_path}")
        else:
            # 回退到系统标准图标
            icon = QApplication.style().standardIcon(
                QApplication.style().StandardPixmap.SP_ComputerIcon
            )
            logger.warning("自定义图标不存在，使用系统默认图标")

        # 在 macOS 上，设置图标为模板模式
        if PlatformHelper.is_macos():
            icon.setIsMask(True)

        self._tray_icon.setIcon(icon)

        # macOS 特殊处理
        if PlatformHelper.is_macos():
            self._tray_icon.setVisible(True)

    def _setup_menu(self) -> None:
        """设置托盘菜单"""
        if self._tray_icon is None:
            return

        tray_menu = QMenu()

        # 显示窗口动作
        show_action = QAction("显示窗口", self._parent)
        show_action.triggered.connect(self._on_show_window)
        tray_menu.addAction(show_action)

        tray_menu.addSeparator()

        # 退出动作
        quit_action = QAction("退出", self._parent)
        quit_action.triggered.connect(self._on_quit)
        tray_menu.addAction(quit_action)

        self._tray_icon.setContextMenu(tray_menu)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """托盘图标被激活"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window_requested.emit()

    def _on_show_window(self) -> None:
        """显示窗口"""
        self.show_window_requested.emit()

    def _on_quit(self) -> None:
        """退出应用"""
        self.quit_requested.emit()

    def show_message(self, title: str, message: str, icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information) -> None:
        """显示托盘消息"""
        if self._tray_icon and self._tray_icon.isVisible():
            self._tray_icon.showMessage(title, message, icon)

    def set_visible(self, visible: bool) -> None:
        """设置托盘图标可见性"""
        if self._tray_icon:
            self._tray_icon.setVisible(visible)

    def hide(self) -> None:
        """隐藏托盘图标"""
        if self._tray_icon:
            self._tray_icon.hide()

    def is_available(self) -> bool:
        """检查系统是否支持托盘图标"""
        return QSystemTrayIcon.isSystemTrayAvailable()

    def is_visible(self) -> bool:
        """检查托盘图标是否可见"""
        return self._tray_icon is not None and self._tray_icon.isVisible()
