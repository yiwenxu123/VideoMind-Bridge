"""导出器测试"""

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from src.exporters.base import BaseExporter
from src.exporters.local_exporter import LocalExporter
from src.models.task import (
    ExportContext,
    ExportResult,
    ExportTarget,
    TranscriptSegment,
    VideoMetadata,
)


def test_base_exporter_interface():
    """测试 BaseExporter 接口定义"""
    print("\n=== 测试 BaseExporter 接口 ===")

    # 检查抽象方法
    assert hasattr(BaseExporter, 'name')
    assert hasattr(BaseExporter, 'icon')
    assert hasattr(BaseExporter, 'validate_config')
    assert hasattr(BaseExporter, 'export')

    print("  ✓ BaseExporter 接口定义正确")


def test_local_exporter_init():
    """测试 LocalExporter 初始化"""
    print("\n=== 测试 LocalExporter 初始化 ===")

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        exporter = LocalExporter(
            output_path=Path(tmpdir),
            organize_by="date"
        )

        assert exporter.name == "本地文件夹"
        assert exporter.icon == "💾"
        assert exporter.output_path == Path(tmpdir)

        print("  ✓ LocalExporter 初始化正确")


def test_local_exporter_validate():
    """测试 LocalExporter 配置验证"""
    print("\n=== 测试 LocalExporter 配置验证 ===")

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        # 有效路径
        exporter = LocalExporter(output_path=Path(tmpdir))
        valid, error = exporter.validate_config()
        assert valid is True, f"应验证通过: {error}"
        print("  ✓ 有效路径验证通过")

        # 无效路径
        exporter = LocalExporter(output_path=Path("/不存在的路径/12345"))
        valid, error = exporter.validate_config()
        assert valid is False, "应验证失败"
        print("  ✓ 无效路径正确拒绝")


def test_export_context_creation():
    """测试 ExportContext 创建"""
    print("\n=== 测试 ExportContext 创建 ===")

    metadata = VideoMetadata(
        title="测试视频",
        author="测试作者",
        duration=600,
        platform="bilibili",
        url="https://test.com/video"
    )

    context = ExportContext(
        task_id=uuid4(),
        video_metadata=metadata,
        transcript_text="测试转录内容",
        ai_summary="测试摘要"
    )

    assert context.video_metadata.title == "测试视频"
    assert context.ai_summary == "测试摘要"

    print("  ✓ ExportContext 创建成功")


def test_export_result_creation():
    """测试 ExportResult 创建"""
    print("\n=== 测试 ExportResult 创建 ===")

    result = ExportResult(
        success=True,
        target=ExportTarget.LOCAL,
        output_path=Path("/test/output.md"),
        remote_url=None
    )

    assert result.success is True
    assert result.target == ExportTarget.LOCAL

    print("  ✓ ExportResult 创建成功")


# =============================================================================
# Section 2: BaseExporter interface contract (extended)
# =============================================================================


def test_base_exporter_abstract_cannot_instantiate():
    """BaseExporter 是抽象类，不能直接实例化"""
    try:
        BaseExporter()
        raise AssertionError("应该抛出 TypeError")
    except TypeError:
        pass


def test_base_exporter_concrete_must_implement_abstract():
    """子类必须实现所有抽象方法"""
    class IncompleteExporter(BaseExporter):
        pass

    try:
        IncompleteExporter()  # noqa
        raise AssertionError("应该抛出 TypeError")
    except TypeError:
        pass


def test_base_exporter_get_config_schema_default():
    """get_config_schema 默认返回空字典"""
    class ConcreteExporter(BaseExporter):
        name = "Test"
        icon = "🔬"

        def validate_config(self) -> tuple[bool, str]:
            return True, ""

        def export(self, context: ExportContext) -> ExportResult:
            return ExportResult(success=True, target=ExportTarget.LOCAL)

    exporter = ConcreteExporter()
    assert exporter.get_config_schema() == {}


# =============================================================================
# Section 3: LocalExporter comprehensive tests
# =============================================================================

def test_local_exporter_init_default_organize():
    """LocalExporter 默认 organize_by = 'date'"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        exporter = LocalExporter(output_path=Path(tmpdir))
        assert exporter.organize_by == "date"


def test_local_exporter_init_organize_modes():
    """LocalExporter 支持三种 organize_by 模式"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        for mode in ("date", "title", "flat"):
            exporter = LocalExporter(output_path=Path(tmpdir), organize_by=mode)
            assert exporter.organize_by == mode
            assert exporter.name == "本地文件夹"
            assert exporter.icon == "💾"


def test_local_exporter_validate_permission_error(tmp_path):
    """validate_config 在 PermissionError 时返回 False"""
    exporter = LocalExporter(output_path=tmp_path / "test")
    with patch.object(Path, "mkdir", side_effect=PermissionError("denied")):
        valid, error = exporter.validate_config()
        assert valid is False
        assert "权限错误" in error


def test_local_exporter_validate_os_error(tmp_path):
    """validate_config 在 OSError 时返回 False"""
    exporter = LocalExporter(output_path=tmp_path / "test")
    with patch.object(Path, "mkdir", side_effect=OSError("system error")):
        valid, error = exporter.validate_config()
        assert valid is False
        assert "系统错误" in error


