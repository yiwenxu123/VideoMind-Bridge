"""配置迁移（2026-11-26 A1）：v1 文件 → v2 格式，先备份、幂等、可跳过。

v2 只写 version / archive / asr / export.obsidian —— ai、download、transcribe、
ui、performance 已无执行者，继续写盘只会让人以为改了有用。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.config_manager import ConfigManager  # noqa: E402

LEGACY_YAML = """
version: "1"
ai:
  engine: DeepSeek-V3
  model: deepseek-chat
  api_key: ""
download:
  output_dir: /legacy/out
  video_quality: 1080p
transcribe:
  whisper_model: small
export:
  local:
    save_srt: true
  obsidian:
    vault_path: /legacy/vault
ui:
  theme: dark
performance:
  max_workers: 4
"""


@pytest.fixture(autouse=True)
def reset_singleton():
    ConfigManager._instance = None
    ConfigManager._initialized = False
    yield
    ConfigManager._instance = None
    ConfigManager._initialized = False


@pytest.fixture(autouse=True)
def mock_credential_manager():
    with patch("src.services.config_manager.CredentialManager") as mock:
        mock.get_api_key.return_value = None
        mock.migrate_from_config.return_value = True
        yield mock


@pytest.fixture
def home(tmp_path):
    (tmp_path / ".config" / "VideoMind").mkdir(parents=True)
    return tmp_path


def _config_file(home: Path) -> Path:
    return home / ".config" / "VideoMind" / "config.yaml"


def _load(home: Path) -> ConfigManager:
    with patch("pathlib.Path.home", return_value=home):
        return ConfigManager()


def test_legacy_file_is_migrated_with_backup(home):
    cfg_file = _config_file(home)
    cfg_file.write_text(LEGACY_YAML, encoding="utf-8")

    cm = _load(home)

    # 值没丢：归档目录从旧 download.output_dir 继承
    assert cm.config.archive.output_dir == "/legacy/out"
    assert cm.config.export.obsidian.vault_path == "/legacy/vault"

    data = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    assert data["version"] == "2"
    assert data["archive"]["output_dir"] == "/legacy/out"
    for gone in ("ai", "download", "transcribe", "ui", "performance"):
        assert gone not in data, f"{gone} 已无执行者，不该再写回"
    assert "local" not in data["export"]

    backups = list(cfg_file.parent.glob("config.yaml.bak-*"))
    assert len(backups) == 1
    assert "ai:" in backups[0].read_text(encoding="utf-8"), "备份必须是迁移前的原文"


def test_migration_is_idempotent(home):
    cfg_file = _config_file(home)
    cfg_file.write_text(LEGACY_YAML, encoding="utf-8")

    _load(home)
    ConfigManager._instance = None
    ConfigManager._initialized = False
    cm2 = _load(home)

    assert cm2.config.archive.output_dir == "/legacy/out"
    assert len(list(cfg_file.parent.glob("config.yaml.bak-*"))) == 1


def test_no_migrate_env_keeps_file_untouched(home, monkeypatch):
    cfg_file = _config_file(home)
    cfg_file.write_text(LEGACY_YAML, encoding="utf-8")
    monkeypatch.setenv("VMB_CONFIG_NO_MIGRATE", "1")

    cm = _load(home)

    assert cm.config.archive.output_dir == "/legacy/out", "仍应能读出值"
    assert cfg_file.read_text(encoding="utf-8") == LEGACY_YAML, "文件不该被改"
    assert not list(cfg_file.parent.glob("config.yaml.bak-*"))


def test_archive_section_wins_over_legacy_download(home):
    cfg_file = _config_file(home)
    cfg_file.write_text(
        "version: \"1\"\n"
        "archive:\n  output_dir: /new/out\n"
        "download:\n  output_dir: /old/out\n",
        encoding="utf-8",
    )

    cm = _load(home)

    assert cm.config.archive.output_dir == "/new/out"
    data = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    assert data["archive"]["output_dir"] == "/new/out"


def test_corrupt_yaml_falls_back_to_defaults(home):
    cfg_file = _config_file(home)
    cfg_file.write_text("::: not: [valid yaml", encoding="utf-8")

    cm = _load(home)

    assert cm.config.archive.output_dir == str(Path.home() / "Downloads" / "VideoMind")
    assert not list(cfg_file.parent.glob("config.yaml.bak-*"))


def test_save_writes_only_live_sections(home):
    cm = _load(home)
    cm.update_archive(output_dir="/tmp/x")

    data = yaml.safe_load(_config_file(home).read_text(encoding="utf-8"))
    assert set(data) == {"version", "archive", "asr", "export"}
    assert set(data["export"]) == {"obsidian"}
