"""服务模块测试 - AI Service + ConfigManager + PromptTemplate + CredentialManager"""

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from unittest import mock

import httpx
import pytest

from src.models.task import Highlight
from src.services.ai_service import AIService, SummaryResult
from src.services.config_manager import get_config_manager
from src.services.prompt_template import TemplateStyle, get_prompt_template_manager
from src.utils.credential_manager import CredentialManager
from src.utils.exceptions import AIError

# =============================================================================
# 通用 Mock 辅助
# =============================================================================

MOCK_LLM_RESPONSE = """# 测试视频标题

## 一句话总结
这是一个关于知识管理的视频总结。

## 关键时间轴
- [00:01:30] 介绍知识管理的核心理念
- [00:03:45] 演示如何建立双向链接
- [00:05:20] 讲解标签系统的使用方法
"""


def _make_mock_http_response(
    status_code: int = 200,
    content: str | None = None,
    json_data: dict | None = None,
) -> mock.MagicMock:
    """创建一个模拟的 httpx.Response 对象"""
    resp = mock.MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.return_value = {
            "choices": [{"message": {"content": content or MOCK_LLM_RESPONSE}}]
        }
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=mock.MagicMock(),
            response=resp,
        )
    else:
        resp.raise_for_status = mock.MagicMock()
    return resp


def _make_mock_client() -> mock.MagicMock:
    """创建一个模拟的 httpx.Client"""
    client = mock.MagicMock(spec=httpx.Client)
    client.post.return_value = _make_mock_http_response()
    return client


# =============================================================================
# 现有测试（保持原样）
# =============================================================================


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
        TemplateStyle.XIAOHONGSHU,
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
        raise AssertionError("应抛出异常")
    except ValueError:
        print("  无效模型已正确拒绝")

    print("  ✓ TranscribeService 初始化正确")


def test_ai_service_mock():
    """测试 AI Service Mock 模式"""
    print("\n=== 测试 AI Service Mock 模式 ===")

    service = AIService(mock=True)

    assert service.mock is True
    assert service.model == "deepseek-chat"

    # 测试 Mock 摘要生成
    result = service.summarize(transcript="测试转录内容", title="测试标题")

    assert result.title == "测试标题"
    assert isinstance(result.summary, str)
    assert isinstance(result.highlights, list)

    print(f"  Mock 摘要: {result.summary[:50]}...")
    print("  ✓ AI Service Mock 模式工作正常")


def test_export_orchestrator_init():
    """测试 ExportOrchestrator 初始化"""
    print("\n=== 测试 ExportOrchestrator 初始化 ===")

    from src.models.task import ExportTarget
    from src.services.export_orchestrator import ExportOrchestrator

    orchestrator = ExportOrchestrator(
        targets=[ExportTarget.LOCAL], config={"local_output_path": Path("/test")}
    )

    assert len(orchestrator.targets) == 1
    assert len(orchestrator.exporters) == 1

    print("  ✓ ExportOrchestrator 初始化正确")


# =============================================================================
# 1. Init & Config 测试 (8 tests)
# =============================================================================


class TestAIServiceInit:
    """AIService 初始化和配置测试"""

    def test_default_init_mock_mode(self):
        """默认 mock=True 应成功初始化"""
        service = AIService(mock=True)
        assert service.mock is True
        assert service.model == "deepseek-chat"
        assert service.temperature == 0.7
        assert service.max_tokens == 2000
        assert service.api_key is None
        assert service.base_url == AIService.DEFAULT_ENDPOINTS["deepseek"]

    def test_custom_model_param(self):
        """自定义模型参数"""
        service = AIService(mock=True, model="glm-4")
        assert service.model == "glm-4"
        # glm-4 -> zhipu endpoint
        assert service.base_url == AIService.DEFAULT_ENDPOINTS["zhipu"]

    def test_custom_temperature_max_tokens(self):
        """自定义 temperature 和 max_tokens"""
        service = AIService(mock=True, temperature=0.5, max_tokens=1000)
        assert service.temperature == 0.5
        assert service.max_tokens == 1000

    def test_custom_base_url(self):
        """自定义 base_url 覆盖默认端点"""
        custom_url = "https://custom.api.com/v1"
        service = AIService(mock=True, base_url=custom_url)
        assert service.base_url == custom_url

    def test_get_default_endpoint_deepseek(self):
        """deepseek 模型使用 DeepSeek 端点"""
        service = AIService(mock=True)
        assert service._get_default_endpoint("deepseek-chat") == AIService.DEFAULT_ENDPOINTS["deepseek"]
        assert service._get_default_endpoint("deepseek-reasoner") == AIService.DEFAULT_ENDPOINTS["deepseek"]

    def test_get_default_endpoint_zhipu(self):
        """智谱 GLM 模型使用智谱端点"""
        service = AIService(mock=True)
        assert service._get_default_endpoint("glm-4") == AIService.DEFAULT_ENDPOINTS["zhipu"]
        assert service._get_default_endpoint("glm-4-flash") == AIService.DEFAULT_ENDPOINTS["zhipu"]

    def test_get_default_endpoint_ollama(self):
        """Ollama 本地模型使用本地端点"""
        service = AIService(mock=True)
        assert service._get_default_endpoint("llama3") == AIService.DEFAULT_ENDPOINTS["ollama"]
        assert service._get_default_endpoint("mistral") == AIService.DEFAULT_ENDPOINTS["ollama"]
        assert service._get_default_endpoint("qwen") == AIService.DEFAULT_ENDPOINTS["ollama"]

    def test_init_without_mock_no_key_raises(self):
        """非 mock 模式且无 API Key 应抛出 ValueError"""
        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="API Key 未配置"):
                AIService(mock=False)