def test_local_exporter_build_output_dir_date(tmp_path):
    """_build_output_dir 按 date 模式生成路径"""
    exporter = LocalExporter(output_path=tmp_path, organize_by="date")
    metadata = VideoMetadata(
        title="测试视频", author="作者", duration=100,
        platform="bilibili", url="https://test.com"
    )
    context = ExportContext(task_id=uuid4(), video_metadata=metadata, config={})

    with patch("src.exporters.local_exporter.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "2026-01-15"
        output_dir = exporter._build_output_dir(context)

    assert str(tmp_path) in str(output_dir)
    assert "2026-01-15" in str(output_dir)
    assert "测试视频" in str(output_dir)


def test_local_exporter_build_output_dir_title(tmp_path):
    """_build_output_dir 按 title 模式生成路径"""
    exporter = LocalExporter(output_path=tmp_path, organize_by="title")
    metadata = VideoMetadata(
        title="我的视频", author="作者", duration=100,
        platform="youtube", url="https://test.com"
    )
    context = ExportContext(task_id=uuid4(), video_metadata=metadata, config={})
    output_dir = exporter._build_output_dir(context)

    assert output_dir == tmp_path / "我的视频"


def test_local_exporter_build_output_dir_flat(tmp_path):
    """_build_output_dir 按 flat 模式直接返回 output_path"""
    exporter = LocalExporter(output_path=tmp_path, organize_by="flat")
    metadata = VideoMetadata(
        title="任意视频", author="作者", duration=100,
        platform="youtube", url="https://test.com"
    )
    context = ExportContext(task_id=uuid4(), video_metadata=metadata, config={})
    output_dir = exporter._build_output_dir(context)

    assert output_dir == tmp_path


def test_local_exporter_export_success_video(tmp_path):
    """export 成功导出 - 有视频文件"""
    output_path = tmp_path / "output"
    dummy_video = tmp_path / "source_video.mp4"
    dummy_video.write_text("fake video")

    metadata = VideoMetadata(
        title="测试视频", author="UP主", duration=180,
        platform="bilibili", url="https://bilibili.com/video"
    )
    context = ExportContext(
        task_id=uuid4(),
        video_metadata=metadata,
        video_path=dummy_video,
        transcript_segments=[
            TranscriptSegment(start=0, end=5, text="第一句"),
            TranscriptSegment(start=5, end=10, text="第二句"),
        ],
        transcript_text="[00:00] 第一句\n[00:05] 第二句",
        ai_summary="一句话总结。",
        config={
            "highlights": [
                {"time": "00:01:30", "seconds": 90, "content": "关键要点"},
            ]
        }
    )

    with patch("src.exporters.local_exporter.shutil.copy2") as mock_copy:
        exporter = LocalExporter(output_path=output_path, organize_by="flat")
        result = exporter.export(context)

    assert result.success is True
    assert result.target == ExportTarget.LOCAL
    assert result.output_path is not None
    assert result.metadata["files_created"] >= 3  # video + transcript + markdown
    mock_copy.assert_called_once()

    # Verify files were created in the output directory
    output_files = list(output_path.iterdir())
    assert len(output_files) > 0


def test_local_exporter_export_audio_only(tmp_path):
    """export 成功导出 - 只有音频文件"""
    output_path = tmp_path / "output"
    dummy_audio = tmp_path / "source_audio.m4a"
    dummy_audio.write_text("fake audio")

    metadata = VideoMetadata(
        title="音频测试", author="作者", duration=60,
        platform="youtube", url="https://youtube.com/watch"
    )
    context = ExportContext(
        task_id=uuid4(),
        video_metadata=metadata,
        audio_path=dummy_audio,
        transcript_text="纯音频转录内容",
        ai_summary="摘要",
        config={}
    )

    with (
        patch("src.exporters.local_exporter.shutil.copy2") as mock_copy,
    ):
        exporter = LocalExporter(output_path=output_path, organize_by="flat")
        result = exporter.export(context)

    assert result.success is True
    mock_copy.assert_called_once()


def test_local_exporter_export_no_media(tmp_path):
    """export 成功导出 - 无媒体文件，只有文本"""
    output_path = tmp_path / "output"

    metadata = VideoMetadata(
        title="纯文本", author="作者", duration=30,
        platform="bilibili", url="https://bilibili.com"
    )
    context = ExportContext(
        task_id=uuid4(),
        video_metadata=metadata,
        transcript_text="转录内容",
        ai_summary="摘要内容",
        config={}
    )

    exporter = LocalExporter(output_path=output_path, organize_by="flat")
    result = exporter.export(context)

    assert result.success is True
    assert result.metadata["files_created"] >= 1  # at least markdown


def test_local_exporter_export_invalid_config(tmp_path):
    """export 在验证失败时返回错误结果"""
    exporter = LocalExporter(output_path=tmp_path / "nonexistent")
    with patch.object(exporter, "validate_config", return_value=(False, "权限错误")):
        result = exporter.export(
            ExportContext(
                task_id=uuid4(),
                video_metadata=VideoMetadata(
                    title="t", author="a", duration=1,
                    platform="p", url="https://x.com"
                ),
                config={}
            )
        )
    assert result.success is False
    assert result.error_msg == "权限错误"


def test_local_exporter_generate_markdown_format(tmp_path):
    """_generate_markdown 生成正确的 Markdown 格式"""
    exporter = LocalExporter(output_path=tmp_path, organize_by="flat")
    metadata = VideoMetadata(
        title="测试标题", author="测试作者", duration=125,
        platform="bilibili", url="https://bilibili.com/video"
    )
    context = ExportContext(
        task_id=uuid4(),
        video_metadata=metadata,
        transcript_text="转录",
        ai_summary="AI 摘要内容",
        video_path=tmp_path / "video.mp4",
        config={
            "highlights": [
                {"time": "00:02:05", "seconds": 125, "content": "亮点"},
            ]
        }
    )

    md = exporter._generate_markdown(context)

    # Check markdown structure
    assert "# 测试标题" in md
    assert "## 元数据" in md
    assert "## AI 摘要" in md
    assert "AI 摘要内容" in md
    assert "## 关键时间轴" in md
    assert "00:02:05" in md
    assert "## 文件列表" in md
    assert "VideoMind Bridge" in md


def test_local_exporter_generate_markdown_no_summary(tmp_path):
    """_generate_markdown 没有 AI 摘要时的格式"""
    exporter = LocalExporter(output_path=tmp_path, organize_by="flat")
    metadata = VideoMetadata(
        title="无摘要", author="作者", duration=60,
        platform="youtube", url="https://youtube.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        transcript_text="转录", ai_summary=None,
        config={}
    )

    md = exporter._generate_markdown(context)
    assert "## AI 摘要" not in md
    assert "# 无摘要" in md


def test_local_exporter_generate_markdown_no_local_video(tmp_path):
    """_generate_markdown 无本地视频时使用线上链接"""
    exporter = LocalExporter(output_path=tmp_path, organize_by="flat")
    metadata = VideoMetadata(
        title="线上视频", author="作者", duration=60,
        platform="youtube", url="https://youtube.com/watch?v=xxx"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        ai_summary="摘要", config={
            "highlights": [
                {"time": "00:01:00", "seconds": 60, "content": "重要内容"},
            ]
        }
    )

    md = exporter._generate_markdown(context)
    # Should use online link with ?t=seconds
    assert "?t=60" in md
    assert "在线视频" in md


def test_local_exporter_export_flat_structure(tmp_path):
    """export flat 模式：文件直接在 output_path 下"""
    output_path = tmp_path / "flat_output"

    metadata = VideoMetadata(
        title="Flat视频", author="作者", duration=10,
        platform="bilibili", url="https://bilibili.com"
    )
    context = ExportContext(
        task_id=uuid4(),
        video_metadata=metadata,
        transcript_text="转录",
        ai_summary="摘要",
        config={}
    )

    exporter = LocalExporter(output_path=output_path, organize_by="flat")
    result = exporter.export(context)

    assert result.success is True
    assert result.output_path == output_path


def test_local_exporter_export_date_structure(tmp_path):
    """export date 模式：文件在 {date}/{title} 下"""
    output_path = tmp_path / "date_output"

    metadata = VideoMetadata(
        title="日期视频", author="作者", duration=10,
        platform="bilibili", url="https://bilibili.com"
    )
    context = ExportContext(
        task_id=uuid4(),
        video_metadata=metadata,
        transcript_text="转录",
        ai_summary="摘要",
        config={}
    )

    with patch("src.exporters.local_exporter.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "2026-05-24"
        exporter = LocalExporter(output_path=output_path, organize_by="date")
        result = exporter.export(context)

    assert result.success is True
    assert "2026-05-24" in str(result.output_path)
    assert "日期视频" in str(result.output_path)


def test_local_exporter_export_title_structure(tmp_path):
    """export title 模式：文件在 {title}/ 下"""
    output_path = tmp_path / "title_output"

    metadata = VideoMetadata(
        title="标题视频", author="作者", duration=10,
        platform="bilibili", url="https://bilibili.com"
    )
    context = ExportContext(
        task_id=uuid4(),
        video_metadata=metadata,
        transcript_text="转录",
        ai_summary="摘要",
        config={}
    )

    exporter = LocalExporter(output_path=output_path, organize_by="title")
    result = exporter.export(context)

    assert result.success is True
    assert result.output_path == output_path / "标题视频"


def test_local_exporter_copy_video_error_does_not_block(tmp_path):
    """视频复制失败不阻塞整体导出"""
    output_path = tmp_path / "output"
    dummy_video = tmp_path / "source.mp4"
    dummy_video.write_text("data")

    metadata = VideoMetadata(
        title="复制失败", author="作者", duration=10,
        platform="bilibili", url="https://bilibili.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        video_path=dummy_video, transcript_text="转录",
        ai_summary="摘要", config={}
    )

    with patch("src.exporters.local_exporter.shutil.copy2", side_effect=PermissionError("denied")):
        exporter = LocalExporter(output_path=output_path, organize_by="flat")
        result = exporter.export(context)

    # Export should still succeed (transcript + markdown created)
    assert result.success is True


def test_local_exporter_transcript_segments_generates_srt(tmp_path):
    """有 transcript_segments 时生成 SRT 文件"""
    output_path = tmp_path / "srt_test"

    metadata = VideoMetadata(
        title="SRT测试", author="作者", duration=10,
        platform="bilibili", url="https://bilibili.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        transcript_segments=[
            TranscriptSegment(start=0, end=3, text="第一句"),
            TranscriptSegment(start=3, end=6, text="第二句"),
        ],
        transcript_text="内容", ai_summary="摘要", config={}
    )

    exporter = LocalExporter(output_path=output_path, organize_by="flat")
    result = exporter.export(context)

    assert result.success is True
    # Check that a .srt file was created
    srt_files = list(output_path.glob("*.srt"))
    assert len(srt_files) >= 1
    srt_content = srt_files[0].read_text(encoding="utf-8")
    assert "第一句" in srt_content


# =============================================================================
# Section 4: ObsidianExporter comprehensive tests
# =============================================================================

from src.exporters.obsidian_exporter import ObsidianExporter


def test_obsidian_exporter_init():
    """ObsidianExporter 初始化"""
    exporter = ObsidianExporter(vault_path=Path("/tmp/test_vault"))
    assert exporter.name == "Obsidian"
    assert exporter.icon == "📝"
    assert exporter.vault_path == Path("/tmp/test_vault")
    assert exporter.subfolder == "Inbox/Videos"
    assert exporter.template_path is None


def test_obsidian_exporter_init_no_vault():
    """ObsidianExporter 初始化时 vault_path 可为 None"""
    exporter = ObsidianExporter()
    assert exporter.vault_path is None


def test_obsidian_exporter_init_with_subfolder():
    """ObsidianExporter 可指定 subfolder"""
    exporter = ObsidianExporter(
        vault_path=Path("/tmp/vault"),
        subfolder="Projects/Notes"
    )
    assert exporter.subfolder == "Projects/Notes"


def test_obsidian_exporter_init_with_template():
    """ObsidianExporter 可指定 template_path"""
    exporter = ObsidianExporter(
        vault_path=Path("/tmp/vault"),
        template_path=Path("/tmp/template.md")
    )
    assert exporter.template_path == Path("/tmp/template.md")


def test_obsidian_exporter_validate_no_vault():
    """validate_config: vault_path 为 None 时失败"""
    exporter = ObsidianExporter()
    valid, error = exporter.validate_config()
    assert valid is False
    assert "未配置" in error


def test_obsidian_exporter_validate_vault_not_exists():
    """validate_config: vault_path 不存在时失败"""
    exporter = ObsidianExporter(vault_path=Path("/nonexistent_vault_12345"))
    valid, error = exporter.validate_config()
    assert valid is False
    assert "不存在" in error


def test_obsidian_exporter_validate_success(tmp_path):
    """validate_config: 有效 vault 时通过"""
    exporter = ObsidianExporter(vault_path=tmp_path)
    valid, error = exporter.validate_config()
    assert valid is True
    assert error == ""


def test_obsidian_exporter_validate_with_obsidian_dir(tmp_path):
    """validate_config: vault 含 .obsidian 时通过"""
    obsidian_dir = tmp_path / ".obsidian"
    obsidian_dir.mkdir()
    exporter = ObsidianExporter(vault_path=tmp_path)
    valid, error = exporter.validate_config()
    assert valid is True
    assert error == ""


def test_obsidian_exporter_export_full_mode(tmp_path):
    """export 完整模式：有 AI 摘要"""
    vault = tmp_path / "vault"
    vault.mkdir()
    # Create dummy video file
    dummy_video = tmp_path / "source_video.mp4"
    dummy_video.write_text("data")

    metadata = VideoMetadata(
        title="Obsidian完整", author="作者", duration=300,
        platform="bilibili", url="https://bilibili.com/video"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        video_path=dummy_video, transcript_text="完整转录",
        ai_summary="一句话总结",
        config={
            "highlights": [
                {"time": "00:01:30", "seconds": 90, "content": "要点一"},
            ]
        }
    )

    with (
        patch("src.exporters.obsidian_exporter.safe_create_symlink",
              return_value=(True, "symlink created")),
    ):
        exporter = ObsidianExporter(vault_path=vault)
        result = exporter.export(context)

    assert result.success is True
    assert result.target == ExportTarget.OBSIDIAN
    assert result.output_path is not None
    assert result.output_path.exists()

    # Verify markdown content
    content = result.output_path.read_text(encoding="utf-8")
    assert "---" in content  # frontmatter
    assert "title: Obsidian完整" in content
    assert "一句话总结" in content
    assert "完整转录" in content
    assert "视频笔记" in content
    assert "## AI 提炼关键时间轴" in content


def test_obsidian_exporter_export_transcribe_mode(tmp_path):
    """export 转录模式：无 AI 摘要"""
    vault = tmp_path / "vault"
    vault.mkdir()

    metadata = VideoMetadata(
        title="Only转录", author="作者", duration=120,
        platform="youtube", url="https://youtube.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        transcript_segments=[
            TranscriptSegment(start=0, end=5, text="第一段"),
            TranscriptSegment(start=5, end=10, text="第二段"),
        ],
        transcript_text="转录内容",
        ai_summary=None,
        config={}
    )

    exporter = ObsidianExporter(vault_path=vault)
    result = exporter.export(context)

    assert result.success is True
    content = result.output_path.read_text(encoding="utf-8")
    # Should not have AI summary header
    assert "AI 提炼关键时间轴" not in content
    assert "转录存档模式" in content
    assert "仅包含语音转录文本" in content


