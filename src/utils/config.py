"""配置管理"""

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, SecretStr


class AIProviderConfig(BaseModel):
    """AI 提供商配置"""
    name: str = Field(..., description="显示名称")
    provider_type: Literal["openai", "openai_compatible", "anthropic", "ollama"] = Field(
        ..., description="提供商类型"
    )
    base_url: Optional[str] = Field(None, description="API 基础URL")
    api_key: Optional[SecretStr] = Field(None, description="API 密钥")
    model: str = Field(..., description="默认模型")
    default_prompt: str = Field("academic_summary", description="默认Prompt模板")
    enabled: bool = Field(True, description="是否启用")
    
    class Config:
        frozen = True


class ExportTargetConfig(BaseModel):
    """导出目标配置基类"""
    enabled: bool = Field(False, description="是否启用")
    
    class Config:
        frozen = True


class ObsidianConfig(ExportTargetConfig):
    """Obsidian 导出配置"""
    vault_path: Path = Field(..., description="Vault 路径")
    subfolder: str = Field("Inbox/Videos", description="子文件夹")
    template_path: Optional[Path] = Field(None, description="模板路径")
    use_wikilinks: bool = Field(True, description="使用 [[WikiLinks]]")


class LocalExportConfig(ExportTargetConfig):
    """本地导出配置"""
    output_path: Path = Field(Path.home() / "Downloads" / "VideoMind", description="输出路径")
    organize_by: Literal["date", "title", "flat"] = Field("date", description="组织方式")
    keep_audio: bool = Field(True, description="保留音频")
    keep_video: bool = Field(False, description="保留视频")


class NotionConfig(ExportTargetConfig):
    """Notion 导出配置"""
    token: Optional[SecretStr] = Field(None, description="Integration Token")
    database_id: Optional[str] = Field(None, description="Database ID")


class ProcessingConfig(BaseModel):
    """处理配置"""
    default_mode: Literal["full", "download_only", "transcribe_only"] = Field(
        "full", description="默认处理模式"
    )
    whisper_model: Literal["tiny", "base", "small", "medium", "large"] = Field(
        "small", description="默认Whisper模型"
    )
    concurrent_downloads: int = Field(2, ge=1, le=5, description="并发下载数")
    concurrent_ai: int = Field(1, ge=1, le=3, description="并发AI请求数")
    auto_start: bool = Field(False, description="开机自启")
    minimize_to_tray: bool = Field(True, description="最小化到托盘")


class UIConfig(BaseModel):
    """UI 配置"""
    theme: Literal["light", "dark", "system"] = Field("system", description="主题")
    language: Literal["zh", "en"] = Field("zh", description="界面语言")
    window_width: int = Field(1200, ge=800, le=1920)
    window_height: int = Field(800, ge=600, le=1080)


class AppConfig(BaseModel):
    """
    应用配置根对象
    
    对应配置文件 config.yaml 的结构
    """
    # 版本号（用于配置迁移）
    version: str = Field("1.0.0", description="配置版本")
    
    # 处理配置
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    
    # UI 配置
    ui: UIConfig = Field(default_factory=UIConfig)
    
    # AI 提供商列表
    ai_providers: List[AIProviderConfig] = Field(default_factory=list)
    
    # 导出目标配置
    exports: Dict[str, ExportTargetConfig] = Field(default_factory=dict)
    
    class Config:
        frozen = True
    
    @classmethod
    def load_from_file(cls, path: Path) -> "AppConfig":
        """从文件加载配置"""
        raise NotImplementedError()
    
    def save_to_file(self, path: Path) -> None:
        """保存配置到文件"""
        raise NotImplementedError()


class ConfigManager:
    """
    配置管理器
    
    负责配置的加载、保存和验证
    """
    
    DEFAULT_CONFIG_PATH = Path.home() / ".config" / "VideoMind" / "config.yaml"
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._config: Optional[AppConfig] = None
    
    def load(self) -> AppConfig:
        """加载配置"""
        raise NotImplementedError()
    
    def save(self, config: AppConfig) -> None:
        """保存配置"""
        raise NotImplementedError()
    
    def get(self) -> AppConfig:
        """获取当前配置（缓存）"""
        raise NotImplementedError()
    
    def reset_to_default(self) -> AppConfig:
        """重置为默认配置"""
        raise NotImplementedError()
