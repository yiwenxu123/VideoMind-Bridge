"""视频源 URL 输入组件"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QClipboard


class URLInputWidget(QWidget):
    """视频源 URL 输入组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        title_layout = QHBoxLayout()
        title_label = QLabel("📥 视频源 URL")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        # 批量模式切换按钮
        self.batch_button = QPushButton("+ 批量")
        self.batch_button.setCheckable(True)
        self.batch_button.setStyleSheet("""
            QPushButton {
                padding: 4px 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
            }
            QPushButton:checked {
                background: #e3f2fd;
                border-color: #2196F3;
            }
        """)
        title_layout.addWidget(self.batch_button)

        # 粘贴按钮
        self.paste_button = QPushButton("📋 粘贴")
        self.paste_button.setStyleSheet("""
            QPushButton {
                padding: 4px 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
            }
        """)
        title_layout.addWidget(self.paste_button)

        layout.addLayout(title_layout)

        # 单 URL 输入框
        self.single_input = QLineEdit()
        self.single_input.setPlaceholderText("粘贴视频链接，如: https://www.bilibili.com/video/BV1xx...")
        self.single_input.setStyleSheet("""
            QLineEdit {
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 6px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #2196F3;
            }
        """)
        layout.addWidget(self.single_input)

        # 批量输入框（多行）
        self.batch_input = QTextEdit()
        self.batch_input.setPlaceholderText("每行输入一个视频链接，支持批量处理...")
        self.batch_input.setStyleSheet("""
            QTextEdit {
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 6px;
                font-size: 13px;
            }
            QTextEdit:focus {
                border-color: #2196F3;
            }
        """)
        self.batch_input.setMaximumHeight(100)
        self.batch_input.hide()  # 默认隐藏
        layout.addWidget(self.batch_input)

        # 提示文本
        self.hint_label = QLabel("💡 支持 Bilibili、YouTube、小红书等平台")
        self.hint_label.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(self.hint_label)

    def _connect_signals(self):
        """连接信号"""
        # 批量模式切换
        self.batch_button.toggled.connect(self._on_batch_mode_changed)

        # 粘贴按钮
        self.paste_button.clicked.connect(self._on_paste)

        # 剪贴板自动检测
        self._check_clipboard()

    def _on_batch_mode_changed(self, checked: bool):
        """批量模式切换"""
        if checked:
            self.single_input.hide()
            self.batch_input.show()
            self.batch_button.setText("- 单条")
            self.hint_label.setText("💡 每行一个链接，将按顺序处理")
        else:
            self.batch_input.hide()
            self.single_input.show()
            self.batch_button.setText("+ 批量")
            self.hint_label.setText("💡 支持 Bilibili、YouTube、小红书等平台")

    def _on_paste(self):
        """从剪贴板粘贴"""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        text = clipboard.text()

        if self.batch_button.isChecked():
            # 批量模式
            current = self.batch_input.toPlainText()
            if current:
                self.batch_input.setPlainText(current + "\n" + text)
            else:
                self.batch_input.setPlainText(text)
        else:
            # 单条模式
            self.single_input.setText(text)

    def _check_clipboard(self):
        """检查剪贴板是否包含 URL"""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        text = clipboard.text()

        # 简单的 URL 检测
        if text and ("http://" in text or "https://" in text):
            # 如果输入框为空，自动填入
            if not self.single_input.text() and not self.batch_button.isChecked():
                # 提取第一个 URL
                import re
                url_match = re.search(r'https?://[^\s]+', text)
                if url_match:
                    self.single_input.setText(url_match.group())

    def get_url(self) -> str:
        """获取单个 URL"""
        if self.batch_button.isChecked():
            # 批量模式下返回第一行
            text = self.batch_input.toPlainText().strip()
            if text:
                return text.split('\n')[0].strip()
            return ""
        return self.single_input.text().strip()

    def get_urls(self) -> list:
        """获取所有 URL（批量模式）"""
        if self.batch_button.isChecked():
            text = self.batch_input.toPlainText().strip()
            if text:
                return [url.strip() for url in text.split('\n') if url.strip()]
            return []
        url = self.single_input.text().strip()
        return [url] if url else []

    def clear(self):
        """清空输入"""
        self.single_input.clear()
        self.batch_input.clear()

    def is_batch_mode(self) -> bool:
        """是否批量模式"""
        return self.batch_button.isChecked()