def test_obsidian_exporter_export_video_symlink_fallback_to_copy(tmp_path):
    """export 符号链接失败时回退到复制"""
    vault = tmp_path / "vault"
    vault.mkdir()
    dummy_video = tmp_path / "source_video.mp4"
    dummy_video.write_text("data")

    metadata = VideoMetadata(
        title="回退复制", author="作者", duration=10,
        platform="bilibili", url="https://bilibili.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        video_path=dummy_video, transcript_text="转录",
        ai_summary="摘要", config={}
    )

    with (
        patch("src.exporters.obsidian_exporter.safe_create_symlink",
              return_value=(False, "symlink failed")),
        patch("src.exporters.obsidian_exporter.safe_copy_file",
              return_value=(True, "copied")),
    ):
        exporter = ObsidianExporter(vault_path=vault)
        result = exporter.export(context)

    assert result.success is True
    assert result.metadata["video_copied"] is True


def test_obsidian_exporter_export_invalid_config(tmp_path):
    """export 验证失败时返回错误"""
    exporter = ObsidianExporter()  # no vault_path
    metadata = VideoMetadata(
        title="t", author="a", duration=1,
        platform="p", url="https://x.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata, config={}
    )
    result = exporter.export(context)
    assert result.success is False
    assert result.target == ExportTarget.OBSIDIAN


