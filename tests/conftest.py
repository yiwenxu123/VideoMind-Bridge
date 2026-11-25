import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def isolate_config_dir(request, tmp_path, monkeypatch):
    """测试绝不碰真实 ~/.config/VideoMind

    2026-11-26 实锤：一次普通 pytest 运行（test_api 打 /api/v1/config）把真实配置文件
    按 v2 迁移了一次。迁移本身有备份、值也没丢，但「跑测试会改用户配置」是不能接受的默认。

    这两个模块自己用 tmp home 隔离，放它们自己管，避免和它们的 Path.home patch 打架。
    """
    if request.node.path.name in {"test_config_manager.py", "test_config_migration.py"}:
        yield
        return

    monkeypatch.setenv("VMB_CONFIG_DIR", str(tmp_path / "vmb-config-home"))
    from src.services.config_manager import ConfigManager

    ConfigManager._instance = None
    ConfigManager._initialized = False
    yield
    ConfigManager._instance = None
    ConfigManager._initialized = False


@pytest.fixture(autouse=True)
def disable_platform_rate_limit(monkeypatch):
    """测试默认关闭平台节流，避免真实 sleep；限流测试自行构造实例。"""
    monkeypatch.setenv("VMB_PLATFORM_RATE_LIMIT_ENABLED", "0")
    from src.core.platforms.rate_limit import reset_platform_rate_limiter

    reset_platform_rate_limiter()
    yield
    reset_platform_rate_limiter()


@pytest.fixture(autouse=True)
def mock_keyring():
    """全局 mock keyring，阻止模块初始化时访问真实 macOS 钥匙串

    使用内存存储替代真实钥匙串，支持 set → get 流程，
    确保 test_services.py::test_credential_manager 等集成测试可用。
    test_credential_manager.py 的精确 mock 优先级更高，自动覆盖全局 mock。
    """
    store: dict[str, str] = {}

    def fake_set_password(service: str, username: str, password: str) -> None:
        store[f"{service}:{username}"] = password

    def fake_get_password(service: str, username: str) -> str | None:
        return store.get(f"{service}:{username}")

    def fake_delete_password(service: str, username: str) -> None:
        store.pop(f"{service}:{username}", None)

    with mock.patch("keyring.set_password", side_effect=fake_set_password):
        with mock.patch("keyring.get_password", side_effect=fake_get_password):
            with mock.patch("keyring.delete_password", side_effect=fake_delete_password):
                yield
