"""CLI 模块测试 — 参数解析、纯逻辑函数和输入路由

不运行真实的下载/转录流程。
"""


import sys
from unittest.mock import patch

import pytest

from src.cli import format_duration, main, parse_args, parse_targets
from src.models.task import ExportTarget


# ============================================================
# 参数解析测试
# ============================================================
def test_parse_args_url():
    """测试 URL 参数"""
    print("\n=== 测试 URL 参数 ===")

    args = parse_args(["https://bilibili.com/video/BV1xx"])
    assert args.url == "https://bilibili.com/video/BV1xx"
    print(f"  ✓ URL: {args.url}")
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


def test_parse_args_asr_overrides():
    """测试 --asr / --asr-chain / --asr-language / --list-asr"""
    args = parse_args(["--asr", "sensevoice", "--asr-language", "zh"])
    assert args.asr == "sensevoice"
    assert args.asr_language == "zh"
    assert args.asr_chain is None

    args = parse_args(["--asr-chain", "sensevoice,faster_whisper"])
    assert args.asr_chain == "sensevoice,faster_whisper"

    args = parse_args(["--list-asr"])
    assert args.list_asr is True
def test_parse_args_config_set():
    """测试 --config-set"""
    print("\n=== 测试 --config-set ===")

    args = parse_args(["--config-set", "tikhub", "my_token"])
    assert args.config_set == ["tikhub", "my_token"]
    print("  ✓ --config-set key value")
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
def test_v2_cost_tier_choices():
    """验证 cost-tier 可选值"""
    print("\n=== 测试 cost-tier 可选值 ===")

    valid_tiers = {"free", "cheap", "paid", "expensive", "premium"}
    for tier in valid_tiers:
        args = parse_args(["--cost-tier", tier])
        assert args.cost_tier in valid_tiers
    print(f"  ✓ 有效 cost-tier: {valid_tiers}")



class TestInputRouting:
    """A2 之后的三种输入：远程 URL → v2 提取；本地文件 → 只做 ASR 转写；无参数 → 用法 + 退出码 2。"""

    def test_local_file_routes_to_local_asr(self, tmp_path):
        media = tmp_path / "clip.mp4"
        media.write_bytes(b"x")

        with (
            patch.object(sys, "argv", ["videomind", str(media)]),
            patch("src.cli._run_local_asr", return_value=0) as asr,
            patch("src.cli.run_v2_extraction") as v2,
        ):
            assert main() == 0

        asr.assert_called_once()
        v2.assert_not_called()

    def test_remote_url_keeps_v2_path(self):
        url = "https://www.youtube.com/watch?v=xxx"

        with (
            patch.object(sys, "argv", ["videomind", url]),
            patch("src.cli.run_v2_extraction", return_value=0) as v2,
            patch("src.cli._run_local_asr") as asr,
        ):
            assert main() == 0

        v2.assert_called_once()
        asr.assert_not_called()

    def test_no_url_prints_usage_and_exits_2(self, capsys):
        with patch.object(sys, "argv", ["videomind"]):
            assert main() == 2
        assert "用法" in capsys.readouterr().err

    @pytest.mark.parametrize("flag", ["--mode", "--model", "--mock", "--targets", "--video-quality"])
    def test_v1_only_flags_are_gone(self, flag):
        """v1 专属参数必须真的消失（不是被忽略）—— 否则老脚本会"看起来还能跑"。"""
        with patch.object(sys, "argv", ["videomind", "https://x/v", flag, "full"]):
            with pytest.raises(SystemExit):
                parse_args()
