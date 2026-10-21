"""MCP Server 测试

覆盖 MCP 协议层 (handle_message -> dispatch) 和所有 _call_* 工具处理器。
所有外部依赖被 mock，无网络/磁盘/AI 调用。

测试策略:
  - 协议层: 验证 handle_message 对各类 JSON-RPC 消息的正确响应
  - 处理器层: 验证每个 _call_* 方法在成功/失败路径下的返回值
  - 错误路径: 未知方法、参数缺失、服务异常
  - JSON 可序列化验证: 所有 handler 返回值可被 json.dumps 序列化
"""

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.core.discovery.models import (
    CommentItem,
    CommentsResult,
    CreatorFeedItem,
    CreatorFeedResult,
    CreatorRef,
)
from src.core.models import CostTier
from src.mcp.server import MCPServer

# ============================================================
# Helpers
# ============================================================

_MOCK_URL = "https://www.bilibili.com/video/BV1xx"


def make_extract_result(
    success: bool = True,
    platform: str = "bilibili",
    title: str = "测试视频标题",
    content: str = "视频文字内容",
    source: str = "bilibili_extractor",
    url: str = _MOCK_URL,
    cost_tier: str = "free",
    duration_seconds: float = 600.0,
    error: str | None = None,
    is_placeholder: bool = False,
) -> MagicMock:
    result = MagicMock()
    result.success = success
    result.platform = platform
    result.title = title
    result.content = content
    result.source = source
    result.url = url
    result.cost_tier = MagicMock()
    result.cost_tier.value = cost_tier
    result.duration_seconds = duration_seconds
    result.language = "zh"
    result.error = error
    result.segments = None
    result.metadata = {}
    result.is_placeholder = is_placeholder
    return result


def make_prescreen_result(
    url: str = _MOCK_URL,
    platform: str = "bilibili",
    grade: str = "B",
    score: float = 60.0,
    title: str = "测试视频标题",
    duration_seconds: float = 600.0,
    reasons: list[str] | None = None,
    cost_grade: str = "B",
    recommended_cost_tier: str = "cheap",
    skip_reason: str | None = None,
) -> MagicMock:
    from src.core.models import ContentGrade, CostTier

    result = MagicMock()
    result.url = url
    result.platform = platform
    result.grade = ContentGrade(grade)
    result.cost_grade = ContentGrade(cost_grade)
    result.recommended_cost_tier = CostTier(recommended_cost_tier)
    result.skip_reason = skip_reason
    result.effective_cost_grade.return_value = result.cost_grade
    result.score = score
    result.title = title
    result.duration_seconds = duration_seconds
    result.reasons = reasons or ["评分 60/100 -> B 级"]
    result.metadata = {}
    return result


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def server():
    return MCPServer()


@pytest.fixture
def captured_send(server):
    calls: list[dict[str, Any]] = []

    def _capture(data: dict):
        calls.append(data)

    with patch.object(server, "_send", side_effect=_capture):
        yield calls


# Lazy-imported types need patching at their source modules
# server.py does `from src.core import ContentRouter, Prescreener, HermesFormatter`
# inside methods, so we patch src.core.X instead of src.mcp.server.X
CORE_PATCH = "src.core"
CONFIG_PATCH = "src.services.config_manager"
YTDLP_PATCH = "yt_dlp.extractor.gen_extractors"


# ============================================================
# MCP Protocol Layer
# ============================================================


class TestProtocolInitialize:

    def test_sets_initialized_flag(self, server, captured_send):
        server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {},
        })
        assert server._initialized is True

    def test_returns_capabilities(self, server, captured_send):
        server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {},
        })
        assert len(captured_send) == 1
        data = captured_send[0]
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert "result" in data
        assert data["result"]["protocolVersion"] == "2025-03-26"
        assert data["result"]["serverInfo"]["name"] == "VideoMind Bridge"
        assert data["result"]["serverInfo"]["version"] == "3.0.0"
        assert "tools" in data["result"]["capabilities"]
        assert "resources" in data["result"]["capabilities"]