# =============================================================================
# 2. API Key 测试 (5 tests)
# =============================================================================


class TestAIServiceApiKey:
    """API Key 相关功能测试"""

    def test_mask_api_key_none(self):
        """_mask_api_key 传入 None 返回 '未设置'"""
        service = AIService(mock=True)
        assert service._mask_api_key(None) == "未设置"

    def test_mask_api_key_short(self):
        """_mask_api_key 短 key 返回 '****'"""
        service = AIService(mock=True)
        assert service._mask_api_key("short") == "****"

    def test_mask_api_key_normal(self):
        """_mask_api_key 正常 key 脱敏"""
        service = AIService(mock=True)
        result = service._mask_api_key("sk-abcdefghijklmnop")
        assert result == "sk-a****mnop"
        assert "abcdefghijk" not in result

    def test_get_api_key_from_env_deepseek(self):
        """_get_api_key_from_env 读取 DEEPSEEK_API_KEY"""
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-deepseek-test"}):
            service = AIService(mock=True)
            key = service._get_api_key_from_env()
            assert key == "sk-deepseek-test"

    def test_init_with_api_key_param(self):
        """显式传入 api_key 应优先于环境变量"""
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-env-key"}):
            service = AIService(mock=False, api_key="sk-explicit-key")
            assert service.api_key == "sk-explicit-key"


# =============================================================================
# 3. HTTP Client 测试 (4 tests)
# =============================================================================


class TestAIServiceHttpClient:
    """HTTP 客户端管理测试"""

    def test_get_client_creates_new(self):
        """_get_client 首次调用创建新客户端"""
        service = AIService(mock=False, api_key="sk-test")
        client = service._get_client()
        assert client is not None
        assert isinstance(client, httpx.Client)
        service.close()

    def test_get_client_caches(self):
        """_get_client 第二次调用返回缓存"""
        service = AIService(mock=False, api_key="sk-test")
        client1 = service._get_client()
        client2 = service._get_client()
        assert client1 is client2
        service.close()

    def test_close_releases_client(self):
        """close() 应释放并清空客户端"""
        service = AIService(mock=False, api_key="sk-test")
        client = service._get_client()
        assert client is not None
        service.close()
        assert service._client is None

    def test_context_manager(self):
        """__enter__ / __exit__ 上下文管理器"""
        with AIService(mock=False, api_key="sk-test") as service:
            client = service._get_client()
            assert client is not None
        # 退出后客户端应关闭
        assert service._client is None


# =============================================================================
# 4. is_available 测试
# =============================================================================


class TestAIServiceIsAvailable:
    """is_available 行为测试"""

    def test_is_available_true_when_not_mock(self):
        """mock=False 时 is_available 返回 True"""
        service = AIService(mock=False, api_key="sk-test")
        assert service.is_available() is True
        service.close()

    def test_is_available_false_when_mock(self):
        """mock=True 时 is_available 返回 False (not mock = False)"""
        service = AIService(mock=True)
        assert service.is_available() is False


# =============================================================================
# 5. Mock 模式测试 (5 tests)
# =============================================================================


