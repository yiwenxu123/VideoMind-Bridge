#!/usr/bin/env python3
"""
VideoMind Bridge - CLI 入口

使用示例 (使用 uv):
    uv run python -m src.cli "https://bilibili.com/video/BV1xx"          # 提取正文
    uv run python -m src.cli "https://bilibili.com/video/BV1xx" --smart  # 预筛 + 成本感知
    uv run python -m src.cli ~/Downloads/manual.mp4                       # 本地文件 → 转写
    uv run python -m src.cli --list-extractors                            # 能力发现

v1 流水线（下载 → 转录 → AI 摘要 → 导出）已于 2026-11-25（A2）移除；
本地文件只剩「转写」这一步，走 v2 的 ASR 降级链。
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

from src.models.task import ExportTarget, Highlight, VideoMetadata
from src.services.local_media import is_remote_url

console = Console()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="VideoMind Bridge - 多平台内容提取（v2 引擎）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  # 提取正文（B站/YouTube/抖音/小红书）
  %(prog)s "https://bilibili.com/video/BV1xx"

  # 智能模式（先预筛，再按成本感知提取）
  %(prog)s "https://bilibili.com/video/BV1xx" --smart

  # 本地文件（手动下载的视频）→ 走 ASR 降级链转写
  %(prog)s ~/Downloads/manual.mp4

  # 提取即归档
  %(prog)s "https://bilibili.com/video/BV1xx" --archive obsidian,local

  # 能力发现
  %(prog)s --list-extractors --list-asr
        """
    )

    parser.add_argument("url", nargs="?", help="视频链接")
    parser.add_argument(
        "--output-dir",
        default=str(Path.home() / "Downloads" / "VideoMind"),
        help="输出目录 (默认: ~/Downloads/VideoMind)"
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
        "--json",
        dest="json_output",
        action="store_true",
        default=False,
        help="以 JSON 格式输出结果（适合 Agent/脚本调用）"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="静默模式，仅输出最终结果"
    )
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
        "--asr",
        default=None,
        help="首选 ASR 后端（失败后继续默认链）: faster_whisper / dashscope / aliyun / sensevoice"
    )
    parser.add_argument(
        "--asr-chain",
        default=None,
        help="严格按此 ASR 链执行，逗号分隔（不追加默认后端）"
    )
    parser.add_argument(
        "--asr-language",
        default=None,
        help="ASR 语言提示（如 zh / en / auto）"
    )
    parser.add_argument(
        "--list-asr",
        action="store_true",
        default=False,
        help="列出可用 ASR 后端及其能力"
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
        help="设置提取器 API Key (KEY: tikhub / apify / aliyun_access_key_id / aliyun_access_key_secret / aliyun_appkey)"
    )

    return parser.parse_args(argv)


