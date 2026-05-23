"""导出器测试"""

import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.exporters.base import BaseExporter
from src.exporters.local_exporter import LocalExporter
from src.models.task import ExportContext, ExportResult, ExportTarget, VideoMetadata


def test_base_exporter_interface():
    """测试 BaseExporter 接口定义"""
    print("\n=== 测试 BaseExporter 接口 ===")
    
    # 检查抽象方法
    assert hasattr(BaseExporter, 'name')
    assert hasattr(BaseExporter, 'icon')
    assert hasattr(BaseExporter, 'validate_config')
    assert hasattr(BaseExporter, 'export')
    
    print("  ✓ BaseExporter 接口定义正确")
    return True


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
    
    return True


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
    
    return True


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
    return True


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
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("导出器测试套件")
    print("=" * 50)
    
    all_passed = True
    all_passed &= test_base_exporter_interface()
    all_passed &= test_local_exporter_init()
    all_passed &= test_local_exporter_validate()
    all_passed &= test_export_context_creation()
    all_passed &= test_export_result_creation()
    
    print("\n" + "=" * 50)
    if all_passed:
        print("✓ 所有测试通过")
    else:
        print("✗ 部分测试失败")
    print("=" * 50)
