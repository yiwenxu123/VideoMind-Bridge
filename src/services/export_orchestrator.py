"""导出编排器 - 协调多个 exporter"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

from ..exporters.base import BaseExporter
from ..exporters.local_exporter import LocalExporter
from ..exporters.obsidian_exporter import ObsidianExporter
from ..exporters.webhook_exporter import WebhookExporter
from ..models.task import ExportContext, ExportResult, ExportTarget
from ..utils import get_logger

logger = get_logger(__name__)


class ExportOrchestrator:
    """导出编排器 - 管理多个导出目标"""

    def __init__(self, targets: List[ExportTarget], config: Optional[dict] = None):
        """
        初始化导出编排器

        Args:
            targets: 导出目标列表
            config: 配置字典
        """
        self.targets = targets
        self.config = config or {}
        self.exporters = self._load_exporters()

    def _load_exporters(self) -> List[BaseExporter]:
        """加载 exporter 实例"""
        exporters: List[BaseExporter] = []

        for target in self.targets:
            if target == ExportTarget.LOCAL:
                local = LocalExporter(
                    output_path=self.config.get("local_output_path", Path.home() / "Downloads" / "VideoMind"),
                    organize_by=self.config.get("organize_by", "date")
                )
                exporters.append(local)

            elif target == ExportTarget.OBSIDIAN:
                obsidian = ObsidianExporter(
                    vault_path=self.config.get("obsidian_vault_path"),
                    subfolder=self.config.get("obsidian_subfolder", "Inbox/Videos")
                )
                exporters.append(obsidian)

            elif target == ExportTarget.WEBHOOK:
                webhook_config = self.config.get("webhook", {})
                if webhook_config.get("enabled") and webhook_config.get("url"):
                    webhook = WebhookExporter(
                        url=webhook_config["url"],
                        headers=webhook_config.get("headers", {}),
                        timeout=webhook_config.get("timeout", 30),
                        max_retries=webhook_config.get("max_retries", 3),
                        retry_delay=webhook_config.get("retry_delay", 1.0),
                        events=webhook_config.get("events", ["on_completed"])
                    )
                    exporters.append(webhook)
                else:
                    logger.warning("Webhook 导出目标已选择但未启用或未配置 URL")

            elif target == ExportTarget.NOTION:
                # NotionExporter 留空，暂不实现
                pass

        return exporters

    def export_all(self, context: ExportContext) -> List[ExportResult]:
        """
        并发执行所有 exporter

        Args:
            context: 导出上下文

        Returns:
            List[ExportResult]: 各导出结果列表
        """
        results = []

        # 使用线程池并发执行
        with ThreadPoolExecutor(max_workers=len(self.exporters)) as executor:
            # 提交所有任务
            future_to_exporter = {
                executor.submit(self._safe_export, exporter, context): exporter
                for exporter in self.exporters
            }

            # 收集结果
            for future in as_completed(future_to_exporter):
                exporter = future_to_exporter[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    # 任一失败不影响其他
                    from datetime import datetime
                    results.append(ExportResult(
                        success=False,
                        target=self._get_target_for_exporter(exporter),
                        error_msg=str(e),
                        timestamp=datetime.now()
                    ))

        return results

    def _safe_export(self, exporter: BaseExporter, context: ExportContext) -> ExportResult:
        """安全执行导出（捕获异常）"""
        try:
            logger.debug(f"Starting export with {exporter.name}")
            result = exporter.export(context)
            logger.debug(f"Export result: success={result.success}, error={result.error_msg}")
            return result
        except Exception as e:
            logger.error(f"Export exception: {e}", exc_info=True)
            raise

    def _get_target_for_exporter(self, exporter: BaseExporter) -> ExportTarget:
        """根据 exporter 获取对应的目标类型"""
        if isinstance(exporter, LocalExporter):
            return ExportTarget.LOCAL
        elif isinstance(exporter, ObsidianExporter):
            return ExportTarget.OBSIDIAN
        elif isinstance(exporter, WebhookExporter):
            return ExportTarget.WEBHOOK
        return ExportTarget.LOCAL


# 测试代码
if __name__ == "__main__":
    import sys
    from pathlib import Path
    from uuid import uuid4

    from ..models.task import VideoMetadata, ExportContext

    # 创建测试上下文
    context = ExportContext(
        task_id=uuid4(),
        video_metadata=VideoMetadata(
            title="测试视频",
            author="测试作者",
            duration=120,
            platform="bilibili",
            url="https://test.com"
        ),
        transcript_text="这是测试转录内容",
        ai_summary="这是测试摘要"
    )

    # 测试编排器
    orchestrator = ExportOrchestrator(
        targets=[ExportTarget.LOCAL],
        config={"local_output_path": Path("./test_export")}
    )

    print(f"加载了 {len(orchestrator.exporters)} 个 exporter")