class TestProtocolNotifications:

    def test_initialized_notification_sets_flag(self, server, captured_send):
        server.handle_message({
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        assert server._initialized is True
        assert len(captured_send) == 0

    def test_cancelled_notification_is_silent(self, server, captured_send):
        server.handle_message({
            "jsonrpc": "2.0", "method": "notifications/cancelled",
        })
        assert len(captured_send) == 0


class TestProtocolToolsList:

    def test_returns_tools(self, server, captured_send, monkeypatch):
        monkeypatch.delenv("VMB_ENABLE_CREATOR_FEED", raising=False)
        monkeypatch.delenv("VMB_ENABLE_COMMENTS", raising=False)
        server.handle_message({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
        })
        assert len(captured_send) == 1
        data = captured_send[0]
        assert data["id"] == 2
        tools = data["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        expected = [
            "videomind_process", "videomind_download", "videomind_transcribe",
            "videomind_supported", "videomind_config", "configure",
            "prescreen_video", "smart_extract", "extract_video",
            "archive_extract", "list_extractors", "videomind_capabilities",
        ]
        for name in expected:
            assert name in tool_names
        assert len(tools) == 12

    def test_each_tool_has_required_fields(self, server, captured_send):
        server.handle_message({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
        })
        for tool in captured_send[0]["result"]["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"
            assert "properties" in tool["inputSchema"]


class TestProtocolResources:

    def test_resources_list(self, server, captured_send):
        server.handle_message({
            "jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {},
        })
        assert captured_send[0]["result"]["resources"] == []

    def test_resources_read(self, server, captured_send):
        server.handle_message({
            "jsonrpc": "2.0", "id": 3, "method": "resources/read", "params": {},
        })
        assert captured_send[0]["result"]["contents"] == []


class TestProtocolUnknownMethod:

    def test_unknown_method_with_id_returns_error(self, server, captured_send):
        server.handle_message({
            "jsonrpc": "2.0", "id": 99, "method": "unknown_method", "params": {},
        })
        data = captured_send[0]
        assert data["id"] == 99
        assert data["error"]["code"] == -32601
        assert "unknown_method" in data["error"]["message"]

    def test_unknown_method_without_id_is_silent(self, server, captured_send):
        server.handle_message({
            "jsonrpc": "2.0", "method": "unknown_method", "params": {},
        })
        assert len(captured_send) == 0


class TestProtocolToolsCallDispatch:

    def test_unknown_tool_returns_error(self, server, captured_send):
        server.handle_message({
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        })
        data = captured_send[0]
        assert data["error"]["code"] == -32601
        assert "Unknown tool" in data["error"]["message"]


# ============================================================
# _call_prescreen_video
# ============================================================


class TestCallPrescreenVideo:

    @patch(f"{CORE_PATCH}.ContentRouter")
    @patch(f"{CORE_PATCH}.Prescreener")
    def test_quick_mode(self, MockPrescreener, MockContentRouter, server, captured_send):
        mock_prescreener = MockPrescreener.return_value
        mock_prescreener.prescreen_quick.return_value = make_prescreen_result(
            grade="B", score=55.0,
        )

        server.handle_message({
            "jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {
                "name": "prescreen_video",
                "arguments": {"url": _MOCK_URL, "mode": "quick"},
            },
        })

        MockContentRouter.assert_called_once()
        MockPrescreener.assert_called_once_with(MockContentRouter.return_value)
        mock_prescreener.prescreen_quick.assert_called_once_with(_MOCK_URL)
        mock_prescreener.prescreen.assert_not_called()

        result = captured_send[0]["result"]
        assert result["url"] == _MOCK_URL
        assert result["grade"] == "B"
        assert result["score"] == 55.0

    @patch(f"{CORE_PATCH}.ContentRouter")
    @patch(f"{CORE_PATCH}.Prescreener")
    def test_full_mode_with_successful_extraction(
        self, MockPrescreener, MockContentRouter, server, captured_send,
    ):
        mock_router = MockContentRouter.return_value
        mock_router.extract.return_value = make_extract_result(
            title="测试视频标题", duration_seconds=600.0,
        )
        mock_prescreener = MockPrescreener.return_value
        mock_prescreener.prescreen.return_value = make_prescreen_result(
            grade="A", score=75.0, title="测试视频标题",
        )

        server.handle_message({
            "jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {
                "name": "prescreen_video",
                "arguments": {"url": _MOCK_URL, "mode": "full"},
            },
        })

        from src.core.models import CostTier
        mock_router.extract.assert_called_once_with(_MOCK_URL, max_cost=CostTier.FREE)
        mock_prescreener.prescreen.assert_called_once_with(
            _MOCK_URL, title="测试视频标题", duration_seconds=600.0,
        )

        result = captured_send[0]["result"]
        assert result["grade"] == "A"
        assert result["score"] == 75.0
        assert result["title"] == "测试视频标题"

    @patch(f"{CORE_PATCH}.ContentRouter")
    @patch(f"{CORE_PATCH}.Prescreener")
    def test_full_mode_with_failed_extraction(
        self, MockPrescreener, MockContentRouter, server, captured_send,
    ):
        mock_router = MockContentRouter.return_value
        mock_router.extract.return_value = make_extract_result(
            success=False, error="提取失败",
        )
        mock_prescreener = MockPrescreener.return_value
        mock_prescreener.prescreen_quick.return_value = make_prescreen_result(
            grade="C", score=45.0,
        )

        server.handle_message({
            "jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {
                "name": "prescreen_video",
                "arguments": {"url": _MOCK_URL, "mode": "full"},
            },
        })

        mock_prescreener.prescreen_quick.assert_called_once()
        mock_prescreener.prescreen.assert_not_called()

        result = captured_send[0]["result"]
        assert result["grade"] == "C"
        assert result["score"] == 45.0

    @patch(f"{CORE_PATCH}.ContentRouter")
    @patch(f"{CORE_PATCH}.Prescreener")
    def test_default_mode_is_quick(
        self, MockPrescreener, MockContentRouter, server, captured_send,
    ):
        mock_prescreener = MockPrescreener.return_value
        mock_prescreener.prescreen_quick.return_value = make_prescreen_result()

        server.handle_message({
            "jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {
                "name": "prescreen_video",
                "arguments": {"url": _MOCK_URL},
            },
        })

        mock_prescreener.prescreen_quick.assert_called_once()
        mock_prescreener.prescreen.assert_not_called()


# ============================================================
# _call_smart_extract
# ============================================================


