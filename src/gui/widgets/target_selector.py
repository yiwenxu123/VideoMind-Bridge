"""输出目标选择组件"""

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...models.task import ExportTarget


class TargetCard(QGroupBox):
    """目标选择卡片"""

    def __init__(self, icon: str, title: str, description: str, target: ExportTarget, parent=None):
        super().__init__(parent)
        self.target = target
        self._setup_ui(icon, title, description)

    def _setup_ui(self, icon: str, title: str, description: str):
        """设置 UI"""
        self.setStyleSheet("""
            QGroupBox {
                border: 1px solid #ddd;
                border-radius: 6px;
                margin-top: 5px;
                padding-top: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)

        # 标题行
        header_layout = QHBoxLayout()

        self.checkbox = QCheckBox(f"{icon} {title}")
        self.checkbox.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(self.checkbox)

        header_layout.addStretch()

        self.config_button = QPushButton("⚙️")
        self.config_button.setMaximumWidth(40)
        self.config_button.setStyleSheet("""
            QPushButton {
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
            }
        """)
        header_layout.addWidget(self.config_button)

        layout.addLayout(header_layout)

        # 描述
        desc_label = QLabel(description)
        desc_label.setStyleSheet("color: #666; font-size: 12px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # 配置区域（默认隐藏）
        self.config_widget = QWidget()
        self.config_layout = QVBoxLayout(self.config_widget)
        self.config_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.config_widget)
        self.config_widget.hide()

        # 连接信号
        self.checkbox.toggled.connect(self._on_checked_changed)
        self.config_button.clicked.connect(self._on_config_clicked)

    def _on_checked_changed(self, checked: bool):
        """选中状态变化"""
        if checked:
            self.setStyleSheet("""
                QGroupBox {
                    border: 2px solid #2196F3;
                    border-radius: 6px;
                    margin-top: 5px;
                    padding-top: 5px;
                    background-color: #e3f2fd;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
            """)
        else:
            self.setStyleSheet("""
                QGroupBox {
                    border: 1px solid #ddd;
                    border-radius: 6px;
                    margin-top: 5px;
                    padding-top: 5px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
            """)

    def _on_config_clicked(self):
        """配置按钮点击"""
        self.config_widget.setVisible(not self.config_widget.isVisible())

    def is_selected(self) -> bool:
        """是否选中"""
        return self.checkbox.isChecked()

    def set_selected(self, selected: bool):
        """设置选中状态"""
        self.checkbox.setChecked(selected)


class TargetSelector(QWidget):
    """输出目标选择组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        title_label = QLabel("📤 输出目标（可多选）")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        # 卡片容器
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(15)

        # Obsidian
        self.obsidian_card = TargetCard(
            icon="📓",
            title="Obsidian",
            description="导出到 Obsidian Vault\n生成标准 Markdown 笔记",
            target=ExportTarget.OBSIDIAN
        )
        # 添加 Obsidian 配置
        obsidian_config_layout = QHBoxLayout()
        obsidian_config_layout.addWidget(QLabel("Vault 路径:"))
        self.obsidian_path_input = QLineEdit()
        self.obsidian_path_input.setPlaceholderText("/Users/xxx/Documents/Obsidian")
        obsidian_config_layout.addWidget(self.obsidian_path_input)
        self.obsidian_browse_button = QPushButton("浏览...")
        self.obsidian_browse_button.clicked.connect(self._on_browse_obsidian)
        obsidian_config_layout.addWidget(self.obsidian_browse_button)
        self.obsidian_card.config_layout.addLayout(obsidian_config_layout)

        obsidian_subfolder_layout = QHBoxLayout()
        obsidian_subfolder_layout.addWidget(QLabel("子文件夹:"))
        self.obsidian_subfolder_input = QLineEdit("Inbox/Videos")
        obsidian_subfolder_layout.addWidget(self.obsidian_subfolder_input)
        self.obsidian_card.config_layout.addLayout(obsidian_subfolder_layout)
        cards_layout.addWidget(self.obsidian_card)

        # 本地文件夹
        from pathlib import Path
        default_local_path = Path.home() / "Downloads" / "VideoMind"
        default_local_path.mkdir(parents=True, exist_ok=True)

        self.local_card = TargetCard(
            icon="📁",
            title="本地文件夹",
            description=f"保存到: {default_local_path}\n包含视频、音频、字幕",
            target=ExportTarget.LOCAL
        )
        # 添加本地配置
        local_config_layout = QHBoxLayout()
        local_config_layout.addWidget(QLabel("输出路径:"))
        self.local_path_input = QLineEdit(str(default_local_path))
        self.local_path_input.setPlaceholderText("~/Downloads/VideoMind")
        local_config_layout.addWidget(self.local_path_input)
        self.local_browse_button = QPushButton("浏览...")
        self.local_browse_button.clicked.connect(self._on_browse_local)
        local_config_layout.addWidget(self.local_browse_button)
        self.local_card.config_layout.addLayout(local_config_layout)
        cards_layout.addWidget(self.local_card)

        # Webhook
        self.webhook_card = TargetCard(
            icon="🔗",
            title="Webhook",
            description="推送到自定义 URL\n支持自动化集成",
            target=ExportTarget.WEBHOOK
        )
        # 添加 Webhook 配置
        webhook_url_layout = QHBoxLayout()
        webhook_url_layout.addWidget(QLabel("URL:"))
        self.webhook_url_input = QLineEdit()
        self.webhook_url_input.setPlaceholderText("https://your-app.com/webhook")
        webhook_url_layout.addWidget(self.webhook_url_input)
        self.webhook_card.config_layout.addLayout(webhook_url_layout)

        webhook_headers_layout = QHBoxLayout()
        webhook_headers_layout.addWidget(QLabel("Headers:"))
        self.webhook_headers_input = QLineEdit()
        self.webhook_headers_input.setPlaceholderText('{"Authorization": "Bearer xxx"}')
        webhook_headers_layout.addWidget(self.webhook_headers_input)
        self.webhook_card.config_layout.addLayout(webhook_headers_layout)

        # Webhook 测试按钮
        webhook_test_layout = QHBoxLayout()
        webhook_test_layout.addStretch()
        self.webhook_test_button = QPushButton("🧪 测试连接")
        self.webhook_test_button.clicked.connect(self._on_test_webhook)
        webhook_test_layout.addWidget(self.webhook_test_button)
        self.webhook_card.config_layout.addLayout(webhook_test_layout)
        cards_layout.addWidget(self.webhook_card)

        # Notion
        self.notion_card = TargetCard(
            icon="📝",
            title="Notion",
            description="导出到 Notion 数据库\n(需配置 API)",
            target=ExportTarget.NOTION
        )
        # 添加 Notion 配置
        notion_config_layout = QHBoxLayout()
        notion_config_layout.addWidget(QLabel("Database ID:"))
        self.notion_db_input = QLineEdit()
        self.notion_db_input.setPlaceholderText("输入 Notion Database ID...")
        notion_config_layout.addWidget(self.notion_db_input)
        self.notion_card.config_layout.addLayout(notion_config_layout)
        cards_layout.addWidget(self.notion_card)

        layout.addLayout(cards_layout)

        # 默认选中本地文件夹
        self.local_card.set_selected(True)

    def _on_browse_obsidian(self):
        """浏览 Obsidian Vault"""
        path = QFileDialog.getExistingDirectory(self, "选择 Obsidian Vault 目录")
        if path:
            self.obsidian_path_input.setText(path)

    def _on_browse_local(self):
        """浏览本地输出目录"""
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.local_path_input.setText(path)
            # 更新卡片描述显示新路径
            self._update_local_description()

    def _on_test_webhook(self):
        """测试 Webhook 连接"""
        import json

        import httpx
        from PySide6.QtWidgets import QMessageBox

        url = self.webhook_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "警告", "请先输入 Webhook URL")
            return

        # 解析 headers
        headers = {}
        headers_text = self.webhook_headers_input.text().strip()
        if headers_text:
            try:
                headers = json.loads(headers_text)
            except json.JSONDecodeError:
                QMessageBox.warning(self, "警告", "Headers 格式错误，应为 JSON 格式")
                return

        # 发送测试请求
        try:
            test_payload = {
                "event": "test",
                "timestamp": "2026-01-01T00:00:00Z",
                "data": {"message": "This is a test from VideoMind Bridge"}
            }

            response = httpx.post(
                url,
                json=test_payload,
                headers={"Content-Type": "application/json", **headers},
                timeout=10
            )

            if response.status_code < 400:
                QMessageBox.information(
                    self,
                    "测试成功",
                    f"Webhook 测试成功！\n\n状态码: {response.status_code}\n响应: {response.text[:200]}"
                )
            else:
                QMessageBox.warning(
                    self,
                    "测试失败",
                    f"Webhook 返回错误状态码: {response.status_code}\n响应: {response.text[:200]}"
                )

        except httpx.TimeoutException:
            QMessageBox.warning(self, "测试失败", "请求超时，请检查 URL 是否正确")
        except httpx.ConnectError as e:
            QMessageBox.warning(self, "测试失败", f"连接错误: {str(e)}")
        except Exception as e:
            QMessageBox.warning(self, "测试失败", f"请求异常: {str(e)}")

    def _update_local_description(self):
        """更新本地文件夹卡片描述"""
        path = self.local_path_input.text() or str(Path.home() / "Downloads" / "VideoMind")
        # 找到描述标签并更新
        for i in range(self.local_card.layout().count()):
            item = self.local_card.layout().itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, QLabel) and widget != self.local_card.checkbox:
                    # 这是描述标签
                    widget.setText(f"保存到: {path}\n包含视频、音频、字幕")
                    break

    def get_selected_targets(self) -> list:
        """获取选中的目标列表"""
        targets = []
        if self.obsidian_card.is_selected():
            targets.append({
                "type": ExportTarget.OBSIDIAN,
                "vault_path": self.obsidian_path_input.text(),
                "subfolder": self.obsidian_subfolder_input.text()
            })
        if self.local_card.is_selected():
            targets.append({
                "type": ExportTarget.LOCAL,
                "output_path": self.local_path_input.text()
            })
        if self.webhook_card.is_selected():
            import json
            headers = {}
            headers_text = self.webhook_headers_input.text().strip()
            if headers_text:
                try:
                    headers = json.loads(headers_text)
                except json.JSONDecodeError:
                    pass
            targets.append({
                "type": ExportTarget.WEBHOOK,
                "url": self.webhook_url_input.text(),
                "headers": headers
            })
        if self.notion_card.is_selected():
            targets.append({
                "type": ExportTarget.NOTION,
                "database_id": self.notion_db_input.text()
            })
        return targets

    def set_download_mode(self, download_only: bool):
        """设置下载模式

        Args:
            download_only: True 时仅保留本地文件夹选项
        """
        if download_only:
            # 取消选中 Obsidian 和 Notion
            self.obsidian_card.set_selected(False)
            self.notion_card.set_selected(False)
            # 禁用它们
            self.obsidian_card.setEnabled(False)
            self.notion_card.setEnabled(False)
            # 确保本地选中
            self.local_card.set_selected(True)
        else:
            # 重新启用
            self.obsidian_card.setEnabled(True)
            self.notion_card.setEnabled(True)

    def set_transcribe_mode(self):
        """设置转录存档模式 - 只启用本地文件夹，保持轻量级"""
        # 禁用 Obsidian 和 Notion，只保留本地文件夹
        self.obsidian_card.setEnabled(False)
        self.obsidian_card.set_selected(False)  # 取消选中
        self.notion_card.setEnabled(False)
        self.notion_card.set_selected(False)  # 取消选中
        self.local_card.setEnabled(True)
        # 默认选中本地
        if not self.local_card.is_selected():
            self.local_card.set_selected(True)

    def set_full_mode(self):
        """设置完整处理模式 - 启用所有目标"""
        # 启用所有目标选项
        self.obsidian_card.setEnabled(True)
        self.notion_card.setEnabled(True)
        self.local_card.setEnabled(True)
        # 默认选中本地和 Obsidian
        if not self.local_card.is_selected() and not self.obsidian_card.is_selected() and not self.notion_card.is_selected():
            self.local_card.set_selected(True)
            self.obsidian_card.set_selected(True)

    def set_obsidian_config(self, vault_path: str, subfolder: str):
        """设置 Obsidian 配置"""
        self.obsidian_path_input.setText(vault_path)
        self.obsidian_subfolder_input.setText(subfolder)
        self.obsidian_card.set_selected(True)

    def get_obsidian_config(self) -> dict:
        """获取 Obsidian 配置"""
        if not self.obsidian_card.is_selected():
            return None
        return {
            "vault_path": self.obsidian_path_input.text(),
            "subfolder": self.obsidian_subfolder_input.text()
        }

    def set_local_path(self, path: str):
        """设置本地文件夹路径"""
        self.local_path_input.setText(path)
        self._update_local_description()

    def get_local_path(self) -> str:
        """获取本地文件夹路径"""
        return self.local_path_input.text() or str(Path.home() / "Downloads" / "VideoMind")
