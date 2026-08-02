"""Prompt 模板管理对话框"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...services.prompt_template import TemplateStyle, get_prompt_template_manager
from ..constants import DialogConfig, Icons


class PromptTemplateDialog(QDialog):
    """Prompt 模板管理对话框（完整功能）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{Icons.TEMPLATE} Prompt 模板管理")
        self.setMinimumSize(DialogConfig.TEMPLATE_DIALOG_MIN_WIDTH, DialogConfig.TEMPLATE_DIALOG_MIN_HEIGHT)
        self._setup_ui()
        self._load_templates()

    def _setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # 使用分割器：左侧模板列表，右侧详情/编辑
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ===== 左侧：模板列表 =====
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 列表标题
        left_layout.addWidget(QLabel("📋 模板列表"))

        # 模板列表
        self.template_list = QListWidget()
        self.template_list.setMaximumWidth(DialogConfig.TEMPLATE_LIST_MAX_WIDTH)
        self.template_list.currentItemChanged.connect(self._on_template_selected)
        left_layout.addWidget(self.template_list)

        # 左侧按钮组
        button_layout = QHBoxLayout()

        self.new_button = QPushButton("➕ 新建")
        self.new_button.clicked.connect(self._on_new_template)
        button_layout.addWidget(self.new_button)

        self.delete_button = QPushButton("🗑️ 删除")
        self.delete_button.clicked.connect(self._on_delete_template)
        button_layout.addWidget(self.delete_button)

        left_layout.addLayout(button_layout)

        splitter.addWidget(left_widget)

        # ===== 右侧：模板详情/编辑 =====
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 表单布局
        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        # 模板名称
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("输入模板名称...")
        form_layout.addRow("名称:", self.name_input)

        # 模板描述
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("输入模板描述...")
        form_layout.addRow("描述:", self.desc_input)

        # 模板风格
        self.style_combo = QComboBox()
        for style in TemplateStyle:
            self.style_combo.addItem(style.value, style)
        form_layout.addRow("风格:", self.style_combo)

        # 是否设为默认
        self.default_checkbox = QCheckBox("设为默认模板（新建任务时自动使用）")
        self.default_checkbox.setStyleSheet("color: #666;")
        form_layout.addRow("默认:", self.default_checkbox)

        right_layout.addLayout(form_layout)

        # 模板内容编辑
        right_layout.addWidget(QLabel("📝 模板内容:"))

        self.content_edit = QTextEdit()
        self.content_edit.setPlaceholderText(
            "输入 Prompt 模板内容...\n\n"
            "可用变量:\n"
            "  {title} - 视频标题\n"
            "  {transcript} - 转录文本\n"
            "  {author} - 视频作者\n"
            "  {platform} - 视频平台\n"
            "  {duration} - 视频时长"
        )
        right_layout.addWidget(self.content_edit)

        # 按钮组
        button_box = QHBoxLayout()

        self.save_button = QPushButton("💾 保存")
        self.save_button.clicked.connect(self._on_save_template)
        button_box.addWidget(self.save_button)

        self.preview_button = QPushButton("👁️ 预览")
        self.preview_button.clicked.connect(self._on_preview)
        button_box.addWidget(self.preview_button)

        self.import_button = QPushButton("📥 导入")
        self.import_button.clicked.connect(self._on_import)
        button_box.addWidget(self.import_button)

        self.export_button = QPushButton("📤 导出")
        self.export_button.clicked.connect(self._on_export)
        button_box.addWidget(self.export_button)

        button_box.addStretch()

        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.accept)
        button_box.addWidget(self.close_button)

        right_layout.addLayout(button_box)

        splitter.addWidget(right_widget)
        splitter.setSizes([DialogConfig.SPLITTER_LEFT_SIZE, DialogConfig.SPLITTER_RIGHT_SIZE])

        layout.addWidget(splitter)

        # 当前编辑的模板ID
        self.current_template_id = None

    def _load_templates(self):
        """加载模板列表"""
        self.template_list.clear()

        try:
            manager = get_prompt_template_manager()
            templates = manager.get_all_templates()

            for template in templates:
                display_text = template.name
                if template.is_default:
                    display_text = f"⭐ {display_text}"
                if template.is_builtin:
                    display_text = f"[内置] {display_text}"
                else:
                    display_text = f"[自定义] {display_text}"

                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, template.id)
                self.template_list.addItem(item)

        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载模板失败: {e}")

    def _on_template_selected(self, current: QListWidgetItem, _previous: QListWidgetItem) -> None:
        """选中模板"""
        if not current:
            return

        template_id = current.data(Qt.ItemDataRole.UserRole)
        self._load_template_details(template_id)

    def _load_template_details(self, template_id: str):
        """加载模板详情"""
        try:
            manager = get_prompt_template_manager()
            template = manager.get_template(template_id)

            if not template:
                return

            self.current_template_id = template_id

            # 填充表单
            self.name_input.setText(template.name)
            self.desc_input.setText(template.description or "")

            # 设置风格
            style_index = self.style_combo.findData(template.style)
            if style_index >= 0:
                self.style_combo.setCurrentIndex(style_index)

            # 设置默认状态
            self.default_checkbox.setChecked(template.is_default)

            # 设置内容
            self.content_edit.setPlainText(template.template)

            # 内置模板不能编辑内容和删除，但可以设为默认
            is_builtin = template.is_builtin
            self.content_edit.setReadOnly(is_builtin)
            self.delete_button.setEnabled(not is_builtin)
            # 内置模板可以设为默认
            self.default_checkbox.setEnabled(True)

            if is_builtin:
                self.content_edit.setStyleSheet("background-color: #f5f5f5;")
            else:
                self.content_edit.setStyleSheet("")

        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载模板详情失败: {e}")

    def _on_new_template(self) -> None:
        """新建模板"""
        self.current_template_id = None
        self.name_input.clear()
        self.desc_input.clear()
        self.style_combo.setCurrentIndex(0)
        self.default_checkbox.setChecked(False)
        self.content_edit.clear()
        self.content_edit.setReadOnly(False)
        self.content_edit.setStyleSheet("")
        self.template_list.clearSelection()

    def _on_save_template(self) -> None:
        """保存模板"""
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "警告", "请输入模板名称")
            return

        content = self.content_edit.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "警告", "请输入模板内容")
            return

        try:
            manager = get_prompt_template_manager()

            if self.current_template_id:
                # 获取当前模板信息
                existing_template = manager.get_template(self.current_template_id)
                is_builtin = existing_template.is_builtin if existing_template else False

                # 更新现有模板
                if is_builtin:
                    # 内置模板只更新名称和描述，不更新内容
                    success = manager.update_template(
                        self.current_template_id,
                        name=name,
                        description=self.desc_input.text().strip()
                    )
                else:
                    # 自定义模板可以更新所有内容
                    success = manager.update_template(
                        self.current_template_id,
                        name=name,
                        description=self.desc_input.text().strip(),
                        template=content
                    )
                if success:
                    # 如果勾选了设为默认，调用 set_default_template
                    if self.default_checkbox.isChecked():
                        manager.set_default_template(self.current_template_id)
                    QMessageBox.information(self, "成功", "模板已更新")
                else:
                    QMessageBox.warning(self, "错误", "更新模板失败")
            else:
                # 创建新模板
                template = manager.create_template(
                    name=name,
                    description=self.desc_input.text().strip(),
                    template=content,
                    style=self.style_combo.currentData(),
                    set_as_default=self.default_checkbox.isChecked()
                )
                if template:
                    self.current_template_id = template.id
                    QMessageBox.information(self, "成功", "模板已创建")
                else:
                    QMessageBox.warning(self, "错误", "创建模板失败")

            # 刷新列表
            self._load_templates()

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存模板失败: {e}")

    def _on_delete_template(self) -> None:
        """删除模板"""
        if not self.current_template_id:
            return

        try:
            manager = get_prompt_template_manager()
            template = manager.get_template(self.current_template_id)

            if not template:
                return

            if template.is_builtin:
                QMessageBox.warning(self, "警告", "内置模板不能删除")
                return

            reply = QMessageBox.question(
                self, "确认删除",
                f"确定要删除模板 '{template.name}' 吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                if manager.delete_template(self.current_template_id):
                    QMessageBox.information(self, "成功", "模板已删除")
                    self._on_new_template()  # 清空表单
                    self._load_templates()  # 刷新列表
                else:
                    QMessageBox.warning(self, "错误", "删除模板失败")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"删除模板失败: {e}")

    def _on_preview(self) -> None:
        """预览模板"""
        if not self.current_template_id:
            QMessageBox.warning(self, "警告", "请先选择一个模板")
            return

        try:
            manager = get_prompt_template_manager()
            preview = manager.preview_template(self.current_template_id)

            # 显示预览对话框
            preview_dialog = QDialog(self)
            preview_dialog.setWindowTitle("👁️ 模板预览")
            preview_dialog.setMinimumSize(DialogConfig.PREVIEW_DIALOG_WIDTH, DialogConfig.PREVIEW_DIALOG_HEIGHT)

            layout = QVBoxLayout(preview_dialog)

            text_edit = QTextEdit()
            text_edit.setPlainText(preview)
            text_edit.setReadOnly(True)
            layout.addWidget(text_edit)

            close_btn = QPushButton("关闭")
            close_btn.clicked.connect(preview_dialog.accept)
            layout.addWidget(close_btn)

            preview_dialog.exec()

        except Exception as e:
            QMessageBox.critical(self, "错误", f"预览模板失败: {e}")

    def _on_import(self) -> None:
        """导入模板"""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入模板", "", "YAML files (*.yaml *.yml)"
        )

        if file_path:
            try:
                manager = get_prompt_template_manager()
                template = manager.import_template(file_path)

                if template:
                    QMessageBox.information(
                        self, "成功",
                        f"模板 '{template.name}' 已导入"
                    )
                    self._load_templates()
                else:
                    QMessageBox.warning(self, "错误", "导入模板失败")

            except Exception as e:
                QMessageBox.critical(self, "错误", f"导入模板失败: {e}")

    def _on_export(self) -> None:
        """导出模板"""
        if not self.current_template_id:
            QMessageBox.warning(self, "警告", "请先选择一个模板")
            return

        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出模板", "", "YAML files (*.yaml)"
        )

        if file_path:
            try:
                manager = get_prompt_template_manager()
                if manager.export_template(self.current_template_id, file_path):
                    QMessageBox.information(
                        self, "成功",
                        f"模板已导出到:\n{file_path}"
                    )
                else:
                    QMessageBox.warning(self, "错误", "导出模板失败")

            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出模板失败: {e}")
