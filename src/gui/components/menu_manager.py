"""菜单栏管理组件"""

from PySide6.QtWidgets import QMenuBar, QMenu, QMessageBox, QDialog
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction

from ...utils import get_logger

logger = get_logger(__name__)


class MenuManager(QObject):
    """菜单栏管理器"""

    # 信号
    settings_requested = Signal()
    about_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self._parent = parent

    def setup(self) -> QMenuBar:
        """
        设置菜单栏

        Returns:
            QMenuBar: 配置好的菜单栏
        """
        menubar = QMenuBar(self._parent)

        # 文件菜单
        self._setup_file_menu(menubar)

        # 帮助菜单
        self._setup_help_menu(menubar)

        return menubar

    def _setup_file_menu(self, menubar: QMenuBar) -> None:
        """设置文件菜单"""
        file_menu = menubar.addMenu("文件")

        # 设置菜单项
        settings_action = QAction("设置", self._parent)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._on_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        # 退出菜单项
        exit_action = QAction("退出", self._parent)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self._on_quit)
        file_menu.addAction(exit_action)

    def _setup_help_menu(self, menubar: QMenuBar) -> None:
        """设置帮助菜单"""
        help_menu = menubar.addMenu("帮助")

        about_action = QAction("关于", self._parent)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _on_settings(self) -> None:
        """打开设置"""
        self.settings_requested.emit()

    def _on_about(self) -> None:
        """显示关于对话框"""
        self.about_requested.emit()

    def _on_quit(self) -> None:
        """退出应用"""
        self.quit_requested.emit()

    def show_about_dialog(self, parent=None) -> None:
        """显示关于对话框"""
        QMessageBox.about(
            parent or self._parent,
            "关于 VideoMind Bridge",
            "<h2>VideoMind Bridge</h2>"
            "<p>版本: 0.1.0</p>"
            "<p>一个智能视频处理工具，支持下载、转录、AI 摘要和导出。</p>"
            "<p>支持平台: Bilibili, YouTube, 抖音, 小红书等</p>"
        )
