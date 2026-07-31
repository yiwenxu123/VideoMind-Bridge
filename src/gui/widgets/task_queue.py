"""任务队列可视化组件"""

import logging
from dataclasses import dataclass
from enum import Enum, auto
from uuid import uuid4

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .mode_selector import ProcessingMode

logger = logging.getLogger(__name__)

# 运行中状态按钮文本 (统一常量, 避免文本判断漂移)
RUNNING_BUTTON_TEXT = "暂停"


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = auto()       # 等待中
    DOWNLOADING = auto()   # 下载中
    TRANSCRIBING = auto()  # 转录中
    AI_PROCESSING = auto() # AI处理中
    AI_RETRYING = auto()   # AI重试中
    EXPORTING = auto()     # 导出中
    PAUSED = auto()        # 已暂停
    COMPLETED = auto()     # 已完成
    FAILED = auto()        # 失败
    CANCELLED = auto()     # 已取消


@dataclass
class TaskInfo:
    """任务信息"""
    id: str
    url: str
    title: str
    mode: ProcessingMode
    targets: list
    status: TaskStatus
    progress: int
    message: str
    time_estimate: str = ""  # 预估时间消息
    video_duration: int = 0  # 视频时长（秒）
    platform: str = ""  # 视频平台


class TaskItemWidget(QFrame):
    """任务项组件"""

    cancel_clicked = Signal(str)  # 任务ID
    delete_clicked = Signal(str)  # 任务ID
    pause_clicked = Signal(str)   # 任务ID
    resume_clicked = Signal(str)  # 任务ID

    def __init__(self, task_info: TaskInfo, parent=None):
        super().__init__(parent)
        self.task_id = task_info.id
        self.task_info = task_info  # 保存完整任务信息
        self._setup_ui(task_info)

    def _setup_ui(self, task_info: TaskInfo):
        """设置 UI"""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            TaskItemWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                margin: 2px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # 第一行：标题和状态
        header_layout = QHBoxLayout()

        # 状态图标
        status_icons = {
            TaskStatus.PENDING: "⏸️",
            TaskStatus.DOWNLOADING: "⬇️",
            TaskStatus.TRANSCRIBING: "🎤",
            TaskStatus.AI_PROCESSING: "🤖",
            TaskStatus.AI_RETRYING: "🔄",
            TaskStatus.EXPORTING: "📤",
            TaskStatus.PAUSED: "⏸️",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.FAILED: "❌",
            TaskStatus.CANCELLED: "🚫",
        }
        status_icon = status_icons.get(task_info.status, "⏸️")

        self.status_label = QLabel(f"{status_icon}")
        self.status_label.setStyleSheet("font-size: 16px;")
        header_layout.addWidget(self.status_label)

        # 标题
        title = task_info.title or "获取中..."
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.title_label.setWordWrap(True)
        header_layout.addWidget(self.title_label, stretch=1)

        # 操作按钮
        self.action_button = QPushButton()
        self.action_button.setMaximumWidth(60)
        self.action_button.setStyleSheet("""
            QPushButton {
                padding: 4px 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 12px;
            }
        """)
        header_layout.addWidget(self.action_button)

        # 删除按钮（×）- 用于失败任务
        self.delete_button = QPushButton("×")
        self.delete_button.setMaximumWidth(30)
        self.delete_button.setStyleSheet("""
            QPushButton {
                padding: 4px 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                color: #666;
            }
            QPushButton:hover {
                background-color: #ffebee;
                color: #f44336;
                border-color: #f44336;
            }
        """)
        self.delete_button.setToolTip("删除任务")
        self.delete_button.clicked.connect(self._on_delete_clicked)
        header_layout.addWidget(self.delete_button)

        layout.addLayout(header_layout)

        # 第二行：进度条和状态信息
        progress_layout = QHBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(task_info.progress)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
                border-radius: 4px;
            }
        """)
        progress_layout.addWidget(self.progress_bar, stretch=1)

        # 状态文本
        self.message_label = QLabel(task_info.message)
        self.message_label.setStyleSheet("color: #666; font-size: 12px; min-width: 100px;")
        progress_layout.addWidget(self.message_label)

        layout.addLayout(progress_layout)

        # 第三行：预估时间
        self.time_estimate_label = QLabel(task_info.time_estimate)
        self.time_estimate_label.setStyleSheet("color: #888; font-size: 11px; margin-top: 2px;")
        layout.addWidget(self.time_estimate_label)

        # 连接信号
        self.action_button.clicked.connect(self._on_action_clicked)

        # 更新按钮状态
        self._update_button_state(task_info.status)

    def _update_button_state(self, status: TaskStatus):
        """更新按钮状态"""
        if status == TaskStatus.PAUSED:
            # 暂停状态：显示"恢复"和"删除"按钮
            self.action_button.setText("恢复")
            self.delete_button.setVisible(True)
        elif status in [TaskStatus.PENDING, TaskStatus.DOWNLOADING,
                      TaskStatus.TRANSCRIBING, TaskStatus.AI_PROCESSING, TaskStatus.AI_RETRYING, TaskStatus.EXPORTING]:
            # 运行中状态：显示"暂停"，隐藏删除按钮
            self.action_button.setText(RUNNING_BUTTON_TEXT)
            self.delete_button.setVisible(False)
        else:
            # 失败/已完成/已取消：显示"删除"按钮
            self.action_button.setText("删除")
            self.delete_button.setVisible(True)

    def _on_action_clicked(self):
        """操作按钮点击"""
        text = self.action_button.text()
        if text == RUNNING_BUTTON_TEXT:
            self.pause_clicked.emit(self.task_id)
        elif text == "恢复":
            self.resume_clicked.emit(self.task_id)
        elif text == "删除":
            self.delete_clicked.emit(self.task_id)

    def _on_delete_clicked(self):
        """删除按钮点击"""
        self.delete_clicked.emit(self.task_id)

    def update_progress(self, progress: int, message: str, time_estimate: str = ""):
        """更新进度"""
        self.progress_bar.setValue(progress)
        self.message_label.setText(message)
        if time_estimate:
            self.time_estimate_label.setText(time_estimate)

    def update_time_estimate(self, time_estimate: str):
        """更新预估时间"""
        self.time_estimate_label.setText(time_estimate)

    def update_status(self, status: TaskStatus, message: str = ""):
        """更新状态"""
        status_icons = {
            TaskStatus.PENDING: "⏸️",
            TaskStatus.DOWNLOADING: "⬇️",
            TaskStatus.TRANSCRIBING: "🎤",
            TaskStatus.AI_PROCESSING: "🤖",
            TaskStatus.AI_RETRYING: "🔄",
            TaskStatus.EXPORTING: "📤",
            TaskStatus.PAUSED: "⏸️",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.FAILED: "❌",
            TaskStatus.CANCELLED: "🚫",
        }
        status_icon = status_icons.get(status, "⏸️")
        self.status_label.setText(f"{status_icon}")

        # 更新任务信息中的状态
        self.task_info.status = status

        if message:
            self.message_label.setText(message)

        self._update_button_state(status)

    def update_title(self, title: str):
        """更新标题"""
        self.title_label.setText(title)

    def get_task_info(self) -> TaskInfo:
        """获取任务信息"""
        return self.task_info


class TaskQueueWidget(QWidget):
    """任务队列可视化组件"""

    task_cancelled = Signal(str)  # 任务ID
    task_deleted = Signal(str)    # 任务ID
    task_paused = Signal(str)     # 任务ID
    task_resumed = Signal(str)    # 任务ID

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tasks = {}  # task_id -> TaskItemWidget
        self._setup_ui()

    def _setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        title_layout = QHBoxLayout()
        self.title_label = QLabel("📋 任务队列")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(self.title_label)

        self.count_label = QLabel("(0 个待处理)")
        self.count_label.setStyleSheet("color: #888;")
        title_layout.addWidget(self.count_label)

        title_layout.addStretch()

        # 清空按钮
        self.clear_button = QPushButton("🗑️ 清空已完成")
        self.clear_button.setStyleSheet("""
            QPushButton {
                padding: 4px 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 12px;
            }
        """)
        self.clear_button.clicked.connect(self._on_clear_completed)
        title_layout.addWidget(self.clear_button)

        layout.addLayout(title_layout)

        # 任务列表
        self.list_widget = EmptyLabelListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 6px;
                background-color: #f5f5f5;
            }
            QListWidget::item {
                padding: 0px;
                margin: 4px;
            }
        """)
        self.list_widget.setSpacing(4)
        layout.addWidget(self.list_widget)

        # 空状态提示
        self.empty_label = QLabel("暂无任务，添加视频链接开始处理")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #888; padding: 40px;")
        self.list_widget.setEmptyLabel(self.empty_label)

    def add_task(self, url: str, mode: ProcessingMode, targets: list) -> str:
        """添加任务"""
        task_id = str(uuid4())[:8]

        task_info = TaskInfo(
            id=task_id,
            url=url,
            title=url[:50] + "..." if len(url) > 50 else url,
            mode=mode,
            targets=targets,
            status=TaskStatus.PENDING,
            progress=0,
            message="等待中"
        )

        # 创建任务项
        task_widget = TaskItemWidget(task_info)
        task_widget.cancel_clicked.connect(self._on_task_cancel)
        task_widget.delete_clicked.connect(self._on_task_delete)
        task_widget.pause_clicked.connect(self._on_task_pause)
        task_widget.resume_clicked.connect(self._on_task_resume)

        # 添加到列表 - 先添加item，再设置widget，避免渲染时序问题
        item = QListWidgetItem()
        # 使用固定大小，避免动态计算sizeHint导致的问题
        item.setSizeHint(QSize(400, 80))
        self.list_widget.addItem(item)

        # 使用QTimer延迟设置widget，确保item已完全初始化
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self._set_task_widget(item, task_widget))

        # 保存引用
        self.tasks[task_id] = task_widget

        # 更新计数
        self._update_count()

        return task_id

    def _set_task_widget(self, item: QListWidgetItem, widget: TaskItemWidget):
        """延迟设置任务widget，避免渲染时序问题"""
        try:
            self.list_widget.setItemWidget(item, widget)
        except Exception as e:
            logger.debug(f"Error setting task widget: {e}")

    def update_task_progress(self, task_id: str, progress: int, message: str, time_estimate: str = ""):
        """更新任务进度"""
        if task_id in self.tasks:
            self.tasks[task_id].update_progress(progress, message, time_estimate)

    def update_task_time_estimate(self, task_id: str, time_estimate: str):
        """更新任务预估时间"""
        if task_id in self.tasks:
            self.tasks[task_id].update_time_estimate(time_estimate)

    def update_task_status(self, task_id: str, status: TaskStatus, message: str = ""):
        """更新任务状态"""
        if task_id in self.tasks:
            self.tasks[task_id].update_status(status, message)
            self._update_count()

    def update_task_title(self, task_id: str, title: str):
        """更新任务标题"""
        if task_id in self.tasks:
            self.tasks[task_id].update_title(title)

    def get_task_info(self, task_id: str) -> TaskInfo | None:
        """获取任务信息"""
        if task_id in self.tasks:
            return self.tasks[task_id].get_task_info()
        return None

    def remove_task(self, task_id: str):
        """移除任务"""
        if task_id in self.tasks:
            # 找到对应的 QListWidgetItem
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                widget = self.list_widget.itemWidget(item)
                if widget and widget.task_id == task_id:
                    self.list_widget.takeItem(i)
                    break

            del self.tasks[task_id]
            self._update_count()

    def has_running_tasks(self) -> bool:
        """是否有运行中的任务"""
        for task_widget in self.tasks.values():
            # 运行中任务的操作按钮为 RUNNING_BUTTON_TEXT
            if task_widget.action_button.text() == RUNNING_BUTTON_TEXT:
                return True
        return False

    def _update_count(self):
        """更新任务计数"""
        total = len(self.tasks)
        pending = sum(1 for w in self.tasks.values() if w.action_button.text() == RUNNING_BUTTON_TEXT)

        if pending > 0:
            self.count_label.setText(f"({pending} 个进行中, {total} 个总计)")
        else:
            self.count_label.setText(f"({total} 个任务)")

    def _on_task_cancel(self, task_id: str):
        """任务取消"""
        self.task_cancelled.emit(task_id)
        self.update_task_status(task_id, TaskStatus.CANCELLED, "已取消")

    def _on_task_delete(self, task_id: str):
        """任务删除"""
        self.task_deleted.emit(task_id)
        self.remove_task(task_id)

    def _on_task_pause(self, task_id: str):
        """任务暂停"""
        self.task_paused.emit(task_id)
        self.update_task_status(task_id, TaskStatus.PAUSED, "已暂停")

    def _on_task_resume(self, task_id: str):
        """任务恢复"""
        self.task_resumed.emit(task_id)
        # 恢复时状态会由工作线程更新，这里先显示"恢复中"
        self.update_task_status(task_id, TaskStatus.PENDING, "恢复中...")

    def _on_clear_completed(self):
        """清空已完成和已取消的任务"""
        to_remove = []
        for task_id, task_widget in self.tasks.items():
            text = task_widget.action_button.text()
            if text == "删除":
                to_remove.append(task_id)

        for task_id in to_remove:
            self.remove_task(task_id)


