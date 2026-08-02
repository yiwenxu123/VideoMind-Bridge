import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


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
