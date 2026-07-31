"""CredentialManager 测试"""

from unittest import mock

import keyring
import pytest
from keyring.errors import PasswordDeleteError, PasswordSetError

from src.utils.credential_manager import (
    CredentialManager,
    delete_api_key,
    get_api_key,
    save_api_key,
)


class TestCredentialManagerSave:
    """save_api_key 测试"""

    def test_save_success(self):
        with mock.patch("src.utils.credential_manager.keyring.set_password", return_value=None):
            result = CredentialManager.save_api_key("deepseek", "sk-xxx")
            assert result is True

    def test_save_password_set_error(self):
        with mock.patch("src.utils.credential_manager.keyring.set_password", side_effect=PasswordSetError("keyring locked")):
            result = CredentialManager.save_api_key("deepseek", "sk-xxx")
            assert result is False

    def test_save_unexpected_error(self):
        with mock.patch("src.utils.credential_manager.keyring.set_password", side_effect=RuntimeError("unexpected")):
            result = CredentialManager.save_api_key("deepseek", "sk-xxx")
            assert result is False


class TestCredentialManagerGet:
    """get_api_key 测试"""

    def test_get_success(self):
        with mock.patch("src.utils.credential_manager.keyring.get_password", return_value="sk-xxx"):
            result = CredentialManager.get_api_key("deepseek")
            assert result == "sk-xxx"

    def test_get_none(self):
        with mock.patch("src.utils.credential_manager.keyring.get_password", return_value=None):
            result = CredentialManager.get_api_key("deepseek")
            assert result is None

    def test_get_empty_string(self):
        with mock.patch("src.utils.credential_manager.keyring.get_password", return_value=""):
            result = CredentialManager.get_api_key("deepseek")
            assert result == ""

    def test_get_exception(self):
        with mock.patch("src.utils.credential_manager.keyring.get_password", side_effect=RuntimeError("keyring unavailable")):
            result = CredentialManager.get_api_key("deepseek")
            assert result is None


class TestCredentialManagerDelete:
    """delete_api_key 测试"""

    def test_delete_success(self):
        with mock.patch("src.utils.credential_manager.keyring.delete_password", return_value=None):
            result = CredentialManager.delete_api_key("deepseek")
            assert result is True

    def test_delete_password_not_found(self):
        with mock.patch("src.utils.credential_manager.keyring.delete_password", side_effect=PasswordDeleteError("not found")):
            result = CredentialManager.delete_api_key("deepseek")
            assert result is True

    def test_delete_unexpected_error(self):
        with mock.patch("src.utils.credential_manager.keyring.delete_password", side_effect=RuntimeError("permission denied")):
            result = CredentialManager.delete_api_key("deepseek")
            assert result is False


class TestCredentialManagerMigrate:
    """migrate_from_config 测试"""

    def test_migrate_empty_key_returns_true(self):
        result = CredentialManager.migrate_from_config("deepseek", "")
        assert result is True

    def test_migrate_none_key_returns_true(self):
        result = CredentialManager.migrate_from_config("deepseek", None)
        assert result is True

    def test_migrate_skip_when_already_exists(self):
        with mock.patch.object(CredentialManager, "get_api_key", return_value="sk-existing"):
            with mock.patch.object(CredentialManager, "save_api_key") as mock_save:
                result = CredentialManager.migrate_from_config("deepseek", "sk-plain")
                assert result is True
                mock_save.assert_not_called()

    def test_migrate_success(self):
        with mock.patch.object(CredentialManager, "get_api_key", return_value=None):
            with mock.patch.object(CredentialManager, "save_api_key", return_value=True):
                result = CredentialManager.migrate_from_config("deepseek", "sk-plain")
                assert result is True

    def test_migrate_save_fails(self):
        with mock.patch.object(CredentialManager, "get_api_key", return_value=None):
            with mock.patch.object(CredentialManager, "save_api_key", return_value=False):
                result = CredentialManager.migrate_from_config("deepseek", "sk-plain")
                assert result is False


class TestConvenienceFunctions:
    """全局便捷函数测试"""

    def test_save_api_key(self):
        with mock.patch.object(CredentialManager, "save_api_key", return_value=True):
            assert save_api_key("deepseek", "sk-xxx") is True

    def test_get_api_key(self):
        with mock.patch.object(CredentialManager, "get_api_key", return_value="sk-xxx"):
            assert get_api_key("deepseek") == "sk-xxx"

    def test_delete_api_key(self):
        with mock.patch.object(CredentialManager, "delete_api_key", return_value=True):
            assert delete_api_key("deepseek") is True