class TestCallSmartExtract:

    @patch(f"{CORE_PATCH}.HermesFormatter")
    @patch(f"{CORE_PATCH}.ContentRouter")
    @patch(f"{CORE_PATCH}.Prescreener")
    def test_extraction_worthwhile(
        self, MockPrescreener, MockContentRouter, MockFormatter,
        server, captured_send,
    ):
        mock_router = MockContentRouter.return_value
        mock_router.extract.return_value = make_extract_result(
            title="深度分析", duration_seconds=1200.0,
        )
        mock_prescreener = MockPrescreener.return_value
        mock_prescreener.prescreen.return_value = make_prescreen_result(
            grade="A", score=80.0,
        )
        mock_prescreener.is_extraction_worthwhile.return_value = True
        mock_prescreener.recommend_cost_tier.return_value = "paid"
        mock_formatted = {"success": True, "content": "提取内容", "platform": "bilibili"}
        MockFormatter.format_extract_result_full.return_value = mock_formatted

        server.handle_message({
            "jsonrpc": "2.0", "id": 20, "method": "tools/call",
            "params": {
                "name": "smart_extract",
                "arguments": {"url": _MOCK_URL},
            },
        })

        assert mock_prescreener.is_extraction_worthwhile.called
        # FREE 提取已拿到完整内容 → 直接复用, 不升级成本, 不二次提取
        assert not mock_prescreener.recommend_cost_tier.called
        assert mock_router.extract.call_count == 1

        result = captured_send[0]["result"]
        assert result["success"] is True
        assert result["prescreen"]["grade"] == "A"
        assert result["extraction_performed"] is True
        assert result["extraction_skipped"] is False
        assert result["result"] == mock_formatted

    @patch(f"{CORE_PATCH}.HermesFormatter")
    @patch(f"{CORE_PATCH}.ContentRouter")
    @patch(f"{CORE_PATCH}.Prescreener")
    def test_extraction_skipped(
        self, MockPrescreener, MockContentRouter, MockFormatter,
        server, captured_send,
    ):
        mock_router = MockContentRouter.return_value
        mock_router.extract.return_value = make_extract_result(
            title="低质量视频", duration_seconds=30.0,
        )
        mock_prescreener = MockPrescreener.return_value
        mock_prescreener.prescreen.return_value = make_prescreen_result(
            grade="D", score=20.0, cost_grade="D", recommended_cost_tier="paid",
        )
        mock_prescreener.is_extraction_worthwhile.return_value = False

        server.handle_message({
            "jsonrpc": "2.0", "id": 20, "method": "tools/call",
            "params": {
                "name": "smart_extract",
                "arguments": {"url": _MOCK_URL, "min_grade": "C"},
            },
        })

        assert mock_router.extract.call_count == 1
        MockFormatter.format_extract_result_full.assert_not_called()

        result = captured_send[0]["result"]
        assert result["extraction_performed"] is False
        assert result["extraction_skipped"] is True
        assert result["result"] is None
        assert "低于" in (result.get("skip_reason") or "")
        assert "D" in (result.get("skip_reason") or "")

    @patch(f"{CORE_PATCH}.HermesFormatter")
    @patch(f"{CORE_PATCH}.ContentRouter")
    @patch(f"{CORE_PATCH}.Prescreener")
    def test_with_custom_max_cost(
        self, MockPrescreener, MockContentRouter, MockFormatter,
        server, captured_send,
    ):
        mock_router = MockContentRouter.return_value
        mock_router.extract.return_value = make_extract_result(
            title="付费提取测试", duration_seconds=600.0,
        )
        mock_prescreener = MockPrescreener.return_value
        mock_prescreener.prescreen.return_value = make_prescreen_result(grade="A", score=75.0)
        mock_prescreener.is_extraction_worthwhile.return_value = True
        mock_formatted = {"success": True, "content": "提取内容"}
        MockFormatter.format_extract_result_full.return_value = mock_formatted

        server.handle_message({
            "jsonrpc": "2.0", "id": 20, "method": "tools/call",
            "params": {
                "name": "smart_extract",
                "arguments": {"url": _MOCK_URL, "max_cost": "paid"},
            },
        })

        from src.core.models import CostTier
        # FREE 提取已成功 → 复用, 不因 max_cost=paid 而重复提取
        assert mock_router.extract.call_count == 1
        assert mock_router.extract.call_args.kwargs.get("max_cost") == CostTier.FREE

    @patch(f"{CORE_PATCH}.HermesFormatter")
    @patch(f"{CORE_PATCH}.ContentRouter")
    @patch(f"{CORE_PATCH}.Prescreener")
    def test_free_extract_placeholder_upgrades_cost(
        self, MockPrescreener, MockContentRouter, MockFormatter,
        server, captured_send,
    ):
        # FREE 提取仅返回占位 (无内容) → 按推荐成本二次提取
        placeholder = make_extract_result(title="占位", content="", is_placeholder=True)
        success = make_extract_result(title="完整内容", content="正文内容")
        mock_router = MockContentRouter.return_value
        mock_router.extract.side_effect = [placeholder, success]
        mock_prescreener = MockPrescreener.return_value
        mock_prescreener.prescreen.return_value = make_prescreen_result(
            grade="A", score=80.0, cost_grade="A", recommended_cost_tier="paid",
        )
        mock_prescreener.is_extraction_worthwhile.return_value = True
        mock_prescreener.recommend_cost_tier.return_value = "paid"
        mock_formatted = {"success": True, "content": "正文内容"}
        MockFormatter.format_extract_result_full.return_value = mock_formatted

        server.handle_message({
            "jsonrpc": "2.0", "id": 20, "method": "tools/call",
            "params": {
                "name": "smart_extract",
                "arguments": {"url": _MOCK_URL},
            },
        })

        from src.core.models import CostTier
        assert mock_router.extract.call_count == 2
        # 直接消费 prescreen_result.recommended_cost_tier, 无需再调用方法
        assert mock_router.extract.call_args.kwargs.get("max_cost") == CostTier.PAID
        assert not mock_prescreener.recommend_cost_tier.called

        result = captured_send[0]["result"]
        assert result["extraction_performed"] is True
        assert result["result"] == mock_formatted

    @patch(f"{CORE_PATCH}.ContentRouter")
    @patch(f"{CORE_PATCH}.Prescreener")
    def test_free_extract_fails_falls_back_to_quick(
        self, MockPrescreener, MockContentRouter, server, captured_send,
    ):
        mock_router = MockContentRouter.return_value
        mock_router.extract.return_value = make_extract_result(
            success=False, error="失败",
        )
        mock_prescreener = MockPrescreener.return_value
        mock_prescreener.prescreen_quick.return_value = make_prescreen_result(grade="C", score=40.0)
        mock_prescreener.is_extraction_worthwhile.return_value = False

        server.handle_message({
            "jsonrpc": "2.0", "id": 20, "method": "tools/call",
            "params": {
                "name": "smart_extract",
                "arguments": {"url": _MOCK_URL},
            },
        })

        mock_prescreener.prescreen_quick.assert_called_once()
        mock_prescreener.prescreen.assert_not_called()


