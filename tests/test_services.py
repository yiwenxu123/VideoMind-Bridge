"""服务模块测试"""

import sys
from pathlib import Path

from src.services.config_manager import ConfigManager, get_config_manager
from src.services.prompt_template import (
    get_prompt_template_manager, PromptTemplate, TemplateStyle
)
from src.utils.credential_manager import CredentialManager


def test_config_manager_singleton():
    """测试 ConfigManager 单例模式"""
    print("=== 测试 ConfigManager 单例 ===")
    
    manager1 = get_config_manager()
    manager2 = get_config_manager()
    
    assert manager1 is manager2, "应该是同一个实例"
    print("  ✓ ConfigManager 是单例")


def test_config_manager_default():
    """测试 ConfigManager 默认配置"""
    print("\n=== 测试 ConfigManager 默认配置 ===")
    
    manager = get_config_manager()
    config = manager.config
    
    assert config is not None
    assert config.ai.engine.value == "DeepSeek-V3"
    assert config.download.video_quality == "1080p"
    
    print("  ✓ ConfigManager 默认配置正确")


def test_config_manager_ai_key():
    """测试 AI Key 获取（无配置时返回 None）"""
    print("\n=== 测试 ConfigManager AI Key ===")
    
    manager = get_config_manager()
    api_key = manager.get_api_key()
    
    # 如果没有配置，应该返回 None 而不是抛出异常
    assert api_key is None or isinstance(api_key, str)
    print(f"  API Key 状态: {'已配置' if api_key else '未配置'}")


def test_prompt_template_manager():
    """测试 PromptTemplateManager"""
    print("\n=== 测试 PromptTemplateManager ===")
    
    manager = get_prompt_template_manager()
    templates = manager.get_all_templates()
    
    assert isinstance(templates, list)
    print(f"  找到 {len(templates)} 个模板")
    
    # 测试获取默认模板
    default_template = manager.get_default_template()
    assert default_template is not None
    print(f"  默认模板: {default_template.name}")


def test_prompt_template_styles():
    """测试 PromptTemplateStyle 枚举"""
    print("\n=== 测试 PromptTemplateStyle ===")
    
    styles = [
        TemplateStyle.DEFAULT,
        TemplateStyle.ACADEMIC,
        TemplateStyle.QUICK,
        TemplateStyle.ACTION,
        TemplateStyle.TRANSLATION,
        TemplateStyle.QNA,
        TemplateStyle.XIAOHONGSHU
    ]
    
    for style in styles:
        assert isinstance(style.value, str)
    
    print(f"  找到 {len(styles)} 种模板风格")
    print("  ✓ PromptTemplateStyle 测试通过")


def test_credential_manager():
    """测试 CredentialManager"""
    print("\n=== 测试 CredentialManager ===")
    
    test_provider = "test_provider"
    test_key = "test_api_key_12345"
    
    # 测试保存
    save_result = CredentialManager.save_api_key(test_provider, test_key)
    assert save_result is True, "保存应成功"
    print("  API Key 保存成功")
    
    # 测试获取
    retrieved_key = CredentialManager.get_api_key(test_provider)
    assert retrieved_key == test_key, "获取的 Key 应与保存的一致"
    print("  API Key 获取成功")
    
    # 清理测试数据
    try:
        from keyring.errors import PasswordDeleteError
        keyring = __import__("keyring")
        keyring.delete_password(CredentialManager.SERVICE_NAME, test_provider)
        print("  测试数据已清理")
    except Exception:
        pass
    
    print("  ✓ CredentialManager 测试通过")


def test_download_service_init():
    """测试 DownloadService 初始化"""
    print("\n=== 测试 DownloadService 初始化 ===")
    
    from src.services.download_service import DownloadService
    from pathlib import Path
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        service = DownloadService(Path(tmpdir))
        
        assert service.output_dir == Path(tmpdir)
        assert service.MAX_RETRIES == 3
    
    print("  ✓ DownloadService 初始化正确")


def test_transcribe_service_init():
    """测试 TranscribeService 初始化"""
    print("\n=== 测试 TranscribeService 初始化 ===")
    
    from src.services.transcribe_service import TranscribeService
    
    service = TranscribeService("small")
    
    assert service.SUPPORTED_MODELS == ["tiny", "base", "small", "medium", "large"]
    assert service.model_size == "small"
    
    # 测试不支持的模型
    try:
        TranscribeService("invalid")
        assert False, "应抛出异常"
    except ValueError:
        print("  无效模型已正确拒绝")
    
    print("  ✓ TranscribeService 初始化正确")


def test_ai_service_mock():
    """测试 AI Service Mock 模式"""
    print("\n=== 测试 AI Service Mock 模式 ===")
    
    from src.services.ai_service import AIService
    
    service = AIService(mock=True)
    
    assert service.mock is True
    assert service.model == "deepseek-chat"
    
    # 测试 Mock 摘要生成
    result = service.summarize(
        transcript="测试转录内容",
        title="测试标题"
    )
    
    assert result.title == "测试标题"
    assert isinstance(result.summary, str)
    assert isinstance(result.highlights, list)
    
    print(f"  Mock 摘要: {result.summary[:50]}...")
    print("  ✓ AI Service Mock 模式工作正常")


def test_export_orchestrator_init():
    """测试 ExportOrchestrator 初始化"""
    print("\n=== 测试 ExportOrchestrator 初始化 ===")
    
    from src.services.export_orchestrator import ExportOrchestrator
    from src.models.task import ExportTarget
    from pathlib import Path
    
    orchestrator = ExportOrchestrator(
        targets=[ExportTarget.LOCAL],
        config={"local_output_path": Path("/test")}
    )
    
    assert len(orchestrator.targets) == 1
    assert len(orchestrator.exporters) == 1
    
    print("  ✓ ExportOrchestrator 初始化正确")


if __name__ == "__main__":
    print("=" * 50)
    print("服务模块测试套件")
    print("=" * 50)
    
    test_config_manager_singleton()
    test_config_manager_default()
    test_config_manager_ai_key()
    test_prompt_template_manager()
    test_prompt_template_styles()
    test_credential_manager()
    test_download_service_init()
    test_transcribe_service_init()
    test_ai_service_mock()
    test_export_orchestrator_init()
    
    print("\n" + "=" * 50)
    print("✓ 所有测试通过")
    print("=" * 50)
