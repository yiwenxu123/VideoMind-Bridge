#!/usr/bin/env python3
"""
VideoMind Bridge - CLI 入口

使用示例 (使用 uv):
    uv run python -m src.cli "https://bilibili.com/video/BV1xx" --mode full --model small
    uv run python -m src.cli "https://bilibili.com/video/BV1xx" --mode transcribe --model tiny
    uv run python -m src.cli "https://bilibili.com/video/BV1xx" --mock  # 测试模式

或使用虚拟环境:
    source .venv/bin/activate
    python -m src.cli "https://bilibili.com/video/BV1xx" --mode full
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.text import Text

# 处理导入路径（支持 python -m src.cli 和直接运行）
try:
    # 作为模块运行: python -m src.cli
    from src.models.task import ExportTarget, ProcessingMode, VideoMetadata, ExportContext
    from src.services.download_service import DownloadService
    from src.services.transcribe_service import TranscribeService
    from src.services.ai_service import AIService, Highlight
    from src.services.export_orchestrator import ExportOrchestrator
except ImportError:
    # 直接运行: python src/cli.py
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.models.task import ExportTarget, ProcessingMode, VideoMetadata, ExportContext
    from src.services.download_service import DownloadService
    from src.services.transcribe_service import TranscribeService
    from src.services.ai_service import AIService, Highlight
    from src.services.export_orchestrator import ExportOrchestrator


console = Console()


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="VideoMind Bridge - 视频知识处理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 完整处理（下载视频+音频、转录、AI摘要、导出）
  %(prog)s "https://bilibili.com/video/BV1xx" --mode full --model small

  # 仅转录（不下载视频，只下载音频）
  %(prog)s "https://bilibili.com/video/BV1xx" --mode transcribe --model tiny

  # 测试模式（使用模拟AI数据）
  %(prog)s "https://bilibili.com/video/BV1xx" --mock

  # 不保留视频（节省空间）
  %(prog)s "https://bilibili.com/video/BV1xx" --no-keep-video

  # 指定视频质量
  %(prog)s "https://bilibili.com/video/BV1xx" --video-quality 720p
        """
    )

    parser.add_argument("url", help="视频链接")
    parser.add_argument(
        "--mode",
        choices=["full", "download", "transcribe"],
        default="full",
        help="处理模式 (默认: full)"
    )
    parser.add_argument(
        "--model",
        choices=["tiny", "base", "small", "medium"],
        default="small",
        help="Whisper 模型大小 (默认: small)"
    )
    parser.add_argument(
        "--targets",
        default="local",
        help="导出目标，逗号分隔 (默认: local，可选: obsidian,local,notion)"
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path.home() / "Downloads" / "VideoMind"),
        help="输出目录 (默认: ~/Downloads/VideoMind)"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="测试模式 - 使用模拟数据，不调用真实 AI API"
    )
    parser.add_argument(
        "--obsidian-vault",
        default=None,
        help="Obsidian Vault 路径 (用于导出到 Obsidian)"
    )

    # 新增视频控制参数
    parser.add_argument(
        "--keep-video",
        dest="keep_video",
        action="store_true",
        default=True,
        help="保留视频文件 (默认: True)"
    )
    parser.add_argument(
        "--no-keep-video",
        dest="keep_video",
        action="store_false",
        help="不保留视频文件，仅下载音频 (节省空间)"
    )
    parser.add_argument(
        "--video-quality",
        default="best",
        choices=["best", "worst", "1080p", "720p", "480p"],
        help="视频质量 (默认: best，可选: worst/1080p/720p/480p)"
    )

    return parser.parse_args()


def parse_targets(targets_str: str) -> List[ExportTarget]:
    """解析导出目标字符串"""
    target_map = {
        "local": ExportTarget.LOCAL,
        "obsidian": ExportTarget.OBSIDIAN,
        "notion": ExportTarget.NOTION,
    }

    targets = []
    for t in targets_str.split(","):
        t = t.strip().lower()
        if t in target_map:
            targets.append(target_map[t])

    return targets if targets else [ExportTarget.LOCAL]


