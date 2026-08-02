"""archiver (提取即归档) 测试

纯文本归档: 从 v2 ExtractResult 直接生成 Obsidian 笔记 / 本地 Markdown+SRT,
不依赖 v1 的下载/转录文件。
"""


from src.core.archiver import (
    SUPPORTED_ARCHIVE_TARGETS,
    ArchiverConfig,
    archive_extract_result,
    build_export_context,
)
from src.core.models import CostTier, ExtractResult


def make_extract_result(content: str = "这是一段测试转录内容。\n第二行内容。", segments: bool = True) -> ExtractResult:
    segs = None
    if segments:
        segs = [
            {"start": 0.0, "end": 2.5, "text": "这是一段测试转录内容。"},
            {"start": 2.5, "end": 5.0, "text": "第二行内容。"},
        ]
    return ExtractResult(
        success=True,
        platform="bilibili",
        title="测试视频标题",
        content=content,
        source="bilibili_api",
        url="https://www.bilibili.com/video/BV1xx411c7mD",
        cost_tier=CostTier.FREE,
        duration_seconds=300.0,
        segments=segs,
    )


def test_supported_targets():
    assert set(SUPPORTED_ARCHIVE_TARGETS) == {"obsidian", "local", "html_player"}


def test_build_export_context():
    """ExtractResult → ExportContext 字段映射"""
    result = make_extract_result()
    ctx = build_export_context(result, ai_summary="一句话总结")

    assert ctx.video_metadata.title == "测试视频标题"
    assert ctx.video_metadata.platform == "bilibili"
    assert ctx.video_metadata.duration == 300
    assert ctx.transcript_text == result.content
    assert ctx.ai_summary == "一句话总结"
    assert len(ctx.transcript_segments) == 2
    assert ctx.transcript_segments[0].text == "这是一段测试转录内容。"
    # 无媒体文件 (纯文本归档模式)
    assert ctx.video_path is None
    assert ctx.audio_path is None


def test_archive_local(tmp_path):
    """归档到本地: 生成 Markdown + SRT + 转录文本"""
    result = make_extract_result()
    config = ArchiverConfig(local_output_path=tmp_path / "out")

    results = archive_extract_result(result, targets=["local"], config=config)

    assert len(results) == 1
    assert results[0].success, results[0].error_msg
    out = tmp_path / "out"
    md_files = list(out.rglob("*.md"))
    srt_files = list(out.rglob("*.srt"))
    txt_files = list(out.rglob("*_transcript.txt"))
    assert md_files, "应生成 Markdown 笔记"
    assert srt_files, "应生成 SRT 字幕"
    assert txt_files, "应生成转录文本"
    assert "测试视频标题" in md_files[0].read_text(encoding="utf-8")


def test_archive_obsidian(tmp_path):
    """归档到 Obsidian: 生成带 frontmatter 的笔记"""
    result = make_extract_result()
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    config = ArchiverConfig(obsidian_vault_path=vault)

    results = archive_extract_result(result, targets=["obsidian"], config=config)

    assert len(results) == 1
    assert results[0].success, results[0].error_msg
    note_path = results[0].output_path
    assert note_path is not None and note_path.exists()
    content = note_path.read_text(encoding="utf-8")
    assert "---" in content  # frontmatter
    assert "测试视频标题" in content
    assert "https://www.bilibili.com/video/BV1xx411c7mD" in content
    assert "这是一段测试转录内容。" in content


def test_archive_obsidian_with_summary(tmp_path):
    """带 AI 摘要归档: 笔记包含一句话总结"""
    result = make_extract_result()
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    config = ArchiverConfig(obsidian_vault_path=vault)

    results = archive_extract_result(result, targets=["obsidian"], config=config, ai_summary="本视频介绍测试")

    assert results[0].success
    content = results[0].output_path.read_text(encoding="utf-8")
    assert "本视频介绍测试" in content


def test_archive_empty_content_returns_failure():
    """无真实内容的提取结果 → 归档返回失败"""
    result = make_extract_result(content="   ")
    results = archive_extract_result(result, targets=["local"])
    assert len(results) == 1
    assert results[0].success is False
    assert "无法归档" in (results[0].error_msg or "")


def test_archive_ignores_invalid_target(tmp_path):
    """未知归档目标被忽略, 不报错"""
    result = make_extract_result()
    config = ArchiverConfig(local_output_path=tmp_path / "out")

    results = archive_extract_result(result, targets=["local", "notion"], config=config)

    assert len(results) == 1
    assert results[0].success


def test_archive_parallel_targets(tmp_path):
    """多目标并发归档, 全部成功"""
    result = make_extract_result()
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    config = ArchiverConfig(
        obsidian_vault_path=vault,
        local_output_path=tmp_path / "out",
    )

    results = archive_extract_result(result, targets=["obsidian", "local"], config=config)

    assert len(results) == 2
    assert all(r.success for r in results)
