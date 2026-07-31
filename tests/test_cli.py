"""CLI 模块测试 — 参数解析和纯逻辑函数

只测试 argparse 解析和辅助函数, 不运行 CLI 主流程。
"""


import pytest

from src.cli import format_duration, parse_args, parse_targets
from src.models.task import ExportTarget

# ============================================================
# 参数解析测试
# ============================================================


def test_parse_args_defaults():
    """测试默认值"""
    print("\n=== 测试 parse_args 默认值 ===")

    args = parse_args([])

    assert args.url is None
    assert args.mode == "full"
    assert args.model == "small"
    assert args.targets == "local"
    assert args.mock is False
    assert args.json_output is False
    assert args.quiet is False
    assert args.keep_video is True
    assert args.video_quality == "best"
    assert args.prescreen is False
    assert args.smart is False
    assert args.prescreen_only is False
    assert args.cost_tier is None
    assert args.list_extractors is False
    assert args.config_list is False
    assert args.config_set is None
    assert args.timeout == 600
    assert args.cookie_browser is None
    assert args.stdin is False

    print("  ✓ 所有默认值正确")


def test_parse_args_url():
    """测试 URL 参数"""
    print("\n=== 测试 URL 参数 ===")

    args = parse_args(["https://bilibili.com/video/BV1xx"])
    assert args.url == "https://bilibili.com/video/BV1xx"
    print(f"  ✓ URL: {args.url}")


def test_parse_args_mode():
    """测试 --mode 参数"""
    print("\n=== 测试 --mode 参数 ===")

    for mode in ("full", "download", "transcribe"):
        args = parse_args(["--mode", mode])
        assert args.mode == mode, f"期望 {mode}, 实际 {args.mode}"
        print(f"  ✓ --mode {mode}")

    # 默认应为 full
    args = parse_args([])
    assert args.mode == "full"
    print("  ✓ 默认 mode=full")


def test_parse_args_invalid_mode():
    """测试无效的 --mode 值"""
    print("\n=== 测试无效 --mode ===")

    with pytest.raises(SystemExit):
        parse_args(["--mode", "invalid_mode"])
    print("  ✓ 无效 mode 抛出 SystemExit")


def test_parse_args_model():
    """测试 --model 参数"""
    print("\n=== 测试 --model 参数 ===")

    for model in ("tiny", "base", "small", "medium"):
        args = parse_args(["--model", model])
        assert args.model == model
        print(f"  ✓ --model {model}")

    # 默认
    args = parse_args([])
    assert args.model == "small"
    print("  ✓ 默认 model=small")


def test_parse_args_json_flag():
    """测试 --json 标志"""
    print("\n=== 测试 --json 标志 ===")

    args = parse_args(["--json"])
    assert args.json_output is True
    print("  ✓ --json 为 True (默认 False)")


def test_parse_args_v2_prescreen():
    """测试 v2 --prescreen/-p 参数"""
    print("\n=== 测试 v2 参数 ===")

    args = parse_args(["--prescreen"])
    assert args.prescreen is True
    assert args.smart is False
    print("  ✓ --prescreen")

    args = parse_args(["-p"])
    assert args.prescreen is True
    print("  ✓ -p")

    args = parse_args(["--smart"])
    assert args.smart is True
    assert args.prescreen is False
    print("  ✓ --smart")

    args = parse_args(["-s"])
    assert args.smart is True
    print("  ✓ -s")

    args = parse_args(["--prescreen-only"])
    assert args.prescreen_only is True
    print("  ✓ --prescreen-only")

    args = parse_args(["--cost-tier", "free"])
    assert args.cost_tier == "free"
    print("  ✓ --cost-tier free")

    args = parse_args(["--cost-tier", "premium"])
    assert args.cost_tier == "premium"
    print("  ✓ --cost-tier premium")


def test_parse_args_invalid_cost_tier():
    """测试无效的 --cost-tier"""
    print("\n=== 测试无效 --cost-tier ===")

    with pytest.raises(SystemExit):
        parse_args(["--cost-tier", "ultra"])
    print("  ✓ 无效 cost-tier 抛出 SystemExit")


def test_parse_args_list_extractors():
    """测试 --list-extractors"""
    print("\n=== 测试 --list-extractors ===")

    args = parse_args(["--list-extractors"])
    assert args.list_extractors is True
    print("  ✓ --list-extractors 为 True")