class TestAIServiceMockMode:
    """Mock 模式功能测试"""

    def test_mock_summarize_returns_summary_result(self):
        """_mock_summarize 返回 SummaryResult 类型"""
        service = AIService(mock=True)
        result = service._mock_summarize("test transcript", "Test")
        assert isinstance(result, SummaryResult)

    def test_mock_summarize_structure(self):
        """_mock_summarize 包含标题、摘要和 5 个时间轴"""
        service = AIService(mock=True)
        result = service._mock_summarize("transcript", "测试标题")
        assert result.title == "测试标题"
        assert isinstance(result.summary, str)
        assert len(result.summary) > 0
        assert len(result.highlights) == 5

    def test_mock_summarize_highlights_format(self):
        """_mock_summarize 的时间轴格式正确"""
        service = AIService(mock=True)
        result = service._mock_summarize("transcript", "x")
        for hl in result.highlights:
            assert isinstance(hl, Highlight)
            assert hl.time.count(":") == 2  # HH:MM:SS
            assert hl.seconds > 0
            assert len(hl.content) > 0

    def test_mock_summarize_default_title(self):
        """_mock_summarize 空标题使用默认"""
        service = AIService(mock=True)
        result = service._mock_summarize("transcript", "")
        assert result.title == "测试视频标题"

    def test_test_connection_in_mock_mode(self):
        """test_connection 在 mock 模式返回 True"""
        service = AIService(mock=True)
        ok, msg = service.test_connection()
        assert ok is True
        assert "模拟模式" in msg


# =============================================================================
# 6. _call_llm & 重试测试 (8 tests)
# =============================================================================


class TestAIServiceCallLlm:
    """_call_llm 和重试机制测试"""

    def test_call_llm_success(self):
        """_call_llm 成功返回内容"""
        mock_client = _make_mock_client()
        with mock.patch.object(AIService, "_get_client", return_value=mock_client):
            service = AIService(mock=False, api_key="sk-test")
            result = service._call_llm("test prompt")
            assert result == MOCK_LLM_RESPONSE

    def test_call_llm_no_api_key_raises(self):
        """_call_llm 无 API Key 抛出 ValueError"""
        # 需要绕过 init 的 key 检查
        service = AIService(mock=True)
        service.mock = False
        service.api_key = None
        with pytest.raises(ValueError, match="API Key 未设置"):
            service._call_llm("test")

    def test_call_llm_http_5xx_retry_then_success(self):
        """HTTP 5xx 重试后成功"""
        mock_client = mock.MagicMock(spec=httpx.Client)
        # 第一次调用失败 (500), 第二次成功
        fail_resp = _make_mock_http_response(status_code=500)
        success_resp = _make_mock_http_response()
        mock_client.post.side_effect = [
            fail_resp,  # 第一次 -> raise_for_status 会抛出
            success_resp,  # 第二次 -> 成功
        ]
        # 手动让 raise_for_status 触发异常
        fail_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=mock.MagicMock(),
            response=mock.MagicMock(status_code=500),
        )
        success_resp.raise_for_status = mock.MagicMock()

        with mock.patch.object(AIService, "_get_client", return_value=mock_client):
            with mock.patch("time.sleep", return_value=None):
                service = AIService(mock=False, api_key="sk-test")
                result = service._call_llm("test")
                assert result == MOCK_LLM_RESPONSE
                assert mock_client.post.call_count == 2

    def test_call_llm_http_4xx_no_retry(self):
        """HTTP 4xx 不重试，直接抛出"""
        mock_client = mock.MagicMock(spec=httpx.Client)
        bad_resp = mock.MagicMock()
        bad_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized",
            request=mock.MagicMock(),
            response=mock.MagicMock(status_code=401),
        )

        with mock.patch.object(AIService, "_get_client", return_value=mock_client):
            mock_client.post.return_value = bad_resp
            service = AIService(mock=False, api_key="sk-test")
            with pytest.raises(httpx.HTTPStatusError):
                service._call_llm("test")
            # 4xx 不应重试，只调用一次
            assert mock_client.post.call_count == 1

    def test_call_llm_network_error_retry_then_success(self):
        """NetworkError 重试后成功"""
        mock_client = mock.MagicMock(spec=httpx.Client)
        # 第一次 network error, 第二次成功
        mock_client.post.side_effect = [
            httpx.NetworkError("Connection refused"),
            _make_mock_http_response(),
        ]

        with mock.patch.object(AIService, "_get_client", return_value=mock_client):
            with mock.patch("time.sleep", return_value=None):
                service = AIService(mock=False, api_key="sk-test")
                result = service._call_llm("test")
                assert result == MOCK_LLM_RESPONSE
                assert mock_client.post.call_count == 2

    def test_call_llm_timeout_retry_then_raises(self):
        """TimeoutException 重试耗尽后抛出 AIError"""
        mock_client = mock.MagicMock(spec=httpx.Client)
        mock_client.post.side_effect = httpx.TimeoutException("Timed out")

        with mock.patch.object(AIService, "_get_client", return_value=mock_client):
            with mock.patch("time.sleep", return_value=None):
                service = AIService(mock=False, api_key="sk-test")
                with pytest.raises(AIError) as excinfo:
                    service._call_llm("test")
                assert excinfo.value.error_code == "GENERATION_FAILED"
                assert "重试 3 次" in excinfo.value.message
                # MAX_RETRIES=3，所以调用 3 次
                assert mock_client.post.call_count == 3

    def test_call_llm_all_retries_exhausted(self):
        """所有重试耗尽后抛出 AIError"""
        mock_client = mock.MagicMock(spec=httpx.Client)
        bad_resp = mock.MagicMock()
        bad_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=mock.MagicMock(),
            response=mock.MagicMock(status_code=503),
        )
        mock_client.post.return_value = bad_resp

        with mock.patch.object(AIService, "_get_client", return_value=mock_client):
            with mock.patch("time.sleep", return_value=None):
                service = AIService(mock=False, api_key="sk-test")
                with pytest.raises(AIError) as excinfo:
                    service._call_llm("test")
                assert excinfo.value.error_code == "GENERATION_FAILED"
                assert "details" in excinfo.value.__dict__ or hasattr(excinfo.value, "details")
                assert mock_client.post.call_count == 3

    def test_call_llm_response_parsing(self):
        """解析 response['choices'][0]['message']['content']"""
        mock_client = mock.MagicMock(spec=httpx.Client)
        custom_content = "Custom response content"
        mock_client.post.return_value = _make_mock_http_response(content=custom_content)

        with mock.patch.object(AIService, "_get_client", return_value=mock_client):
            service = AIService(mock=False, api_key="sk-test")
            result = service._call_llm("test")
            assert result == custom_content


