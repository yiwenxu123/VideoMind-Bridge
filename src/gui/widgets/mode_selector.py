"""处理模式选择组件 - 三级处理模式卡片"""

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QRadioButton, QButtonGroup,
    QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal

# 导入统一的 ProcessingMode
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from src.models.task import ProcessingMode


class ModeCard(QFrame):
    """模式选择卡片"""

    def __init__(self, icon: str, title: str, desc: str, mode: ProcessingMode, parent=None):
        super().__init__(parent)
        self.mode = mode
        self._setup_ui(icon, title, desc)

    def _setup_ui(self, icon: str, title: str, desc: str):
        """设置 UI"""
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet("""
            ModeCard {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
            }
            ModeCard:hover {
                border-color: #2196F3;
                background-color: #f5f5f5;
            }
            ModeCard[selected="true"] {
                border: 2px solid #2196F3;
                background-color: #e3f2fd;
            }
        """)

        # 紧凑的大小策略
        self.setMinimumSize(200, 80)
        self.setMaximumSize(280, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(10, 8, 10, 8)

        # 图标和标题行
        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 18px;")
        header_layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #333;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        # 单选按钮
        self.radio = QRadioButton()
        header_layout.addWidget(self.radio)

        layout.addLayout(header_layout)

        # 描述 - 紧凑显示
        desc_label = QLabel(desc)
        desc_label.setStyleSheet("color: #666; font-size: 11px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

    def set_selected(self, selected: bool):
        """设置选中状态"""
        self.radio.setChecked(selected)
        self.setProperty("selected", str(selected).lower())
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        """鼠标点击事件"""
        self.radio.setChecked(True)
        super().mousePressEvent(event)


class ModeSelector(QWidget):
    """处理模式选择组件"""

    mode_changed = Signal(ProcessingMode)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """设置 UI"""
        # 设置自身大小策略 - 使用 Fixed 确保高度不被压缩
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # 设置紧凑高度
        self.setFixedHeight(130)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        title_label = QLabel("⚙️ 处理模式")
        title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title_label)

        # 卡片容器 - 使用 Fixed 大小策略防止被压缩
        cards_container = QWidget()
        cards_container.setFixedHeight(100)
        cards_container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        cards_layout = QHBoxLayout(cards_container)
        cards_layout.setSpacing(10)
        cards_layout.setContentsMargins(0, 0, 0, 0)

        # Mode A: 完整处理
        self.card_full = ModeCard(
            icon="🧠",
            title="完整处理",
            desc="下载→转录→AI摘要→生成笔记",
            mode=ProcessingMode.FULL
        )
        cards_layout.addWidget(self.card_full)

        # Mode B: 仅下载
        self.card_download = ModeCard(
            icon="💾",
            title="仅下载",
            desc="仅下载原始视频+音频，跳过AI",
            mode=ProcessingMode.DOWNLOAD_ONLY
        )
        cards_layout.addWidget(self.card_download)

        # Mode C: 转录存档
        self.card_transcribe = ModeCard(
            icon="📝",
            title="转录存档",
            desc="生成SRT字幕，不调LLM省成本",
            mode=ProcessingMode.TRANSCRIBE_ONLY
        )
        cards_layout.addWidget(self.card_transcribe)

        layout.addWidget(cards_container)

        # 按钮组
        self.button_group = QButtonGroup(self)
        self.button_group.addButton(self.card_full.radio, 0)
        self.button_group.addButton(self.card_download.radio, 1)
        self.button_group.addButton(self.card_transcribe.radio, 2)

        # 默认选中 Mode A
        self.card_full.radio.setChecked(True)
        self.card_full.set_selected(True)

    def _connect_signals(self):
        """连接信号"""
        self.button_group.buttonClicked.connect(self._on_mode_changed)

        # 卡片点击也触发切换
        self.card_full.mousePressEvent = lambda e: self._select_card(self.card_full)
        self.card_download.mousePressEvent = lambda e: self._select_card(self.card_download)
        self.card_transcribe.mousePressEvent = lambda e: self._select_card(self.card_transcribe)

    def _select_card(self, card: ModeCard):
        """选中卡片"""
        card.radio.setChecked(True)
        self._on_mode_changed()

    def _on_mode_changed(self):
        """模式切换处理"""
        # 更新卡片样式
        self.card_full.set_selected(self.card_full.radio.isChecked())
        self.card_download.set_selected(self.card_download.radio.isChecked())
        self.card_transcribe.set_selected(self.card_transcribe.radio.isChecked())

        # 发送信号
        mode = self.get_current_mode()
        self.mode_changed.emit(mode)

    def get_current_mode(self) -> ProcessingMode:
        """获取当前选中的模式"""
        if self.card_full.radio.isChecked():
            return ProcessingMode.FULL
        elif self.card_download.radio.isChecked():
            return ProcessingMode.DOWNLOAD_ONLY
        else:
            return ProcessingMode.TRANSCRIBE_ONLY

    def set_mode(self, mode: ProcessingMode):
        """设置模式"""
        if mode == ProcessingMode.FULL:
            self.card_full.radio.setChecked(True)
        elif mode == ProcessingMode.DOWNLOAD_ONLY:
            self.card_download.radio.setChecked(True)
        elif mode == ProcessingMode.TRANSCRIBE_ONLY:
            self.card_transcribe.radio.setChecked(True)
        self._on_mode_changed()