def test_obsidian_exporter_generate_note_format(tmp_path):
    """_generate_note 生成完整 Obsidian Markdown 格式"""
    exporter = ObsidianExporter(vault_path=tmp_path)
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_text("data")
    metadata = VideoMetadata(
        title="格式测试", author="作者君", duration=125,
        platform="bilibili", url="https://bilibili.com/video"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        video_path=dummy_video,
        transcript_text="转录文本内容",
        ai_summary="精彩总结",
        config={
            "highlights": [
                {"time": "00:02:05", "seconds": 125, "content": "高光时刻"},
            ]
        }
    )

    md = exporter._generate_note(context, video_filename="Attachments/test/video.mp4")

    # Frontmatter checks
    assert md.startswith("---")
    assert "title: 格式测试" in md
    assert "author: 作者君" in md
    assert "duration: 2分5秒" in md
    assert "platform: bilibili" in md
    assert "tags:" in md
    assert "  - 视频笔记" in md

    # Body checks
    assert "# 格式测试" in md
    assert "> **一句话总结**: 精彩总结" in md
    assert "## AI 提炼关键时间轴" in md
    assert "![[Attachments/test/video.mp4]]" in md
    assert "00:02:05" in md

    # Footer
    assert "VideoMind Bridge" in md
    assert "---" in md