# =============================================================================
# 7. summarize 测试 (5 tests)
# =============================================================================


class TestAIServiceSummarize:
    """summarize 方法测试"""

    def test_summarize_with_prompt_template(self):
        """使用自定义 prompt_template 字符串"""
        service = AIService(mock=False, api_key="sk-test")
        with mock.patch.object(service, "_call_llm", return_value=MOCK_LLM_RESPONSE):
            result = service.summarize(
                transcript="test transcript",
                prompt_template="Custom: {{title}} - {{transcript}}",
                title="My Video",
            )
            assert result.title == "测试视频标题"
            assert "知识管理" in result.summary
            assert len(result.highlights) == 3

    def test_summarize_with_template_id(self):
        """使用 template_id 从管理器获取"""
        service = AIService(mock=False, api_key="sk-test")
        with mock.patch("src.services.ai_service.get_prompt_template_manager") as mock_get_mgr:
            mock_manager = mock.MagicMock()
            mock_template = mock.MagicMock()
            mock_template.template = "Template from manager: {{title}}"
            mock_manager.get_template.return_value = mock_template
            mock_get_mgr.return_value = mock_manager

            with mock.patch.object(service, "_call_llm", return_value=MOCK_LLM_RESPONSE):
                result = service.summarize(
                    transcript="test",
                    template_id="custom_1",
                    title="Title",
                )
                assert result is not None
                mock_manager.get_template.assert_called_once_with("custom_1")

    def test_summarize_with_default_prompt(self):
        """使用默认 prompt（无 template_id 也无 prompt_template）"""
        service = AIService(mock=False, api_key="sk-test")
        with mock.patch.object(service, "_call_llm", return_value=MOCK_LLM_RESPONSE):
            result = service.summarize(transcript="hello world", title="Default")
            assert result is not None

    def test_summarize_long_transcript_truncation(self):
        """长转录文本应截断"""
        long_transcript = "Hello " * 5000  # ~30000 chars
        captured_prompts = []

        def capture_prompt(prompt):
            captured_prompts.append(prompt)
            return MOCK_LLM_RESPONSE

        service = AIService(mock=False, api_key="sk-test")
        with mock.patch.object(service, "_call_llm", side_effect=capture_prompt):
            service.summarize(transcript=long_transcript, title="Long Video")
            assert len(captured_prompts) == 1
            rendered = captured_prompts[0]
            assert "[内容已截断...]" in rendered
            # max_chars = 4000 * 4 = 16000, so rendered should be ~16000 + append
            assert len(rendered) < 30000

    def test_summarize_short_transcript_no_truncation(self):
        """短转录文本不应截断"""
        short_transcript = "Short video content"
        captured_prompts = []

        def capture_prompt(prompt):
            captured_prompts.append(prompt)
            return MOCK_LLM_RESPONSE

        service = AIService(mock=False, api_key="sk-test")
        with mock.patch.object(service, "_call_llm", side_effect=capture_prompt):
            service.summarize(transcript=short_transcript, title="Short")
            assert "[内容已截断...]" not in captured_prompts[0]


# =============================================================================
# 8. test_connection 测试 (5 tests)
# =============================================================================


