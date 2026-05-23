"""AI 引擎配置组件"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QLineEdit,
    QGroupBox, QMessageBox, QDialog, QTextEdit,
    QDialogButtonBox, QFormLayout
)
from PySide6.QtCore import Qt

from ...services.prompt_template import get_prompt_template_manager, TemplateStyle
from ...services.config_manager import get_config_manager
from ...utils import get_logger

logger = get_logger(__name__)


class AIConfigWidget(QGroupBox):
    """AI 引擎配置组件"""

    def __init__(self, parent=None):
        super().__init__("🤖 AI 引擎配置", parent)
        self._setup_ui()

    def _setup_ui(self):
        """设置 UI"""
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                border: 1px solid #ddd;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 第一行：引擎选择
        engine_layout = QHBoxLayout()

        engine_label = QLabel("引擎:")
        engine_layout.addWidget(engine_label)

        self.engine_combo = QComboBox()
        self.engine_combo.addItems([
            "DeepSeek",
            "智谱 AI",
            "Moonshot AI (Kimi)",
            "MiniMax",
            "豆包",
            "本地 Ollama"
        ])
        self.engine_combo.setMinimumWidth(200)
        self.engine_combo.setStyleSheet("""
            QComboBox {
                padding: 6px;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
        """)
        engine_layout.addWidget(self.engine_combo)

        # 配置 Prompt 按钮
        self.prompt_button = QPushButton("⚙️ 配置 Prompt")
        self.prompt_button.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
            }
        """)
        engine_layout.addWidget(self.prompt_button)

        engine_layout.addStretch()

        # API Key 输入
        api_key_label = QLabel("API Key:")
        engine_layout.addWidget(api_key_label)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("输入 API Key...")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setMinimumWidth(200)
        self.api_key_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
        """)
        engine_layout.addWidget(self.api_key_input)

        # 测试连接按钮
        self.test_btn = QPushButton("🔄 测试")
        self.test_btn.setToolTip("测试 API 连接")
        self.test_btn.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
            }
            QPushButton:hover {
                background: #f0f0f0;
            }
        """)
        self.test_btn.clicked.connect(self._on_test_connection)
        engine_layout.addWidget(self.test_btn)

        # 连接状态标签
        self.connection_status = QLabel("")
        self.connection_status.setStyleSheet("font-size: 12px;")
        engine_layout.addWidget(self.connection_status)

        engine_layout.addStretch()

        layout.addLayout(engine_layout)

        # 第二行：模型和模板选择
        model_layout = QHBoxLayout()

        model_label = QLabel("模型:")
        model_layout.addWidget(model_label)

        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "deepseek-chat",
            "deepseek-reasoner"
        ])
        self.model_combo.setMinimumWidth(200)
        model_layout.addWidget(self.model_combo)

        # Prompt 模板选择
        template_label = QLabel("摘要风格:")
        model_layout.addWidget(template_label)

        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(150)
        self._load_templates()
        model_layout.addWidget(self.template_combo)

        model_layout.addStretch()

        # 提示文本
        self.hint_label = QLabel("💡 此模式将调用 LLM API 生成摘要，会消耗 Token")
        self.hint_label.setStyleSheet("color: #666; font-size: 12px;")
        model_layout.addWidget(self.hint_label)

        layout.addLayout(model_layout)

        # 连接信号
        self.engine_combo.currentTextChanged.connect(self._on_engine_changed)
        self.prompt_button.clicked.connect(self._on_config_prompt)
        self.template_combo.currentIndexChanged.connect(self._on_template_changed)

    def _on_engine_changed(self, engine_name: str):
        """引擎切换"""
        # 根据引擎更新模型选项
        self.model_combo.clear()

        if "DeepSeek" in engine_name:
            self.model_combo.addItems(["deepseek-chat", "deepseek-reasoner"])
        elif "智谱" in engine_name:
            self.model_combo.addItems(["glm-4.7", "glm-4.7-Flash"])
        elif "Kimi" in engine_name or "Moonshot" in engine_name:
            self.model_combo.addItems([
                "moonshot-v1-8k",
                "moonshot-v1-32k",
                "moonshot-v1-128k",
                "kimi-latest"
            ])
        elif "MiniMax" in engine_name:
            self.model_combo.addItems([
                "MiniMax-Text-01",
                "abab6.5-chat",
                "minmax-2.1"
            ])
        elif "豆包" in engine_name:
            self.model_combo.addItems([
                "doubao-1.6-pro",
                "doubao-1.6-lite",
                "doubao-1.6-flash"
            ])
        elif "Ollama" in engine_name:
            self.model_combo.addItems(["llama2", "mistral", "qwen"])

    def _load_templates(self):
        """加载 Prompt 模板列表"""
        self.template_combo.clear()

        try:
            manager = get_prompt_template_manager()
            templates = manager.get_all_templates()

            for template in templates:
                display_text = f"{template.name}"
                if template.is_default:
                    display_text += " (默认)"
                self.template_combo.addItem(display_text, template.id)

            # 设置当前选中默认模板
            for i, template in enumerate(templates):
                if template.is_default:
                    self.template_combo.setCurrentIndex(i)
                    break

        except Exception as e:
            logger.error(f"加载模板失败: {e}")
            # 加载失败时添加默认选项
            self.template_combo.addItem("默认风格", "default")

    def _on_template_changed(self, index: int):
        """模板选择变更"""
        template_id = self.template_combo.currentData()
        logger.debug(f"选择模板: {template_id}")

    def _on_test_connection(self):
        """测试 API 连接"""
        api_key = self.api_key_input.text().strip()
        if not api_key:
            self.connection_status.setText("❌ 请先输入 API Key")
            self.connection_status.setStyleSheet("color: #f44336; font-size: 12px;")
            return

        model = self.model_combo.currentText()
        if not model:
            self.connection_status.setText("❌ 请先选择模型")
            self.connection_status.setStyleSheet("color: #f44336; font-size: 12px;")
            return

        self.connection_status.setText("🔄 测试中...")
        self.connection_status.setStyleSheet("color: #666; font-size: 12px;")
        self.test_btn.setEnabled(False)

        try:
            from ...services.ai_service import AIService

            # 创建临时服务实例测试连接
            service = AIService(
                api_key=api_key,
                model=model,
                mock=False
            )

            success, message = service.test_connection()
            service.close()

            if success:
                self.connection_status.setText(f"✅ {message}")
                self.connection_status.setStyleSheet("color: #4CAF50; font-size: 12px;")
                # 测试成功后，保存 API Key 到密钥环
                if self.save_api_key(api_key):
                    logger.info("API Key 已保存到系统密钥环")
            else:
                self.connection_status.setText(f"❌ {message}")
                self.connection_status.setStyleSheet("color: #f44336; font-size: 12px;")

        except Exception as e:
            self.connection_status.setText(f"❌ 测试失败: {str(e)}")
            self.connection_status.setStyleSheet("color: #f44336; font-size: 12px;")

        finally:
            self.test_btn.setEnabled(True)

    def _on_config_prompt(self):
        """配置 Prompt - 打开模板管理对话框"""
        dialog = PromptTemplateDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 刷新模板列表
            self._load_templates()

    def get_selected_template_id(self) -> str:
        """获取当前选中的模板 ID"""
        return self.template_combo.currentData() or "default"

    def get_config(self) -> dict:
        """获取配置（API Key 从密钥环获取）"""
        config_manager = get_config_manager()
        return {
            "engine": self.engine_combo.currentText(),
            "model": self.model_combo.currentText(),
            "api_key": config_manager.get_api_key()  # 从密钥环获取
        }

    def save_api_key(self, api_key: str) -> bool:
        """保存 API Key 到密钥环"""
        if not api_key or not api_key.strip():
            return False
        config_manager = get_config_manager()
        return config_manager.set_api_key(api_key.strip())

    def set_config(self, config: dict):
        """设置配置（API Key 从密钥环加载）"""
        engine = config.get("engine")
        model = config.get("model")

        if engine:
            index = self.engine_combo.findText(engine)
            if index >= 0:
                self.engine_combo.setCurrentIndex(index)

        if model:
            index = self.model_combo.findText(model)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)

        # 从密钥环加载 API Key
        config_manager = get_config_manager()
        api_key = config_manager.get_api_key()
        if api_key:
            self.api_key_input.setText(api_key)

    def set_disabled_mode(self, disabled: bool):
        """设置禁用模式（转录存档模式使用）"""
        if disabled:
            self.hint_label.setText("📝 此模式仅生成字幕，不调用 AI API，节省 Token")
            self.hint_label.setStyleSheet("color: #4CAF50; font-size: 12px;")
        else:
            self.hint_label.setText("💡 此模式将调用 LLM API 生成摘要，会消耗 Token")
            self.hint_label.setStyleSheet("color: #666; font-size: 12px;")


