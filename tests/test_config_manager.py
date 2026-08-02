"""ConfigManager 全面测试套件

覆盖范围:
  - 单例模式 (get_config_manager vs ConfigManager())
  - 默认配置生成
  - Config 文件读写 + tmp_path + 环境变量覆盖
  - get_extractor_key / set_extractor_key / list_extractor_key_status
  - EXTRACTOR_PROVIDERS 和 EXTRACTOR_GROUPS 结构
  - Obsidian 配置 (vault_path / subfolder)
  - update_ai / config.ai 属性
  - 错误处理: 损坏 YAML、缺失键、无效值
  - 边界情况: 空配置、特殊字符
  - 持久化: 设置值 → 重建 ConfigManager → 验证
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def reset_singleton():
    """每个测试前后重置 ConfigManager 单例"""
    from src.services.config_manager import ConfigManager

    ConfigManager._instance = None
    ConfigManager._initialized = False
    yield
    ConfigManager._instance = None
    ConfigManager._initialized = False


@pytest.fixture(autouse=True)
def clear_extractor_env_vars():
    """清除提取器环境变量，确保 keyring mock 不被外部环境变量绕过"""
    extractor_vars = [
        "COZE_API_KEY", "COZE_API_TOKEN", "TIKHUB_API_KEY",
        "APIFY_API_KEY", "ALIYUN_ACCESS_KEY_ID", "ALIYUN_ACCESS_KEY_SECRET",
        "ALIYUN_APPKEY", "AL_API_KEY",
    ]
    with patch.dict(os.environ, dict.fromkeys(extractor_vars, "")):
        yield


@pytest.fixture(autouse=True)
def mock_credential_manager():
    """Mock CredentialManager → 内存存储，避免操作真实系统密钥环"""
    store: dict[str, str] = {}

    with patch("src.services.config_manager.CredentialManager") as mock:
        mock.get_api_key.side_effect = lambda p: store.get(p)
        mock.save_api_key.side_effect = lambda p, k: store.update({p: k}) or True
        mock.delete_api_key.side_effect = (
            lambda p: store.pop(p, None) is not None or True
        )
        mock.migrate_from_config.side_effect = lambda p, k: True
        yield store


@pytest.fixture
def tmp_config_dir(tmp_path):
    """在 tmp_path 下创建 ~/.config/VideoMind/"""
    d = tmp_path / ".config" / "VideoMind"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def cm(tmp_config_dir, mock_credential_manager):
    """创建指向 tmp_path 的 ConfigManager"""
    with patch("pathlib.Path.home", return_value=tmp_config_dir.parent.parent):
        from src.services.config_manager import ConfigManager

        ConfigManager._instance = None
        ConfigManager._initialized = False
        cm = ConfigManager()
        yield cm
        ConfigManager._instance = None
        ConfigManager._initialized = False


@pytest.fixture
def cm_with_config(tmp_config_dir, mock_credential_manager, request):
    """创建 ConfigManager，预先写入指定 YAML 内容"""
    config_file = tmp_config_dir / "config.yaml"
    config_file.write_text(request.param, encoding="utf-8")

    with patch("pathlib.Path.home", return_value=tmp_config_dir.parent.parent):
        from src.services.config_manager import ConfigManager

        ConfigManager._instance = None
        ConfigManager._initialized = False
        cm = ConfigManager()
        yield cm
        ConfigManager._instance = None
        ConfigManager._initialized = False


# ═══════════════════════════════════════════════════════════════
# 1. 单例模式
# ═══════════════════════════════════════════════════════════════

class TestSingleton:
    """ConfigManager 单例模式测试"""

    def test_get_config_manager_returns_same_instance(self, cm):
        """get_config_manager() 返回同一实例"""
        from src.services.config_manager import get_config_manager

        mgr1 = get_config_manager()
        mgr2 = get_config_manager()
        assert mgr1 is mgr2

    def test_ConfigManager_constructor_returns_same_instance(self, cm):
        """ConfigManager() 直接调用也返回同一实例"""
        from src.services.config_manager import ConfigManager

        m1 = ConfigManager()
        m2 = ConfigManager()
        assert m1 is m2

    def test_get_config_manager_and_constructor_same(self, cm):
        """两种获取方式指向同一实例"""
        from src.services.config_manager import ConfigManager, get_config_manager

        assert get_config_manager() is ConfigManager()

    def test_singleton_across_reset_and_reinit(self, mock_credential_manager):
        """重置后重新初始化，单例仍保持"""
        from src.services.config_manager import ConfigManager

        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path("/tmp/fake_home")
            ConfigManager._instance = None
            ConfigManager._initialized = False
            m1 = ConfigManager()

            # 再次获取
            m2 = ConfigManager()
            assert m1 is m2


# ═══════════════════════════════════════════════════════════════
# 2. 默认配置
# ═══════════════════════════════════════════════════════════════

class TestDefaultConfig:
    """无配置文件时应使用默认配置"""

    def test_default_config_not_none(self, cm):
        """config 不为 None"""
        assert cm.config is not None

    def test_default_ai_engine(self, cm):
        """默认 AI 引擎为 DeepSeek-V3"""
        assert cm.config.ai.engine.value == "DeepSeek-V3"

    def test_default_ai_model(self, cm):
        """默认 AI 模型为 deepseek-chat"""
        assert cm.config.ai.model == "deepseek-chat"

    def test_default_download_quality(self, cm):
        """默认下载画质为 1080p"""
        assert cm.config.download.video_quality == "1080p"

    def test_default_export_targets(self, cm):
        """默认导出目标为 local"""
        assert cm.config.export.default_targets == ["local"]

    def test_default_obsidian_disabled(self, cm):
        """Obsidian 默认不启用"""
        assert cm.config.export.obsidian.enabled is False

    def test_default_obsidian_subfolder(self, cm):
        """Obsidian 默认 subfolder"""
        assert cm.config.export.obsidian.subfolder == "Inbox/Videos"

    def test_default_ui(self, cm):
        """UI 默认配置"""
        assert cm.config.ui.theme == "system"
        assert cm.config.ui.language == "zh_CN"
        assert cm.config.ui.minimize_to_tray is True

    def test_default_performance(self, cm):
        """性能默认配置"""
        assert cm.config.performance.max_concurrent_tasks == 2

    def test_default_config_from_function(self, cm):
        """get_default_config() 应返回有效默认值"""
        from src.models.config import AppConfig

        default = AppConfig.get_default_config()
        assert default.ai.engine.value == "DeepSeek-V3"

    def test_config_property_shortcuts(self, cm):
        """快捷属性应指向同一子对象"""
        assert cm.ai is cm.config.ai
        assert cm.download is cm.config.download
        assert cm.export is cm.config.export
        assert cm.ui is cm.config.ui


# ═══════════════════════════════════════════════════════════════
# 3. Config 文件读写
# ═══════════════════════════════════════════════════════════════

class TestConfigFile:
    """配置文件读写与持久化"""

    def test_no_config_file_uses_defaults(self, cm):
        """无配置文件时使用默认值"""
        assert cm.config.ai.engine.value == "DeepSeek-V3"

    def test_read_valid_config(self, tmp_config_dir, mock_credential_manager):
        """读取有效 YAML 配置文件"""
        yaml_content = """