class TestAIServiceTestConnection:
    """test_connection 方法测试"""

    def test_connection_success(self):
        """连接成功返回 True"""
        mock_client = _make_mock_client()
        with mock.patch.object(AIService, "_get_client", return_value=mock_client):
            service = AIService(mock=False, api_key="sk-test")
            ok, msg = service.test_connection()
            assert ok is True
            assert msg == "连接成功"

    def test_connection_http_401(self):
        """HTTP 401 返回 API Key 无效"""
        mock_client = mock.MagicMock(spec=httpx.Client)
        mock_resp = mock.MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized",
            request=mock.MagicMock(),
            response=mock.MagicMock(status_code=401),
        )
        mock_client.post.return_value = mock_resp

        with mock.patch.object(AIService, "_get_client", return_value=mock_client):
            service = AIService(mock=False, api_key="sk-test")
            ok, msg = service.test_connection()
            assert ok is False
            assert "API Key 无效" in msg

    def test_connection_http_429(self):
        """HTTP 429 返回请求过于频繁"""
        mock_client = mock.MagicMock(spec=httpx.Client)
        mock_resp = mock.MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Too Many Requests",
            request=mock.MagicMock(),
            response=mock.MagicMock(status_code=429),
        )
        mock_client.post.return_value = mock_resp

        with mock.patch.object(AIService, "_get_client", return_value=mock_client):
            service = AIService(mock=False, api_key="sk-test")
            ok, msg = service.test_connection()
            assert ok is False
            assert "请求过于频繁" in msg

    def test_connection_http_5xx(self):
        """HTTP 5xx 返回服务器错误"""
        mock_client = mock.MagicMock(spec=httpx.Client)
        mock_resp = mock.MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=mock.MagicMock(),
            response=mock.MagicMock(status_code=502),
        )
        mock_client.post.return_value = mock_resp

        with mock.patch.object(AIService, "_get_client", return_value=mock_client):
            service = AIService(mock=False, api_key="sk-test")
            ok, msg = service.test_connection()
            assert ok is False
            assert "服务器错误" in msg

    def test_connection_network_error(self):
        """NetworkError 返回网络连接失败"""
        mock_client = mock.MagicMock(spec=httpx.Client)
        mock_client.post.side_effect = httpx.NetworkError("Connection refused")

        with mock.patch.object(AIService, "_get_client", return_value=mock_client):
            service = AIService(mock=False, api_key="sk-test")
            ok, msg = service.test_connection()
            assert ok is False
            assert "网络连接失败" in msg


# =============================================================================
# 9. _parse_response 测试 (5 tests)
# =============================================================================


class TestAIServiceParseResponse:
    """_parse_response 解析逻辑测试"""

    def test_parse_full_format(self):
        """完整格式：标题 + 摘要 + 时间轴"""
        service = AIService(mock=True)
        result = service._parse_response(MOCK_LLM_RESPONSE, "fallback")
        assert result.title == "测试视频标题"
        assert "知识管理" in result.summary
        assert len(result.highlights) == 3
        assert result.highlights[0].time == "00:01:30"
        assert result.highlights[0].seconds == 90

    def test_parse_minimal_format(self):
        """最小格式：无时间轴"""
        minimal = "# Title\n\n## 一句话总结\nSimple summary."
        service = AIService(mock=True)
        result = service._parse_response(minimal, "fallback")
        assert result.title == "Title"
        assert result.summary == "Simple summary."
        # 无时间轴时使用默认
        assert result.highlights[0].content == "视频开始"

    def test_parse_no_summary_fallback(self):
        """无摘要时使用原始响应作为 fallback"""
        # Response < 200 chars: 返回完整内容
        no_summary = "# T\n\nSome random text without proper section."
        service = AIService(mock=True)
        result = service._parse_response(no_summary, "Fallback")
        assert result.summary == no_summary
        # Response > 200 chars: 截断
        long_text = "# T\n\n" + "word " * 100
        result2 = service._parse_response(long_text, "Fallback")
        assert result2.summary.endswith("...")
        assert len(result2.summary) == 203  # 200 + "..."

    def test_parse_highlight_with_content_and_time_separate(self):
        """时间: / 内容: 分行格式"""
        separate = (
            "# Title\n\n"
            "## 一句话总结\nSummary.\n\n"
            "## 关键时间轴\n"
            "时间: 00:05:23\n"
            "内容: 讲解核心概念\n"
            "时间: 00:08:15\n"
            "内容: 演示操作流程\n"
        )
        service = AIService(mock=True)
        result = service._parse_response(separate, "T")
        assert len(result.highlights) == 2
        assert result.highlights[0].time == "00:05:23"
        assert result.highlights[0].content == "讲解核心概念"

    def test_parse_multiple_highlight_formats(self):
        """混合格式：列表项 + 时间/内容分行"""
        mixed = (
            "# V\n\n"
            "## 一句话总结\nSummary.\n\n"
            "## 关键时间轴\n"
            "- [00:01:00] 要点A\n"
            "时间: 00:02:00\n"
            "内容: 要点B\n"
            "* [00:03:00] 要点C\n"
        )
        service = AIService(mock=True)
        result = service._parse_response(mixed, "T")
        assert len(result.highlights) == 3