def test_parse_args_boolean_flags():
    """测试布尔标志参数"""
    print("\n=== 测试布尔标志参数 ===")

    args = parse_args(["--quiet", "--stdin", "--mock"])
    assert args.quiet is True
    assert args.stdin is True
    assert args.mock is True
    assert args.json_output is False
    print("  ✓ --quiet, --stdin, --mock")


def test_parse_args_cookie_browser():
    """测试 --cookie-browser"""
    print("\n=== 测试 --cookie-browser ===")

    for browser in ("chrome", "safari", "firefox", "edge", "brave"):
        args = parse_args(["--cookie-browser", browser])
        assert args.cookie_browser == browser
    print("  ✓ 所有 cookie-browser 选项")


def test_parse_args_invalid_cookie_browser():
    """测试无效 --cookie-browser"""
    print("\n=== 测试无效 --cookie-browser ===")

    with pytest.raises(SystemExit):
        parse_args(["--cookie-browser", "opera"])
    print("  ✓ 无效 cookie-browser 抛出 SystemExit")


def test_parse_args_timeout():
    """测试 --timeout"""
    print("\n=== 测试 --timeout ===")

    args = parse_args(["--timeout", "120"])
    assert args.timeout == 120
    print("  ✓ --timeout 120")

    args = parse_args([])
    assert args.timeout == 600
    print("  ✓ 默认 timeout=600")


def test_parse_args_output():
    """测试输出相关参数"""
    print("\n=== 测试输出参数 ===")

    # --output-file
    args = parse_args(["--output-file", "result.json"])
    assert args.output_file == "result.json"
    print("  ✓ --output-file")

    # --output-dir
    args = parse_args(["--output-dir", "/tmp/videomind"])
    assert args.output_dir == "/tmp/videomind"
    print("  ✓ --output-dir")

    # --no-keep-video 覆盖 --keep-video
    args = parse_args(["--no-keep-video"])
    assert args.keep_video is False
    print("  ✓ --no-keep-video")


def test_parse_args_video_quality():
    """测试 --video-quality"""
    print("\n=== 测试 --video-quality ===")

    for q in ("best", "worst", "1080p", "720p", "480p"):
        args = parse_args(["--video-quality", q])
        assert args.video_quality == q
    print("  ✓ 所有 video-quality 选项")


def test_parse_args_config_set():
    """测试 --config-set"""
    print("\n=== 测试 --config-set ===")

    args = parse_args(["--config-set", "coze", "my_token"])
    assert args.config_set == ["coze", "my_token"]
    print("  ✓ --config-set key value")


def test_parse_args_combined():
    """测试组合参数"""
    print("\n=== 测试组合参数 ===")

    args = parse_args([
        "https://example.com/video",
        "--mode", "transcribe",
        "--model", "tiny",
        "--json",
        "--quiet",
        "--timeout", "300",
        "--prescreen",
    ])

    assert args.url == "https://example.com/video"
    assert args.mode == "transcribe"
    assert args.model == "tiny"
    assert args.json_output is True
    assert args.quiet is True
    assert args.timeout == 300
    assert args.prescreen is True
    print("  ✓ 组合参数正确解析")


# ============================================================
# parse_targets 测试
# ============================================================


def test_parse_targets_single():
    """测试单个导出目标"""
    print("\n=== 测试 parse_targets 单个目标 ===")

    targets = parse_targets("local")
    assert targets == [ExportTarget.LOCAL]
    print("  ✓ 'local' → [LOCAL]")

    targets = parse_targets("obsidian")
    assert targets == [ExportTarget.OBSIDIAN]
    print("  ✓ 'obsidian' → [OBSIDIAN]")

    targets = parse_targets("notion")
    assert targets == [ExportTarget.NOTION]
    print("  ✓ 'notion' → [NOTION]")


def test_parse_targets_multiple():
    """测试多个导出目标"""
    print("\n=== 测试 parse_targets 多个目标 ===")

    targets = parse_targets("local,obsidian")
    assert targets == [ExportTarget.LOCAL, ExportTarget.OBSIDIAN]
    print("  ✓ 'local,obsidian'")

    targets = parse_targets("obsidian,notion,local")
    assert targets == [ExportTarget.OBSIDIAN, ExportTarget.NOTION, ExportTarget.LOCAL]
    print("  ✓ 'obsidian,notion,local'")

    targets = parse_targets("local,obsidian,notion")
    assert targets == [ExportTarget.LOCAL, ExportTarget.OBSIDIAN, ExportTarget.NOTION]
    print("  ✓ 'local,obsidian,notion'")


