"""ASR 配置测试（阶段 2）：模型序列化、环境变量覆盖与链默认值。"""

from __future__ import annotations

import pytest

from src.core.asr import resolve_chain, resolve_language, resolve_max_cost
from src.core.models import CostTier
from src.models.config import AppConfig, AsrBackendConfig, AsrConfig


@pytest.fixture
def manager(monkeypatch):
    """隔离 ConfigManager 单例，并清空 ASR 相关环境变量。"""
    for name in (
        "VMB_ASR_CHAIN", "VMB_ASR_LANGUAGE", "VMB_ASR_MAX_COST",
        "VMB_ASR_MODEL", "VMB_WHISPER_MODEL",
        "VMB_SENSEVOICE_PYTHON", "VMB_SENSEVOICE_MODEL_DIR",
        "VMB_SENSEVOICE_SCRIPT", "VMB_SENSEVOICE_TIMEOUT",
    ):
        monkeypatch.delenv(name, raising=False)

    from src.services.config_manager import ConfigManager

    ConfigManager._instance = None
    ConfigManager._initialized = False
    cm = ConfigManager()
    cm._config = AppConfig.get_default_config()
    yield cm
    ConfigManager._instance = None
    ConfigManager._initialized = False


def test_app_config_roundtrip_includes_asr():
    config = AppConfig.get_default_config()
    assert config.asr.chain == ["faster_whisper", "dashscope"]
    assert config.asr.max_cost == "premium"

    restored = AppConfig.from_dict(config.to_dict())
    assert restored.asr.chain == config.asr.chain
    assert restored.asr.language == config.asr.language


def test_asr_config_backend_configs_flattens_model_and_skips_disabled():
    cfg = AsrConfig(
        backends={
            "faster_whisper": AsrBackendConfig(model="small", options={"device": "cpu"}),
            "dashscope": AsrBackendConfig(enabled=False),
        }
    )
    assert cfg.backend_configs() == {"faster_whisper": {"device": "cpu", "model": "small"}}


def test_get_asr_config_env_overrides(manager, monkeypatch):
    monkeypatch.setenv("VMB_ASR_CHAIN", "sensevoice, faster_whisper")
    monkeypatch.setenv("VMB_ASR_LANGUAGE", "en")
    monkeypatch.setenv("VMB_ASR_MAX_COST", "paid")
    monkeypatch.setenv("VMB_ASR_MODEL", "small")

    cfg = manager.get_asr_config()

    assert cfg.chain == ["sensevoice", "faster_whisper"]
    assert cfg.language == "en"
    assert cfg.max_cost == "paid"
    assert cfg.backends["faster_whisper"].model == "small"


def test_get_asr_config_empty_language_means_auto(manager, monkeypatch):
    monkeypatch.setenv("VMB_ASR_LANGUAGE", "")
    assert manager.get_asr_config().language is None


def test_get_asr_config_new_model_env_wins_over_legacy(manager, monkeypatch):
    monkeypatch.setenv("VMB_WHISPER_MODEL", "tiny")
    monkeypatch.setenv("VMB_ASR_MODEL", "medium")
    assert manager.get_asr_config().backends["faster_whisper"].model == "medium"


def test_get_asr_config_sensevoice_env_options(manager, monkeypatch):
    monkeypatch.setenv("VMB_SENSEVOICE_PYTHON", "/venv/python")
    monkeypatch.setenv("VMB_SENSEVOICE_MODEL_DIR", "/models/sensevoice")
    monkeypatch.setenv("VMB_SENSEVOICE_TIMEOUT", "120")

    sv = manager.get_asr_config().backends["sensevoice"]
    assert sv.options["python"] == "/venv/python"
    assert sv.options["model_dir"] == "/models/sensevoice"
    assert sv.options["timeout"] == "120"


def test_get_asr_config_returns_copy(manager):
    cfg = manager.get_asr_config()
    cfg.chain.append("aliyun")
    assert manager.get_asr_config().chain == ["faster_whisper", "dashscope"]


def test_resolve_chain_prefers_request_then_env_then_config(monkeypatch):
    cfg = AsrConfig(chain=["aliyun"])
    monkeypatch.delenv("VMB_ASR_CHAIN", raising=False)
    assert resolve_chain(cfg=cfg) == ["aliyun"]
    assert resolve_chain(["sensevoice"], cfg=cfg) == ["sensevoice"]

    monkeypatch.setenv("VMB_ASR_CHAIN", "dashscope")
    assert resolve_chain(cfg=cfg) == ["dashscope"]


def test_resolve_language_and_max_cost_precedence(monkeypatch):
    cfg = AsrConfig(language="zh", max_cost="paid")
    monkeypatch.delenv("VMB_ASR_LANGUAGE", raising=False)
    monkeypatch.delenv("VMB_ASR_MAX_COST", raising=False)
    assert resolve_language(cfg=cfg) == "zh"
    assert resolve_language("en", cfg=cfg) == "en"
    assert resolve_max_cost(cfg=cfg) == CostTier.PAID
    assert resolve_max_cost(CostTier.FREE, cfg=cfg) == CostTier.FREE

    monkeypatch.setenv("VMB_ASR_LANGUAGE", "ja")
    monkeypatch.setenv("VMB_ASR_MAX_COST", "cheap")
    assert resolve_language(cfg=cfg) == "ja"
    assert resolve_max_cost(cfg=cfg) == CostTier.CHEAP