# ============================================================
# _call_extract_video
# ============================================================


class TestCallExtractVideo:

    @patch(f"{CORE_PATCH}.HermesFormatter")
    @patch(f"{CORE_PATCH}.ContentRouter")
    def test_successful_extraction(
        self, MockContentRouter, MockFormatter, server, captured_send,
    ):
        mock_router = MockContentRouter.return_value
        mock_router.extract.return_value = make_extract_result(
            title="提取测试", content="提取内容",
        )
        mock_formatted = {
            "success": True, "platform": "bilibili",
            "title": "提取测试", "content": "提取内容",
            "source_type": "video_content", "version": "2.0",
        }
        MockFormatter.format_extract_result_full.return_value = mock_formatted

        server.handle_message({
            "jsonrpc": "2.0", "id": 30, "method": "tools/call",
            "params": {
                "name": "extract_video",
                "arguments": {"url": _MOCK_URL},
            },
        })

        from src.core.models import CostTier
        mock_router.extract.assert_called_once_with(_MOCK_URL, max_cost=CostTier.CHEAP)

        result = captured_send[0]["result"]
        assert result["success"] is True
        assert result["source_type"] == "video_content"

    @patch(f"{CORE_PATCH}.HermesFormatter")
    @patch(f"{CORE_PATCH}.ContentRouter")
    def test_with_custom_cost_tier(
        self, MockContentRouter, MockFormatter, server, captured_send,
    ):
        mock_router = MockContentRouter.return_value
        mock_router.extract.return_value = make_extract_result()
        MockFormatter.format_extract_result_full.return_value = {"success": True}

        server.handle_message({
            "jsonrpc": "2.0", "id": 30, "method": "tools/call",
            "params": {
                "name": "extract_video",
                "arguments": {"url": _MOCK_URL, "cost_tier": "premium"},
            },
        })

        from src.core.models import CostTier
        mock_router.extract.assert_called_once_with(_MOCK_URL, max_cost=CostTier.PREMIUM)

    @patch(f"{CORE_PATCH}.HermesFormatter")
    @patch(f"{CORE_PATCH}.ContentRouter")
    def test_failed_extraction(
        self, MockContentRouter, MockFormatter, server, captured_send,
    ):
        mock_router = MockContentRouter.return_value
        mock_router.extract.return_value = make_extract_result(
            success=False, error="不支持的 URL",
        )
        mock_formatted = {"success": False, "error": "不支持的 URL", "platform": "bilibili"}
        MockFormatter.format_extract_result_full.return_value = mock_formatted

        server.handle_message({
            "jsonrpc": "2.0", "id": 30, "method": "tools/call",
            "params": {
                "name": "extract_video",
                "arguments": {"url": "https://example.com/unknown"},
            },
        })

        result = captured_send[0]["result"]
        assert result["success"] is False
        assert "error" in result


class TestCallExtractVideoAsrOverride:

    @patch("src.services.config_manager.ConfigManager.get_asr_config")
    @patch(f"{CORE_PATCH}.HermesFormatter")
    @patch(f"{CORE_PATCH}.ContentRouter")
    def test_asr_override_passes_options(
        self, MockContentRouter, MockFormatter, mock_cfg, server, captured_send,
    ):
        from src.models.config import AsrConfig

        mock_cfg.return_value = AsrConfig(chain=["faster_whisper", "dashscope"])
        mock_router = MockContentRouter.return_value
        mock_router.extract.return_value = make_extract_result()
        MockFormatter.format_extract_result_full.return_value = {"success": True}

        server.handle_message({
            "jsonrpc": "2.0", "id": 30, "method": "tools/call",
            "params": {
                "name": "extract_video",
                "arguments": {
                    "url": _MOCK_URL,
                    "asr": "sensevoice",
                    "asr_language": "zh",
                },
            },
        })

        options = mock_router.extract.call_args.kwargs["options"]
        assert options.asr_chain == ["sensevoice", "faster_whisper", "dashscope"]
        assert options.asr_language == "zh"


