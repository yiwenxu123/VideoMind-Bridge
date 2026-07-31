"""VideoMind Bridge GUI 应用程序入口"""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


class VideoMindApp(QApplication):
    """VideoMind Bridge GUI 应用程序"""

    def __init__(self, argv=None):
        if argv is None:
            argv = sys.argv
        super().__init__(argv)

        # 设置应用程序属性
        self.setApplicationName("VideoMind Bridge")
        self.setApplicationVersion("3.0.0")
        self.setOrganizationName("VideoMind")

        # 设置全局字体
        font = QFont("-apple-system", 13)  # macOS 系统字体
        if sys.platform == "win32":
            font = QFont("Segoe UI", 9)
        self.setFont(font)

        # 启用高分屏支持
        self.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

        # 设置应用程序在最后一个窗口关闭时不退出（支持托盘）
        self.setQuitOnLastWindowClosed(False)

        # 创建主窗口
        self.main_window = MainWindow()
        self.main_window.show()

    def run(self):
        """运行应用程序"""
        return self.exec()


def main():
    """GUI 入口函数"""
    app = VideoMindApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
