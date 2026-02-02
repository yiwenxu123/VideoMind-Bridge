"""简化的 Prompt 模板选择组件"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton
)
from PySide6.QtCore import Qt

from ...services.prompt_template import get_prompt_template_manager


class PromptTemplateSelector(QWidget):
    """简化的 Prompt 模板选择组件（仅包含模板选择和管理按钮）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._load_templates()

    def _setup_ui(self):
        """设置 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 标签
        label = QLabel("📝 Prompt模板:")
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)

        # 模板选择下拉框
        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(200)
        self.template_combo.setStyleSheet("""
            QComboBox {
                padding: 6px;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.template_combo)

        # 管理模板按钮
        self.manage_button = QPushButton("⚙️ 管理模板")
        self.manage_button.setStyleSheet("""
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
        self.manage_button.clicked.connect(self._on_manage_clicked)
        layout.addWidget(self.manage_button)

        # 显示当前AI引擎信息
        self.ai_info_label = QLabel()
        self.ai_info_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.ai_info_label)

        layout.addStretch()

    def _load_templates(self):
        """加载模板列表"""
        self.template_combo.clear()

        try:
            manager = get_prompt_template_manager()
            templates = manager.get_all_templates()

            for template in templates:
                display_text = template.name
                if template.is_default:
                    display_text = f"⭐ {display_text}"
                if template.is_builtin:
                    display_text = f"[内置] {display_text}"

                self.template_combo.addItem(display_text, template.id)

            # 设置当前选中默认模板
            for i, template in enumerate(templates):
                if template.is_default:
                    self.template_combo.setCurrentIndex(i)
                    break

        except Exception as e:
            print(f"加载模板失败: {e}")
            self.template_combo.addItem("默认风格", "default")

    def _load_ai_info(self):
        """加载AI引擎信息"""
        try:
            from ...services.config_manager import get_config_manager
            config = get_config_manager().ai

            engine_map = {
                "deepseek": "DeepSeek",
                "zhipu": "智谱AI",
                "moonshot": "Moonshot",
                "minimax": "MiniMax",
                "doubao": "豆包",
                "ollama": "Ollama"
            }
            engine_name = engine_map.get(config.engine, config.engine)
            self.ai_info_label.setText(f"当前AI: {engine_name} ({config.model})")
        except Exception:
            self.ai_info_label.setText("")

    def _on_manage_clicked(self):
        """打开模板管理对话框"""
        from PySide6.QtWidgets import QDialog
        from .prompt_template_dialog import PromptTemplateDialog

        dialog = PromptTemplateDialog(self)
        dialog.exec()
        # 刷新模板列表
        self._load_templates()

    def get_selected_template_id(self) -> str:
        """获取当前选中的模板 ID"""
        return self.template_combo.currentData() or "default"

    def refresh(self):
        """刷新模板列表和AI信息"""
        self._load_templates()
        self._load_ai_info()
