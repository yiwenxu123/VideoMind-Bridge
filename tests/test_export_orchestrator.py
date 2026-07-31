"""ExportOrchestrator 单元测试

覆盖 ExportOrchestrator 的所有方法和边界情况。
所有测试使用 unittest.mock 隔离外部依赖，不涉及真实文件系统或网络。
"""

from datetime import datetime
from pathlib import Path
from typing import cast
from unittest import mock
from uuid import uuid4

import pytest

from src.exporters.base import BaseExporter
from src.exporters.local_exporter import LocalExporter
from src.exporters.obsidian_exporter import ObsidianExporter
from src.exporters.webhook_exporter import WebhookExporter
from src.models.task import ExportContext, ExportResult, ExportTarget, VideoMetadata
from src.services.export_orchestrator import ExportOrchestrator


# =============================================================================
# Fixtures: 公共测试数据
# =============================================================================


@pytest.fixture
def export_context() -> ExportContext:
    """创建一个标准的导出上下文供测试使用"""
    return ExportContext(
        task_id=uuid4(),
        video_metadata=VideoMetadata(
            title="测试视频",
            author="测试作者",
            duration=120,
            platform="bilibili",
            url="https://test.com/video",
        ),
        transcript_text="这是测试转录内容",
        ai_summary="这是测试摘要",
    )


@pytest.fixture
def mock_local_exporter() -> mock.MagicMock:
    """创建一个模拟的 LocalExporter 实例"""
    exporter = mock.MagicMock(spec=LocalExporter)
    exporter.name = "本地文件夹"
    exporter.icon = "💾"
    exporter.export.return_value = ExportResult(
        success=True,
        target=ExportTarget.LOCAL,
        output_path=Path("/tmp/test_output"),
        timestamp=datetime.now(),
    )
    return exporter


@pytest.fixture
def mock_obsidian_exporter() -> mock.MagicMock:
    """创建一个模拟的 ObsidianExporter 实例"""
    exporter = mock.MagicMock(spec=ObsidianExporter)
    exporter.name = "Obsidian"
    exporter.icon = "📝"
    exporter.export.return_value = ExportResult(
        success=True,
        target=ExportTarget.OBSIDIAN,
        output_path=Path("/tmp/test_vault/Inbox/Videos/test.md"),
        timestamp=datetime.now(),
    )
    return exporter


@pytest.fixture
def mock_webhook_exporter() -> mock.MagicMock:
    """创建一个模拟的 WebhookExporter 实例"""
    exporter = mock.MagicMock(spec=WebhookExporter)
    exporter.name = "Webhook"
    exporter.icon = "🔗"
    exporter.export.return_value = ExportResult(
        success=True,
        target=ExportTarget.WEBHOOK,
        remote_url="https://hooks.test.com/callback",
        timestamp=datetime.now(),
    )
    return exporter


@pytest.fixture
def failing_exporter() -> mock.MagicMock:
    """创建一个总是失败的模拟 exporter"""
    exporter = mock.MagicMock(spec=BaseExporter)
    exporter.name = "故障导出器"
    exporter.icon = "💥"
    exporter.export.side_effect = RuntimeError("导出过程中发生意外错误")
    return exporter


# =============================================================================
# 1. __init__ 测试
# =============================================================================


class TestExportOrchestratorInit:
    """ExportOrchestrator 初始化测试"""

    def test_init_with_targets_and_config(self):
        """给定 targets 和 config 应正确初始化"""
        targets = [ExportTarget.LOCAL]
        config = {"local_output_path": Path("/tmp/test")}
        orchestrator = ExportOrchestrator(targets=targets, config=config)
        assert orchestrator.targets == targets
        assert orchestrator.config == config
        assert isinstance(orchestrator.exporters, list)

    def test_init_without_config_uses_empty_dict(self):
        """不传 config 时使用空字典"""
        targets = [ExportTarget.LOCAL]
        orchestrator = ExportOrchestrator(targets=targets)
        assert orchestrator.config == {}

    def test_init_empty_targets(self):
        """空 targets 列表不加载任何 exporter"""
        orchestrator = ExportOrchestrator(targets=[])
        assert orchestrator.targets == []
        assert orchestrator.exporters == []


# =============================================================================
# 2. _load_exporters 测试
# =============================================================================