# ============================================================
# _call_capabilities
# ============================================================


class TestCallCapabilities:

    @patch(f"{CORE_PATCH}.ContentRouter")
    def test_returns_asr_capabilities(self, MockContentRouter, server, captured_send):
        MockContentRouter.return_value.list_extractors.return_value = {"bilibili": True}

        server.handle_message({
            "jsonrpc": "2.0", "id": 41, "method": "tools/call",
            "params": {"name": "videomind_capabilities", "arguments": {}},
        })

        result = captured_send[0]["result"]
        assert result["schema_version"] == "1.0"
        backend_names = [b["name"] for b in result["asr"]["backends"]]
        assert "faster_whisper" in backend_names
        assert result["extractors"]["bilibili"] is True


# ============================================================
# _call_archive_extract
# ============================================================


class TestCallArchiveExtract:

    @patch(f"{CORE_PATCH}.HermesFormatter")
    @patch(f"{CORE_PATCH}.ContentRouter")
    def test_successful_archive(self, MockContentRouter, MockFormatter, server, captured_send):
        """提取成功后归档到 local, 返回提取+归档结果"""
        mock_router = MockContentRouter.return_value
        mock_router.extract.return_value = make_extract_result(
            title="归档测试", content="这是要归档的内容",
        )
        MockFormatter.format_extract_result_full.return_value = {
            "success": True, "content": "这是要归档的内容", "platform": "bilibili",
        }

        with patch("src.core.archiver.archive_extract_result") as mock_archive:
            mock_archive.return_value = [
                MagicMock(success=True, target=MagicMock(value="local"), output_path=Path("/tmp/out.md"), error_msg=None),
            ]

            server.handle_message({
                "jsonrpc": "2.0", "id": 31, "method": "tools/call",
                "params": {
                    "name": "archive_extract",
                    "arguments": {
                        "url": _MOCK_URL,
                        "targets": ["local"],
                        "local_output": "/tmp/out",
                    },
                },
            })

        from src.core.models import CostTier
        # archive_extract 现在会先 FREE 预筛, 再按推荐成本提取 (可能两次调用)
        calls = mock_router.extract.call_args_list
        assert len(calls) >= 1
        assert calls[0].args == (_MOCK_URL,)
        assert calls[0].kwargs.get("max_cost") == CostTier.FREE
        assert all(c.args == (_MOCK_URL,) for c in calls)
        mock_archive.assert_called_once()
        result = captured_send[0]["result"]
        assert result["success"] is True
        assert result["extract"]["content"] == "这是要归档的内容"
        assert len(result["archive"]) == 1
        assert result["archive"][0]["target"] == "local"

    @patch(f"{CORE_PATCH}.HermesFormatter")
    @patch(f"{CORE_PATCH}.ContentRouter")
    def test_failed_extract_returns_error(self, MockContentRouter, MockFormatter, server, captured_send):
        """提取失败 → 返回失败, 不归档"""
        mock_router = MockContentRouter.return_value
        mock_router.extract.return_value = make_extract_result(
            success=False, error="提取失败",
        )

        with patch("src.core.archiver.archive_extract_result") as mock_archive:
            server.handle_message({
                "jsonrpc": "2.0", "id": 31, "method": "tools/call",
                "params": {
                    "name": "archive_extract",
                    "arguments": {"url": _MOCK_URL, "targets": ["local"]},
                },
            })

        mock_archive.assert_not_called()
        result = captured_send[0]["result"]
        assert result["success"] is False
        assert "提取失败" in (result.get("error") or "")


# ============================================================
# _call_list_extractors
# ============================================================


class TestCallListExtractors:

    @patch(f"{CORE_PATCH}.ContentRouter")
    def test_returns_extractors(self, MockContentRouter, server, captured_send):
        mock_router = MockContentRouter.return_value
        mock_router.list_extractors.return_value = {
            "bilibili": {"available": True, "cost_tier": "free"},
            "youtube": {"available": True, "cost_tier": "free"},
            "douyin": {"available": True, "cost_tier": "free"},
        }

        server.handle_message({
            "jsonrpc": "2.0", "id": 40, "method": "tools/call",
            "params": {"name": "list_extractors", "arguments": {}},
        })

        assert "bilibili" in captured_send[0]["result"]
        assert captured_send[0]["result"]["bilibili"]["available"] is True


# ============================================================
# _call_supported
# ============================================================