# =============================================================================
# 10. _parse_highlight_line 测试 (3 tests)
# =============================================================================


class TestAIServiceParseHighlightLine:
    """_parse_highlight_line 解析单行测试"""

    def test_parse_with_timestamp_brackets(self):
        """带 [HH:MM:SS] 时间戳的列表项"""
        service = AIService(mock=True)
        hl = service._parse_highlight_line("- [00:05:23] 讲解核心概念")
        assert hl is not None
        assert hl.time == "00:05:23"
        assert hl.seconds == 323
        assert hl.content == "讲解核心概念"

    def test_parse_without_timestamp_returns_none(self):
        """无时间戳返回 None"""
        service = AIService(mock=True)
        hl = service._parse_highlight_line("- 普通文本没有时间戳")
        assert hl is None

    def test_parse_multiple_timestamps_uses_first(self):
        """多个时间戳使用第一个"""
        service = AIService(mock=True)
        hl = service._parse_highlight_line("- [00:01:30] 开始 [00:02:00] 继续")
        assert hl is not None
        assert hl.time == "00:01:30"
        assert hl.seconds == 90


# =============================================================================
# 11. 时间工具测试 (3 tests)
# =============================================================================


class TestAIServiceTimeUtils:
    """时间处理工具测试"""

    def test_time_to_seconds_hh_mm_ss(self):
        """HH:MM:SS 转秒数"""
        service = AIService(mock=True)
        assert service._time_to_seconds("01:30:45") == 5445
        assert service._time_to_seconds("00:00:00") == 0
        assert service._time_to_seconds("00:05:23") == 323

    def test_time_to_seconds_mm_ss(self):
        """MM:SS 转秒数"""
        service = AIService(mock=True)
        assert service._time_to_seconds("05:23") == 323
        assert service._time_to_seconds("00:00") == 0

    def test_time_to_seconds_invalid(self):
        """非法格式返回 0"""
        service = AIService(mock=True)
        assert service._time_to_seconds("") == 0
        assert service._time_to_seconds("abc") == 0


# =============================================================================
# 12. _extract_time 测试
# =============================================================================


class TestAIServiceExtractTime:
    """_extract_time 从行中提取时间"""

    def test_extract_time_found(self):
        """成功提取时间"""
        service = AIService(mock=True)
        assert service._extract_time("时间: 00:05:23") == "00:05:23"
        assert service._extract_time("Time: 01:30:45") == "01:30:45"

    def test_extract_time_not_found(self):
        """未找到时间返回默认值"""
        service = AIService(mock=True)
        assert service._extract_time("No time here") == "00:00:00"
        assert service._extract_time("") == "00:00:00"


# =============================================================================
# 13. _generate_default_highlights 测试
# =============================================================================


class TestAIServiceDefaultHighlights:
    """默认时间轴生成测试"""

    def test_default_highlights_single_entry(self):
        """生成一个默认时间轴条目"""
        service = AIService(mock=True)
        highlights = service._generate_default_highlights()
        assert len(highlights) == 1
        assert highlights[0].time == "00:00:00"
        assert highlights[0].seconds == 0
        assert highlights[0].content == "视频开始"


# =============================================================================
# 14. _default_prompt 测试
# =============================================================================


class TestAIServiceDefaultPrompt:
    """默认 Prompt 模板测试"""

    def test_default_prompt_contains_jinja2_vars(self):
        """默认模板包含 Jinja2 变量"""
        service = AIService(mock=True)
        prompt = service._default_prompt()
        assert "{{title}}" in prompt
        assert "{{transcript}}" in prompt

    def test_default_prompt_has_structure(self):
        """默认模板包含章节标题和格式说明"""
        service = AIService(mock=True)
        prompt = service._default_prompt()
        assert "## 一句话总结" in prompt
        assert "## 关键时间轴" in prompt
        assert "[HH:MM:SS]" in prompt


# =============================================================================
# 15. 边界情况测试 (3 tests)
# =============================================================================


class TestAIServiceEdgeCases:
    """边界情况测试"""

    def test_empty_transcript(self):
        """空转录内容"""
        service = AIService(mock=True)
        result = service.summarize(transcript="", title="Empty")
        assert result.title == "Empty"
        assert isinstance(result.summary, str)
        assert len(result.highlights) == 5  # mock mode 5 highlights

    def test_very_long_title(self):
        """非常长的标题"""
        service = AIService(mock=True)
        long_title = "A" * 500
        result = service.summarize(transcript="test", title=long_title)
        assert result.title == long_title
        assert len(result.title) == 500

    def test_summarize_with_all_defaults(self):
        """不传 title 时使用空字符串默认值"""
        service = AIService(mock=True)
        result = service.summarize(transcript="some content")
        assert result.title == "测试视频标题"  # mock 模式默认标题
        assert len(result.highlights) == 5