class TestLoadExporters:
    """_load_exporters 加载 exporter 测试"""

    def test_load_local_exporter(self):
        """LOCAL 目标应创建 LocalExporter 实例"""
        orchestrator = ExportOrchestrator(
            targets=[ExportTarget.LOCAL],
            config={"local_output_path": Path("/tmp/exports"), "organize_by": "title"},
        )
        assert len(orchestrator.exporters) == 1
        exporter = orchestrator.exporters[0]
        assert isinstance(exporter, LocalExporter)
        assert exporter.output_path == Path("/tmp/exports")
        assert exporter.organize_by == "title"

    def test_load_local_exporter_default_config(self):
        """LOCAL 目标无配置时使用默认值"""
        orchestrator = ExportOrchestrator(targets=[ExportTarget.LOCAL])
        assert len(orchestrator.exporters) == 1
        exporter = orchestrator.exporters[0]
        assert isinstance(exporter, LocalExporter)
        assert exporter.output_path == Path.home() / "Downloads" / "VideoMind"
        assert exporter.organize_by == "date"

    def test_load_obsidian_exporter(self):
        """OBSIDIAN 目标应创建 ObsidianExporter 实例"""
        orchestrator = ExportOrchestrator(
            targets=[ExportTarget.OBSIDIAN],
            config={
                "obsidian_vault_path": Path("/tmp/vault"),
                "obsidian_subfolder": "Inbox/Videos",
            },
        )
        assert len(orchestrator.exporters) == 1
        exporter = orchestrator.exporters[0]
        assert isinstance(exporter, ObsidianExporter)
        assert exporter.vault_path == Path("/tmp/vault")
        assert exporter.subfolder == "Inbox/Videos"

    def test_load_obsidian_exporter_default_subfolder(self):
        """OBSIDIAN 无 subfolder 配置时使用默认值"""
        orchestrator = ExportOrchestrator(
            targets=[ExportTarget.OBSIDIAN],
            config={"obsidian_vault_path": Path("/tmp/vault")},
        )
        assert len(orchestrator.exporters) == 1
        exporter = orchestrator.exporters[0]
        assert isinstance(exporter, ObsidianExporter)
        assert exporter.subfolder == "Inbox/Videos"

    def test_load_webhook_exporter_enabled(self):
        """WEBHOOK enabled + url 应创建 WebhookExporter 实例"""
        orchestrator = ExportOrchestrator(
            targets=[ExportTarget.WEBHOOK],
            config={
                "webhook": {
                    "enabled": True,
                    "url": "https://hooks.test.com/callback",
                    "headers": {"X-Custom": "value"},
                    "timeout": 15,
                    "max_retries": 5,
                    "retry_delay": 2.0,
                    "events": ["on_completed", "on_failed"],
                }
            },
        )
        assert len(orchestrator.exporters) == 1
        exporter = orchestrator.exporters[0]
        assert isinstance(exporter, WebhookExporter)
        assert exporter.url == "https://hooks.test.com/callback"
        assert exporter.headers == {"X-Custom": "value"}
        assert exporter.timeout == 15
        assert exporter.max_retries == 5
        assert exporter.retry_delay == 2.0
        assert exporter.events == ["on_completed", "on_failed"]

    def test_load_webhook_exporter_disabled(self):
        """WEBHOOK enabled=False 不应创建 exporter"""
        orchestrator = ExportOrchestrator(
            targets=[ExportTarget.WEBHOOK],
            config={"webhook": {"enabled": False, "url": "https://hooks.test.com/callback"}},
        )
        assert len(orchestrator.exporters) == 0

    def test_load_webhook_exporter_no_url(self):
        """WEBHOOK enabled=True 但无 url 不应创建 exporter"""
        orchestrator = ExportOrchestrator(
            targets=[ExportTarget.WEBHOOK],
            config={"webhook": {"enabled": True}},
        )
        assert len(orchestrator.exporters) == 0

    def test_load_webhook_exporter_no_webhook_config(self):
        """WEBHOOK 无 webhook 配置段不应创建 exporter"""
        orchestrator = ExportOrchestrator(
            targets=[ExportTarget.WEBHOOK],
            config={},
        )
        assert len(orchestrator.exporters) == 0

    def test_load_notion_exporter_skipped(self):
        """NOTION 目标被跳过 (暂未实现)"""
        orchestrator = ExportOrchestrator(targets=[ExportTarget.NOTION])
        assert len(orchestrator.exporters) == 0

    def test_load_multiple_exporters(self):
        """多个目标应加载多个 exporter"""
        orchestrator = ExportOrchestrator(
            targets=[ExportTarget.LOCAL, ExportTarget.OBSIDIAN],
            config={
                "local_output_path": Path("/tmp/exports"),
                "obsidian_vault_path": Path("/tmp/vault"),
            },
        )
        assert len(orchestrator.exporters) == 2
        assert isinstance(orchestrator.exporters[0], LocalExporter)
        assert isinstance(orchestrator.exporters[1], ObsidianExporter)

    def test_load_webhook_defaults_when_partial_config(self):
        """WEBHOOK 部分配置使用默认值"""
        orchestrator = ExportOrchestrator(
            targets=[ExportTarget.WEBHOOK],
            config={
                "webhook": {
                    "enabled": True,
                    "url": "https://hooks.test.com/callback",
                }
            },
        )
        assert len(orchestrator.exporters) == 1
        exporter = cast(WebhookExporter, orchestrator.exporters[0])
        assert exporter.headers == {}
        assert exporter.timeout == 30
        assert exporter.max_retries == 3
        assert exporter.retry_delay == 1.0
        assert exporter.events == ["on_completed"]


