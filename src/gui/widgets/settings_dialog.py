"""设置对话框 - 应用配置管理"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QLineEdit, QComboBox, QPushButton, QSpinBox,
    QCheckBox, QFileDialog, QMessageBox,
    QDialogButtonBox, QFormLayout, QGroupBox, QWidget,
    QSlider, QSizePolicy
)
from PySide6.QtCore import Qt
from pathlib import Path

from ...services.config_manager import get_config_manager
from ...utils.credential_manager import CredentialManager
from ...config.constants import Defaults, DialogConfig, Icons, ConfigMaps, SliderConfig, SpinBoxConfig


class SettingsDialog(QDialog):
    """设置对话框 - 管理应用配置"""

    # 使用双向映射类简化配置映射
    THEME_MAP = ConfigMaps.THEME
    LANG_MAP = ConfigMaps.LANGUAGE
    ORGANIZE_MAP = ConfigMaps.ORGANIZE
    QUALITY_MAP = ConfigMaps.VIDEO_QUALITY

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{Icons.SETTINGS} 设置")
        self.setMinimumSize(DialogConfig.SETTINGS_MIN_WIDTH, DialogConfig.SETTINGS_MIN_HEIGHT)
        self.resize(DialogConfig.SETTINGS_WIDTH, DialogConfig.SETTINGS_HEIGHT)
        
        self.config_manager = get_config_manager()
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 创建标签页
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(False)
        
        # 设置标签页样式
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #d0d0d0;
                border-radius: 6px;
                background: white;
                margin-top: -1px;
            }
            QTabBar::tab {
                padding: 10px 20px;
                margin-right: 4px;
                border: 1px solid #d0d0d0;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                background: #f5f5f5;
                color: #666;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background: white;
                color: #2196F3;
                font-weight: bold;
                border-bottom: 2px solid #2196F3;
            }
            QTabBar::tab:hover:!selected {
                background: #e8e8e8;
                color: #333;
            }
        """)
        
        # 通用设置标签页
        self.general_tab = self._create_general_tab()
        self.tab_widget.addTab(self.general_tab, "⚙️ 通用")
        
        # AI 设置标签页
        self.ai_tab = self._create_ai_tab()
        self.tab_widget.addTab(self.ai_tab, "🤖 AI 引擎")

        # Prompt 模板标签页
        self.prompt_tab = self._create_prompt_tab()
        self.tab_widget.addTab(self.prompt_tab, "📝 Prompt 模板")

        # 导出设置标签页
        self.export_tab = self._create_export_tab()
        self.tab_widget.addTab(self.export_tab, "📤 导出")

        # 下载设置标签页
        self.download_tab = self._create_download_tab()
        self.tab_widget.addTab(self.download_tab, "⬇️ 下载")
        
        layout.addWidget(self.tab_widget)

        # 按钮区域
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _create_general_tab(self) -> QWidget:
        """创建通用设置标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(20)
        layout.setContentsMargins(15, 15, 15, 15)

        # 主题设置
        theme_group = QGroupBox("🎨 外观")
        theme_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        theme_layout = QFormLayout(theme_group)
        theme_layout.setSpacing(12)
        theme_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["跟随系统", "浅色", "深色"])
        self.theme_combo.setCurrentText("跟随系统")
        self.theme_combo.setMinimumWidth(200)
        theme_layout.addRow("主题:", self.theme_combo)
        
        self.language_combo = QComboBox()
        self.language_combo.addItems(["简体中文", "English"])
        self.language_combo.setCurrentText("简体中文")
        self.language_combo.setMinimumWidth(200)
        theme_layout.addRow("语言:", self.language_combo)
        
        layout.addWidget(theme_group)

        # 系统托盘设置
        tray_group = QGroupBox("🔔 系统托盘")
        tray_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        tray_layout = QVBoxLayout(tray_group)
        tray_layout.setSpacing(10)
        
        self.minimize_to_tray = QCheckBox("最小化到系统托盘而不是关闭")
        self.minimize_to_tray.setChecked(True)
        tray_layout.addWidget(self.minimize_to_tray)
        
        self.show_notifications = QCheckBox("任务完成时显示系统通知")
        self.show_notifications.setChecked(True)
        tray_layout.addWidget(self.show_notifications)
        
        layout.addWidget(tray_group)
        layout.addStretch()
        
        return tab

    def _create_ai_tab(self) -> QWidget:
        """创建 AI 设置标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(20)
        layout.setContentsMargins(15, 15, 15, 15)

        # AI 引擎设置
        engine_group = QGroupBox("🤖 AI 引擎")
        engine_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        engine_layout = QFormLayout(engine_group)
        engine_layout.setSpacing(12)
        engine_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self.ai_engine_combo = QComboBox()
        self.ai_engine_combo.addItems(["DeepSeek", "OpenAI", "Anthropic"])
        self.ai_engine_combo.setCurrentText("DeepSeek")
        self.ai_engine_combo.setMinimumWidth(200)
        engine_layout.addRow("引擎:", self.ai_engine_combo)
        
        self.ai_model_input = QLineEdit()
        self.ai_model_input.setText("deepseek-chat")
        self.ai_model_input.setMinimumWidth(300)
        self.ai_model_input.setPlaceholderText("例如: deepseek-chat, gpt-4, claude-3-opus")
        engine_layout.addRow("模型:", self.ai_model_input)
        
        self.base_url_input = QLineEdit()
        self.base_url_input.setText("https://api.deepseek.com")
        self.base_url_input.setMinimumWidth(300)
        self.base_url_input.setPlaceholderText("API 基础 URL")
        engine_layout.addRow("Base URL:", self.base_url_input)
        
        layout.addWidget(engine_group)

        # API Key 设置
        api_key_group = QGroupBox("🔑 API Key")
        api_key_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        api_key_layout = QFormLayout(api_key_group)
        api_key_layout.setSpacing(12)
        api_key_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # API Key 输入行（输入框 + 显示按钮）
        api_key_row = QHBoxLayout()
        api_key_row.setSpacing(8)
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("输入您的 API Key...")
        self.api_key_input.setMinimumWidth(350)
        api_key_row.addWidget(self.api_key_input)
        
        # 显示/隐藏按钮
        show_btn = QPushButton("显示")
        show_btn.setCheckable(True)
        show_btn.setFixedWidth(60)
        show_btn.setStyleSheet("""
            QPushButton {
                padding: 5px 10px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background: #f5f5f5;
            }
            QPushButton:hover {
                background: #e0e0e0;
            }
        """)
        show_btn.toggled.connect(lambda checked: (
            self.api_key_input.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            ),
            show_btn.setText("隐藏" if checked else "显示")
        ))
        api_key_row.addWidget(show_btn)
        
        api_key_layout.addRow("API Key:", api_key_row)
        
        # API Key 说明
        api_key_hint = QLabel("💡 API Key 将安全存储在系统密钥环中，不会以明文保存")
        api_key_hint.setStyleSheet("color: #666; font-size: 11px;")
        api_key_layout.addRow("", api_key_hint)
        
        layout.addWidget(api_key_group)

        # 生成参数设置
        params_group = QGroupBox("⚙️ 生成参数")
        params_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        params_layout = QFormLayout(params_group)
        params_layout.setSpacing(12)
        params_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # 温度滑块行
        temp_row = QHBoxLayout()
        temp_row.setSpacing(10)
        
        self.temperature_slider = QSlider(Qt.Orientation.Horizontal)
        self.temperature_slider.setRange(SliderConfig.TEMPERATURE_MIN, SliderConfig.TEMPERATURE_MAX)
        self.temperature_slider.setValue(SliderConfig.TEMPERATURE_DEFAULT)
        self.temperature_slider.setMinimumWidth(200)
        temp_row.addWidget(self.temperature_slider, 1)

        self.temp_value_label = QLabel(f"{SliderConfig.TEMPERATURE_DEFAULT / 100:.1f}")
        self.temp_value_label.setFixedWidth(40)
        self.temp_value_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        temp_row.addWidget(self.temp_value_label)

        self.temperature_slider.valueChanged.connect(
            lambda v: self.temp_value_label.setText(f"{v/100:.1f}")
        )

        params_layout.addRow("温度:", temp_row)

        temp_hint = QLabel("较低值使输出更确定，较高值使输出更有创意")
        temp_hint.setStyleSheet("color: #666; font-size: 11px;")
        params_layout.addRow("", temp_hint)

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(SpinBoxConfig.MAX_TOKENS_MIN, SpinBoxConfig.MAX_TOKENS_MAX)
        self.max_tokens_spin.setValue(SpinBoxConfig.MAX_TOKENS_DEFAULT)
        self.max_tokens_spin.setSingleStep(SpinBoxConfig.MAX_TOKENS_STEP)
        self.max_tokens_spin.setMinimumWidth(200)
        params_layout.addRow("最大 Token:", self.max_tokens_spin)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(SpinBoxConfig.TIMEOUT_MIN, SpinBoxConfig.TIMEOUT_MAX)
        self.timeout_spin.setValue(SpinBoxConfig.TIMEOUT_DEFAULT)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setMinimumWidth(200)
        params_layout.addRow("超时:", self.timeout_spin)
        
        layout.addWidget(params_group)
        layout.addStretch()

        return tab

    def _create_prompt_tab(self) -> QWidget:
        """创建 Prompt 模板标签页"""
        from .prompt_template_dialog import PromptTemplateDialog

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(20)
        layout.setContentsMargins(15, 15, 15, 15)

        # 说明文本
        hint_label = QLabel("💡 在此管理 Prompt 模板，包括创建、编辑、删除、导入和导出模板")
        hint_label.setStyleSheet("color: #666; font-size: 12px;")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        # 打开模板管理按钮
        manage_btn = QPushButton("📝 打开模板管理器")
        manage_btn.setStyleSheet("""
            QPushButton {
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        manage_btn.clicked.connect(self._open_prompt_manager)
        layout.addWidget(manage_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # 模板说明
        info_group = QGroupBox("📖 模板变量说明")
        info_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        info_layout = QVBoxLayout(info_group)

        info_text = QLabel("""
        在 Prompt 模板中可以使用以下变量：

        <b>{title}</b> - 视频标题
        <b>{transcript}</b> - 转录文本内容
        <b>{author}</b> - 视频作者
        <b>{platform}</b> - 视频平台（如 Bilibili、YouTube）
        <b>{duration}</b> - 视频时长（秒）

        示例：
        <code>请总结视频"{title}"的内容，作者是{author}。</code>
        """)
        info_text.setStyleSheet("color: #333; font-size: 12px; line-height: 1.6;")
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)

        layout.addWidget(info_group)
        layout.addStretch()

        return tab

    def _open_prompt_manager(self):
        """打开 Prompt 模板管理对话框"""
        from .prompt_template_dialog import PromptTemplateDialog

        dialog = PromptTemplateDialog(self)
        dialog.exec()

    def _create_export_tab(self) -> QWidget:
        """创建导出设置标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(20)
        layout.setContentsMargins(15, 15, 15, 15)

        # Obsidian 设置
        obsidian_group = QGroupBox("📝 Obsidian")
        obsidian_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        obsidian_layout = QFormLayout(obsidian_group)
        obsidian_layout.setSpacing(12)
        obsidian_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self.obsidian_enabled = QCheckBox("启用 Obsidian 导出")
        self.obsidian_enabled.setChecked(True)
        obsidian_layout.addRow(self.obsidian_enabled)
        
        # Vault 路径行
        vault_row = QHBoxLayout()
        vault_row.setSpacing(8)
        
        self.obsidian_vault_input = QLineEdit()
        self.obsidian_vault_input.setPlaceholderText("选择 Obsidian Vault 路径...")
        self.obsidian_vault_input.setMinimumWidth(350)
        # 当路径为空时自动取消启用
        self.obsidian_vault_input.textChanged.connect(self._on_obsidian_path_changed)
        vault_row.addWidget(self.obsidian_vault_input, 1)
        
        browse_vault_btn = QPushButton("浏览...")
        browse_vault_btn.setFixedWidth(80)
        browse_vault_btn.clicked.connect(self._browse_obsidian_vault)
        vault_row.addWidget(browse_vault_btn)
        
        obsidian_layout.addRow("Vault 路径:", vault_row)
        
        self.obsidian_subfolder_input = QLineEdit()
        self.obsidian_subfolder_input.setText(Defaults.OBSIDIAN_SUBFOLDER)
        self.obsidian_subfolder_input.setMinimumWidth(350)
        self.obsidian_subfolder_input.setPlaceholderText("笔记保存的子文件夹路径")
        obsidian_layout.addRow("子文件夹:", self.obsidian_subfolder_input)
        
        layout.addWidget(obsidian_group)

        # 本地文件夹设置
        local_group = QGroupBox("📁 本地文件夹")
        local_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        local_layout = QFormLayout(local_group)
        local_layout.setSpacing(12)
        local_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # 本地文件夹说明
        local_hint = QLabel("💡 本地文件夹为必需，如路径为空将使用默认路径")
        local_hint.setStyleSheet("color: #2196F3; font-size: 11px;")
        local_layout.addRow(local_hint)

        # 本地路径行
        local_row = QHBoxLayout()
        local_row.setSpacing(8)

        self.local_path_input = QLineEdit()
        self.local_path_input.setPlaceholderText(f"默认: ~/Downloads/VideoMind")
        self.local_path_input.setMinimumWidth(350)
        local_row.addWidget(self.local_path_input, 1)
        
        browse_local_btn = QPushButton("浏览...")
        browse_local_btn.setFixedWidth(80)
        browse_local_btn.clicked.connect(self._browse_local_path)
        local_row.addWidget(browse_local_btn)
        
        local_layout.addRow("输出路径:", local_row)
        
        self.organize_by_combo = QComboBox()
        self.organize_by_combo.addItems(["按日期", "按来源", "不组织"])
        self.organize_by_combo.setCurrentText("按日期")
        self.organize_by_combo.setMinimumWidth(200)
        local_layout.addRow("组织方式:", self.organize_by_combo)
        
        organize_hint = QLabel("💡 按日期组织: 2024-01-15/video_title/")
        organize_hint.setStyleSheet("color: #666; font-size: 11px;")
        local_layout.addRow("", organize_hint)
        
        layout.addWidget(local_group)
        layout.addStretch()
        
        return tab

    def _create_download_tab(self) -> QWidget:
        """创建下载设置标签页"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(20)
        layout.setContentsMargins(15, 15, 15, 15)

        # 下载设置
        download_group = QGroupBox("⬇️ 下载设置")
        download_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 13px; }")
        download_layout = QFormLayout(download_group)
        download_layout.setSpacing(12)
        download_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # 下载目录行
        download_row = QHBoxLayout()
        download_row.setSpacing(8)
        
        self.download_output_input = QLineEdit()
        self.download_output_input.setPlaceholderText("选择下载目录...")
        self.download_output_input.setMinimumWidth(350)
        download_row.addWidget(self.download_output_input, 1)
        
        browse_download_btn = QPushButton("浏览...")
        browse_download_btn.setFixedWidth(80)
        browse_download_btn.clicked.connect(self._browse_download_path)
        download_row.addWidget(browse_download_btn)
        
        download_layout.addRow("下载目录:", download_row)
        
        self.video_quality_combo = QComboBox()
        self.video_quality_combo.addItems(["最佳质量", "1080p", "720p", "480p", "最低质量"])
        self.video_quality_combo.setCurrentText("最佳质量")
        self.video_quality_combo.setMinimumWidth(200)
        download_layout.addRow("视频质量:", self.video_quality_combo)
        
        quality_hint = QLabel("💡 实际下载质量取决于视频源提供的选项")
        quality_hint.setStyleSheet("color: #666; font-size: 11px;")
        download_layout.addRow("", quality_hint)
        
        self.download_video_check = QCheckBox("默认下载视频（而非仅音频）")
        self.download_video_check.setChecked(True)
        download_layout.addRow(self.download_video_check)
        
        layout.addWidget(download_group)
        layout.addStretch()
        
        return tab

    def _browse_obsidian_vault(self):
        """浏览 Obsidian Vault 路径"""
        path = QFileDialog.getExistingDirectory(self, "选择 Obsidian Vault")
        if path:
            self.obsidian_vault_input.setText(path)

    def _browse_local_path(self):
        """浏览本地输出路径"""
        path = QFileDialog.getExistingDirectory(self, "选择本地输出目录")
        if path:
            self.local_path_input.setText(path)

    def _on_obsidian_path_changed(self, text):
        """当 Obsidian 路径改变时，如果为空则自动取消启用"""
        if not text.strip():
            self.obsidian_enabled.setChecked(False)
        else:
            self.obsidian_enabled.setChecked(True)

    def _browse_download_path(self):
        """浏览下载路径"""
        path = QFileDialog.getExistingDirectory(self, "选择下载目录")
        if path:
            self.download_output_input.setText(path)

    def _load_settings(self):
        """加载当前设置"""
        config = self.config_manager.config

        # 通用设置
        self.theme_combo.setCurrentText(self.THEME_MAP.to_display(config.ui.theme, "跟随系统"))
        self.language_combo.setCurrentText(self.LANG_MAP.to_display(config.ui.language, "简体中文"))
        
        self.minimize_to_tray.setChecked(config.ui.minimize_to_tray)
        self.show_notifications.setChecked(config.ui.show_notifications)
        
        # AI 设置
        self.ai_engine_combo.setCurrentText(config.ai.engine)
        self.ai_model_input.setText(config.ai.model)
        self.base_url_input.setText(config.ai.base_url)
        
        # 从密钥环加载 API Key
        api_key = self.config_manager.get_api_key()
        if api_key:
            self.api_key_input.setText(api_key)
        
        self.temperature_slider.setValue(int(config.ai.temperature * 100))
        self.temp_value_label.setText(f"{config.ai.temperature:.1f}")
        self.max_tokens_spin.setValue(config.ai.max_tokens)
        self.timeout_spin.setValue(config.ai.timeout)
        
        # 导出设置 - 先设置路径，再设置启用状态，避免信号触发覆盖
        self.obsidian_vault_input.setText(config.export.obsidian.vault_path)
        self.obsidian_subfolder_input.setText(config.export.obsidian.subfolder)
        self.obsidian_enabled.setChecked(config.export.obsidian.enabled)

        # 本地文件夹始终启用，不需要加载 enabled 状态
        self.local_path_input.setText(config.export.local.output_path)

        self.organize_by_combo.setCurrentText(self.ORGANIZE_MAP.to_display(config.export.local.organize_by, "按日期"))

        # 下载设置
        self.download_output_input.setText(config.download.output_dir)

        self.video_quality_combo.setCurrentText(self.QUALITY_MAP.to_display(config.download.video_quality, "最佳质量"))
        
        self.download_video_check.setChecked(config.download.download_video)

    def _on_save(self):
        """保存设置"""
        try:
            # ===== 验证本地文件夹路径 =====
            local_path = self.local_path_input.text().strip()
            if not local_path:
                # 如果路径为空，使用默认路径
                local_path = str(Defaults.OUTPUT_DIR)
                self.local_path_input.setText(local_path)
                QMessageBox.information(
                    self,
                    "提示",
                    f"本地文件夹路径为空，已自动设置为默认路径:\n{local_path}"
                )

            # ===== 验证 Obsidian 配置 =====
            if self.obsidian_enabled.isChecked() and not self.obsidian_vault_input.text().strip():
                QMessageBox.warning(
                    self,
                    "配置错误",
                    "已启用 Obsidian 导出，但未配置 Vault 路径。\n\n"
                    "请配置 Vault 路径，或取消勾选 Obsidian 导出。"
                )
                return  # 不保存，让用户修正

            # 通用设置
            self.config_manager.update_ui(
                theme=self.THEME_MAP.to_config(self.theme_combo.currentText(), "system"),
                language=self.LANG_MAP.to_config(self.language_combo.currentText(), "zh_CN"),
                minimize_to_tray=self.minimize_to_tray.isChecked(),
                show_notifications=self.show_notifications.isChecked()
            )

            # AI 设置
            self.config_manager.update_ai(
                engine=self.ai_engine_combo.currentText(),
                model=self.ai_model_input.text(),
                base_url=self.base_url_input.text(),
                temperature=self.temperature_slider.value() / 100,
                max_tokens=self.max_tokens_spin.value(),
                timeout=self.timeout_spin.value()
            )

            # 保存或删除 API Key
            api_key = self.api_key_input.text().strip()
            if api_key:
                self.config_manager.set_api_key(api_key)
            else:
                # 如果输入框为空，删除已保存的 API Key
                provider = self.ai_engine_combo.currentText().lower()
                from ...utils.credential_manager import delete_api_key
                delete_api_key(provider)

            # 导出设置（本地文件夹始终启用）
            self.config_manager.update_export(
                obsidian={
                    "enabled": self.obsidian_enabled.isChecked(),
                    "vault_path": self.obsidian_vault_input.text(),
                    "subfolder": self.obsidian_subfolder_input.text()
                },
                local={
                    "enabled": True,  # 本地文件夹始终启用
                    "output_path": local_path,
                    "organize_by": self.ORGANIZE_MAP.to_config(self.organize_by_combo.currentText(), "date")
                }
            )

            # 下载设置
            self.config_manager.update_download(
                output_dir=self.download_output_input.text(),
                video_quality=self.QUALITY_MAP.to_config(self.video_quality_combo.currentText(), "best"),
                download_video=self.download_video_check.isChecked()
            )
            
            QMessageBox.information(self, "成功", "设置已保存")
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存设置失败: {e}")