def format_duration(seconds: float) -> str:
    """格式化时长"""
    if seconds < 60:
        return f"{seconds:.0f}秒"
    elif seconds < 3600:
        return f"{seconds/60:.1f}分钟"
    else:
        return f"{seconds/3600:.1f}小时"


def main():
    """主入口"""
    args = parse_args()
    start_time = time.time()

    # 显示欢迎信息
    video_status = "保留视频" if args.keep_video else "仅音频"
    console.print(Panel.fit(
        "[bold cyan]VideoMind Bridge[/bold cyan] - 视频知识处理工具\n"
        f"模式: [green]{args.mode}[/green] | "
        f"模型: [green]{args.model}[/green] | "
        f"目标: [green]{args.targets}[/green] | "
        f"视频: [green]{video_status}[/green]",
        title="🎬",
        border_style="cyan"
    ))

    # 解析参数
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    targets = parse_targets(args.targets)
    processing_mode = {
        "full": ProcessingMode.FULL,
        "download": ProcessingMode.DOWNLOAD_ONLY,
        "transcribe": ProcessingMode.TRANSCRIBE_ONLY,
    }[args.mode]

    # 初始化服务
    download_service = DownloadService(output_dir)
    transcribe_service = TranscribeService(model_size=args.model)
    ai_service = None
    if processing_mode == ProcessingMode.FULL and not args.mock:
        try:
            ai_service = AIService()
        except ValueError as e:
            console.print(f"[yellow]警告: {e}[/yellow]")
            console.print("[yellow]将使用 mock 模式继续...[/yellow]")
            ai_service = AIService(mock=True)
    elif args.mock:
        ai_service = AIService(mock=True)

    # 存储结果供后续使用
    video_path: Optional[Path] = None
    audio_path: Optional[Path] = None
    metadata: Optional[VideoMetadata] = None
    transcript_result = None
    summary_result = None
    highlights: List[Highlight] = []

    # 创建进度显示
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:

        # ========== 步骤 1: 下载 ==========
        download_task = progress.add_task("[cyan]下载视频...", total=100)

        def download_callback(status: str, percent: float):
            progress.update(download_task, description=f"[cyan]{status}", completed=percent)

        try:
            result = download_service.download(
                args.url,
                download_video=args.keep_video,
                video_quality=args.video_quality,
                progress_callback=download_callback
            )
            video_path = result.video_path
            audio_path = result.audio_path
            metadata = result.metadata

            progress.update(download_task, description="[green]✓ 下载完成", completed=100)
            console.print(f"  [dim]标题: {metadata.title}[/dim]")
            console.print(f"  [dim]UP主: {metadata.author}[/dim]")
            console.print(f"  [dim]时长: {metadata.duration//60}分{metadata.duration%60}秒[/dim]")
            if video_path:
                console.print(f"  [dim]视频: {video_path.name}[/dim]")
            console.print(f"  [dim]音频: {audio_path.name}[/dim]")
        except Exception as e:
            console.print(f"[red]✗ 下载失败: {e}[/red]")
            return 1

        # 如果是仅下载模式，到此结束
        if processing_mode == ProcessingMode.DOWNLOAD_ONLY:
            console.print(f"\n[green]✓ 下载完成![/green]")
            if video_path:
                console.print(f"  [dim]视频: {video_path}[/dim]")
            console.print(f"  [dim]音频: {audio_path}[/dim]")
            return 0

        # ========== 步骤 2: 转录 ==========
        transcribe_task = progress.add_task("[cyan]语音转录...", total=100)

        def transcribe_callback(status: str, percent: float):
            progress.update(transcribe_task, description=f"[cyan]{status}", completed=percent)

        try:
            transcript_result = transcribe_service.transcribe(
                audio_path,
                language="zh",
                progress_callback=transcribe_callback
            )

            progress.update(transcribe_task, description="[green]✓ 转录完成", completed=100)
            console.print(f"  [dim]语言: {transcript_result.language} ({transcript_result.language_probability:.0%})[/dim]")
            console.print(f"  [dim]片段: {len(transcript_result.segments)} 个[/dim]")
        except Exception as e:
            console.print(f"[red]✗ 转录失败: {e}[/red]")
            return 1

        # 如果是仅转录模式，保存 SRT 并结束
        if processing_mode == ProcessingMode.TRANSCRIBE_ONLY:
            srt_path = audio_path.with_suffix(".srt")
            srt_content = generate_srt(transcript_result.segments)
            srt_path.write_text(srt_content, encoding="utf-8")
            console.print(f"\n[green]✓ 转录完成![/green]")
            console.print(f"  [dim]SRT: {srt_path}[/dim]")
            return 0

        # ========== 步骤 3: AI 摘要 ==========
        if ai_service:
            ai_task = progress.add_task("[cyan]AI 生成摘要...", total=100)
            progress.update(ai_task, completed=50)

            try:
                summary_result = ai_service.summarize(
                    transcript=transcript_result.full_text,
                    title=metadata.title
                )
                highlights = summary_result.highlights
                progress.update(ai_task, description="[green]✓ AI 摘要完成", completed=100)
                console.print(f"  [dim]总结: {summary_result.summary[:50]}...[/dim]")
                console.print(f"  [dim]时间轴: {len(highlights)} 个要点[/dim]")
            except Exception as e:
                console.print(f"[red]✗ AI 摘要失败: {e}[/red]")
                summary_result = None
                highlights = []
        else:
            summary_result = None
            highlights = []

    # ========== 步骤 4: 导出 ==========
    console.print("\n[cyan]导出到目标...[/cyan]")

    # 构建导出上下文
    export_context = ExportContext(
        task_id=uuid4(),
        video_metadata=metadata,
        video_path=video_path,
        audio_path=audio_path,
        transcript_segments=transcript_result.segments,
        transcript_text=transcript_result.formatted_text,
        ai_summary=summary_result.summary if summary_result else None,
        config={
            "highlights": [{"time": h.time, "seconds": h.seconds, "content": h.content} for h in highlights]
        }
    )

    # 配置
    export_config = {
        "local_output_path": output_dir,
        "organize_by": "date",
        "obsidian_vault_path": Path(args.obsidian_vault) if args.obsidian_vault else None,
    }

    # 执行导出
    orchestrator = ExportOrchestrator(targets=targets, config=export_config)
    export_results = orchestrator.export_all(export_context)

    # 显示导出结果
    for result in export_results:
        if result.success:
            console.print(f"[green]✓ {result.target.value}:[/green] {result.output_path}")
            if result.metadata.get("files"):
                console.print(f"  [dim]文件: {', '.join(result.metadata['files'])}[/dim]")
        else:
            console.print(f"[red]✗ {result.target.value}:[/red] {result.error_msg}")

    # 生成 HTML 播放器（如果保留视频）
    if video_path and highlights:
        try:
            from src.exporters.html_player_exporter import HTMLPlayerExporter
            html_exporter = HTMLPlayerExporter()
            html_result = html_exporter.export(export_context)
            if html_result.success:
                console.print(f"[green]✓ HTML播放器:[/green] {html_result.output_path}")
        except Exception as e:
            console.print(f"[yellow]⚠ HTML播放器生成失败: {e}[/yellow]")

    # ========== 完成 ==========
    elapsed = time.time() - start_time
    console.print(f"\n[bold green]✓ 完成![/bold green] 总耗时: {format_duration(elapsed)}")

    # 显示时间轴预览
    if highlights:
        console.print(f"\n[cyan]关键时间轴预览:[/cyan]")
        for i, h in enumerate(highlights[:5], 1):
            console.print(f"  [{h.time}] {h.content[:40]}...")
        if len(highlights) > 5:
            console.print(f"  ... 还有 {len(highlights) - 5} 个要点")

    return 0


def generate_srt(segments: list) -> str:
    """生成 SRT 字幕格式"""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = format_srt_time(seg.start)
        end = format_srt_time(seg.end)
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(seg.text)
        lines.append("")
    return "\n".join(lines)


def format_srt_time(seconds: float) -> str:
    """格式化为 SRT 时间格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


if __name__ == "__main__":
    sys.exit(main())