def run_v2_extraction(args: argparse.Namespace) -> int:
    """运行 v2 提取引擎 (prescreen/extract/router)"""
    import logging

    from src.core import ContentRouter, HermesFormatter, Prescreener
    from src.core.models import ContentGrade, CostTier, ExtractOptions, ExtractResult

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

    # --list-asr 模式
    if args.list_asr:
        from src.core.asr import available_transcribers

        caps = [c.to_dict() for c in available_transcribers()]
        if use_json:
            print(json.dumps(caps, ensure_ascii=False, indent=2))
        else:
            for cap in caps:
                icon = "[green]✓[/green]" if cap["available"] else "[red]✗[/red]"
                console.print(
                    f"  {icon} {cap['name']}: {'可用' if cap['available'] else '不可用'} "
                    f"(model={cap['model'] or '-'}, cost={cap['cost_tier']}, "
                    f"timestamps={'yes' if cap['timestamps'] else 'no'})"
                )
                if cap.get("notes") and not cap["available"]:
                    console.print(f"    [dim]{cap['notes']}[/dim]")
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

    # ASR 请求级覆盖（--asr / --asr-chain / --asr-language）
    asr_chain = None
    if args.asr_chain:
        from src.core.asr import validate_chain

        asr_chain = [name.strip() for name in args.asr_chain.split(",") if name.strip()]
        validate_chain(asr_chain)
    elif args.asr:
        from src.core.asr import validate_chain
        from src.services.config_manager import ConfigManager

        validate_chain([args.asr])
        default_chain = ConfigManager().get_asr_config().chain
        asr_chain = [args.asr] + [name for name in default_chain if name != args.asr]

    extract_options = (
        ExtractOptions(asr_chain=asr_chain, asr_language=args.asr_language)
        if (asr_chain or args.asr_language)
        else None
    )

    def _extract(target_url: str, **kwargs):
        if extract_options is not None:
            kwargs["options"] = extract_options
        return router.extract(target_url, **kwargs)

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

    # 校验默认 ASR 链，坏配置在提取前快速失败
    from src.core.asr import validate_configured_chain

    validate_configured_chain()

    # --prescreen 或 --smart: 先提取获取元信息, 再用元信息评分
    prescreen_meta = None
    if args.prescreen or args.smart:
        if not use_json:
            console.print("[cyan]获取元信息...[/cyan]")

        # --smart 模式: 先用最小成本获取元信息做预筛决策
        if args.smart:
            quick_result = _extract(url, max_cost=CostTier.FREE)
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
            prescreen_extract = _extract(url, max_cost=max_cost_info)
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
        result = prescreen_meta.pop("extract_result")
    else:
        if not use_json:
            console.print(f"\n[cyan]提取中 ({'成本上限: ' + max_cost.value if max_cost else '无限'} )...[/cyan]")
        result = _extract(url, max_cost=max_cost)

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
    """主入口

    A2（2026-11-25）后只有三种行为：配置管理、能力发现、提取（远程 URL 或本地文件）。
    不带参数直接打印用法并以退出码 2 结束 —— 不再有「隐式默认模式」。
    """
    args = parse_args()

    if args.config_list:
        return _run_config_list(args)
    if args.config_set:
        return _run_config_set(args.config_set[0], args.config_set[1], json_output=args.json_output)

    # 能力发现不需要 URL
    if args.list_extractors or args.list_asr:
        return run_v2_extraction(args)

    if not args.url:
        print(
            "用法: python -m src.cli <URL 或本地文件> [--smart|--prescreen|--archive ...]\n"
            "       python -m src.cli --list-extractors | --list-asr | --config-list\n"
            "提取远程链接用 URL；本地文件只会被转写（v1 的下载/AI 摘要已移除）。",
            file=sys.stderr,
        )
        return 2

    if not is_remote_url(args.url):
        return _run_local_asr(args)

    return run_v2_extraction(args)


def _run_local_asr(args: argparse.Namespace) -> int:
    """本地文件 → 只做转写（复用 v2 的 ASR 降级链）。

    存在的理由：有些平台（视频号等）拿不到直链，只能人先手动下载，再把语音变成文字。
    这是「转写」这一项能力的延续，不是 v1 流水线复活 —— 没有下载、没有 AI 摘要。
    """
    import tempfile

    from src.core.asr import MediaRef, TranscribeOptions, transcribe_with_chain
    from src.core.media import to_16k_mono_wav

    src = Path(args.url).expanduser()
    if not src.is_file():
        print(f"文件不存在: {src}", file=sys.stderr)
        return 2

    chain: list[str] | None = None
    if args.asr_chain:
        chain = [x.strip() for x in args.asr_chain.split(",") if x.strip()]
    elif args.asr:
        chain = [args.asr.strip()]

    try:
        with tempfile.TemporaryDirectory() as tmp:
            wav = to_16k_mono_wav(src, Path(tmp) / "audio.wav")
            transcript = transcribe_with_chain(
                MediaRef(path=wav),
                TranscribeOptions(language=args.asr_language),
                chain=chain,
            )
    except Exception as exc:  # noqa: BLE001 - CLI 边界，统一转成可读错误
        print(f"转写失败: {exc}", file=sys.stderr)
        return 1

    if args.json_output:
        print(json.dumps(
            {
                "success": bool(transcript.text.strip()),
                "source": "local_asr",
                "url": str(src),
                "platform": "local",
                "title": src.stem,
                "content": transcript.text,
                "language": transcript.language,
                "duration_seconds": transcript.duration_seconds,
                "method": "asr",
                "completeness": "full" if transcript.text.strip() else "none",
                "asr": {
                    "provider": transcript.provider,
                    "model": transcript.model,
                    "model_version": transcript.model_version,
                },
                "segments": transcript.segments,
            },
            ensure_ascii=False,
            indent=2,
        ))
    else:
        console.print(transcript.text)
    return 0 if transcript.text.strip() else 1