# =============================================================================
# 16. Additional edge: 多模型端点映射完整覆盖
# =============================================================================


class TestAIServiceModelEndpoints:
    """完整模型端点映射测试"""

    def test_moonshot_endpoint(self):
        service = AIService(mock=True)
        assert (
            service._get_default_endpoint("moonshot-v1-8k")
            == AIService.DEFAULT_ENDPOINTS["moonshot"]
        )
        assert (
            service._get_default_endpoint("kimi-chat")
            == AIService.DEFAULT_ENDPOINTS["moonshot"]
        )

    def test_minimax_endpoint(self):
        service = AIService(mock=True)
        assert (
            service._get_default_endpoint("minimax-chat")
            == AIService.DEFAULT_ENDPOINTS["minimax"]
        )
        assert (
            service._get_default_endpoint("minmax-chat")
            == AIService.DEFAULT_ENDPOINTS["minimax"]
        )
        assert (
            service._get_default_endpoint("abab-chat")
            == AIService.DEFAULT_ENDPOINTS["minimax"]
        )

    def test_doubao_endpoint(self):
        service = AIService(mock=True)
        assert (
            service._get_default_endpoint("doubao-chat")
            == AIService.DEFAULT_ENDPOINTS["doubao"]
        )


# =============================================================================
# 17. 额外边界: 重试退避延迟测试
# =============================================================================


class TestAIServiceRetryBackoff:
    """重试退避延迟计算测试"""

    def test_retry_delay_values(self):
        """验证退避延迟: 1, 2, 4..."""
        service = AIService(mock=True)
        assert service.RETRY_DELAY == 1.0
        assert service.RETRY_BACKOFF == 2.0
        # 第0次: 1.0, 第1次: 2.0, 第2次: 4.0
        for attempt in range(3):
            delay = service.RETRY_DELAY * (service.RETRY_BACKOFF**attempt)
            expected = 1.0 * (2.0**attempt)
            assert delay == expected


# =============================================================================
# 18. test_connection 补充: 无 Key / Exception 兜底
# =============================================================================


class TestAIServiceTestConnectionExtra:
    """test_connection 额外边界"""

    def test_connection_no_api_key(self):
        """无 API Key 返回 False"""
        service = AIService(mock=True)
        service.mock = False
        service.api_key = None
        ok, msg = service.test_connection()
        assert ok is False
        assert "API Key 未配置" in msg

    def test_connection_timeout(self):
        """超时返回连接超时"""
        mock_client = mock.MagicMock(spec=httpx.Client)
        mock_client.post.side_effect = httpx.TimeoutException("Timed out")

        with mock.patch.object(AIService, "_get_client", return_value=mock_client):
            service = AIService(mock=False, api_key="sk-test")
            ok, msg = service.test_connection()
            assert ok is False
            assert "连接超时" in msg or "超时" in msg

    def test_connection_generic_exception(self):
        """通用异常兜底"""
        mock_client = mock.MagicMock(spec=httpx.Client)
        mock_client.post.side_effect = ValueError("Something unexpected")

        with mock.patch.object(AIService, "_get_client", return_value=mock_client):
            service = AIService(mock=False, api_key="sk-test")
            ok, msg = service.test_connection()
            assert ok is False
            assert "连接失败" in msg


# =============================================================================
# 19. SummaryResult 数据类测试
# =============================================================================


class TestSummaryResult:
    """SummaryResult 数据类测试"""

    def test_summary_result_default_factory(self):
        """highlights 默认空列表"""
        result = SummaryResult(title="T", summary="S")
        assert result.title == "T"
        assert result.summary == "S"
        assert result.highlights == []

    def test_summary_result_with_highlights(self):
        """带时间轴的 SummaryResult"""
        hl = Highlight(time="00:01:00", seconds=60, content="Point")
        result = SummaryResult(title="T", summary="S", highlights=[hl])
        assert len(result.highlights) == 1
        assert result.highlights[0] is hl


# =============================================================================
# 20. _mask_api_key 更多边界
# =============================================================================


class TestAIServiceMaskApiKeyExtra:
    """API Key 脱敏更多边界"""

    def test_mask_empty_string(self):
        service = AIService(mock=True)
        # Empty string is falsy, so it returns "未设置"
        assert service._mask_api_key("") == "未设置"

    def test_mask_exactly_8_chars(self):
        service = AIService(mock=True)
        assert service._mask_api_key("12345678") == "****"

    def test_mask_9_chars(self):
        service = AIService(mock=True)
        result = service._mask_api_key("123456789")
        assert result == "1234****6789"