class PromptTemplateDialog(QDialog):
    """Prompt 模板管理对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Prompt 模板管理")
        self.setMinimumSize(700, 500)
        self._setup_ui()
        self._load_templates()

    def _setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)

        # 模板列表
        list_layout = QHBoxLayout()

        # 左侧：模板列表
        list_group = QGroupBox("可用模板")
        list_group_layout = QVBoxLayout(list_group)

        self.template_list = QComboBox()
        self.template_list.currentIndexChanged.connect(self._on_template_selected)
        list_group_layout.addWidget(self.template_list)

        # 模板信息
        self.template_info = QLabel()
        self.template_info.setWordWrap(True)
        self.template_info.setStyleSheet("color: #666; font-size: 12px;")
        list_group_layout.addWidget(self.template_info)

        list_layout.addWidget(list_group, 1)

        # 右侧：操作按钮
        button_group = QGroupBox("操作")
        button_layout = QVBoxLayout(button_group)

        self.preview_btn = QPushButton("👁️ 预览")
        self.preview_btn.clicked.connect(self._on_preview)
        button_layout.addWidget(self.preview_btn)

        self.set_default_btn = QPushButton("⭐ 设为默认")
        self.set_default_btn.clicked.connect(self._on_set_default)
        button_layout.addWidget(self.set_default_btn)

        button_layout.addStretch()

        self.export_btn = QPushButton("📤 导出")
        self.export_btn.clicked.connect(self._on_export)
        button_layout.addWidget(self.export_btn)

        self.import_btn = QPushButton("📥 导入")
        self.import_btn.clicked.connect(self._on_import)
        button_layout.addWidget(self.import_btn)

        list_layout.addWidget(button_group)

        layout.addLayout(list_layout)

        # 模板内容预览
        content_group = QGroupBox("模板内容")
        content_layout = QVBoxLayout(content_group)

        self.template_preview = QTextEdit()
        self.template_preview.setReadOnly(True)
        self.template_preview.setMaximumHeight(150)
        content_layout.addWidget(self.template_preview)

        layout.addWidget(content_group)

        # 对话框按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
        )
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

    def _load_templates(self):
        """加载模板列表"""
        self.template_list.clear()

        try:
            manager = get_prompt_template_manager()
            templates = manager.get_all_templates()

            for template in templates:
                display_text = f"{template.name}"
                if template.is_builtin:
                    display_text += " [内置]"
                if template.is_default:
                    display_text += " ⭐"
                self.template_list.addItem(display_text, template.id)

        except Exception as e:
            print(f"加载模板失败: {e}")

    def _on_template_selected(self, index: int):
        """模板选择变更"""
        template_id = self.template_list.currentData()
        if not template_id:
            return

        try:
            manager = get_prompt_template_manager()
            template = manager.get_template(template_id)

            if template:
                self.template_info.setText(
                    f"描述: {template.description}\n"
                    f"风格: {template.style.value}\n"
                    f"类型: {'内置' if template.is_builtin else '自定义'}"
                )
                self.template_preview.setText(template.template)

                # 内置模板不能设为默认（通过管理器设置）
                self.set_default_btn.setEnabled(True)

        except Exception as e:
            print(f"加载模板详情失败: {e}")

    def _on_preview(self):
        """预览模板"""
        template_id = self.template_list.currentData()
        if not template_id:
            return

        try:
            manager = get_prompt_template_manager()
            preview = manager.preview_template(template_id)

            # 显示预览对话框
            preview_dialog = QDialog(self)
            preview_dialog.setWindowTitle("模板预览")
            preview_dialog.setMinimumSize(600, 400)

            layout = QVBoxLayout(preview_dialog)

            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setText(preview)
            layout.addWidget(text_edit)

            button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
            button_box.accepted.connect(preview_dialog.accept)
            layout.addWidget(button_box)

            preview_dialog.exec()

        except Exception as e:
            QMessageBox.warning(self, "预览失败", f"无法预览模板: {e}")

    def _on_set_default(self):
        """设为默认模板"""
        template_id = self.template_list.currentData()
        if not template_id:
            return

        try:
            manager = get_prompt_template_manager()
            if manager.set_default_template(template_id):
                QMessageBox.information(self, "成功", "已设为默认模板")
                self._load_templates()  # 刷新列表
            else:
                QMessageBox.warning(self, "失败", "设置默认模板失败")

        except Exception as e:
            QMessageBox.warning(self, "错误", f"设置失败: {e}")

    def _on_export(self):
        """导出模板"""
        template_id = self.template_list.currentData()
        if not template_id:
            return

        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出模板",
            f"{template_id}.yaml",
            "YAML files (*.yaml *.yml)"
        )

        if file_path:
            try:
                manager = get_prompt_template_manager()
                if manager.export_template(template_id, file_path):
                    QMessageBox.information(self, "成功", f"模板已导出到:\n{file_path}")
                else:
                    QMessageBox.warning(self, "失败", "导出模板失败")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"导出失败: {e}")

    def _on_import(self):
        """导入模板"""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "导入模板",
            "",
            "YAML files (*.yaml *.yml)"
        )

        if file_path:
            try:
                manager = get_prompt_template_manager()
                template = manager.import_template(file_path)

                if template:
                    QMessageBox.information(
                        self,
                        "成功",
                        f"模板 '{template.name}' 导入成功"
                    )
                    self._load_templates()  # 刷新列表
                else:
                    QMessageBox.warning(self, "失败", "导入模板失败")

            except Exception as e:
                QMessageBox.warning(self, "错误", f"导入失败: {e}")
