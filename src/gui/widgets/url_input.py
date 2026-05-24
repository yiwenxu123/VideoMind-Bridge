"""视频源 URL 输入组件"""

import re
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class URLInputWidget(QWidget):
    """视频源 URL 输入组件 - 支持单条和批量输入"""

    # 信号：URL 列表变化时触发
    urls_changed = Signal(int)  # 参数：URL 数量

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

        # URL 计数标签
        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #666; font-size: 12px;")
        title_layout.addWidget(self.count_label)

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

        # 导入文件按钮（批量模式下显示）
        self.import_button = QPushButton("📁 导入")
        self.import_button.setStyleSheet("""
            QPushButton {
                padding: 4px 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
            }
        """)
        self.import_button.hide()
        title_layout.addWidget(self.import_button)

        # 清空按钮
        self.clear_button = QPushButton("🗑️ 清空")
        self.clear_button.setStyleSheet("""
            QPushButton {
                padding: 4px 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
            }
        """)
        title_layout.addWidget(self.clear_button)

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
        self.batch_input.setPlaceholderText(
            "每行输入一个视频链接，支持批量处理...\n"
            "示例：\n"
            "https://www.bilibili.com/video/BV1xx...\n"
            "https://www.youtube.com/watch?v=xxx...\n"
            "https://www.xiaohongshu.com/explore/xxx..."
        )
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
        self.batch_input.setMaximumHeight(150)
        self.batch_input.hide()
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

        # 导入文件按钮
        self.import_button.clicked.connect(self._on_import_file)

        # 清空按钮
        self.clear_button.clicked.connect(self._on_clear)

        # 文本变化时更新计数
        self.batch_input.textChanged.connect(self._update_url_count)
        self.single_input.textChanged.connect(self._update_url_count)

        # 剪贴板自动检测
        self._check_clipboard()

    def _on_batch_mode_changed(self, checked: bool):
        """批量模式切换"""
        if checked:
            self.single_input.hide()
            self.batch_input.show()
            self.import_button.show()
            self.batch_button.setText("- 单条")
            self.hint_label.setText("💡 每行一个链接，将按顺序处理")
            # 将单条输入的内容转移到批量输入
            single_url = self.single_input.text().strip()
            if single_url:
                current = self.batch_input.toPlainText().strip()
                if current:
                    self.batch_input.setPlainText(current + "\n" + single_url)
                else:
                    self.batch_input.setPlainText(single_url)
                self.single_input.clear()
        else:
            self.batch_input.hide()
            self.import_button.hide()
            self.single_input.show()
            self.batch_button.setText("+ 批量")
            self.hint_label.setText("💡 支持 Bilibili、YouTube、小红书等平台")
            # 将批量输入的第一行转移到单条输入
            urls = self.get_urls()
            if urls:
                self.single_input.setText(urls[0])
                if len(urls) > 1:
                    remaining = '\n'.join(urls[1:])
                    self.batch_input.setPlainText(remaining)

        self._update_url_count()

    def _on_paste(self):
        """从剪贴板粘贴"""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        text = clipboard.text()

        if not text:
            return

        # 提取所有 URL
        urls = self._extract_urls(text)

        if self.batch_button.isChecked():
            # 批量模式
            if urls:
                current = self.batch_input.toPlainText().strip()
                new_urls = '\n'.join(urls)
                if current:
                    self.batch_input.setPlainText(current + "\n" + new_urls)
                else:
                    self.batch_input.setPlainText(new_urls)
        else:
            # 单条模式 - 只取第一个 URL
            if urls:
                self.single_input.setText(urls[0])

    def _on_import_file(self):
        """从文件导入 URL"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "导入 URL 列表",
            str(Path.home()),
            "文本文件 (*.txt);;所有文件 (*.*)"
        )

        if not file_path:
            return

        try:
            with open(file_path, encoding='utf-8') as f:
                content = f.read()

            urls = self._extract_urls(content)
            if urls:
                current = self.batch_input.toPlainText().strip()
                new_urls = '\n'.join(urls)
                if current:
                    self.batch_input.setPlainText(current + "\n" + new_urls)
                else:
                    self.batch_input.setPlainText(new_urls)

                self.hint_label.setText(f"✅ 已从文件导入 {len(urls)} 个链接")
            else:
                self.hint_label.setText("⚠️ 文件中未找到有效的视频链接")

        except Exception as e:
            self.hint_label.setText(f"❌ 导入失败: {str(e)}")

    def _on_clear(self):
        """清空输入"""
        self.single_input.clear()
        self.batch_input.clear()
        self._update_url_count()

    def _extract_urls(self, text: str) -> list:
        """从文本中提取所有 URL"""
        # 支持常见的视频平台 URL 模式（包括短链接）
        url_pattern = r'https?://(?:[^\s<>"\']+\.)?(?:bilibili\.com|b23\.tv|youtube\.com|youtu\.be|xiaohongshu\.com|xhs\.link|douyin\.com|iesdouyin\.com|tiktok\.com)[^\s<>"\']*'
        urls = re.findall(url_pattern, text, re.IGNORECASE)
        return [url.strip() for url in urls if url.strip()]

    def _update_url_count(self):
        """更新 URL 计数显示"""
        count = len(self.get_urls())
        if count > 0:
            self.count_label.setText(f"({count} 个链接)")
            self.urls_changed.emit(count)
        else:
            self.count_label.setText("")

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
                urls = self._extract_urls(text)
                if urls:
                    self.single_input.setText(urls[0])

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
                # 提取每行的 URL
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                urls = []
                for line in lines:
                    # 如果整行是 URL，直接添加
                    if line.startswith('http://') or line.startswith('https://'):
                        urls.append(line)
                    else:
                        # 尝试从行中提取 URL
                        extracted = self._extract_urls(line)
                        urls.extend(extracted)
                return urls
            return []
        url = self.single_input.text().strip()
        return [url] if url else []

    def remove_first_url(self):
        """移除第一个 URL（用于批量处理时）"""
        if self.batch_button.isChecked():
            urls = self.get_urls()
            if len(urls) > 1:
                remaining = '\n'.join(urls[1:])
                self.batch_input.setPlainText(remaining)
            else:
                self.batch_input.clear()
        else:
            self.single_input.clear()
        self._update_url_count()

    def clear(self):
        """清空输入"""
        self.single_input.clear()
        self.batch_input.clear()
        self._update_url_count()

    def is_batch_mode(self) -> bool:
        """是否批量模式"""
        return self.batch_button.isChecked()

    def get_valid_urls(self) -> list:
        """获取有效的视频平台 URL"""
        urls = self.get_urls()
        valid_platforms = [
            'bilibili.com', 'b23.tv',
            'youtube.com', 'youtu.be',
            'xiaohongshu.com', 'xhs.link',
            'douyin.com', 'iesdouyin.com',
            'tiktok.com'
        ]

        valid_urls = []
        for url in urls:
            url_lower = url.lower()
            if any(platform in url_lower for platform in valid_platforms):
                valid_urls.append(url)

        return valid_urls
