"""本地文件导出器实现"""

import json
import shutil
from datetime import datetime
from pathlib import Path

from ..models.task import ExportContext, ExportResult, ExportTarget, TranscriptSegment
from ..utils import (
    Highlight,
    extract_highlights_from_context,
    generate_srt,
    get_logger,
    safe_write_text,
    sanitize_filename,
)
from .base import BaseExporter

logger = get_logger(__name__)


class LocalExporter(BaseExporter):
    """本地文件夹导出器"""

    name = "本地文件夹"
    icon = "💾"

    def __init__(self, output_path: Path, organize_by: str = "date"):
        """
        初始化本地导出器

        Args:
            output_path: 输出根目录
            organize_by: 组织方式 ("date" | "title" | "flat")
        """
        self.output_path = Path(output_path)
        self.organize_by = organize_by

    def validate_config(self) -> tuple[bool, str]:
        """验证配置"""
        try:
            self.output_path.mkdir(parents=True, exist_ok=True)
            return True, ""
        except PermissionError as e:
            logger.error(f"权限错误，无法创建输出目录: {e}")
            return False, f"权限错误，无法创建输出目录: {e}"
        except OSError as e:
            logger.error(f"系统错误，无法创建输出目录: {e}")
            return False, f"系统错误，无法创建输出目录: {e}"

    def export(self, context: ExportContext) -> ExportResult:
        """
        导出到本地文件夹

        目录结构: {output_path}/{date}/{sanitized_title}/
        包含: video.mp4, audio.m4a, transcript.txt, note.md, highlights.json
        """
        # 验证配置
        valid, error = self.validate_config()
        if not valid:
            return ExportResult(
                success=False,
                target=ExportTarget.LOCAL,
                error_msg=error
            )

        # 构建输出目录
        output_dir = self._build_output_dir(context)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 生成文件名（安全化）
        safe_title = sanitize_filename(context.video_metadata.title)

        files_created = []

        # 1. 复制视频文件（如果有）- 视频已包含音频，优先使用视频
        if context.video_path and context.video_path.exists():
            video_dest = output_dir / f"{safe_title}.mp4"
            # 清理可能存在的旧音频文件（避免之前版本残留）
            audio_dest = output_dir / f"{safe_title}.m4a"
            if audio_dest.exists():
                try:
                    audio_dest.unlink()
                    logger.info(f"清理旧音频文件: {audio_dest}")
                except (OSError, PermissionError) as e:
                    logger.warning(f"清理旧音频文件失败: {e}")
            # 避免源文件和目标文件相同
            if context.video_path.resolve() != video_dest.resolve():
                try:
                    shutil.copy2(context.video_path, video_dest)
                    files_created.append(video_dest.name)
                    logger.info(f"复制视频文件: {video_dest}")
                except (OSError, PermissionError) as e:
                    logger.error(f"复制视频文件失败: {e}")
            else:
                files_created.append(context.video_path.name)

        # 2. 只有在没有视频文件时，才复制音频文件
        # 注意：视频文件已经包含音频，不需要单独复制音频文件
        elif context.audio_path and context.audio_path.exists():
            audio_dest = output_dir / f"{safe_title}.m4a"
            # 避免源文件和目标文件相同
            if context.audio_path.resolve() != audio_dest.resolve():
                try:
                    shutil.copy2(context.audio_path, audio_dest)
                    files_created.append(audio_dest.name)
                    logger.info(f"复制音频文件: {audio_dest}")
                except (OSError, PermissionError) as e:
                    logger.error(f"复制音频文件失败: {e}")
            else:
                files_created.append(context.audio_path.name)

        # 3. 保存转录文本（带时间戳）
        if context.transcript_text:
            transcript_path = output_dir / f"{safe_title}_transcript.txt"
            success, msg = safe_write_text(transcript_path, context.transcript_text)
            if success:
                files_created.append(transcript_path.name)
                logger.info(msg)
            else:
                logger.error(msg)

        # 4. 保存 SRT 格式字幕
        if context.transcript_segments:
            srt_path = output_dir / f"{safe_title}.srt"
            srt_content = generate_srt(context.transcript_segments)
            success, msg = safe_write_text(srt_path, srt_content)
            if success:
                files_created.append(srt_path.name)
                logger.info(msg)
            else:
                logger.error(msg)

        # 5. 生成 Markdown 笔记（包含时间轴）
        md_path = output_dir / f"{safe_title}.md"
        md_content = self._generate_markdown(context)
        success, msg = safe_write_text(md_path, md_content)
        if success:
            files_created.append(md_path.name)
            logger.info(msg)
        else:
            logger.error(msg)

        # 6. 保存时间轴 JSON（便于其他工具使用）
        highlights = extract_highlights_from_context(context.config)
        if highlights:
            json_path = output_dir / f"{safe_title}_highlights.json"
            highlights_data = [
                {"time": h.time, "seconds": h.seconds, "content": h.content}
                for h in highlights
            ]
            json_content = json.dumps(highlights_data, ensure_ascii=False, indent=2)
            success, msg = safe_write_text(json_path, json_content)
            if success:
                files_created.append(json_path.name)
                logger.info(msg)
            else:
                logger.error(msg)

        return ExportResult(
            success=True,
            target=ExportTarget.LOCAL,
            output_path=output_dir,
            metadata={
                "files_created": len(files_created),
                "files": files_created,
                "organized_by": self.organize_by
            }
        )

    def _build_output_dir(self, context: ExportContext) -> Path:
        """构建输出目录路径"""
        metadata = context.video_metadata

        if self.organize_by == "date":
            date_str = datetime.now().strftime("%Y-%m-%d")
            safe_title = sanitize_filename(metadata.title)
            return self.output_path / date_str / safe_title

        elif self.organize_by == "title":
            safe_title = sanitize_filename(metadata.title)
            return self.output_path / safe_title

        else:  # flat
            return self.output_path

    def _generate_markdown(self, context: ExportContext) -> str:
        """生成 Markdown 笔记（包含时间轴）"""
        meta = context.video_metadata
        highlights = self._extract_highlights_from_context(context)

        lines = [
            f"# {meta.title}",
            "",
            "## 元数据",
            f"- **来源**: [{meta.platform}]({meta.url})",
            f"- **作者**: {meta.author}",
            f"- **时长**: {meta.duration // 60}分{meta.duration % 60}秒",
            f"- **导出时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        # AI 摘要
        if context.ai_summary:
            lines.extend([
                "## AI 摘要",
                context.ai_summary,
                "",
            ])

        # 关键时间轴
        if highlights:
            lines.extend([
                "## 关键时间轴",
                "",
            ])

            # 根据是否有本地视频决定链接格式
            if context.video_path:
                # 有本地视频: 链接到本地文件，使用 player.html 播放器
                for h in highlights:
                    link = f"[{h.time}](player.html)"
                    lines.append(f"- {link} - {h.content}")
                lines.append("")
                lines.append("> 💡 **提示**: 点击时间戳打开 [player.html](player.html) 播放器，可跳转到对应位置")
            else:
                # 无本地视频: 链接到线上 URL
                video_url = meta.url
                for h in highlights:
                    # Bilibili 和 YouTube 都支持 ?t=seconds 参数
                    link = f"[{h.time}]({video_url}?t={h.seconds})"
                    lines.append(f"- {link} - {h.content}")
                lines.append("")
                lines.append("> 💡 **提示**: 点击时间戳在浏览器中打开在线视频并跳转到对应位置")
            lines.append("")

        lines.extend([
            "## 文件列表",
            f"- 视频: `{meta.title}.mp4`" if context.video_path else "- 视频: (未下载)",
            f"- 音频: `{meta.title}.m4a`",
            f"- 字幕: `{meta.title}.srt`",
            f"- 转录: `{meta.title}_transcript.txt`",
            f"- 时间轴: `{meta.title}_highlights.json`",
            "",
            "---",
            "*由 VideoMind Bridge 自动生成*"
        ])

        return "\n".join(lines)

    def _extract_highlights_from_context(self, context: ExportContext) -> list[Highlight]:
        """从 ExportContext 提取时间轴数据（使用共享工具）"""
        return extract_highlights_from_context(context.config)


# 测试代码
if __name__ == "__main__":
    from pathlib import Path
    from uuid import uuid4

    from ..models.task import ExportContext, TranscriptSegment, VideoMetadata

    # 创建测试上下文
    context = ExportContext(
        task_id=uuid4(),
        video_metadata=VideoMetadata(
            title="测试视频标题",
            author="测试UP主",
            duration=180,
            platform="bilibili",
            url="https://test.com/video"
        ),
        video_path=Path("./test_video.mp4"),  # 模拟视频路径
        audio_path=Path("./test_audio.m4a"),  # 模拟音频路径
        transcript_segments=[
            TranscriptSegment(start=0, end=5, text="这是第一句"),
            TranscriptSegment(start=5, end=10, text="这是第二句"),
        ],
        transcript_text="[00:00:00] 这是第一句\n[00:00:05] 这是第二句",
        ai_summary="这是一个测试视频的摘要内容。",
        config={
            "highlights": [
                {"time": "00:01:30", "seconds": 90, "content": "介绍知识管理的核心理念"},
                {"time": "00:03:45", "seconds": 225, "content": "演示如何建立双向链接"},
            ]
        }
    )

    # 测试导出
    exporter = LocalExporter(output_path=Path("./test_local_export"))
    result = exporter.export(context)

    print(f"导出结果: {'成功' if result.success else '失败'}")
    if result.success:
        print(f"输出目录: {result.output_path}")
        print(f"创建文件: {result.metadata.get('files', [])}")