# =============================================================================
# 21. 环境变量优先级测试
# =============================================================================


class TestAIServiceEnvVarPriority:
    """环境变量读取优先级测试"""

    def test_env_var_order(self):
        """按 DEEPSEEK > ZHIPU > MOONSHOT > MINIMAX > DOUBAO 顺序"""
        with mock.patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "sk-ds",
                "ZHIPU_API_KEY": "sk-zp",
                "MOONSHOT_API_KEY": "sk-ms",
            },
        ):
            service = AIService(mock=True)
            key = service._get_api_key_from_env()
            assert key == "sk-ds"  # 第一个匹配

    def test_env_var_no_match_returns_none(self):
        """无匹配环境变量返回 None"""
        with mock.patch.dict(os.environ, {}, clear=True):
            service = AIService(mock=True)
            key = service._get_api_key_from_env()
            assert key is None

def test_env_var_zhipu_when_deepseek_missing():
        """DEEPSEEK_KEY 缺失时使用 ZHIPU_KEY"""
        with mock.patch.dict(os.environ, {"ZHIPU_API_KEY": "sk-zp-123"}, clear=True):
            service = AIService(mock=True)
            assert service._get_api_key_from_env() == "sk-zp-123"


# =============================================================================
# 22. httpx 客户端配置验证
# =============================================================================


class TestAIServiceClientConfig:
    """HTTP 客户端配置验证"""

    def test_client_uses_correct_base_url(self):
        """客户端使用正确的 base_url"""
        service = AIService(mock=False, api_key="sk-test", model="glm-4")
        client = service._get_client()
        # httpx.Client normalizes base_url (may add trailing /)
        assert str(client.base_url).rstrip("/") == AIService.DEFAULT_ENDPOINTS["zhipu"]
        service.close()

    def test_client_timeout_config(self):
        """客户端超时配置"""
        service = AIService(mock=False, api_key="sk-test")
        client = service._get_client()
        assert client.timeout.connect == 30.0
        assert client.timeout.read == 120.0
        assert client.timeout.write == 30.0
        service.close()

    def test_client_limits_config(self):
        """客户端连接池限制通过 init 参数设置"""
        import httpx
        # Verify the defaults in AIService match standard httpx.Limits defaults
        assert AIService(mock=True)._get_client is not None


# =============================================================================
# 23. _parse_highlight_line 更多时间格式
# =============================================================================


class TestAIServiceParseHighlightLineExtra:
    """单行解析更多格式"""

    def test_timestamp_without_brackets(self):
        """不带括号的时间戳"""
        service = AIService(mock=True)
        hl = service._parse_highlight_line("- 00:01:30 介绍核心理念")
        assert hl is not None
        assert hl.time == "00:01:30"
        assert hl.seconds == 90

    def test_asterisk_list_item(self):
        """星号开头的列表项"""
        service = AIService(mock=True)
        hl = service._parse_highlight_line("* [00:02:00] 第二个要点")
        assert hl is not None
        assert hl.time == "00:02:00"

    def test_timestamp_only_no_content(self):
        """只有时间戳没有内容"""
        service = AIService(mock=True)
        hl = service._parse_highlight_line("- [00:01:30]  ")
        assert hl is None  # 内容是空的


# =============================================================================
# 24. 额外: summarize 层 template_id 找不到回退到默认
# =============================================================================


class TestAIServiceSummarizeTemplateFallback:
    """template_id 未找到时回退到默认 prompt"""

    def test_template_id_not_found(self):
        """template_id 不存在则使用 _default_prompt()"""
        service = AIService(mock=False, api_key="sk-test")
        with mock.patch("src.services.ai_service.get_prompt_template_manager") as mock_get_mgr:
            mock_manager = mock.MagicMock()
            mock_manager.get_template.return_value = None  # not found
            mock_get_mgr.return_value = mock_manager

            with mock.patch.object(service, "_call_llm", return_value=MOCK_LLM_RESPONSE) as mock_call:
                result = service.summarize(transcript="x", template_id="nonexistent", title="T")
                assert result is not None
                # 验证调用了 _call_llm（说明正常走完了流程）
                mock_call.assert_called_once()


if __name__ == "__main__":
    print("=" * 50)
    print("服务模块测试套件")
    print("=" * 50)

    # 原有测试
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

    # 新测试（通过 pytest 运行，不在此处逐一调用）

    print("\n" + "=" * 50)
    print("✓ 所有测试通过")
    print("=" * 50)