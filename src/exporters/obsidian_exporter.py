"""Obsidian 导出器实现"""

from datetime import datetime
from pathlib import Path

from ..models.task import ExportContext, ExportResult, ExportTarget
from ..utils import (
    Highlight,
    extract_highlights_from_context,
    format_time_for_media_extended,
    get_logger,
    safe_copy_file,
    safe_create_symlink,
    sanitize_filename,
)
from .base import BaseExporter

logger = get_logger(__name__)


class ObsidianExporter(BaseExporter):
    """Obsidian Vault 导出器"""

    name = "Obsidian"
    icon = "📝"

    def __init__(
        self,
        vault_path: Path | None = None,
        subfolder: str = "Inbox/Videos",
        template_path: Path | None = None
    ):
        """
        初始化 Obsidian 导出器

        Args:
            vault_path: Vault 根目录
            subfolder: 子文件夹路径
            template_path: Markdown 模板路径（可选）
        """
        self.vault_path: Path | None = Path(vault_path) if vault_path else None
        self.subfolder = subfolder
        self.template_path = template_path

    def validate_config(self) -> tuple[bool, str]:
        """验证配置"""
        if not self.vault_path:
            return False, "未配置 Obsidian Vault 路径"

        if not self.vault_path.exists():
            return False, f"Vault 路径不存在: {self.vault_path}"

        # 放宽验证：只要路径存在即可（支持 iCloud Vault 等各种配置）
        # 可选：检查是否是有效的 Vault（包含 .obsidian 目录）
        # 但 iCloud 同步的 Vault 可能没有这个目录
        if not (self.vault_path / ".obsidian").exists():
            # 发出警告但不阻止导出
            logger.warning(f"指定的路径可能不是标准 Obsidian Vault（缺少 .obsidian 目录）: {self.vault_path}")

        return True, ""

    def export(self, context: ExportContext) -> ExportResult:
        """
        导出到 Obsidian Vault

        生成标准 Markdown，包含 YAML Frontmatter 和可点击时间戳
        媒体文件放入 Vault 根目录的 Attachments 文件夹，与笔记完全隔离
        """

        # 验证配置
        valid, error = self.validate_config()
        if not valid:
            return ExportResult(
                success=False,
                target=ExportTarget.OBSIDIAN,
                error_msg=error
            )

        # 构建输出路径
        assert self.vault_path is not None  # validated by validate_config()
        output_dir = self.vault_path / self.subfolder
        output_dir.mkdir(parents=True, exist_ok=True)

        # 安全化文件名
        safe_title = sanitize_filename(context.video_metadata.title)
        note_path = output_dir / f"{safe_title}.md"

        # 在 Vault 根目录创建 Attachments 文件夹（与笔记完全隔离）
        attachments_dir = self.vault_path / "Attachments" / safe_title
        attachments_dir.mkdir(parents=True, exist_ok=True)

        # 处理媒体文件：放入 Vault 根目录的 Attachments，优先使用符号链接
        video_filename = None
        audio_filename = None

        # 1. 处理视频文件（完整模式）- 视频已包含音频，不需要单独处理音频
        if context.video_path and context.video_path.exists():
            video_dest = attachments_dir / f"{safe_title}.mp4"
            # 清理可能存在的旧音频文件（避免之前版本残留的音频符号链接）
            audio_dest = attachments_dir / f"{safe_title}.m4a"
            if audio_dest.exists() or audio_dest.is_symlink():
                try:
                    audio_dest.unlink()
                    logger.info(f"清理旧音频文件: {audio_dest}")
                except (OSError, PermissionError) as e:
                    logger.warning(f"清理旧音频文件失败: {e}")

            # 尝试创建符号链接，失败则复制
            success, msg = safe_create_symlink(context.video_path, video_dest)
            if success:
                logger.info(msg)
                video_filename = f"Attachments/{safe_title}/{safe_title}.mp4"
            else:
                logger.warning(f"符号链接失败: {msg}，尝试复制")
                success, msg = safe_copy_file(context.video_path, video_dest)
                if success:
                    logger.info(msg)
                    video_filename = f"Attachments/{safe_title}/{safe_title}.mp4"
                else:
                    logger.error(f"复制视频失败: {msg}")
                    video_filename = context.video_path.name

        # 2. 只有在没有视频文件时，才处理音频文件（转录模式）
        # 注意：视频文件已经包含音频，不需要单独链接音频文件
        elif context.audio_path and context.audio_path.exists():
            audio_dest = attachments_dir / f"{safe_title}.m4a"
            # 尝试创建符号链接，失败则复制
            success, msg = safe_create_symlink(context.audio_path, audio_dest)
            if success:
                logger.info(msg)
                audio_filename = f"Attachments/{safe_title}/{safe_title}.m4a"
            else:
                logger.warning(f"符号链接失败: {msg}，尝试复制")
                success, msg = safe_copy_file(context.audio_path, audio_dest)
                if success:
                    logger.info(msg)
                    audio_filename = f"Attachments/{safe_title}/{safe_title}.m4a"
                else:
                    logger.error(f"复制音频失败: {msg}")

        # 生成 Markdown 内容
        content = self._generate_note(context, video_filename, audio_filename)

        # 写入文件
        note_path.write_text(content, encoding="utf-8")

        return ExportResult(
            success=True,
            target=ExportTarget.OBSIDIAN,
            output_path=note_path,
            metadata={
                "vault_path": str(self.vault_path),
                "subfolder": self.subfolder,
                "video_copied": video_filename is not None
            }
        )

    def _get_video_filename(self, context: ExportContext) -> str:
        """获取视频文件名（用于时间戳链接）"""
        if context.video_path:
            return context.video_path.name
        # 如果没有本地视频，使用标题作为占位
        return f"{sanitize_filename(context.video_metadata.title)}.mp4"

    def _generate_note(self, context: ExportContext, video_filename: str | None = None, audio_filename: str | None = None) -> str:
        """生成 Obsidian Markdown 笔记（包含可点击时间戳）"""
        meta = context.video_metadata
        now = datetime.now()

        # 判断模式：完整模式有 AI 摘要，转录模式没有
        is_full_mode = context.ai_summary is not None

        # YAML Frontmatter
        frontmatter = f"""---
title: {meta.title}
source: {meta.url}
date: {now.strftime('%Y-%m-%d')}
time: {now.strftime('%H:%M')}
author: {meta.author}
duration: {meta.duration // 60}分{meta.duration % 60}秒
platform: {meta.platform}
tags:
  - 视频笔记
  - {meta.platform}
---

# {meta.title}

"""

        # 根据模式生成不同内容
        if is_full_mode:
            # 完整模式：有 AI 摘要和 highlights
            body = f"""> **一句话总结**: {context.ai_summary}

## 视频信息
- **作者**: {meta.author}
- **时长**: {meta.duration // 60}分{meta.duration % 60}秒
- **链接**: [{meta.platform}]({meta.url})

## AI 提炼关键时间轴

{self._format_highlights(context, video_filename)}

> 💡 **提示**: 安装 [Media Extended](obsidian://show-plugin?id=media-extended) 插件后，点击时间戳可直接跳转播放

## 完整转录

<details>
<summary>点击展开完整转录内容</summary>

```
{context.transcript_text or "暂无转录内容"}
```

</details>
"""
        else:
            # 转录模式：没有 AI 摘要，显示转录时间轴
            body = f"""> **转录存档模式** - 仅包含语音转录文本

## 视频信息
- **作者**: {meta.author}
- **时长**: {meta.duration // 60}分{meta.duration % 60}秒
- **链接**: [{meta.platform}]({meta.url})

{self._format_highlights(context, video_filename)}

## 完整转录

<details>
<summary>点击展开完整转录内容</summary>

```
{context.transcript_text or "暂无转录内容"}
```

</details>
"""

        # 添加附件信息（如果有）
        attachments_section = "\n## 本地附件\n\n"
        if video_filename:
            attachments_section += f"- 视频: `[[{video_filename}]]`\n"
        if audio_filename:
            attachments_section += f"- 音频: `[[{audio_filename}]]`\n"
        if not video_filename and not audio_filename:
            attachments_section = ""

        footer = f"""

---

*由 [[VideoMind Bridge]] 自动生成于 {now.strftime('%Y-%m-%d %H:%M')}*
"""

        return frontmatter + body + attachments_section + footer

    def _format_highlights(self, context: ExportContext, video_filename: str | None = None) -> str:
        """格式化时间轴要点为可点击链接"""
        # 从 context 获取 highlights（需要确保 ExportContext 包含 highlights）
        highlights = self._extract_highlights_from_context(context)

        lines = []

        # 转录模式：没有 highlights，显示转录文本的前几个段落作为时间轴
        if not highlights:
            if context.transcript_segments:
                lines.append("### 转录时间轴")
                lines.append("")
                # 显示前 10 个转录段落作为时间轴
                for i, segment in enumerate(context.transcript_segments[:10]):
                    time_str = format_time_for_media_extended(int(segment.start))
                    # 转录模式没有本地视频，链接到线上 URL
                    video_url = context.video_metadata.url
                    link = f"[{segment.start:.0f}]({video_url}?t={int(segment.start)})"
                    # 截取前 100 个字符作为摘要
                    text_preview = segment.text[:100] + "..." if len(segment.text) > 100 else segment.text
                    lines.append(f"- {link} - {text_preview}")
                if len(context.transcript_segments) > 10:
                    lines.append(f"- ... 还有 {len(context.transcript_segments) - 10} 个段落")
                lines.append("")
                lines.append("> 💡 **提示**: 点击时间戳在浏览器中打开在线视频")
            else:
                lines.append("- 暂无转录数据")
            return "\n".join(lines)

        # 完整模式：有 highlights，使用本地视频或线上链接
        if context.video_path and video_filename:
            # 有本地视频: 使用 Media Extended 插件格式
            # 添加视频嵌入（使用 Attachments/ 子目录路径）
            lines.append(f"![[{video_filename}]]")
            lines.append("")

            # 添加时间轴链接
            for h in highlights:
                time_str = format_time_for_media_extended(h.seconds)
                link = f"[[{video_filename}#t={time_str}|{h.time}]]"
                lines.append(f"- {link} - {h.content}")
            lines.append("")
            lines.append("> 💡 **提示**: 安装 [[Media Extended]] 插件后，点击时间戳可直接跳转到视频对应位置")
            lines.append(f"> 视频文件位置：`{context.video_path}`")
        else:
            # 无本地视频: 链接到线上 URL
            video_url = context.video_metadata.url
            for h in highlights:
                link = f"[{h.time}]({video_url}?t={h.seconds})"
                lines.append(f"- {link} - {h.content}")
            lines.append("")
            lines.append("> 💡 **提示**: 点击时间戳在浏览器中打开在线视频")

        return "\n".join(lines)

    def _extract_highlights_from_context(self, context: ExportContext) -> list[Highlight]:
        """从 ExportContext 提取时间轴数据"""
        # 使用共享工具函数
        return extract_highlights_from_context(context.config)


