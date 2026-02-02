"""配置管理器 - 单例模式"""

import logging
import threading
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
from functools import lru_cache

from ..models.config import AppConfig, AIConfig, DownloadConfig, ExportConfig, UIConfig
from ..utils.credential_manager import CredentialManager

logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器 - 单例模式（线程安全）

    安全特性：
    - API Key 使用系统密钥环加密存储，不在配置文件中保存明文
    - 配置文件只保存 API Key 的占位符，实际值从密钥环读取
    - 线程安全：使用锁保护实例创建
    """

    _instance: Optional["ConfigManager"] = None
    _config: Optional[AppConfig] = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                # 双重检查锁定
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 使用锁保护初始化过程
        with self._lock:
            if self._initialized:
                return

            self._config_dir = Path.home() / ".config" / "VideoMind"
            self._config_file = self._config_dir / "config.yaml"
            self._config = self._load_config()

            # 迁移配置文件中的明文 API Key 到密钥环
            self._migrate_api_keys()

            self._initialized = True

    def _load_config(self) -> AppConfig:
        """从 YAML 文件加载配置"""
        if self._config_file.exists():
            try:
                with open(self._config_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data:
                    return AppConfig.from_dict(data)
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}, 使用默认配置")

        # 如果文件不存在或加载失败，返回默认配置
        return AppConfig.get_default_config()

    def _migrate_api_keys(self) -> None:
        """迁移配置文件中的明文 API Key 到密钥环"""
        # 检查 AI 配置中的 API Key
        ai_config = self._config.ai
        if ai_config.api_key and ai_config.api_key.strip():
            # 尝试迁移到密钥环
            provider = ai_config.engine.lower()
            success = CredentialManager.migrate_from_config(provider, ai_config.api_key)
            if success:
                # 迁移成功后，清空配置文件中的 API Key
                ai_config.api_key = ""
                self.save()
                logger.info(f"API Key 已迁移到系统密钥环，配置文件中的明文已清除")

    def get_api_key(self, provider: Optional[str] = None) -> Optional[str]:
        """
        获取 API Key（从密钥环）

        Args:
            provider: 服务提供商，默认为当前配置的引擎

        Returns:
            API Key 值
        """
        if provider is None:
            provider = self._config.ai.engine.lower()
        return CredentialManager.get_api_key(provider)

    def set_api_key(self, api_key: str, provider: Optional[str] = None) -> bool:
        """
        设置 API Key（保存到密钥环）

        Args:
            api_key: API Key 值
            provider: 服务提供商，默认为当前配置的引擎

        Returns:
            是否保存成功
        """
        if provider is None:
            provider = self._config.ai.engine.lower()
        return CredentialManager.save_api_key(provider, api_key)

    def save(self) -> bool:
        """保存配置到 YAML 文件"""
        try:
            # 确保配置目录存在
            self._config_dir.mkdir(parents=True, exist_ok=True)

            # 转换为字典并保存
            data = self._config.to_dict()
            with open(self._config_file, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

            return True
        except OSError as e:
            logger.error(f"配置文件IO错误: {e}")
            return False
        except yaml.YAMLError as e:
            logger.error(f"配置序列化错误: {e}")
            return False
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            return False

    def reset_to_defaults(self) -> None:
        """重置为默认配置"""
        self._config = AppConfig.get_default_config()
        self.save()

    @property
    def config(self) -> AppConfig:
        """获取当前配置"""
        return self._config

    @property
    def ai(self) -> AIConfig:
        """获取 AI 配置"""
        return self._config.ai

    @property
    def download(self) -> DownloadConfig:
        """获取下载配置"""
        return self._config.download

    @property
    def export(self) -> ExportConfig:
        """获取导出配置"""
        return self._config.export

    @property
    def ui(self) -> UIConfig:
        """获取 UI 配置"""
        return self._config.ui

    def update_ai(self, **kwargs) -> None:
        """更新 AI 配置"""
        for key, value in kwargs.items():
            if hasattr(self._config.ai, key):
                setattr(self._config.ai, key, value)
        self.save()

    def update_download(self, **kwargs) -> None:
        """更新下载配置"""
        for key, value in kwargs.items():
            if hasattr(self._config.download, key):
                setattr(self._config.download, key, value)
        self.save()

    def update_export(self, **kwargs) -> None:
        """更新导出配置"""
        for key, value in kwargs.items():
            if key == "obsidian" and isinstance(value, dict):
                # 更新 Obsidian 配置的各个属性
                for obs_key, obs_value in value.items():
                    if hasattr(self._config.export.obsidian, obs_key):
                        setattr(self._config.export.obsidian, obs_key, obs_value)
            elif key == "local" and isinstance(value, dict):
                # 更新本地配置的各个属性
                for local_key, local_value in value.items():
                    if hasattr(self._config.export.local, local_key):
                        setattr(self._config.export.local, local_key, local_value)
            elif hasattr(self._config.export, key):
                setattr(self._config.export, key, value)
        self.save()

    def update_ui(self, **kwargs) -> None:
        """更新 UI 配置"""
        for key, value in kwargs.items():
            if hasattr(self._config.ui, key):
                setattr(self._config.ui, key, value)
        self.save()

    def export_config(self, file_path: Path) -> bool:
        """导出配置到文件"""
        try:
            data = self._config.to_dict()
            with open(file_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
            return True
        except Exception as e:
            logger.error(f"导出配置失败: {e}")
            return False

    def import_config(self, file_path: Path) -> bool:
        """从文件导入配置"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data:
                self._config = AppConfig.from_dict(data)
                self.save()
                return True
            return False
        except Exception as e:
            logger.error(f"导入配置失败: {e}")
            return False

    def get_config_file_path(self) -> Path:
        """获取配置文件路径"""
        return self._config_file


@lru_cache()
def get_config_manager() -> ConfigManager:
    """获取配置管理器实例（单例）"""
    return ConfigManager()


# 便捷函数
def get_config() -> AppConfig:
    """获取当前配置"""
    return get_config_manager().config


def save_config() -> bool:
    """保存当前配置"""
    return get_config_manager().save()