def test_obsidian_exporter_generate_note_transcribe_mode(tmp_path):
    """_generate_note 转录模式（无 AI summary）"""
    exporter = ObsidianExporter(vault_path=tmp_path)
    metadata = VideoMetadata(
        title="仅转录", author="作者", duration=60,
        platform="youtube", url="https://youtube.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        transcript_segments=[
            TranscriptSegment(start=0, end=5, text="第一段"),
        ],
        transcript_text="转录文本",
        ai_summary=None,
        config={}
    )

    md = exporter._generate_note(context, video_filename=None)

    assert "转录存档模式" in md
    assert "**一句话总结**" not in md
    assert "AI 提炼关键时间轴" not in md
    assert "转录时间轴" in md


def test_obsidian_exporter_format_highlights_with_video(tmp_path):
    """_format_highlights 有本地视频时使用 Media Extended 格式"""
    exporter = ObsidianExporter(vault_path=tmp_path)
    metadata = VideoMetadata(
        title="本地视频", author="作者", duration=100,
        platform="bilibili", url="https://bilibili.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        video_path=tmp_path / "video.mp4",  # exists as path obj
        config={
            "highlights": [
                {"time": "00:01:00", "seconds": 60, "content": "精要"},
            ]
        }
    )

    # Create dummy video file so exists() returns True
    (tmp_path / "video.mp4").write_text("data")

    result = exporter._format_highlights(context, video_filename="Attachments/local/video.mp4")

    assert "![[Attachments/local/video.mp4]]" in result
    assert "00:01:00" in result
    assert "Media Extended" in result


