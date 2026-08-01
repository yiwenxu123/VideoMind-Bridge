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
import json
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from src.models.task import ExportContext, ExportTarget, Highlight, ProcessingMode, VideoMetadata
from src.services.ai_service import AIService
from src.services.download_service import DownloadService
from src.services.export_orchestrator import ExportOrchestrator
from src.services.transcribe_service import TranscribeService
from src.utils.media_utils import generate_srt

console = Console()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
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

    parser.add_argument("url", nargs="?", help="视频链接")
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
    parser.add_argument(
        "--obsidian-subfolder",
        default="Inbox/Videos",
        help="Obsidian 子文件夹 (默认: Inbox/Videos)"
    )
    parser.add_argument(
        "--archive",
        default=None,
        help="提取即归档目标，逗号分隔 (可选: obsidian,local,html_player)。示例: --archive obsidian,local"
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
    parser.add_argument(
        "--stdin",
        action="store_true",
        default=False,
        help="从 stdin 读取 URL（每行一个），支持管道"
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        default=False,
        help="以 JSON 格式输出结果（适合 Agent/脚本调用）"
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default=None,
        help="将结果写入文件而非 stdout"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="整体超时时间（秒，默认 600）"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="静默模式，仅输出最终结果"
    )
    parser.add_argument(
        "--cookie-browser",
        default=None,
        choices=["chrome", "safari", "firefox", "edge", "brave"],
        help="从浏览器读取 cookies（国内平台如抖音/小红书需要）"
    )

    # === v2 新参数 ===
    parser.add_argument(
        "--prescreen", "-p",
        action="store_true",
        default=False,
        help="启用内容预筛 (评估内容价值后决策)"
    )
    parser.add_argument(
        "--smart", "-s",
        action="store_true",
        default=False,
        help="智能模式: 预筛 + 成本感知提取 (等价于 --prescreen --cost-tier free)"
    )
    parser.add_argument(
        "--prescreen-only",
        action="store_true",
        default=False,
        help="仅预筛, 不提取内容"
    )
    parser.add_argument(
        "--cost-tier",
        default=None,
        choices=["free", "cheap", "paid", "expensive", "premium"],
        help="最大可接受提取成本等级 (默认: 不限)"
    )
    parser.add_argument(
        "--list-extractors",
        action="store_true",
        default=False,
        help="列出可用提取器及其状态"
    )
    parser.add_argument(
        "--config-list",
        action="store_true",
        default=False,
        help="列出所有提取器 API Key 的配置状态"
    )
    parser.add_argument(
        "--config-set",
        nargs=2,
        metavar=("KEY", "VALUE"),
        default=None,
        help="设置提取器 API Key (KEY: coze / tikhub / apify / aliyun_access_key_id / aliyun_access_key_secret / aliyun_appkey)"
    )

    return parser.parse_args(argv)


def run_v2_extraction(args: argparse.Namespace) -> int:
    """运行 v2 提取引擎 (prescreen/extract/router)"""
    import logging

    from src.core import ContentRouter, HermesFormatter, Prescreener
    from src.core.models import ContentGrade, CostTier, ExtractResult

    # quiet 模式: 抑制 HTTP 和路由器日志
    if args.quiet or args.json_output:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("src.core.router").setLevel(logging.WARNING)

    router = ContentRouter()
    prescreener = Prescreener(router)
    url = args.url
    use_json = args.json_output

    # --list-extractors 模式
    if args.list_extractors:
        extractors = router.list_extractors()
        if use_json:
            print(json.dumps(extractors, ensure_ascii=False, indent=2))
        else:
            for name, avail in extractors.items():
                icon = "[green]✓[/green]" if avail else "[red]✗[/red]"
                console.print(f"  {icon} {name}: {'可用' if avail else '不可用'}")
        return 0

    if not url:
        console.print("[red]错误: 需要提供 URL[/red]")
        return 1

    # 解析成本等级
    cost_map = {
        "free": CostTier.FREE, "cheap": CostTier.CHEAP,
        "paid": CostTier.PAID, "expensive": CostTier.EXPENSIVE,
        "premium": CostTier.PREMIUM,
    }
    max_cost = cost_map.get(args.cost_tier) if args.cost_tier else None

    # --prescreen-only: 仅预筛 (快速模式, 无网络)
    if args.prescreen_only:
        ps_result = prescreener.prescreen_quick(url)
        cost_grade = ps_result.effective_cost_grade()
        if use_json:
            print(json.dumps({
                "url": ps_result.url,
                "platform": ps_result.platform,
                "grade": ps_result.grade.value,
                "cost_grade": cost_grade.value,
                "score": ps_result.score,
                "reasons": ps_result.reasons,
                "recommended_cost_tier": ps_result.recommended_cost_tier.value if ps_result.recommended_cost_tier else None,
                "skip_reason": ps_result.skip_reason,
                "note": "快速预筛 — 执行 --prescreen 获取完整评分",
            }, ensure_ascii=False, indent=2))
        else:
            grade_color = {"S": "green", "A": "cyan", "B": "yellow", "C": "red", "D": "dim"}
            color = grade_color.get(cost_grade.value, "white")
            console.print(f"  [bold]预筛(成本):[/bold] [{color}]{cost_grade.value} 级[/{color}] "
                          f"(基本面 {ps_result.grade.value} 级)")
            console.print(f"  平台: {ps_result.platform}")
            if ps_result.recommended_cost_tier:
                console.print(f"  推荐成本: {ps_result.recommended_cost_tier.value}")
            if ps_result.skip_reason:
                console.print(f"  [yellow]⚠ {ps_result.skip_reason}[/yellow]")
            if ps_result.platform == "unknown":
                console.print("  [yellow]⚠ 未识别的平台 — 可能无法正常提取内容[/yellow]")
            for reason in ps_result.reasons:
                console.print(f"  [dim]• {reason}[/dim]")
            console.print("\n  [dim]提示: 执行 \"--smart\" 获取完整评分+提取[/dim]")
        return 0

    # --prescreen 或 --smart: 先提取获取元信息, 再用元信息评分
    prescreen_meta = None
    if args.prescreen or args.smart:
        if not use_json:
            console.print("[cyan]获取元信息...[/cyan]")

        # --smart 模式: 先用最小成本获取元信息做预筛决策
        if args.smart:
            quick_result = router.extract(url, max_cost=CostTier.FREE)
            if quick_result.success and quick_result.title:
                prescreen_result = prescreener.prescreen(
                    url,
                    title=quick_result.title,
                    duration_seconds=quick_result.duration_seconds,
                )
            else:
                prescreen_result = prescreener.prescreen_quick(url)

            cost_grade = prescreen_result.effective_cost_grade()
            is_worth = prescreener.is_extraction_worthwhile(cost_grade, ContentGrade.C)
            prescreen_meta = {
                "url": prescreen_result.url,
                "platform": prescreen_result.platform,
                "title": prescreen_result.title,
                "duration_seconds": prescreen_result.duration_seconds,
                "grade": prescreen_result.grade.value,
                "cost_grade": cost_grade.value,
                "score": prescreen_result.score,
                "reasons": prescreen_result.reasons,
                "recommended_cost_tier": prescreen_result.recommended_cost_tier.value if prescreen_result.recommended_cost_tier else None,
                "extraction_recommended": is_worth,
                "extraction_skipped": False,
                "extract_result": quick_result,  # 缓存提取结果, 避免重复提取
            }

            if not use_json:
                grade_color = {"S": "green", "A": "cyan", "B": "yellow", "C": "red", "D": "dim"}
                color = grade_color.get(cost_grade.value, "white")
                console.print(f"  [bold]预筛(成本):[/bold] [{color}]{cost_grade.value} 级[/{color}] "
                              f"(基本面 {prescreen_result.grade.value} 级, {prescreen_result.score:.0f}/100)")
                for reason in (prescreen_result.reasons[:3] + prescreen_result.metadata.get("cost_reasons", [])[:3]):
                    console.print(f"  [dim]• {reason}[/dim]")

            # 跳过不通过视频
            if not is_worth:
                prescreen_meta["extraction_skipped"] = True
                prescreen_meta["skip_reason"] = (
                    prescreen_result.skip_reason
                    or f"成本分级 {cost_grade.value} 级, 低于提取阈值 C 级"
                )
                # extract_result 是 ExtractResult 对象, 需转 dict 或移除
                prescreen_meta.pop("extract_result", None)
                if use_json:
                    print(json.dumps(prescreen_meta, ensure_ascii=False, indent=2))
                else:
                    console.print(f"[yellow]⏭ 跳过提取: 成本分级 {cost_grade.value} 级低于 C 级阈值[/yellow]")
                    console.print(f"  [dim]{prescreen_meta['skip_reason']}[/dim]")
                    console.print("  [dim]提示: 使用 --prescreen 强制提取（跳过预筛判断）[/dim]")
                return 0

            # 推荐提取成本 (来自成本分级决策)
            if max_cost is None and prescreen_result.recommended_cost_tier is not None:
                max_cost = prescreen_result.recommended_cost_tier
                if not use_json:
                    console.print(f"  推荐成本: [cyan]{max_cost.value}[/cyan]")
        else:
            # --prescreen 模式: 提取一次, 用提取结果做预筛评分
            max_cost_info = max_cost or CostTier.CHEAP
            prescreen_extract = router.extract(url, max_cost=max_cost_info)
            prescreen_result = prescreener.prescreen(
                url,
                title=prescreen_extract.title if prescreen_extract.success else "",
                duration_seconds=prescreen_extract.duration_seconds if prescreen_extract.success else 0.0,
            )

            cost_grade = prescreen_result.effective_cost_grade()
            prescreen_meta = {
                "url": prescreen_result.url,
                "platform": prescreen_result.platform,
                "title": prescreen_result.title,
                "duration_seconds": prescreen_result.duration_seconds,
                "grade": prescreen_result.grade.value,
                "cost_grade": cost_grade.value,
                "score": prescreen_result.score,
                "reasons": prescreen_result.reasons,
                "recommended_cost_tier": prescreen_result.recommended_cost_tier.value if prescreen_result.recommended_cost_tier else None,
                "skip_reason": prescreen_result.skip_reason,
                "extraction_recommended": True,
            }

            # 仅真成功 (有真实内容) 才复用提取结果, 避免失败/占位结果被二次使用
            if (
                prescreen_extract.success
                and prescreen_extract.content.strip()
                and not prescreen_extract.is_placeholder
            ):
                prescreen_meta["extract_result"] = prescreen_extract

            if not use_json:
                grade_color = {"S": "green", "A": "cyan", "B": "yellow", "C": "red", "D": "dim"}
                color = grade_color.get(cost_grade.value, "white")
                console.print(f"  [bold]预筛(成本):[/bold] [{color}]{cost_grade.value} 级[/{color}] "
                              f"(基本面 {prescreen_result.grade.value} 级, {prescreen_result.score:.0f}/100)")
                for reason in (prescreen_result.reasons[:3] + prescreen_result.metadata.get("cost_reasons", [])[:3]):
                    console.print(f"  [dim]• {reason}[/dim]")

    # 提取内容 (复用 --prescreen 的结果, 避免重复提取)
    result: ExtractResult
    if prescreen_meta and "extract_result" in prescreen_meta:
        result = prescreen_meta.pop("extract_result")  # type: ignore
    else:
        if not use_json:
            console.print(f"\n[cyan]提取中 ({'成本上限: ' + max_cost.value if max_cost else '无限'} )...[/cyan]")
        result = router.extract(url, max_cost=max_cost)

    # 输出
    if use_json:
        output = HermesFormatter.format_extract_result_full(result)
        if prescreen_meta:
            output["prescreen"] = prescreen_meta
        if args.archive and result.success and result.content.strip():
            from src.core.archiver import ArchiverConfig, archive_extract_result
            archive_targets = [t.strip() for t in args.archive.split(",") if t.strip()]
            archiver_config = ArchiverConfig(
                obsidian_vault_path=Path(args.obsidian_vault) if args.obsidian_vault else None,
                obsidian_subfolder=args.obsidian_subfolder,
                local_output_path=Path(args.output_dir),
            )
            archive_results = archive_extract_result(result, archive_targets, archiver_config)
            output["archive"] = [
                {
                    "success": r.success,
                    "target": r.target.value,
                    "output_path": str(r.output_path) if r.output_path else None,
                    "error": r.error_msg,
                }
                for r in archive_results
            ]
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        if result.success:
            grade_info = ""
            if prescreen_meta:
                grade = str(prescreen_meta.get('grade', 'C'))
                grade_info = f" ({grade}级)"
            console.print(f"[green]✓ 提取成功[/green]{grade_info} ({result.source})")
            console.print(f"  标题: {result.title}")
            console.print(f"  平台: {result.platform}")
            console.print(f"  成本: {result.cost_tier.value}")
            if result.language:
                console.print(f"  语言: {result.language}")
            if result.duration_seconds:
                console.print(f"  时长: {format_duration(result.duration_seconds)}")
            preview = result.content[:200] + "..." if len(result.content) > 200 else result.content
            console.print(f"\n[dim]{preview}[/dim]")

            if args.archive and result.content.strip():
                from src.core.archiver import ArchiverConfig, archive_extract_result
                archive_targets = [t.strip() for t in args.archive.split(",") if t.strip()]
                archiver_config = ArchiverConfig(
                    obsidian_vault_path=Path(args.obsidian_vault) if args.obsidian_vault else None,
                    obsidian_subfolder=args.obsidian_subfolder,
                    local_output_path=Path(args.output_dir),
                )
                console.print("\n[cyan]归档中...[/cyan]")
                for r in archive_extract_result(result, archive_targets, archiver_config):
                    if r.success:
                        console.print(f"  [green]✓[/green] {r.target.value}: {r.output_path}")
                    else:
                        console.print(f"  [red]✗[/red] {r.target.value}: {r.error_msg}")
        else:
            console.print(f"[red]✗ 提取失败: {result.error}[/red]")
            return 1

    return 0


def parse_targets(targets_str: str) -> list[ExportTarget]:
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


def _build_json_result(
    success: bool,
    url: str,
    mode: str,
    metadata: VideoMetadata | None = None,
    video_path: Path | None = None,
    audio_path: Path | None = None,
    transcript_result: Any | None = None,
    summary_result: Any | None = None,
    highlights: list[Highlight] | None = None,
    export_results: list | None = None,
    elapsed: float = 0.0,
    error: str | None = None,
    error_step: str | None = None,
) -> dict[str, Any]:
    """构建 JSON 输出结果"""
    result: dict[str, Any] = {
        "success": success,
        "url": url,
        "mode": mode,
        "elapsed_seconds": round(elapsed, 2),
    }

    if error:
        result["error"] = error
        result["error_step"] = error_step

    if metadata:
        result["metadata"] = {
            "title": metadata.title,
            "author": metadata.author,
            "duration": metadata.duration,
            "platform": metadata.platform,
            "url": metadata.url,
            "thumbnail_url": metadata.thumbnail_url,
            "description": metadata.description,
        }

    if video_path:
        result["video_path"] = str(video_path)
    if audio_path:
        result["audio_path"] = str(audio_path)

    if transcript_result:
        result["transcript"] = {
            "language": transcript_result.language,
            "language_probability": round(transcript_result.language_probability, 4),
            "segments_count": len(transcript_result.segments),
            "full_text": transcript_result.full_text,
            "formatted_text": transcript_result.formatted_text,
            "segments": [
                {
                    "start": round(s.start, 2),
                    "end": round(s.end, 2),
                    "text": s.text,
                    "confidence": round(s.confidence, 4) if s.confidence else None,
                }
                for s in transcript_result.segments
            ],
        }

    if summary_result:
        result["summary"] = {
            "text": summary_result.summary,
            "highlights": [
                {"time": h.time, "seconds": h.seconds, "content": h.content}
                for h in (highlights or [])
            ],
        }

    if export_results:
        result["exports"] = []
        for r in export_results:
            export_info: dict[str, Any] = {
                "target": r.target.value,
                "success": r.success,
            }
            if r.output_path:
                export_info["output_path"] = str(r.output_path)
            if r.error_msg:
                export_info["error"] = r.error_msg
            if r.metadata.get("files"):
                export_info["files"] = r.metadata["files"]
            result["exports"].append(export_info)

    return result


def _run_config_list(args: argparse.Namespace) -> int:
    """列出所有提取器 API Key 的配置状态"""
    from src.services.config_manager import ConfigManager
    config_mgr = ConfigManager()
    status = config_mgr.list_extractor_key_status()
    use_json = args.json_output
    if use_json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0
    console.print("\n[bold cyan]提取器 API Key 配置状态[/bold cyan]")
    for group_name, group in status.items():
        configured = group["all_configured"]
        icon = "[green]✓[/green]" if configured else "[red]✗[/red]"
        console.print(f"  {icon} [bold]{group['label']}[/bold] ({group_name})")
        for key in group["keys"]:
            status_icon = "[green]✓[/green]" if key["configured"] else "[yellow]−[/yellow]"
            console.print(f"    {status_icon} {key['label']} ({key['env']})")
    console.print()
    return 0


def _run_config_set(key: str, value: str, json_output: bool = False) -> int:
    """设置提取器 API Key"""
    from src.services.config_manager import ConfigManager
    config_mgr = ConfigManager()
    valid_names = set(config_mgr.EXTRACTOR_PROVIDERS.keys())
    if key not in valid_names:
        msg = f"未知配置键: {key}。有效键名: {', '.join(sorted(valid_names))}"
        if json_output:
            print(json.dumps({"success": False, "error": msg}, ensure_ascii=False))
        else:
            console.print(f"[red]错误:[/red] {msg}")
        return 1
    ok = config_mgr.set_extractor_key(key, value)
    if not ok:
        msg = f"设置失败: {key}"
        if json_output:
            print(json.dumps({"success": False, "error": msg}, ensure_ascii=False))
        else:
            console.print(f"[red]错误:[/red] {msg}")
        return 1
    if json_output:
        print(json.dumps({"success": True, "key": key}, ensure_ascii=False))
    else:
        console.print(f"[green]✓[/green] {key} 已设置")
    return 0


def main() -> int:
    """主入口"""
    args = parse_args()
    start_time = time.time()

    # 配置管理 (不依赖 URL)
    if args.config_list:
        return _run_config_list(args)
    if args.config_set:
        return _run_config_set(*args.config_set, json_output=args.json_output)

    # v2 提取引擎为默认路径 (成本感知路由, 无需下载/转录, Agent 友好):
    # 仅当显式请求 v1 专属参数时才走旧版 下载→转录→摘要 流程
    v1_requested = (
        args.mode != "full"
        or args.model != "small"
        or args.targets != "local"
        or args.output_dir != str(Path.home() / "Downloads" / "VideoMind")
        or not args.keep_video
        or args.video_quality != "best"
        or args.mock
    )
    if (
        args.prescreen or args.smart or args.prescreen_only
        or args.cost_tier or args.list_extractors
        or not v1_requested
    ):
        return run_v2_extraction(args)

    # stdin 模式：每行一个 URL，JSONL 批量输出
    if args.stdin:
        urls = [line.strip() for line in sys.stdin if line.strip()]
        has_error = False
        for url in urls:
            import copy
            a = copy.copy(args)
            a.url = url
            a.json_output = True
            a.quiet = True
            if _process_single(a, time.time()) != 0:
                has_error = True
        return 1 if has_error else 0

    return _process_single(args, start_time)


def _process_single(args: argparse.Namespace, start_time: float) -> int:
    """处理单个视频链接"""
    use_json = args.json_output
    use_quiet = args.quiet or use_json

    out_file = open(args.output_file, "a", encoding="utf-8") if args.output_file else None  # noqa: SIM115
    def _write_json(data: dict) -> None:
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if out_file:
            out_file.write(text + "\n")
        else:
            print(text)

    if not use_quiet:
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

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    targets = parse_targets(args.targets)
    processing_mode = {
        "full": ProcessingMode.FULL,
        "download": ProcessingMode.DOWNLOAD_ONLY,
        "transcribe": ProcessingMode.TRANSCRIBE_ONLY,
    }[args.mode]

    download_service = DownloadService(output_dir)
    transcribe_service = TranscribeService(model_size=args.model)
    ai_service = None
    if processing_mode == ProcessingMode.FULL and not args.mock:
        try:
            ai_service = AIService()
        except ValueError as e:
            if not use_quiet:
                console.print(f"[yellow]警告: {e}[/yellow]")
                console.print("[yellow]将使用 mock 模式继续...[/yellow]")
            ai_service = AIService(mock=True)
    elif args.mock:
        ai_service = AIService(mock=True)

    video_path: Path | None = None
    audio_path: Path | None = None
    metadata: VideoMetadata | None = None
    transcript_result = None
    summary_result = None
    highlights: list[Highlight] = []
    export_results_list: list = []

    if not use_quiet:
        progress_ctx: Any = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        )
    else:
        progress_ctx = _DummyProgress()

    with progress_ctx:
        try:
            result = download_service.download(
                args.url,
                download_video=args.keep_video,
                video_quality=args.video_quality,
                cookies_from_browser=args.cookie_browser,
            )
            video_path = result.video_path
            audio_path = result.audio_path
            metadata = result.metadata

            if not use_quiet:
                console.print(f"  [dim]标题: {metadata.title}[/dim]")
                console.print(f"  [dim]UP主: {metadata.author}[/dim]")
                console.print(f"  [dim]时长: {metadata.duration//60}分{metadata.duration%60}秒[/dim]")
                if video_path:
                    console.print(f"  [dim]视频: {video_path.name}[/dim]")
                console.print(f"  [dim]音频: {audio_path.name}[/dim]")
        except Exception as e:
            if use_json:
                _write_json(_build_json_result(
                    success=False, url=args.url, mode=args.mode,
                    error=str(e), error_step="download",
                    elapsed=time.time() - start_time,
                ))
            else:
                console.print(f"[red]✗ 下载失败: {e}[/red]")
            return 1

        if processing_mode == ProcessingMode.DOWNLOAD_ONLY:
            elapsed = time.time() - start_time
            if use_json:
                _write_json(_build_json_result(
                    success=True, url=args.url, mode=args.mode,
                    metadata=metadata, video_path=video_path, audio_path=audio_path,
                    elapsed=elapsed,
                ))
            else:
                console.print("\n[green]✓ 下载完成![/green]")
                if video_path:
                    console.print(f"  [dim]视频: {video_path}[/dim]")
                console.print(f"  [dim]音频: {audio_path}[/dim]")
            return 0

        try:
            transcript_result = transcribe_service.transcribe(
                audio_path,
                language="zh",
            )

            if not use_quiet:
                console.print(f"  [dim]语言: {transcript_result.language} ({transcript_result.language_probability:.0%})[/dim]")
                console.print(f"  [dim]片段: {len(transcript_result.segments)} 个[/dim]")
        except Exception as e:
            if use_json:
                _write_json(_build_json_result(
                    success=False, url=args.url, mode=args.mode,
                    metadata=metadata, video_path=video_path, audio_path=audio_path,
                    error=str(e), error_step="transcribe",
                    elapsed=time.time() - start_time,
                ))
            else:
                console.print(f"[red]✗ 转录失败: {e}[/red]")
            return 1

        if processing_mode == ProcessingMode.TRANSCRIBE_ONLY:
            srt_path = audio_path.with_suffix(".srt")
            srt_content = generate_srt(transcript_result.segments)
            srt_path.write_text(srt_content, encoding="utf-8")
            elapsed = time.time() - start_time
            if use_json:
                json_result = _build_json_result(
                    success=True, url=args.url, mode=args.mode,
                    metadata=metadata, audio_path=audio_path,
                    transcript_result=transcript_result,
                    elapsed=elapsed,
                )
                json_result["transcript"]["srt_path"] = str(srt_path)
                _write_json(json_result)
            else:
                console.print("\n[green]✓ 转录完成![/green]")
                console.print(f"  [dim]SRT: {srt_path}[/dim]")
            return 0

        if ai_service:
            try:
                summary_result = ai_service.summarize(
                    transcript=transcript_result.full_text,
                    title=metadata.title
                )
                highlights = summary_result.highlights
                if not use_quiet:
                    console.print(f"  [dim]总结: {summary_result.summary[:50]}...[/dim]")
                    console.print(f"  [dim]时间轴: {len(highlights)} 个要点[/dim]")
            except Exception as e:
                if not use_quiet:
                    console.print(f"[red]✗ AI 摘要失败: {e}[/red]")
                summary_result = None
                highlights = []
        else:
            summary_result = None
            highlights = []

    if not use_quiet:
        console.print("\n[cyan]导出到目标...[/cyan]")

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

    export_config = {
        "local_output_path": output_dir,
        "organize_by": "date",
        "obsidian_vault_path": Path(args.obsidian_vault) if args.obsidian_vault else None,
    }

    orchestrator = ExportOrchestrator(targets=targets, config=export_config)
    export_results_list = orchestrator.export_all(export_context)

    if not use_quiet:
        for export_result in export_results_list:
            if export_result.success:
                console.print(f"[green]✓ {export_result.target.value}:[/green] {export_result.output_path}")
                if export_result.metadata.get("files"):
                    console.print(f"  [dim]文件: {', '.join(export_result.metadata['files'])}[/dim]")
            else:
                console.print(f"[red]✗ {export_result.target.value}:[/red] {export_result.error_msg}")

    if video_path and highlights:
        try:
            from src.exporters.html_player_exporter import HTMLPlayerExporter
            html_exporter = HTMLPlayerExporter()
            html_result = html_exporter.export(export_context)
            if html_result.success and not use_quiet:
                console.print(f"[green]✓ HTML播放器:[/green] {html_result.output_path}")
            if html_result.success:
                export_results_list.append(html_result)
        except Exception as e:
            if not use_quiet:
                console.print(f"[yellow]⚠ HTML播放器生成失败: {e}[/yellow]")

    elapsed = time.time() - start_time

    if use_json:
        _write_json(_build_json_result(
            success=True, url=args.url, mode=args.mode,
            metadata=metadata, video_path=video_path, audio_path=audio_path,
            transcript_result=transcript_result,
            summary_result=summary_result, highlights=highlights,
            export_results=export_results_list,
            elapsed=elapsed,
        ))
    else:
        console.print(f"\n[bold green]✓ 完成![/bold green] 总耗时: {format_duration(elapsed)}")
        if highlights:
            console.print("\n[cyan]关键时间轴预览:[/cyan]")
            for _i, h in enumerate(highlights[:5], 1):
                console.print(f"  [{h.time}] {h.content[:40]}...")
            if len(highlights) > 5:
                console.print(f"  ... 还有 {len(highlights) - 5} 个要点")

    if out_file:
        out_file.close()
    return 0


class _DummyProgress:
    """静默模式下的空进度条替代"""

    def __enter__(self) -> "_DummyProgress":
        return self

    def __exit__(self, *args: Any) -> None:
        pass





if __name__ == "__main__":
    sys.exit(main())
