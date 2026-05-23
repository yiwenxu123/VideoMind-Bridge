"""任务历史侧边栏组件"""

from datetime import datetime
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QFrame,
    QMenu, QMessageBox, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction

from ...models.task import TaskHistory, TaskStatus
from ...services.task_database import get_task_database
from ...utils import get_logger
from ...config.constants import HistoryConfig, Icons, ButtonConfig, DatabaseConfig

logger = get_logger(__name__)


class HistoryItemWidget(QFrame):
    """历史记录项组件"""

    clicked = Signal(str)  # 任务ID
    delete_clicked = Signal(str)  # 任务ID
    reprocess_clicked = Signal(str)  # 任务ID

    def __init__(self, task: TaskHistory, parent=None):
        super().__init__(parent)
        self.task_id = task.id
        self.task = task
        self._setup_ui()

    def _setup_ui(self):
        """设置UI"""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            HistoryItemWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                margin: 2px;
            }
            HistoryItemWidget:hover {
                background-color: #f5f5f5;
                border-color: #2196F3;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(10, 8, 10, 8)

        # 第一行：标题和状态
        header_layout = QHBoxLayout()

        # 状态图标
        status_icons = {
            TaskStatus.COMPLETED: Icons.STATUS_COMPLETED,
            TaskStatus.FAILED: Icons.STATUS_FAILED,
            TaskStatus.CANCELLED: Icons.STATUS_CANCELLED,
        }
        status_icon = status_icons.get(self.task.status, Icons.STATUS_PENDING)

        self.status_label = QLabel(status_icon)
        self.status_label.setStyleSheet("font-size: 14px;")
        header_layout.addWidget(self.status_label)

        # 标题
        title = self.task.title or "未知标题"
        # 截断长标题
        if len(title) > HistoryConfig.TITLE_MAX_LENGTH:
            title = title[:HistoryConfig.TITLE_MAX_LENGTH - len(HistoryConfig.TITLE_TRUNCATE_SUFFIX)] + HistoryConfig.TITLE_TRUNCATE_SUFFIX
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.title_label.setWordWrap(False)
        header_layout.addWidget(self.title_label, stretch=1)

        layout.addLayout(header_layout)

        # 第二行：平台和时间
        info_layout = QHBoxLayout()

        # 平台
        platform_icons = {
            "bilibili": Icons.PLATFORM_BILIBILI,
            "youtube": Icons.PLATFORM_YOUTUBE,
            "xiaohongshu": Icons.PLATFORM_XIAOHONGSHU,
        }
        platform_icon = platform_icons.get(self.task.platform, Icons.PLATFORM_DEFAULT)
        self.platform_label = QLabel(f"{platform_icon} {self.task.platform or '未知'}")
        self.platform_label.setStyleSheet("color: #666; font-size: 11px;")
        info_layout.addWidget(self.platform_label)

        info_layout.addStretch()

        # 时间
        time_str = self._format_time(self.task.created_at)
        self.time_label = QLabel(time_str)
        self.time_label.setStyleSheet("color: #999; font-size: 11px;")
        info_layout.addWidget(self.time_label)

        layout.addLayout(info_layout)

        # 第三行：操作按钮（鼠标悬停时显示）
        self.action_widget = QWidget()
        action_layout = QHBoxLayout(self.action_widget)
        action_layout.setSpacing(4)
        action_layout.setContentsMargins(0, 0, 0, 0)

        # 重新处理按钮
        reprocess_btn = QPushButton("🔄 重新处理")
        reprocess_btn.setStyleSheet("""
            QPushButton {
                padding: 2px 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 11px;
                background-color: #f5f5f5;
            }
            QPushButton:hover {
                background-color: #e3f2fd;
                border-color: #2196F3;
            }
        """)
        reprocess_btn.clicked.connect(self._on_reprocess)
        action_layout.addWidget(reprocess_btn)

        # 删除按钮
        delete_btn = QPushButton("🗑️ 删除")
        delete_btn.setStyleSheet("""
            QPushButton {
                padding: 2px 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 11px;
                background-color: #f5f5f5;
            }
            QPushButton:hover {
                background-color: #ffebee;
                border-color: #f44336;
                color: #f44336;
            }
        """)
        delete_btn.clicked.connect(self._on_delete)
        action_layout.addWidget(delete_btn)

        action_layout.addStretch()

        self.action_widget.setVisible(False)
        layout.addWidget(self.action_widget)

    def _format_time(self, dt: datetime) -> str:
        """格式化时间显示"""
        now = datetime.now()
        diff = now - dt

        if diff.days == 0:
            if diff.seconds < 60:
                return "刚刚"
            elif diff.seconds < 3600:
                return f"{diff.seconds // 60}分钟前"
            else:
                return f"{diff.seconds // 3600}小时前"
        elif diff.days == 1:
            return "昨天"
        elif diff.days < 7:
            return f"{diff.days}天前"
        else:
            return dt.strftime("%m-%d")

    def enterEvent(self, event):
        """鼠标进入"""
        self.action_widget.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开"""
        self.action_widget.setVisible(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        """鼠标点击"""
        self.clicked.emit(self.task_id)
        super().mousePressEvent(event)

    def _on_reprocess(self):
        """重新处理"""
        self.reprocess_clicked.emit(self.task_id)

    def _on_delete(self):
        """删除"""
        self.delete_clicked.emit(self.task_id)


class TaskHistorySidebar(QWidget):
    """任务历史侧边栏"""

    task_selected = Signal(str)  # 任务ID
    task_reprocess = Signal(str)  # 任务ID

    # 分页配置
    PAGE_SIZE = 20  # 每页显示数量

    def __init__(self, parent=None):
        super().__init__(parent)
        self.db = get_task_database()
        self.current_page = 0
        self.total_records = 0
        self.current_filter = "all"
        self.search_keyword = ""
        self._setup_ui()
        self._load_history()

    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # 标题栏
        header_layout = QHBoxLayout()

        title_label = QLabel("📚 任务历史")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # 刷新按钮
        refresh_btn = QPushButton("🔄")
        refresh_btn.setMaximumWidth(ButtonConfig.REFRESH_BUTTON_MAX_WIDTH)
        refresh_btn.setToolTip("刷新")
        refresh_btn.clicked.connect(self._load_history)
        header_layout.addWidget(refresh_btn)

        layout.addLayout(header_layout)

        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索任务...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
        """)
        self.search_input.returnPressed.connect(self._on_search)
        layout.addWidget(self.search_input)

        # 筛选按钮
        filter_layout = QHBoxLayout()

        self.filter_all_btn = QPushButton("全部")
        self.filter_all_btn.setCheckable(True)
        self.filter_all_btn.setChecked(True)
        self.filter_all_btn.clicked.connect(lambda: self._on_filter("all"))
        filter_layout.addWidget(self.filter_all_btn)

        self.filter_completed_btn = QPushButton("已完成")
        self.filter_completed_btn.setCheckable(True)
        self.filter_completed_btn.clicked.connect(lambda: self._on_filter("completed"))
        filter_layout.addWidget(self.filter_completed_btn)

        self.filter_failed_btn = QPushButton("失败")
        self.filter_failed_btn.setCheckable(True)
        self.filter_failed_btn.clicked.connect(lambda: self._on_filter("failed"))
        filter_layout.addWidget(self.filter_failed_btn)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # 历史列表
        self.history_list = QListWidget()
        self.history_list.setSpacing(4)
        self.history_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_list.setStyleSheet("""
            QListWidget {
                border: none;
                background-color: transparent;
            }
            QListWidget::item {
                background-color: transparent;
            }
        """)
        layout.addWidget(self.history_list)

        # 统计信息
        self.stats_label = QLabel("共 0 条记录")
        self.stats_label.setStyleSheet("color: #999; font-size: 11px;")
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.stats_label)

        # 分页控制
        pagination_layout = QHBoxLayout()

        self.prev_btn = QPushButton("◀ 上一页")
        self.prev_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self._on_prev_page)
        pagination_layout.addWidget(self.prev_btn)

        self.page_label = QLabel("第 1 页")
        self.page_label.setStyleSheet("color: #666; font-size: 12px;")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pagination_layout.addWidget(self.page_label, stretch=1)

        self.next_btn = QPushButton("下一页 ▶")
        self.next_btn.setEnabled(False)
        self.next_btn.clicked.connect(self._on_next_page)
        pagination_layout.addWidget(self.next_btn)

        layout.addLayout(pagination_layout)

        # 底部按钮
        bottom_layout = QHBoxLayout()

        clear_btn = QPushButton("清空历史")
        clear_btn.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 12px;
                color: #666;
            }
            QPushButton:hover {
                background-color: #ffebee;
                color: #f44336;
                border-color: #f44336;
            }
        """)
        clear_btn.clicked.connect(self._on_clear_history)
        bottom_layout.addWidget(clear_btn)

        bottom_layout.addStretch()

        export_btn = QPushButton("导出")
        export_btn.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e3f2fd;
                border-color: #2196F3;
            }
        """)
        export_btn.clicked.connect(self._on_export)
        bottom_layout.addWidget(export_btn)

        layout.addLayout(bottom_layout)

        # 设置最小宽度，但不限制最大宽度，让内容填充可用空间
        self.setMinimumWidth(400)

    def _load_history(self):
        """加载历史记录（分页）"""
        try:
            # 计算偏移量
            offset = self.current_page * self.PAGE_SIZE

            # 根据当前筛选条件加载数据
            if self.search_keyword:
                # 搜索模式（暂不支持分页，加载前100条）
                tasks = self.db.search_tasks(self.search_keyword, limit=100)
                self.total_records = len(tasks)
            elif self.current_filter == "completed":
                tasks = self.db.get_tasks(
                    status=TaskStatus.COMPLETED,
                    limit=self.PAGE_SIZE,
                    offset=offset
                )
                # 获取总数
                all_completed = self.db.get_tasks(status=TaskStatus.COMPLETED, limit=10000)
                self.total_records = len(all_completed)
            elif self.current_filter == "failed":
                tasks = self.db.get_tasks(
                    status=TaskStatus.FAILED,
                    limit=self.PAGE_SIZE,
                    offset=offset
                )
                all_failed = self.db.get_tasks(status=TaskStatus.FAILED, limit=10000)
                self.total_records = len(all_failed)
            else:
                tasks = self.db.get_tasks(
                    limit=self.PAGE_SIZE,
                    offset=offset
                )
                stats = self.db.get_statistics()
                self.total_records = stats.get("total", 0)

            self._display_tasks(tasks)
            self._update_stats()
            self._update_pagination()
        except Exception as e:
            logger.error(f"加载历史记录失败: {e}")

    def _display_tasks(self, tasks: list):
        """显示任务列表"""
        # 先断开旧信号连接，避免内存泄漏
        for i in range(self.history_list.count()):
            item = self.history_list.item(i)
            old_widget = self.history_list.itemWidget(item)
            if old_widget:
                try:
                    old_widget.clicked.disconnect()
                    old_widget.delete_clicked.disconnect()
                    old_widget.reprocess_clicked.disconnect()
                except RuntimeError:
                    # 信号可能已经被断开
                    pass
                old_widget.deleteLater()

        self.history_list.clear()

        for task in tasks:
            item = QListWidgetItem()
            item.setSizeHint(QSize(HistoryConfig.ITEM_WIDTH, HistoryConfig.ITEM_HEIGHT))

            widget = HistoryItemWidget(task)
            widget.clicked.connect(self._on_task_clicked)
            widget.delete_clicked.connect(self._on_task_delete)
            widget.reprocess_clicked.connect(self._on_task_reprocess)

            self.history_list.addItem(item)
            self.history_list.setItemWidget(item, widget)

    def _update_stats(self):
        """更新统计信息"""
        try:
            start = self.current_page * self.PAGE_SIZE + 1
            end = min(start + self.PAGE_SIZE - 1, self.total_records)
            self.stats_label.setText(f"显示 {start}-{end} 条，共 {self.total_records} 条")
        except Exception as e:
            logger.error(f"更新统计信息失败: {e}")

    def _update_pagination(self):
        """更新分页按钮状态"""
        total_pages = (self.total_records + self.PAGE_SIZE - 1) // self.PAGE_SIZE
        total_pages = max(1, total_pages)

        self.page_label.setText(f"第 {self.current_page + 1} / {total_pages} 页")
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < total_pages - 1)

    def _on_prev_page(self):
        """上一页"""
        if self.current_page > 0:
            self.current_page -= 1
            self._load_history()

    def _on_next_page(self):
        """下一页"""
        total_pages = (self.total_records + self.PAGE_SIZE - 1) // self.PAGE_SIZE
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._load_history()

    def _on_search(self):
        """搜索"""
        self.search_keyword = self.search_input.text().strip()
        self.current_page = 0  # 重置到第一页
        self._load_history()

    def _on_filter(self, filter_type: str):
        """筛选"""
        # 更新按钮状态
        self.filter_all_btn.setChecked(filter_type == "all")
        self.filter_completed_btn.setChecked(filter_type == "completed")
        self.filter_failed_btn.setChecked(filter_type == "failed")

        self.current_filter = filter_type
        self.current_page = 0  # 重置到第一页
        self._load_history()

    def _on_task_clicked(self, task_id: str):
        """任务点击"""
        self.task_selected.emit(task_id)

    def _on_task_delete(self, task_id: str):
        """删除任务"""
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除这条历史记录吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.db.delete_task(task_id)
                self._load_history()
            except Exception as e:
                logger.error(f"删除任务失败: {e}")

    def _on_task_reprocess(self, task_id: str):
        """重新处理任务"""
        self.task_reprocess.emit(task_id)

    def _on_clear_history(self):
        """清空历史"""
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有历史记录吗？此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 获取所有任务并删除
                tasks = self.db.get_tasks(limit=1000)
                for task in tasks:
                    self.db.delete_task(task.id)
                self._load_history()
            except Exception as e:
                logger.error(f"清空历史失败: {e}")

    def _on_export(self) -> None:
        """导出历史记录到文件"""
        from PySide6.QtWidgets import QFileDialog
        from datetime import datetime
        import json

        # 选择导出文件路径
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出历史记录",
            f"task_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON files (*.json);;CSV files (*.csv)"
        )

        if not file_path:
            return

        try:
            # 获取所有任务
            tasks = self.db.get_tasks(limit=10000)

            if not tasks:
                QMessageBox.information(self, "提示", "没有可导出的历史记录")
                return

            # 准备导出数据
            export_data = []
            for task in tasks:
                export_data.append({
                    "id": task.id,
                    "title": task.title,
                    "platform": task.platform,
                    "url": task.url,
                    "status": task.status.value if hasattr(task.status, 'value') else str(task.status),
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                    "error_message": task.error_message
                })

            # 根据文件扩展名选择导出格式
            if file_path.endswith('.csv'):
                # CSV 格式
                import csv
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    if export_data:
                        writer = csv.DictWriter(f, fieldnames=export_data[0].keys())
                        writer.writeheader()
                        writer.writerows(export_data)
            else:
                # JSON 格式（默认）
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)

            QMessageBox.information(
                self,
                "导出成功",
                f"已成功导出 {len(export_data)} 条历史记录到:\n{file_path}"
            )

        except Exception as e:
            logger.error(f"导出历史记录失败: {e}")
            QMessageBox.critical(self, "导出失败", f"导出历史记录时出错:\n{e}")

    def refresh(self):
        """刷新历史记录"""
        self._load_history()

    def add_task(self, task: TaskHistory):
        """添加新任务到历史"""
        try:
            self.db.save_task(task)
            self._load_history()
        except Exception as e:
            logger.error(f"添加任务到历史失败: {e}")