# 测试代码
if __name__ == "__main__":
    from pathlib import Path
    from uuid import uuid4

    from ..models.task import ExportContext, VideoMetadata
    from ..services.ai_service import Highlight

    # 创建测试上下文
    context = ExportContext(
        task_id=uuid4(),
        video_metadata=VideoMetadata(
            title="Obsidian 测试视频",
            author="测试作者",
            duration=300,
            platform="bilibili",
            url="https://test.com/obsidian"
        ),
        video_path=Path("./test_video.mp4"),
        transcript_text="测试转录内容",
        ai_summary="这是测试视频的一句话总结。",
        config={
            "highlights": [
                {"time": "00:01:30", "seconds": 90, "content": "介绍知识管理的核心理念"},
                {"time": "00:03:45", "seconds": 225, "content": "演示如何建立双向链接"},
                {"time": "00:05:20", "seconds": 320, "content": "讲解标签系统的使用方法"},
            ]
        }
    )

    # 注意：需要提供有效的 Vault 路径才能测试
    # exporter = ObsidianExporter(vault_path=Path("~/Documents/Obsidian").expanduser())
    # result = exporter.export(context)
    # print(result)

    print("ObsidianExporter 已定义，需要提供 Vault 路径进行测试")
    print("\n生成的 Markdown 示例：")
    exporter = ObsidianExporter(vault_path=Path("/tmp/test_vault"))
    md_content = exporter._generate_note(context, "test_video.mp4")
    print(md_content[:1500] + "...")