def test_obsidian_exporter_format_highlights_without_video(tmp_path):
    """_format_highlights 无本地视频时使用线上链接"""
    exporter = ObsidianExporter(vault_path=tmp_path)
    metadata = VideoMetadata(
        title="线上视频", author="作者", duration=100,
        platform="youtube", url="https://youtube.com/watch?v=abc"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        config={
            "highlights": [
                {"time": "00:01:00", "seconds": 60, "content": "线上高光"},
            ]
        }
    )

    result = exporter._format_highlights(context)
    assert "线上高光" in result
    assert "?t=60" in result
    assert "线上视频" not in result  # no video embed


def test_obsidian_exporter_format_highlights_no_highlights_transcript(tmp_path):
    """_format_highlights 无 highlights 但有 transcript_segments 时使用转录时间轴"""
    exporter = ObsidianExporter(vault_path=tmp_path)
    metadata = VideoMetadata(
        title="仅转录", author="作者", duration=10,
        platform="bilibili", url="https://bilibili.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        transcript_segments=[
            TranscriptSegment(start=0, end=3, text="第一句话内容"),
            TranscriptSegment(start=3, end=6, text="第二句话内容"),
        ],
        config={}
    )

    result = exporter._format_highlights(context)
    assert "转录时间轴" in result
    assert "第一句话内容" in result


def test_obsidian_exporter_format_highlights_no_data(tmp_path):
    """_format_highlights 无任何数据时显示占位"""
    exporter = ObsidianExporter(vault_path=tmp_path)
    metadata = VideoMetadata(
        title="空", author="作者", duration=0,
        platform="bilibili", url="https://bilibili.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata, config={}
    )

    result = exporter._format_highlights(context)
    assert "暂无转录数据" in result


def test_obsidian_exporter_generate_note_with_attachments(tmp_path):
    """_generate_note 附件信息"""
    exporter = ObsidianExporter(vault_path=tmp_path)
    metadata = VideoMetadata(
        title="附件测试", author="作者", duration=10,
        platform="bilibili", url="https://bilibili.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        ai_summary="摘要", config={}
    )

    md = exporter._generate_note(context, video_filename="Attachments/test/test.mp4")
    assert "## 本地附件" in md
    assert "`[[Attachments/test/test.mp4]]`" in md

    md_no_attach = exporter._generate_note(context)
    assert "## 本地附件" not in md_no_attach


# =============================================================================
# Section 5: HtmlPlayerExporter comprehensive tests
# =============================================================================

from src.exporters.html_player_exporter import HTMLPlayerExporter


def test_html_player_exporter_init():
    """HTMLPlayerExporter 初始化"""
    exporter = HTMLPlayerExporter()
    assert exporter.name == "HTML 播放器"
    assert exporter.icon == "🎬"


def test_html_player_exporter_validate_config():
    """validate_config 始终返回 True"""
    exporter = HTMLPlayerExporter()
    valid, error = exporter.validate_config()
    assert valid is True
    assert error == ""


def test_html_player_exporter_sanitize_filename():
    """_sanitize_filename 移除非法字符"""
    exporter = HTMLPlayerExporter()
    assert exporter._sanitize_filename("normal") == "normal"
    assert exporter._sanitize_filename("file<name>") == "file_name_"
    assert exporter._sanitize_filename('path:name"test') == "path_name_test"
    assert exporter._sanitize_filename("") == "untitled"
    assert exporter._sanitize_filename("a" * 200) == "a" * 100


def test_html_player_exporter_format_time():
    """_format_time 格式化为 MM:SS"""
    exporter = HTMLPlayerExporter()
    assert exporter._format_time(0) == "00:00"
    assert exporter._format_time(5) == "00:05"
    assert exporter._format_time(60) == "01:00"
    assert exporter._format_time(125) == "02:05"
    assert exporter._format_time(3661) == "61:01"


def test_html_player_exporter_extract_highlights(tmp_path):
    """_extract_highlights_from_context 从 config 提取"""
    exporter = HTMLPlayerExporter()
    metadata = VideoMetadata(
        title="t", author="a", duration=1,
        platform="p", url="https://x.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        config={
            "highlights": [
                {"time": "00:01:00", "seconds": 60, "content": "要点A"},
                {"time": "00:02:00", "seconds": 120, "content": "要点B"},
            ]
        }
    )

    highlights = exporter._extract_highlights_from_context(context)
    assert len(highlights) == 2
    assert highlights[0].time == "00:01:00"
    assert highlights[0].seconds == 60
    assert highlights[0].content == "要点A"

    # Empty config
    context.config = {}
    assert exporter._extract_highlights_from_context(context) == []


def test_html_player_exporter_extract_subtitles(tmp_path):
    """_extract_subtitles_from_context 转换字幕"""
    exporter = HTMLPlayerExporter()
    metadata = VideoMetadata(
        title="t", author="a", duration=1,
        platform="p", url="https://x.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        transcript_segments=[
            TranscriptSegment(start=0, end=5, text="Hello"),
            TranscriptSegment(start=5, end=10, text="World"),
        ],
        config={}
    )

    subtitles = exporter._extract_subtitles_from_context(context)
    assert len(subtitles) == 2
    assert subtitles[0]["start"] == 0
    assert subtitles[0]["end"] == 5
    assert subtitles[0]["text"] == "Hello"
    assert subtitles[0]["start_formatted"] == "00:00"
    assert subtitles[1]["start_formatted"] == "00:05"