class TestCallSupported:

    @patch("src.mcp.server.DownloadService")
    def test_supported_url(self, MockDownloadService, server, captured_send):
        mock_service = MockDownloadService.return_value
        mock_service.is_supported.return_value = True
        mock_service._detect_platform.return_value = "bilibili"

        server.handle_message({
            "jsonrpc": "2.0", "id": 50, "method": "tools/call",
            "params": {
                "name": "videomind_supported",
                "arguments": {"url": _MOCK_URL},
            },
        })

        result = captured_send[0]["result"]
        assert result["url"] == _MOCK_URL
        assert result["supported"] is True
        assert result["platform"] == "bilibili"

    @patch("src.mcp.server.DownloadService")
    def test_unsupported_url(self, MockDownloadService, server, captured_send):
        mock_service = MockDownloadService.return_value
        mock_service.is_supported.return_value = False
        mock_service._detect_platform.return_value = "unknown"

        server.handle_message({
            "jsonrpc": "2.0", "id": 50, "method": "tools/call",
            "params": {
                "name": "videomind_supported",
                "arguments": {"url": "https://example.com/unknown"},
            },
        })

        result = captured_send[0]["result"]
        assert result["supported"] is False
        assert result["platform"] == "unknown"


# ============================================================
# _call_configure
# ============================================================


class TestCallConfigure:

    @patch(f"{CONFIG_PATCH}.ConfigManager")
    def test_get_mode(self, MockConfigManager, server, captured_send):
        mock_config = MockConfigManager.return_value
        mock_config.list_extractor_key_status.return_value = {
            "tikhub": {"label": "Tikhub", "all_configured": True, "keys": []},
            "apify": {"label": "Tikhub", "all_configured": False, "keys": []},
        }
        mock_config.EXTRACTOR_GROUPS = {"tikhub": {}, "apify": {}}

        server.handle_message({
            "jsonrpc": "2.0", "id": 60, "method": "tools/call",
            "params": {
                "name": "configure",
                "arguments": {"action": "get"},
            },
        })

        result = captured_send[0]["result"]
        assert result["success"] is True
        assert result["action"] == "get"
        assert result["config"]["extractors_available"] == 1
        assert result["config"]["total_extractors"] == 2

    @patch(f"{CONFIG_PATCH}.ConfigManager")
    def test_set_mode_success(self, MockConfigManager, server, captured_send):
        mock_config = MockConfigManager.return_value
        type(mock_config).EXTRACTOR_PROVIDERS = PropertyMock(
            return_value={"dashscope_key": {"env": "ALI_API_KEY", "label": "DashScope ASR 阿里云 Key"}},
        )
        mock_config.set_extractor_key.return_value = True

        server.handle_message({
            "jsonrpc": "2.0", "id": 60, "method": "tools/call",
            "params": {
                "name": "configure",
                "arguments": {"action": "set", "key": "dashscope_key", "value": "sk-xxx"},
            },
        })

        mock_config.set_extractor_key.assert_called_once_with("dashscope_key", "sk-xxx")
        result = captured_send[0]["result"]
        assert result["success"] is True
        assert result["action"] == "set"
        assert result["key"] == "dashscope_key"

    @patch(f"{CONFIG_PATCH}.ConfigManager")
    def test_set_mode_missing_args(self, MockConfigManager, server, captured_send):
        mock_config = MockConfigManager.return_value
        type(mock_config).EXTRACTOR_PROVIDERS = PropertyMock(return_value={"dashscope_key": {}})

        server.handle_message({
            "jsonrpc": "2.0", "id": 60, "method": "tools/call",
            "params": {
                "name": "configure",
                "arguments": {"action": "set", "key": "", "value": ""},
            },
        })

        result = captured_send[0]["result"]
        assert result["success"] is False
        assert "error" in result
        mock_config.set_extractor_key.assert_not_called()

    @patch(f"{CONFIG_PATCH}.ConfigManager")
    def test_set_mode_unknown_key(self, MockConfigManager, server, captured_send):
        mock_config = MockConfigManager.return_value
        type(mock_config).EXTRACTOR_PROVIDERS = PropertyMock(
            return_value={"dashscope_key": {"env": "ALI_API_KEY", "label": "DashScope"}},
        )

        server.handle_message({
            "jsonrpc": "2.0", "id": 60, "method": "tools/call",
            "params": {
                "name": "configure",
                "arguments": {"action": "set", "key": "nonexistent_key", "value": "xxx"},
            },
        })

        result = captured_send[0]["result"]
        assert result["success"] is False
        assert "未知配置键" in result["error"]

    @patch(f"{CONFIG_PATCH}.ConfigManager")
    def test_set_mode_failure(self, MockConfigManager, server, captured_send):
        mock_config = MockConfigManager.return_value
        type(mock_config).EXTRACTOR_PROVIDERS = PropertyMock(
            return_value={"dashscope_key": {"env": "ALI_API_KEY", "label": "DashScope"}},
        )
        mock_config.set_extractor_key.return_value = False

        server.handle_message({
            "jsonrpc": "2.0", "id": 60, "method": "tools/call",
            "params": {
                "name": "configure",
                "arguments": {"action": "set", "key": "dashscope_key", "value": "sk-xxx"},
            },
        })

        result = captured_send[0]["result"]
        assert result["success"] is False
        assert "设置失败" in result["error"]


# ============================================================
# _call_config (yt_dlp)
# ============================================================