# =============================================================================
# 3. export_all 测试
# =============================================================================


class TestExportAll:
    """export_all 并发导出测试"""

    def test_export_all_success(self, export_context, mock_local_exporter, mock_obsidian_exporter):
        """所有 exporter 成功时返回全部成功结果"""
        orchestrator = ExportOrchestrator(targets=[ExportTarget.LOCAL, ExportTarget.OBSIDIAN])
        orchestrator.exporters = [mock_local_exporter, mock_obsidian_exporter]  # type: ignore[assignment]

        results = orchestrator.export_all(export_context)

        assert len(results) == 2
        assert all(r.success for r in results)
        targets = {r.target for r in results}
        assert targets == {ExportTarget.LOCAL, ExportTarget.OBSIDIAN}

    def test_export_all_partial_failure(self, export_context, mock_local_exporter):
        """部分 exporter 失败时返回混合结果"""
        failing = mock.MagicMock(spec=BaseExporter)
        failing.name = "故障导出器"
        failing.icon = "💥"
        failing.export.side_effect = RuntimeError("网络超时")

        orchestrator = ExportOrchestrator(targets=[ExportTarget.LOCAL, ExportTarget.WEBHOOK])
        orchestrator.exporters = [mock_local_exporter, failing]  # type: ignore[assignment]

        results = orchestrator.export_all(export_context)

        assert len(results) == 2
        success_results = [r for r in results if r.success]
        fail_results = [r for r in results if not r.success]
        assert len(success_results) == 1
        assert len(fail_results) == 1
        assert fail_results[0].error_msg is not None
        assert "网络超时" in fail_results[0].error_msg

    def test_export_all_all_fail(self, export_context):
        """所有 exporter 失败时返回全部失败结果"""
        fail1 = mock.MagicMock(spec=BaseExporter)
        fail1.name = "故障A"
        fail1.export.side_effect = RuntimeError("错误A")
        fail2 = mock.MagicMock(spec=BaseExporter)
        fail2.name = "故障B"
        fail2.export.side_effect = RuntimeError("错误B")

        orchestrator = ExportOrchestrator(targets=[ExportTarget.LOCAL, ExportTarget.OBSIDIAN])
        orchestrator.exporters = [fail1, fail2]  # type: ignore[assignment]

        results = orchestrator.export_all(export_context)

        assert len(results) == 2
        assert all(not r.success for r in results)

    def test_export_all_empty_exporters(self, export_context):
        """无 exporter 时返回空列表"""
        orchestrator = ExportOrchestrator(targets=[])
        results = orchestrator.export_all(export_context)
        assert results == []

    def test_export_all_single_exporter(self, export_context, mock_local_exporter):
        """单个 exporter 成功返回单个结果"""
        orchestrator = ExportOrchestrator(targets=[ExportTarget.LOCAL])
        orchestrator.exporters = [mock_local_exporter]  # type: ignore[assignment]

        results = orchestrator.export_all(export_context)

        assert len(results) == 1
        assert results[0].success
        assert results[0].target == ExportTarget.LOCAL

    def test_export_all_captures_target_on_failure(self, export_context, mock_local_exporter):
        """失败时 ExportResult 的 target 应正确映射"""
        failing = mock.MagicMock(spec=WebhookExporter)
        failing.name = "Webhook"
        failing.export.side_effect = RuntimeError("连接失败")

        orchestrator = ExportOrchestrator(targets=[ExportTarget.LOCAL, ExportTarget.WEBHOOK])
        orchestrator.exporters = [mock_local_exporter, failing]  # type: ignore[assignment]

        results = orchestrator.export_all(export_context)

        fail_results = [r for r in results if not r.success]
        assert len(fail_results) == 1
        # WebhookExporter → _get_target_for_exporter → ExportTarget.WEBHOOK
        assert fail_results[0].target == ExportTarget.WEBHOOK


# =============================================================================
# 4. _safe_export 测试
# =============================================================================