def test_html_player_exporter_export_success(tmp_path):
    """export 成功生成 HTML 文件"""
    video_path = tmp_path / "video.mp4"
    video_path.write_text("data")

    metadata = VideoMetadata(
        title="测试播放器", author="UP主", duration=180,
        platform="bilibili", url="https://bilibili.com/video"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        video_path=video_path,
        transcript_segments=[
            TranscriptSegment(start=0, end=5, text="第一句"),
        ],
        ai_summary="测试摘要",
        config={
            "highlights": [
                {"time": "00:01:00", "seconds": 60, "content": "关键内容"},
            ]
        }
    )

    # 通过 _generate_html 直接验证生成的 HTML
    exporter = HTMLPlayerExporter()
    highlights = exporter._extract_highlights_from_context(context)
    subtitles = exporter._extract_subtitles_from_context(context)
    html = exporter._generate_html(
        metadata=context.video_metadata,
        video_filename="video.mp4",
        audio_filename="",
        highlights=highlights,
        subtitles=subtitles,
        summary=context.ai_summary or ""
    )

    assert "<!DOCTYPE html>" in html
    assert "测试播放器" in html
    assert "UP主" in html
    assert "video.mp4" in html
    assert "测试摘要" in html
    assert "关键内容" in html
    assert "第一句" in html


def test_html_player_exporter_export_no_output_dir():
    """export 没有输出目录时返回错误"""
    metadata = VideoMetadata(
        title="无路径", author="a", duration=1,
        platform="p", url="https://x.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata, config={}
    )

    exporter = HTMLPlayerExporter()
    result = exporter.export(context)

    assert result.success is False
    assert "未找到输出目录" in result.error_msg


def test_html_player_exporter_export_audio_path(tmp_path):
    """使用直接生成方式测试 audio_path 路径"""
    audio_path = tmp_path / "audio.m4a"
    audio_path.write_text("data")

    exporter = HTMLPlayerExporter()
    metadata = VideoMetadata(
        title="音频播放器", author="a", duration=10,
        platform="youtube", url="https://youtube.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        audio_path=audio_path, config={}
    )

    # Verify the HTML content via _generate_html directly
    highlights = exporter._extract_highlights_from_context(context)
    subtitles = exporter._extract_subtitles_from_context(context)
    html = exporter._generate_html(
        metadata=metadata,
        video_filename="",
        audio_filename="audio.m4a",
        highlights=highlights,
        subtitles=subtitles,
        summary=""
    )
    assert "<!DOCTYPE html>" in html


def test_html_player_exporter_html_xss_escaping(tmp_path):
    """HTML 模板中的用户内容被正确转义（XSS 防护）"""
    exporter = HTMLPlayerExporter()

    # XSS payloads in metadata
    metadata = VideoMetadata(
        title='<script>alert("xss")</script>',
        author='<img src=x onerror=alert(1)>',
        duration=10,
        platform='"><script>bad()</script>',
        url="https://x.com"
    )

    html = exporter._generate_html(
        metadata=metadata,
        video_filename="video.mp4",
        audio_filename="",
        highlights=[],
        subtitles=[],
        summary='<script>alert("summary")</script>'
    )

    # Raw HTML tags should NOT appear - user content must be escaped
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<script>alert" not in html


def test_html_player_exporter_script_json_xss_escaping(tmp_path):
    """script 标签内的 JSON 数据被转义，防止 </script> 逃逸"""
    exporter = HTMLPlayerExporter()
    metadata = VideoMetadata(
        title="脚本注入测试", author="a", duration=10,
        platform="youtube", url="https://youtube.com"
    )

    payload = "</script><script>alert(1)</script>"
    from src.models.task import Highlight

    html = exporter._generate_html(
        metadata=metadata,
        video_filename="video.mp4",
        audio_filename="",
        highlights=[
            Highlight(time="00:01:00", seconds=60, content=payload)
        ],
        subtitles=[{"start": 0, "end": 1, "text": payload}],
        summary="正常摘要"
    )

    # 不允许出现原始的 </script> 逃逸序列 (JSON 已转义为 \u003c/\u003e)
    assert '</script><script>alert(1)</script>' not in html
    assert '\\u003c/script\\u003e' in html
    # HTML 解析后仍是合法 JS: 不允许提前闭合 script 标签
    assert html.count("<script>") == 1


def test_html_player_exporter_video_filename_escaping(tmp_path):
    """视频文件名嵌入 HTML 属性时被转义"""
    exporter = HTMLPlayerExporter()
    metadata = VideoMetadata(
        title="文件名转义", author="a", duration=10,
        platform="youtube", url="https://youtube.com"
    )

    html = exporter._generate_html(
        metadata=metadata,
        video_filename='evil" onload="alert(1)',
        audio_filename="",
        highlights=[],
        subtitles=[],
        summary=""
    )

    assert 'evil" onload="alert(1)' not in html
    assert "evil&quot; onload=&quot;alert(1)" in html