class TestCallConfig:

    @patch(YTDLP_PATCH)
    def test_returns_config(self, mock_gen, server, captured_send):
        YouTubeIE = type("YouTubeIE", (), {})
        BilibiliIE = type("BilibiliIE", (), {})
        mock_gen.return_value = [YouTubeIE(), BilibiliIE()]

        server.handle_message({
            "jsonrpc": "2.0", "id": 70, "method": "tools/call",
            "params": {"name": "videomind_config", "arguments": {}},
        })

        result = captured_send[0]["result"]
        assert "output_dir" in result
        assert result["whisper_models"] == ["tiny", "base", "small", "medium"]
        assert "export_targets" in result
        platform_names = [p["name"] for p in result["platforms"]]
        assert "YouTube" in platform_names
        assert "Bilibili" in platform_names
        douyin = [p for p in result["platforms"] if p["name"] == "Douyin"][0]
        assert douyin["available"] is True


# ============================================================
# Error Handling
# ============================================================


class TestErrorHandling:

    def test_missing_url_in_args_returns_error(self, server, captured_send):
        server.handle_message({
            "jsonrpc": "2.0", "id": 80, "method": "tools/call",
            "params": {
                "name": "prescreen_video",
                "arguments": {},
            },
        })

        data = captured_send[0]
        # MCP 规范: 工具错误返回 isError:true 的 result, 而非 JSON-RPC error
        assert "error" not in data
        assert data["result"]["isError"] is True
        assert "url" in data["result"]["content"][0]["text"].lower()

    @patch(f"{CORE_PATCH}.ContentRouter")
    def test_service_exception_captured(
        self, MockContentRouter, server, captured_send,
    ):
        mock_router = MockContentRouter.return_value
        mock_router.list_extractors.side_effect = RuntimeError("意外错误")

        server.handle_message({
            "jsonrpc": "2.0", "id": 81, "method": "tools/call",
            "params": {"name": "list_extractors", "arguments": {}},
        })

        data = captured_send[0]
        assert "error" not in data
        assert data["result"]["isError"] is True
        assert "意外错误" in data["result"]["content"][0]["text"]

    def test_unknown_tool_returns_jsonrpc_error(self, server, captured_send):
        """未知工具属于协议层错误, 应返回 JSON-RPC error"""
        server.handle_message({
            "jsonrpc": "2.0", "id": 82, "method": "tools/call",
            "params": {"name": "no_such_tool", "arguments": {}},
        })

        data = captured_send[0]
        assert data["error"]["code"] == -32601

    def test_ping_returns_empty_result(self, server, captured_send):
        """MCP ping 应返回空 result"""
        server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "ping", "params": {},
        })

        data = captured_send[0]
        assert data["result"] == {}

    def test_all_handlers_return_json_serializable(self, server):
        with patch("src.core.ContentRouter") as mock_content_router, \
             patch("src.core.Prescreener") as mock_prscr, \
             patch("src.core.HermesFormatter") as mock_hfmt:
            with patch(f"{CONFIG_PATCH}.ConfigManager") as mock_cm:
                with patch(YTDLP_PATCH) as mock_gen:
                    mock_router = mock_content_router.return_value
                    mock_router.extract.return_value = make_extract_result()
                    mock_router.list_extractors.return_value = {
                        "bilibili": {"available": True},
                    }
                    mock_prescreener = mock_prscr.return_value
                    mock_prescreener.prescreen_quick.return_value = make_prescreen_result()
                    mock_prescreener.prescreen.return_value = make_prescreen_result()
                    mock_prescreener.is_extraction_worthwhile.return_value = False
                    mock_hfmt.format_extract_result_full.return_value = {
                        "success": True, "content": "test",
                    }
                    mock_config = mock_cm.return_value
                    mock_config.list_extractor_key_status.return_value = {}
                    type(mock_config).EXTRACTOR_PROVIDERS = PropertyMock(return_value={})
                    type(mock_config).EXTRACTOR_GROUPS = PropertyMock(return_value={})
                    mock_config.set_extractor_key.return_value = True
                    mock_gen.return_value = []

                    handlers = [
                        ("prescreen_video", {"url": _MOCK_URL}),
                        ("smart_extract", {"url": _MOCK_URL}),
                        ("extract_video", {"url": _MOCK_URL}),
                        ("list_extractors", {}),
                        ("videomind_supported", {"url": _MOCK_URL}),
                        ("videomind_config", {}),
                        ("configure", {"action": "get"}),
                        ("configure", {"action": "set", "key": "dashscope_key", "value": "sk-xxx"}),
                    ]

                    for name, args in handlers:
                        s = MCPServer()
                        captured = []
                        with patch.object(s, "_send", side_effect=captured.append):
                            s.handle_message({
                                "jsonrpc": "2.0", "id": 99, "method": "tools/call",
                                "params": {"name": name, "arguments": args},
                            })
                            assert len(captured) == 1, f"{name} did not send a response"
                            payload = captured[0]
                            if "error" in payload:
                                json.dumps(payload["error"])
                            else:
                                json.dumps(payload["result"])
                            if "error" not in payload:
                                assert payload.get("result") is not None, (
                                    f"{name} returned empty result"
                                )


# ============================================================
# Dispatch coverage - all registered tools work
# ============================================================


