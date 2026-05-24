"""凭证管理器 - 使用 keyring 安全存储敏感信息"""

import logging

import keyring
from keyring.errors import PasswordDeleteError, PasswordSetError

logger = logging.getLogger(__name__)


class CredentialManager:
    """凭证管理器 - 使用系统密钥环安全存储 API Key"""

    # 应用名称，用于 keyring 命名空间
    SERVICE_NAME = "VideoMindBridge"

    @classmethod
    def save_api_key(cls, provider: str, api_key: str) -> bool:
        """
        保存 API Key 到系统密钥环

        Args:
            provider: 服务提供商名称（如 "deepseek", "openai"）
            api_key: API Key 值

        Returns:
            是否保存成功
        """
        try:
            keyring.set_password(cls.SERVICE_NAME, provider, api_key)
            logger.info(f"API Key for {provider} saved to system keyring")
            return True
        except PasswordSetError as e:
            logger.error(f"Failed to save API Key for {provider}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error saving API Key: {e}")
            return False

    @classmethod
    def get_api_key(cls, provider: str) -> str | None:
        """
        从系统密钥环获取 API Key

        Args:
            provider: 服务提供商名称

        Returns:
            API Key 值，如果不存在返回 None
        """
        try:
            api_key = keyring.get_password(cls.SERVICE_NAME, provider)
            if api_key:
                logger.debug(f"API Key for {provider} retrieved from system keyring")
            return api_key
        except Exception as e:
            logger.error(f"Failed to retrieve API Key for {provider}: {e}")
            return None

    @classmethod
    def delete_api_key(cls, provider: str) -> bool:
        """
        从系统密钥环删除 API Key

        Args:
            provider: 服务提供商名称

        Returns:
            是否删除成功
        """
        try:
            keyring.delete_password(cls.SERVICE_NAME, provider)
            logger.info(f"API Key for {provider} deleted from system keyring")
            return True
        except PasswordDeleteError:
            # 密码不存在，视为删除成功
            return True
        except Exception as e:
            logger.error(f"Failed to delete API Key for {provider}: {e}")
            return False

    @classmethod
    def migrate_from_config(cls, provider: str, api_key: str) -> bool:
        """
        从配置文件迁移 API Key 到密钥环

        Args:
            provider: 服务提供商名称
            api_key: 配置文件中的明文 API Key

        Returns:
            是否迁移成功
        """
        if not api_key:
            return True

        # 检查是否已经在密钥环中
        existing = cls.get_api_key(provider)
        if existing:
            logger.info(f"API Key for {provider} already exists in keyring, skipping migration")
            return True

        # 迁移到密钥环
        success = cls.save_api_key(provider, api_key)
        if success:
            logger.info(f"API Key for {provider} migrated from config to keyring")
        return success


# 便捷函数
def save_api_key(provider: str, api_key: str) -> bool:
    """保存 API Key"""
    return CredentialManager.save_api_key(provider, api_key)


def get_api_key(provider: str) -> str | None:
    """获取 API Key"""
    return CredentialManager.get_api_key(provider)


def delete_api_key(provider: str) -> bool:
    """删除 API Key"""
    return CredentialManager.delete_api_key(provider)