# 扩展 QListWidget 支持空状态标签
class EmptyLabelListWidget(QListWidget):
    """支持空状态标签的列表控件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._empty_label = None
        self._empty_item = None

    def setEmptyLabel(self, label: QLabel):
        """设置空状态标签"""
        self._empty_label = label
        # 不立即显示，避免初始化时的渲染问题

    def _show_empty_state(self):
        """显示空状态"""
        if self._empty_label and self._empty_item is None:
            self._empty_item = QListWidgetItem()
            self._empty_item.setSizeHint(QSize(400, 60))
            super().addItem(self._empty_item)
            # 延迟设置widget
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self._set_empty_widget)

    def _set_empty_widget(self):
        """延迟设置空状态widget"""
        if self._empty_item and self._empty_label:
            try:
                self.setItemWidget(self._empty_item, self._empty_label)
            except Exception as e:
                logger.debug(f"Error setting empty widget: {e}")

    def _hide_empty_state(self):
        """隐藏空状态"""
        if self._empty_item:
            for i in range(self.count()):
                if self.item(i) == self._empty_item:
                    self.takeItem(i)
                    self._empty_item = None
                    break

    def addItem(self, item):
        """添加项目"""
        # 先移除空状态
        self._hide_empty_state()
        super().addItem(item)

    def takeItem(self, row: int):
        """移除项目"""
        result = super().takeItem(row)
        # 检查是否需要显示空状态
        if self.count() == 0:
            self._show_empty_state()
        return result