class TestDispatchCoverage:

    def test_all_tools_have_handlers(self, server, captured_send, monkeypatch):
        monkeypatch.delenv("VMB_ENABLE_CREATOR_FEED", raising=False)
        monkeypatch.delenv("VMB_ENABLE_COMMENTS", raising=False)
        server.handle_message({
            "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {},
        })
        tool_names = [t["name"] for t in captured_send[0]["result"]["tools"]]

        with patch("src.core.ContentRouter"), \
             patch("src.core.Prescreener"), \
             patch("src.core.HermesFormatter"), patch("src.mcp.server.DownloadService"):
            with patch(f"{CONFIG_PATCH}.ConfigManager"):
                with patch(YTDLP_PATCH):

                    for name in tool_names:
                        s = MCPServer()
                        args = {}
                        if name in (
                            "prescreen_video", "smart_extract",
                            "extract_video", "videomind_supported",
                            "videomind_process", "videomind_download",
                            "videomind_transcribe",
                        ):
                            args = {"url": _MOCK_URL}
                        if name == "configure":
                            args = {"action": "get"}
                        if name == "videomind_transcribe":
                            args = {"audio_path": "/tmp/test.mp3"}

                        captured = []
                        with patch.object(s, "_send", side_effect=captured.append):
                            s.handle_message({
                                "jsonrpc": "2.0", "id": 1,
                                "method": "tools/call",
                                "params": {"name": name, "arguments": args},
                            })
                            assert len(captured) == 1, (
                                f"Tool '{name}' did not respond"
                            )


class TestDiscoveryTools:

    def test_discovery_tools_hidden_by_default(self, server, captured_send, monkeypatch):
        monkeypatch.delenv("VMB_ENABLE_CREATOR_FEED", raising=False)
        monkeypatch.delenv("VMB_ENABLE_COMMENTS", raising=False)

        server.handle_message({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
        })
        names = [tool["name"] for tool in captured_send[0]["result"]["tools"]]

        assert "get_creator_feed" not in names
        assert "get_comments" not in names

    def test_discovery_tools_listed_when_enabled(
        self, server, captured_send, monkeypatch
    ):
        monkeypatch.setenv("VMB_ENABLE_CREATOR_FEED", "1")
        monkeypatch.setenv("VMB_ENABLE_COMMENTS", "1")

        server.handle_message({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
        })
        names = [tool["name"] for tool in captured_send[0]["result"]["tools"]]

        assert "get_creator_feed" in names
        assert "get_comments" in names

    def test_call_get_creator_feed(self, server, captured_send, monkeypatch):
        monkeypatch.setenv("VMB_ENABLE_CREATOR_FEED", "1")
        fake = MagicMock()
        fake.creator_feed.return_value = CreatorFeedResult(
            success=True,
            platform="bilibili",
            source="bilibili_discovery",
            cost_tier=CostTier.FREE,
            creator=CreatorRef(
                id="123456",
                name="示例UP主",
                url="https://space.bilibili.com/123456",
            ),
            items=[
                CreatorFeedItem(
                    id="BV1demo",
                    url="https://www.bilibili.com/video/BV1demo",
                    title="示例作品",
                )
            ],
            completeness="full",
            fetched_at="2026-10-20T08:00:00+00:00",
            request_id="req-1",
        )
        monkeypatch.setattr(server, "_get_discovery_service", lambda: fake)

        server.handle_message({
            "jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {
                "name": "get_creator_feed",
                "arguments": {
                    "url": "https://space.bilibili.com/123456",
                    "limit": 5,
                },
            },
        })

        result = captured_send[0]["result"]
        assert result["success"] is True
        assert result["creator"]["id"] == "123456"
        assert result["returned_count"] == 1
        fake.creator_feed.assert_called_once()
        assert fake.creator_feed.call_args.kwargs["limit"] == 5

    def test_call_get_comments(self, server, captured_send, monkeypatch):
        monkeypatch.setenv("VMB_ENABLE_COMMENTS", "1")
        fake = MagicMock()
        fake.comments.return_value = CommentsResult(
            success=True,
            platform="bilibili",
            source="bilibili_discovery",
            cost_tier=CostTier.FREE,
            items=[
                CommentItem(
                    id="c1",
                    parent_id=None,
                    root_id="c1",
                    text="示例评论",
                    likes=3,
                )
            ],
            completeness="full",
            sort="recent",
            fetched_at="2026-10-20T08:00:00+00:00",
            request_id="req-2",
        )
        monkeypatch.setattr(server, "_get_discovery_service", lambda: fake)

        server.handle_message({
            "jsonrpc": "2.0", "id": 11, "method": "tools/call",
            "params": {
                "name": "get_comments",
                "arguments": {
                    "url": "https://www.bilibili.com/video/BV1demo",
                    "limit": 10,
                    "sort": "recent",
                    "include_replies": True,
                    "max_replies_per_thread": 2,
                },
            },
        })

        result = captured_send[0]["result"]
        assert result["success"] is True
        assert result["items"][0]["text"] == "示例评论"
        assert result["sort"] == "recent"
        fake.comments.assert_called_once()
        kwargs = fake.comments.call_args.kwargs
        assert kwargs["limit"] == 10
        assert kwargs["sort"] == "recent"
        assert kwargs["include_replies"] is True
        assert kwargs["max_replies_per_thread"] == 2
        assert kwargs["include_author"] is False


def test_close_releases_cached_services(server):
    runtime = MagicMock()
    server._services["router_runtime"] = runtime

    server.close()

    runtime.close.assert_called_once()
    assert server._services == {}