def test_html_player_exporter_html_template_structure(tmp_path):
    """生成 HTML 包含完整的模板结构"""
    exporter = HTMLPlayerExporter()
    metadata = VideoMetadata(
        title="结构测试", author="作者", duration=125,
        platform="bilibili", url="https://bilibili.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata,
        video_path=tmp_path / "video.mp4", ai_summary="摘要",
        config={
            "highlights": [
                {"time": "00:02:05", "seconds": 125, "content": "高光"},
            ]
        }
    )

    highlights = exporter._extract_highlights_from_context(context)
    subtitles = exporter._extract_subtitles_from_context(context)
    html = exporter._generate_html(
        metadata=metadata,
        video_filename="video.mp4",
        audio_filename="",
        highlights=highlights,
        subtitles=subtitles,
        summary="摘要"
    )

    # HTML structure checks
    assert '<!DOCTYPE html>' in html
    assert '<html lang="zh-CN">' in html
    assert '<meta charset="UTF-8">' in html
    assert '<video id="videoPlayer"' in html
    assert 'id="highlights"' in html
    assert 'id="subtitles"' in html
    assert '<script>' in html
    assert 'renderHighlights' in html
    assert 'renderSubtitles' in html
    assert 'timeupdate' in html


def test_html_player_exporter_export_no_highlights_no_subtitles(tmp_path):
    """无时间轴和字幕时也能生成 HTML"""
    exporter = HTMLPlayerExporter()
    metadata = VideoMetadata(
        title="空数据", author="作者", duration=10,
        platform="bilibili", url="https://bilibili.com"
    )
    context = ExportContext(
        task_id=uuid4(), video_metadata=metadata, config={}
    )

    highlights = exporter._extract_highlights_from_context(context)
    subtitles = exporter._extract_subtitles_from_context(context)
    html = exporter._generate_html(
        metadata=metadata,
        video_filename="",
        audio_filename="",
        highlights=highlights,
        subtitles=subtitles,
        summary=""
    )
    assert "<!DOCTYPE html>" in html


# =============================================================================
# Section 6: ExportContext / ExportResult error handling
# =============================================================================


def test_export_context_with_transcript_segments():
    """ExportContext 带转录段落"""
    metadata = VideoMetadata(
        title="转录测试", author="作者", duration=100,
        platform="bilibili", url="https://bilibili.com"
    )
    context = ExportContext(
        task_id=uuid4(),
        video_metadata=metadata,
        transcript_segments=[
            TranscriptSegment(start=0, end=5, text="段1"),
            TranscriptSegment(start=5, end=10, text="段2"),
        ],
        transcript_text="完整文本",
        ai_summary="摘要",
        config={"key": "value"}
    )

    assert len(context.transcript_segments) == 2
    assert context.transcript_text == "完整文本"
    assert context.config["key"] == "value"
    assert context.video_path is None


def test_export_context_with_file_paths(tmp_path):
    """ExportContext 带文件路径"""
    metadata = VideoMetadata(
        title="路径测试", author="作者", duration=100,
        platform="bilibili", url="https://bilibili.com"
    )
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.m4a"
    transcript = tmp_path / "transcript.txt"

    context = ExportContext(
        task_id=uuid4(),
        video_metadata=metadata,
        video_path=video,
        audio_path=audio,
        transcript_path=transcript,
        config={}
    )

    assert context.video_path == video
    assert context.audio_path == audio
    assert context.transcript_path == transcript


def test_export_result_with_error():
    """ExportResult 带错误信息"""
    result = ExportResult(
        success=False,
        target=ExportTarget.LOCAL,
        error_msg="权限不足"
    )

    assert result.success is False
    assert result.error_msg == "权限不足"
    assert result.target == ExportTarget.LOCAL
    assert result.output_path is None
    assert result.remote_url is None


def test_export_result_with_remote_url():
    """ExportResult 带远程 URL"""
    result = ExportResult(
        success=True,
        target=ExportTarget.WEBHOOK,
        output_path=None,
        remote_url="https://notion.so/page"
    )

    assert result.success is True
    assert result.target == ExportTarget.WEBHOOK
    assert result.remote_url == "https://notion.so/page"


def test_export_result_with_metadata():
    """ExportResult 带 metadata"""
    result = ExportResult(
        success=True,
        target=ExportTarget.LOCAL,
        output_path=Path("/output"),
        metadata={"files_created": 5, "organized_by": "date"}
    )

    assert result.metadata["files_created"] == 5
    assert result.metadata["organized_by"] == "date"


def test_export_result_obsidian_target():
    """ExportResult 使用 OBSIDIAN 目标"""
    result = ExportResult(
        success=True,
        target=ExportTarget.OBSIDIAN,
        output_path=Path("/vault/note.md"),
        metadata={"vault_path": "/vault", "subfolder": "Inbox"}
    )

    assert result.target == ExportTarget.OBSIDIAN
    assert result.output_path == Path("/vault/note.md")


def test_export_result_timestamp():
    """ExportResult 自动生成时间戳"""
    result1 = ExportResult(success=True, target=ExportTarget.LOCAL)
    assert result1.timestamp is not None