ai:
  engine: Ollama
  model: llama3
  base_url: http://localhost:11434
"""
        config_file = tmp_config_dir / "config.yaml"
        config_file.write_text(yaml_content, encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_config_dir.parent.parent):
            from src.services.config_manager import ConfigManager

            ConfigManager._instance = None
            ConfigManager._initialized = False
            cm = ConfigManager()
            assert cm.config.ai.engine.value == "Ollama"
            assert cm.config.ai.model == "llama3"
            assert cm.config.ai.base_url == "http://localhost:11434"

    def test_partial_config_fills_defaults(self, tmp_config_dir, mock_credential_manager):
        """部分配置文件 -> 缺失字段使用默认值"""
        yaml_content = """
download:
  video_quality: "4k"
"""
        config_file = tmp_config_dir / "config.yaml"
        config_file.write_text(yaml_content, encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_config_dir.parent.parent):
            from src.services.config_manager import ConfigManager

            ConfigManager._instance = None
            ConfigManager._initialized = False
            cm = ConfigManager()
            # 用户指定的字段
            assert cm.config.download.video_quality == "4k"
            # 默认字段
            assert cm.config.ai.engine.value == "DeepSeek-V3"
            assert cm.config.download.organize_by == "date"

    def test_save_creates_file(self, cm, tmp_config_dir):
        """save() 应创建 YAML 文件"""
        assert cm.save() is True
        config_file = tmp_config_dir / "config.yaml"
        assert config_file.exists()
        content = config_file.read_text(encoding="utf-8")
        assert "ai:" in content

    def test_save_content_correct(self, cm, tmp_config_dir):
        """保存的内容应为有效 YAML"""
        cm.config.ai.model = "gpt-4"
        cm.config.download.video_quality = "4k"
        cm.save()

        config_file = tmp_config_dir / "config.yaml"
        data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert data["ai"]["model"] == "gpt-4"
        assert data["download"]["video_quality"] == "4k"

    def test_persistence_across_reinit(self, tmp_config_dir, mock_credential_manager):
        """设置值 → 重建 ConfigManager → 值持久化"""
        # 第一次: 设置并保存
        with patch("pathlib.Path.home", return_value=tmp_config_dir.parent.parent):
            from src.services.config_manager import ConfigManager

            ConfigManager._instance = None
            ConfigManager._initialized = False
            cm1 = ConfigManager()
            cm1.config.ai.model = "gpt-4o"
            cm1.config.download.organize_by = "title"
            cm1.save()

        # 第二次: 重建后检查
        with patch("pathlib.Path.home", return_value=tmp_config_dir.parent.parent):
            ConfigManager._instance = None
            ConfigManager._initialized = False
            cm2 = ConfigManager()
            assert cm2.config.ai.model == "gpt-4o"
            assert cm2.config.download.organize_by == "title"

    def test_save_unicode_content(self, cm, tmp_config_dir):
        """保存含中文/特殊字符的配置"""
        cm.config.export.obsidian.subfolder = "视频/笔记"
        cm.save()
        config_file = tmp_config_dir / "config.yaml"
        content = config_file.read_text(encoding="utf-8")
        assert "视频/笔记" in content

    def test_save_then_reload(self, cm, tmp_config_dir):
        """save() 后 reload() 应读到最新内容"""
        cm.config.ai.temperature = 0.5
        cm.save()

        # 手动修改文件
        config_file = tmp_config_dir / "config.yaml"
        data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        data["ai"]["temperature"] = 0.9
        config_file.write_text(yaml.dump(data), encoding="utf-8")

        cm.reload()
        assert cm.config.ai.temperature == 0.9

    def test_get_config_file_path(self, cm, tmp_config_dir):
        """get_config_file_path() 返回正确路径"""
        expected = tmp_config_dir / "config.yaml"
        assert cm.get_config_file_path() == expected

    def test_get_config_file_path_without_dir(self, mock_credential_manager):
        """未创建目录时 get_config_file_path 仍返回有效路径"""
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path("/tmp/nonexistent_videomind_test")
            from src.services.config_manager import ConfigManager

            ConfigManager._instance = None
            ConfigManager._initialized = False
            cm = ConfigManager()
            path = cm.get_config_file_path()
            assert str(path).endswith(".config/VideoMind/config.yaml")


# ═══════════════════════════════════════════════════════════════
# 4. 提取器 Key 管理
# ═══════════════════════════════════════════════════════════════

class TestExtractorKeys:
    """get_extractor_key / set_extractor_key / list_extractor_key_status"""

    def test_set_and_get_extractor_key(self, cm, mock_credential_manager):
        """设置后再获取应返回相同值"""
        assert cm.set_extractor_key("tikhub", "tikhub-token-123")
        mock_credential_manager["extractor_tikhub"] = "tikhub-token-123"
        assert cm.get_extractor_key("tikhub") == "tikhub-token-123"

    def test_get_nonexistent_key_returns_none(self, cm):
        """不存在的 key 返回 None"""
        assert cm.get_extractor_key("nonexistent_provider") is None

    def test_set_empty_key_returns_false(self, cm):
        """空值/空白值设置返回 False"""
        assert cm.set_extractor_key("dashscope_key", "") is False
        assert cm.set_extractor_key("dashscope_key", "   ") is False

    def test_env_var_fallback(self, cm):
        """未在密钥环中找到时，应回退到环境变量"""
        with patch.dict(os.environ, {"TIKHUB_API_KEY": "env-tikhub-key"}):
            assert cm.get_extractor_key("tikhub") == "env-tikhub-key"

    def test_env_var_trumps_none_keyring(self, cm, mock_credential_manager):
        """密钥环返回 None 时使用环境变量"""
        mock_credential_manager.pop("extractor_tikhub", None)  # ensure gone
        with patch.dict(os.environ, {"TIKHUB_API_KEY": "from-env"}):
            assert cm.get_extractor_key("tikhub") == "from-env"

    def test_extractor_key_env_var_whitespace_returns_none(self, cm):
        """环境变量值为空白时返回 None"""
        with patch.dict(os.environ, {"APIFY_API_KEY": "   "}):
            assert cm.get_extractor_key("apify") is None

    def test_delete_extractor_key(self, cm, mock_credential_manager):
        """删除提取器 Key"""
        mock_credential_manager["extractor_tikhub"] = "tikhub-token"
        assert cm.delete_extractor_key("tikhub") is True
        assert cm.get_extractor_key("tikhub") is None

    def test_delete_nonexistent_key(self, cm):
        """删除不存在的 key 应返回 True（幂等）"""
        assert cm.delete_extractor_key("nonexistent") is True

    def test_list_extractor_key_status_structure(self, cm):
        """list_extractor_key_status() 返回结构正确"""
        status = cm.list_extractor_key_status()
        # 检查所有分组
        assert "dashscope_asr" in status
        assert "tikhub" in status
        assert "apify" in status
        assert "aliyun_asr" in status

        # 分组字段
        ds_group = status["dashscope_asr"]
        assert "label" in ds_group
        assert "all_configured" in ds_group
        assert "keys" in ds_group

        # key 详情
        first_key = ds_group["keys"][0]
        assert "name" in first_key
        assert "label" in first_key
        assert "env" in first_key
        assert "configured" in first_key

    def test_list_extractor_key_status_none_configured(self, cm):
        """未配置任何 key 时, all_configured 应为 False"""
        with patch.dict(os.environ, {
            "ALI_API_KEY": "", "TIKHUB_API_KEY": "", "APIFY_API_KEY": "",
            "ALIYUN_ACCESS_KEY_ID": "", "ALIYUN_ACCESS_KEY_SECRET": "", "ALIYUN_APPKEY": "",
        }):
            status = cm.list_extractor_key_status()
            assert all(g["all_configured"] is False for g in status.values())

    def test_list_extractor_key_status_partial_configured(self, cm, mock_credential_manager):
        """部分配置时 all_configured 应为 False"""
        mock_credential_manager["extractor_dashscope_key"] = "key"
        mock_credential_manager["extractor_tikhub"] = "token"
        status = cm.list_extractor_key_status()
        assert status["dashscope_asr"]["all_configured"] is True
        assert status["tikhub"]["all_configured"] is True
        # apify 未配置
        assert status["apify"]["all_configured"] is False

    def test_list_extractor_key_aliyun_group(self, cm, mock_credential_manager):
        """aliyun_asr 需要 3 个 key 全部配置才为 True"""
        name = "aliyun_asr"
        status = cm.list_extractor_key_status()
        assert status[name]["all_configured"] is False

        # 只配一个 key
        mock_credential_manager["extractor_aliyun_access_key_id"] = "id"
        status = cm.list_extractor_key_status()
        assert status[name]["all_configured"] is False

        # 配齐三个
        mock_credential_manager["extractor_aliyun_access_key_secret"] = "secret"
        mock_credential_manager["extractor_aliyun_appkey"] = "appkey"
        status = cm.list_extractor_key_status()
        assert status[name]["all_configured"] is True


# ═══════════════════════════════════════════════════════════════
# 5. EXTRACTOR_PROVIDERS / EXTRACTOR_GROUPS 结构
# ═══════════════════════════════════════════════════════════════

class TestExtractorStructure:
    """EXTRACTOR_PROVIDERS 和 EXTRACTOR_GROUPS 结构验证"""

    def test_providers_have_required_fields(self, cm):
        """每个 provider 必须有 env 和 label"""
        for name, info in cm.EXTRACTOR_PROVIDERS.items():
            assert "env" in info, f"{name} missing env"
            assert "label" in info, f"{name} missing label"
            assert isinstance(info["env"], str)
            assert isinstance(info["label"], str)

    def test_groups_have_required_fields(self, cm):
        """每个 group 必须有 label 和 keys"""
        for name, group in cm.EXTRACTOR_GROUPS.items():
            assert "label" in group, f"{name} missing label"
            assert "keys" in group, f"{name} missing keys"
            assert isinstance(group["keys"], list)

    def test_group_keys_reference_valid_providers(self, cm):
        """groups 中的 keys 必须在 providers 中存在"""
        for group_name, group in cm.EXTRACTOR_GROUPS.items():
            for key_name in group["keys"]:
                assert key_name in cm.EXTRACTOR_PROVIDERS, (
                    f"Group '{group_name}' references unknown provider '{key_name}'"
                )

    def test_all_providers_referenced_by_groups(self, cm):
        """所有 provider 应至少被一个 group 引用"""
        referenced = set()
        for group in cm.EXTRACTOR_GROUPS.values():
            referenced.update(group["keys"])
        for provider_name in cm.EXTRACTOR_PROVIDERS:
            assert provider_name in referenced, (
                f"Provider '{provider_name}' not referenced in any group"
            )

    def test_providers_count(self, cm):
        """验证 provider 数量"""
        assert len(cm.EXTRACTOR_PROVIDERS) == 6

    def test_groups_count(self, cm):
        """验证 group 数量"""
        assert len(cm.EXTRACTOR_GROUPS) == 4

    def test_aliyun_group_has_three_keys(self, cm):
        """aliyun_asr 组应有 3 个 key"""
        assert len(cm.EXTRACTOR_GROUPS["aliyun_asr"]["keys"]) == 3


# ═══════════════════════════════════════════════════════════════
# 6. Obsidian 配置
# ═══════════════════════════════════════════════════════════════

class TestObsidianConfig:
    """Obsidian 配置访问与修改"""

    def test_obsidian_default_vault_path(self, cm):
        """默认 vault_path 为空字符串"""
        assert cm.config.export.obsidian.vault_path == ""

    def test_obsidian_default_subfolder(self, cm):
        """默认 subfolder"""
        assert cm.config.export.obsidian.subfolder == "Inbox/Videos"

    def test_update_obsidian_via_update_export(self, cm, tmp_config_dir):
        """通过 update_export() 修改 Obsidian 配置"""
        cm.update_export(
            obsidian={
                "vault_path": "/Users/test/obsidian",
                "subfolder": "Daily Notes/Video",
            }
        )
        assert cm.config.export.obsidian.vault_path == "/Users/test/obsidian"
        assert cm.config.export.obsidian.subfolder == "Daily Notes/Video"

        # 验证持久化
        config_file = tmp_config_dir / "config.yaml"
        data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert data["export"]["obsidian"]["vault_path"] == "/Users/test/obsidian"

    def test_obsidian_persistence(self, tmp_config_dir, mock_credential_manager):
        """Obsidian 配置在重建后仍保留"""
        # 第一次设置
        with patch("pathlib.Path.home", return_value=tmp_config_dir.parent.parent):
            from src.services.config_manager import ConfigManager

            ConfigManager._instance = None
            ConfigManager._initialized = False
            cm1 = ConfigManager()
            cm1.update_export(obsidian={"vault_path": "/vault", "subfolder": "Videos"})

        # 重建后检查
        with patch("pathlib.Path.home", return_value=tmp_config_dir.parent.parent):
            ConfigManager._instance = None
            ConfigManager._initialized = False
            cm2 = ConfigManager()
            assert cm2.config.export.obsidian.vault_path == "/vault"
            assert cm2.config.export.obsidian.subfolder == "Videos"

    def test_update_obsidian_partial(self, cm):
        """仅更新 subfolder 不影响 vault_path"""
        original_vault = cm.config.export.obsidian.vault_path
        cm.update_export(obsidian={"subfolder": "NewFolder"})
        assert cm.config.export.obsidian.subfolder == "NewFolder"
        assert cm.config.export.obsidian.vault_path == original_vault

    def test_obsidian_special_characters(self, cm):
        """路径含特殊字符"""
        cm.update_export(obsidian={"vault_path": "/路径/包含/中文/and spaces"})
        assert cm.config.export.obsidian.vault_path == "/路径/包含/中文/and spaces"


# ═══════════════════════════════════════════════════════════════
# 7. AI 配置
# ═══════════════════════════════════════════════════════════════

class TestAIConfig:
    """AI 配置读取与更新"""

    def test_ai_config_defaults(self, cm):
        """默认 AI 配置值"""
        assert cm.config.ai.temperature == 0.7
        assert cm.config.ai.max_tokens == 4096
        assert cm.config.ai.timeout == 120

    def test_update_ai_single_field(self, cm, tmp_config_dir):
        """update_ai() 更新单个字段"""
        cm.update_ai(temperature=0.3)
        assert cm.config.ai.temperature == 0.3

    def test_update_ai_multiple_fields(self, cm):
        """update_ai() 同时更新多个字段"""
        cm.update_ai(model="gpt-4o", temperature=0.1, max_tokens=8192)
        assert cm.config.ai.model == "gpt-4o"
        assert cm.config.ai.temperature == 0.1
        assert cm.config.ai.max_tokens == 8192

    def test_update_ai_unknown_field_ignored(self, cm):
        """update_ai() 传入不存在的字段应被忽略"""
        original = cm.config.ai.temperature
        cm.update_ai(nonexistent_field="value")
        assert cm.config.ai.temperature == original

    def test_ai_persistence(self, tmp_config_dir, mock_credential_manager):
        """AI 配置在重建后仍保留"""
        with patch("pathlib.Path.home", return_value=tmp_config_dir.parent.parent):
            from src.services.config_manager import ConfigManager

            ConfigManager._instance = None
            ConfigManager._initialized = False
            cm1 = ConfigManager()
            cm1.update_ai(model="claude-3-opus", temperature=0.2)

        with patch("pathlib.Path.home", return_value=tmp_config_dir.parent.parent):
            ConfigManager._instance = None
            ConfigManager._initialized = False
            cm2 = ConfigManager()
            assert cm2.config.ai.model == "claude-3-opus"
            assert cm2.config.ai.temperature == 0.2

    def test_ai_base_url_persistence(self, cm, tmp_config_dir):
        """AI base_url 更改应持久化"""
        cm.update_ai(base_url="https://custom.api.com/v1")
        cm.save()

        config_file = tmp_config_dir / "config.yaml"
        data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert data["ai"]["base_url"] == "https://custom.api.com/v1"


# ═══════════════════════════════════════════════════════════════
# 8. save / reload / reset_to_defaults
# ═══════════════════════════════════════════════════════════════

class TestSaveReloadReset:
    """save / reload / reset_to_defaults 方法"""

    def test_save_returns_true(self, cm):
        """正常 save 返回 True"""
        assert cm.save() is True

    def test_reset_to_defaults(self, cm, tmp_config_dir):
        """reset_to_defaults 恢复默认值并保存到文件"""
        cm.update_ai(model="custom-model")
        cm.reset_to_defaults()
        assert cm.config.ai.model == "deepseek-chat"
        # 文件也更新
        config_file = tmp_config_dir / "config.yaml"
        assert config_file.exists()
        data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert data["ai"]["model"] == "deepseek-chat"

    def test_reset_to_defaults_clears_obsidian(self, cm):
        """reset_to_defaults 应重置 Obsidian 配置"""
        cm.update_export(obsidian={"vault_path": "/custom/vault"})
        cm.reset_to_defaults()
        assert cm.config.export.obsidian.vault_path == ""

    def test_reload_without_file_keeps_defaults(self, cm):
        """无文件时 reload 应保留默认配置"""
        cm.reload()
        assert cm.config.ai.engine.value == "DeepSeek-V3"

    def test_reload_updates_from_disk(self, cm, tmp_config_dir):
        """reload 应从磁盘重新加载"""
        cm.save()
        # 直接改文件
        config_file = tmp_config_dir / "config.yaml"
        data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        data["ui"]["theme"] = "dark"
        config_file.write_text(yaml.dump(data), encoding="utf-8")

        cm.reload()
        assert cm.config.ui.theme == "dark"

    def test_convenience_save_config(self, cm, tmp_config_dir):
        """save_config() 便捷函数工作正常"""
        from src.services.config_manager import save_config

        cm.config.ai.model = "test-model"
        assert save_config() is True
        config_file = tmp_config_dir / "config.yaml"
        data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert data["ai"]["model"] == "test-model"

    def test_convenience_get_config(self, cm):
        """get_config() 便捷函数返回 config"""
        from src.services.config_manager import get_config

        cfg = get_config()
        assert cfg is cm.config


# ═══════════════════════════════════════════════════════════════
# 9. 错误处理
# ═══════════════════════════════════════════════════════════════

class TestErrorHandling:
    """错误处理: 损坏 YAML / 缺失键 / 无效值 / 权限错误"""

    def test_corrupt_yaml_falls_back_to_defaults(
        self, tmp_config_dir, mock_credential_manager
    ):
        """损坏的 YAML 应回退到默认配置并记录错误"""
        config_file = tmp_config_dir / "config.yaml"
        config_file.write_text("{invalid: yaml: broken: [", encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_config_dir.parent.parent):
            from src.services.config_manager import ConfigManager

            ConfigManager._instance = None
            ConfigManager._initialized = False
            cm = ConfigManager()
            # 应回退到默认值
            assert cm.config.ai.engine.value == "DeepSeek-V3"

    def test_empty_yaml_file_falls_back_to_defaults(
        self, tmp_config_dir, mock_credential_manager
    ):
        """空 YAML 文件应回退到默认配置"""
        config_file = tmp_config_dir / "config.yaml"
        config_file.write_text("", encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_config_dir.parent.parent):
            from src.services.config_manager import ConfigManager

            ConfigManager._instance = None
            ConfigManager._initialized = False
            cm = ConfigManager()
            assert cm.config.ai.engine.value == "DeepSeek-V3"

    def test_null_yaml_content_falls_back_to_defaults(
        self, tmp_config_dir, mock_credential_manager
    ):
        """YAML 内容为 null (None) 应回退到默认配置"""
        config_file = tmp_config_dir / "config.yaml"
        config_file.write_text("null", encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_config_dir.parent.parent):
            from src.services.config_manager import ConfigManager

            ConfigManager._instance = None
            ConfigManager._initialized = False
            cm = ConfigManager()
            assert cm.config.ai.engine.value == "DeepSeek-V3"

    def test_save_permission_error(self, cm):
        """保存时权限错误应返回 False"""
        with patch.object(Path, "mkdir", side_effect=PermissionError("denied")):
            result = cm.save()
            assert result is False

    def test_save_os_error(self, cm):
        """保存时 OSError 应返回 False"""
        with patch("src.services.config_manager.Path.mkdir", side_effect=OSError("IO error")):
            result = cm.save()
            assert result is False

    def test_save_yaml_error(self, cm):
        """保存时 YAML 序列化错误应返回 False"""
        with patch(
            "src.services.config_manager.yaml.dump", side_effect=yaml.YAMLError("err")
        ):
            result = cm.save()
            assert result is False

    def test_import_config_file_not_found(self, cm):
        """导入不存在的文件应返回 False"""
        result = cm.import_config(Path("/nonexistent/file.yaml"))
        assert result is False

    def test_import_config_corrupt(self, cm, tmp_config_dir):
        """导入损坏文件应返回 False"""
        bad_file = tmp_config_dir / "import.yaml"
        bad_file.write_text("{invalid", encoding="utf-8")
        result = cm.import_config(bad_file)
        assert result is False

    def test_export_config_permission_error(self, cm, tmp_config_dir):
        """导出到无法写入的路径应返回 False"""
        result = cm.export_config(Path("/nonexistent_dir/output.yaml"))
        assert result is False

    def test_missing_config_dir_still_works(self, mock_credential_manager):
        """配置目录不存在时仍可正常初始化"""
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = Path("/tmp/__videomind_test_nonexistent_dir__")
            from src.services.config_manager import ConfigManager

            ConfigManager._instance = None
            ConfigManager._initialized = False
            cm = ConfigManager()
            assert cm.config.ai.engine.value == "DeepSeek-V3"


# ═══════════════════════════════════════════════════════════════
# 10. 边界情况
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases:
    """边界情况: 空配置 / 特殊字符 / 不完整数据"""

    def test_special_chars_in_ai_config(self, cm, tmp_config_dir):
        """AI 配置含特殊字符"""
        cm.update_ai(base_url="https://api.example.com/v1?key=abc&test=true")
        cm.save()
        config_file = tmp_config_dir / "config.yaml"
        content = config_file.read_text(encoding="utf-8")
        assert "https://api.example.com/v1?key=abc&test=true" in content

    def test_special_chars_in_subfolder(self, cm):
        """subfolder 含中文/符号/空格"""
        cm.update_export(
            obsidian={"subfolder": "我的笔记/Video-2024/测试 (v2)"}
        )
        assert cm.config.export.obsidian.subfolder == "我的笔记/Video-2024/测试 (v2)"
        cm.save()

    def test_update_download(self, cm, tmp_config_dir):
        """update_download 方法"""
        cm.update_download(video_quality="720p", organize_by="title")
        assert cm.config.download.video_quality == "720p"
        assert cm.config.download.organize_by == "title"

        # 持久化验证
        config_file = tmp_config_dir / "config.yaml"
        data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
        assert data["download"]["video_quality"] == "720p"

    def test_update_ui(self, cm):
        """update_ui 方法"""
        cm.update_ui(theme="dark", show_notifications=False)
        assert cm.config.ui.theme == "dark"
        assert cm.config.ui.show_notifications is False

    def test_update_export_local(self, cm):
        """update_export 更新 local 配置"""
        cm.update_export(local={"output_path": "/custom/output", "save_srt": False})
        assert cm.config.export.local.output_path == "/custom/output"
        assert cm.config.export.local.save_srt is False

    def test_update_export_unknown_field_ignored(self, cm):
        """update_export 不存在的字段应被忽略"""
        original = cm.config.export.default_targets
        cm.update_export(nonexistent="value")
        assert cm.config.export.default_targets == original

    def test_api_key_methods_no_provider(self, cm, mock_credential_manager):
        """get_api_key / set_api_key 使用默认 provider"""
        assert cm.set_api_key("test-key-123")
        assert cm.get_api_key() == "test-key-123"

    def test_api_key_with_provider(self, cm, mock_credential_manager):
        """get_api_key / set_api_key 指定 provider"""
        cm.set_api_key("openai-key", provider="openai")
        assert cm.get_api_key(provider="openai") == "openai-key"

    def test_export_and_import_config(self, cm, tmp_config_dir):
        """export_config → import_config 往返"""
        cm.update_ai(model="exported-model")
        cm.update_export(obsidian={"vault_path": "/export/vault"})

        export_file = tmp_config_dir / "exported.yaml"
        assert cm.export_config(export_file) is True

        # 导入到新配置
        cm.update_ai(model="temporary")
        cm.update_export(obsidian={"vault_path": "/temp"})
        assert cm.import_config(export_file) is True
        assert cm.config.ai.model == "exported-model"
        assert cm.config.export.obsidian.vault_path == "/export/vault"

    def test_import_config_empty_data(self, cm, tmp_config_dir):
        """导入空字典 {} 应返回 False（data 为空时为 falsy）"""
        empty_file = tmp_config_dir / "empty.yaml"
        empty_file.write_text("{}", encoding="utf-8")
        result = cm.import_config(empty_file)
        assert result is False

    def test_import_config_only_version(self, cm, tmp_config_dir):
        """只包含 version 的 config 应成功导入"""
        v_file = tmp_config_dir / "version.yaml"
        v_file.write_text("version: 2", encoding="utf-8")
        assert cm.import_config(v_file) is True
        assert cm.config.version == 2

    def test_load_config_with_api_key_in_file(
        self, tmp_config_dir, mock_credential_manager
    ):
        """配置文件中包含 API Key 时，初始化时触发迁移（不报错）"""
        yaml_content = """
ai:
  api_key: "my-secret-key-in-config"
  engine: DeepSeek-V3
"""
        config_file = tmp_config_dir / "config.yaml"
        config_file.write_text(yaml_content, encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_config_dir.parent.parent):
            from src.services.config_manager import ConfigManager

            ConfigManager._instance = None
            ConfigManager._initialized = False
            cm = ConfigManager()
            # 迁移后 api_key 应被清空
            assert cm.config.ai.api_key == ""

    def test_keyring_name_format(self, cm):
        """_keyring_name() 格式正确"""
        name = cm._keyring_name("dashscope_key")
        assert name == "extractor_dashscope_key"

    def test_convenience_functions_exist(self):
        """便捷函数应可导入"""
        from src.services.config_manager import (
            get_config,
            get_config_manager,
            save_config,
        )

        assert callable(get_config_manager)
        assert callable(get_config)
        assert callable(save_config)