def test_parse_targets_whitespace():
    """测试带空格的导出目标"""
    print("\n=== 测试 parse_targets 空格处理 ===")

    targets = parse_targets(" local , obsidian ")
    assert targets == [ExportTarget.LOCAL, ExportTarget.OBSIDIAN]
    print("  ✓ ' local , obsidian '")


def test_parse_targets_empty():
    """测试空字符串"""
    print("\n=== 测试 parse_targets 空值 ===")

    targets = parse_targets("")
    assert targets == [ExportTarget.LOCAL], "空字符串应返回默认 [LOCAL]"
    print("  ✓ 空字符串 → [LOCAL]")


def test_parse_targets_all_invalid():
    """测试全无效目标"""
    print("\n=== 测试 parse_targets 全无效 ===")

    targets = parse_targets("invalid_target")
    assert targets == [ExportTarget.LOCAL], "无效目标应返回 [LOCAL]"
    print("  ✓ 无效 → [LOCAL]")

    targets = parse_targets("foo,bar,baz")
    assert targets == [ExportTarget.LOCAL], "全部无效应返回 [LOCAL]"
    print("  ✓ 全部无效 → [LOCAL]")


def test_parse_targets_partial_invalid():
    """测试部分无效目标"""
    print("\n=== 测试 parse_targets 部分无效 ===")

    targets = parse_targets("local,invalid,obsidian")
    assert len(targets) == 2
    assert ExportTarget.LOCAL in targets
    assert ExportTarget.OBSIDIAN in targets
    assert ExportTarget.NOTION not in targets
    print("  ✓ 'local,invalid,obsidian' → [LOCAL, OBSIDIAN]")


def test_parse_targets_case_insensitive():
    """测试大小写不敏感"""
    print("\n=== 测试 parse_targets 大小写 ===")

    targets = parse_targets("LOCAL")
    assert targets == [ExportTarget.LOCAL]
    print("  ✓ 'LOCAL' 大小写不敏感")

    targets = parse_targets("Local,Obsidian")
    assert targets == [ExportTarget.LOCAL, ExportTarget.OBSIDIAN]
    print("  ✓ 'Local,Obsidian' 混合大小写")


# ============================================================
# format_duration 测试
# ============================================================


def test_format_duration_seconds():
    """测试 format_duration 秒"""
    print("\n=== 测试 format_duration 秒 ===")

    assert format_duration(0) == "0秒"
    assert format_duration(30) == "30秒"
    assert format_duration(59) == "59秒"
    print("  ✓ 秒级: 0s→0秒, 30s→30秒, 59s→59秒")


def test_format_duration_minutes():
    """测试 format_duration 分"""
    print("\n=== 测试 format_duration 分 ===")

    assert format_duration(60) == "1.0分钟"
    assert format_duration(90) == "1.5分钟"
    assert format_duration(1800) == "30.0分钟"
    assert format_duration(3599) == "60.0分钟"  # < 3600 依然走分支
    print("  ✓ 分级: 60s→1.0分钟, 90s→1.5分钟, 1800s→30.0分钟")


def test_format_duration_hours():
    """测试 format_duration 小时"""
    print("\n=== 测试 format_duration 小时 ===")

    assert format_duration(3600) == "1.0小时"
    assert format_duration(5400) == "1.5小时"
    assert format_duration(7200) == "2.0小时"
    print("  ✓ 小时级: 3600s→1.0小时, 5400s→1.5小时, 7200s→2.0小时")


# ============================================================
# 模式字符串验证测试
# ============================================================

def test_valid_modes():
    """验证 mode 可选值"""
    print("\n=== 测试 mode 可选值 ===")

    valid_modes = {"full", "download", "transcribe"}
    # 通过解析来确认 choices
    for mode in valid_modes:
        args = parse_args(["--mode", mode])
        assert args.mode in valid_modes
    print(f"  ✓ 有效 mode: {valid_modes}")


def test_v2_cost_tier_choices():
    """验证 cost-tier 可选值"""
    print("\n=== 测试 cost-tier 可选值 ===")

    valid_tiers = {"free", "cheap", "paid", "expensive", "premium"}
    for tier in valid_tiers:
        args = parse_args(["--cost-tier", tier])
        assert args.cost_tier in valid_tiers
    print(f"  ✓ 有效 cost-tier: {valid_tiers}")