class TestSafeExport:
    """_safe_export 安全导出测试"""

    def test_safe_export_success(self, export_context):
        """成功导出应返回 ExportResult"""
        exporter = mock.MagicMock(spec=LocalExporter)
        exporter.name = "本地文件夹"
        expected = ExportResult(
            success=True,
            target=ExportTarget.LOCAL,
            output_path=Path("/tmp/output"),
            timestamp=datetime.now(),
        )
        exporter.export.return_value = expected

        orchestrator = ExportOrchestrator(targets=[ExportTarget.LOCAL])
        result = orchestrator._safe_export(exporter, export_context)

        assert result is expected
        exporter.export.assert_called_once_with(export_context)

    def test_safe_export_raises_exception(self, export_context):
        """exporter.export 抛出异常时 _safe_export 应继续抛出"""
        exporter = mock.MagicMock(spec=LocalExporter)
        exporter.name = "本地文件夹"
        exporter.export.side_effect = RuntimeError("磁盘空间不足")

        orchestrator = ExportOrchestrator(targets=[ExportTarget.LOCAL])

        with pytest.raises(RuntimeError, match="磁盘空间不足"):
            orchestrator._safe_export(exporter, export_context)


# =============================================================================
# 5. _get_target_for_exporter 测试
# =============================================================================


class TestGetTargetForExporter:
    """_get_target_for_exporter 类型映射测试"""

    def test_local_exporter_returns_local_target(self):
        """LocalExporter → ExportTarget.LOCAL"""
        exporter = mock.MagicMock(spec=LocalExporter)
        orchestrator = ExportOrchestrator(targets=[ExportTarget.LOCAL])
        assert orchestrator._get_target_for_exporter(exporter) == ExportTarget.LOCAL

    def test_obsidian_exporter_returns_obsidian_target(self):
        """ObsidianExporter → ExportTarget.OBSIDIAN"""
        exporter = mock.MagicMock(spec=ObsidianExporter)
        orchestrator = ExportOrchestrator(targets=[ExportTarget.OBSIDIAN])
        assert orchestrator._get_target_for_exporter(exporter) == ExportTarget.OBSIDIAN

    def test_webhook_exporter_returns_webhook_target(self):
        """WebhookExporter → ExportTarget.WEBHOOK"""
        exporter = mock.MagicMock(spec=WebhookExporter)
        orchestrator = ExportOrchestrator(targets=[ExportTarget.WEBHOOK])
        assert orchestrator._get_target_for_exporter(exporter) == ExportTarget.WEBHOOK

    def test_unknown_exporter_defaults_to_local(self):
        """未知 exporter 类型默认返回 ExportTarget.LOCAL"""
        exporter = mock.MagicMock(spec=BaseExporter)
        orchestrator = ExportOrchestrator(targets=[ExportTarget.LOCAL])
        assert orchestrator._get_target_for_exporter(exporter) == ExportTarget.LOCAL


# =============================================================================
# 6. 集成场景: 真实加载 + 模拟导出
# =============================================================================


class TestOrchestratorIntegration:
    """真实加载 exporter 后进行导出测试"""

    def test_real_local_exporter_export_called(self, export_context):
        """真实 LocalExporter 加载后 export_all 应调用其 export 方法"""
        with mock.patch.object(LocalExporter, "export", return_value=ExportResult(
            success=True,
            target=ExportTarget.LOCAL,
            timestamp=datetime.now(),
        )) as mock_export:
            orchestrator = ExportOrchestrator(
                targets=[ExportTarget.LOCAL],
                config={"local_output_path": Path("/tmp/test_export")},
            )
            assert len(orchestrator.exporters) == 1
            assert isinstance(orchestrator.exporters[0], LocalExporter)

            results = orchestrator.export_all(export_context)

            assert len(results) == 1
            assert results[0].success
            mock_export.assert_called_once()

    def test_mixed_local_and_webhook(self, export_context):
        """LOCAL + WEBHOOK 加载后成功导出"""
        with (
            mock.patch.object(LocalExporter, "export", return_value=ExportResult(
                success=True, target=ExportTarget.LOCAL, timestamp=datetime.now(),
            )),
            mock.patch.object(WebhookExporter, "export", return_value=ExportResult(
                success=True, target=ExportTarget.WEBHOOK, timestamp=datetime.now(),
            )),
        ):
            orchestrator = ExportOrchestrator(
                targets=[ExportTarget.LOCAL, ExportTarget.WEBHOOK],
                config={
                    "local_output_path": Path("/tmp/test_export"),
                    "webhook": {
                        "enabled": True,
                        "url": "https://hooks.test.com/callback",
                    },
                },
            )
            assert len(orchestrator.exporters) == 2

            results = orchestrator.export_all(export_context)

            assert len(results) == 2
            assert all(r.success for r in results)