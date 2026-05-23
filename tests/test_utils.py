"""工具函数测试"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.file_utils import sanitize_filename, safe_write_text
from src.utils.time_utils import format_time_for_srt, seconds_to_time_str
from src.utils.media_utils import generate_srt, Highlight
from src.models.task import TranscriptSegment


def test_sanitize_filename():
    """测试文件名清理"""
    print("=== 测试 sanitize_filename ===")
    
    test_cases = [
        ("正常文件名.txt", "正常文件名.txt"),
        ("文件/名:含*特?殊\"字符", "文件_名_含特殊字符"),
        ("  前后空格  ", "前后空格"),
        ("a" * 300, "a" * 255),  # 超长文件名
    ]
    
    for input_name, expected in test_cases:
        result = sanitize_filename(input_name)
        print(f"  输入: {input_name[:30]}...")
        print(f"  输出: {result[:30]}...")
        assert len(result) <= 255, "文件名长度应限制在255字符以内"
    
    print("  ✓ sanitize_filename 测试通过")
    return True


def test_safe_write_text():
    """测试安全写入"""
    print("\n=== 测试 safe_write_text ===")
    
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.txt"
        content = "测试内容\n多行内容"
        
        success = safe_write_text(test_file, content)
        assert success, "写入应成功"
        assert test_file.exists(), "文件应存在"
        
        read_content = test_file.read_text(encoding="utf-8")
        assert read_content == content, "内容应一致"
        
        print("  ✓ safe_write_text 测试通过")
    
    return True


def test_format_time_for_srt():
    """测试 SRT 时间格式"""
    print("\n=== 测试 format_time_for_srt ===")
    
    test_cases = [
        (0, "00:00:00,000"),
        (1.5, "00:00:01,500"),
        (61.234, "00:01:01,234"),
        (3661.0, "01:01:01,000"),
    ]
    
    for seconds, expected in test_cases:
        result = format_time_for_srt(seconds)
        assert result == expected, f"{seconds}s 应为 {expected}，实际 {result}"
        print(f"  {seconds}s -> {result}")
    
    print("  ✓ format_time_for_srt 测试通过")
    return True


def test_seconds_to_time_str():
    """测试时间字符串转换"""
    print("\n=== 测试 seconds_to_time_str ===")
    
    test_cases = [
        (0, "[00:00:00]"),
        (65, "[00:01:05]"),
        (3665, "[01:01:05]"),
    ]
    
    for seconds, expected in test_cases:
        result = seconds_to_time_str(seconds)
        assert result == expected, f"{seconds}s 应为 {expected}，实际 {result}"
        print(f"  {seconds}s -> {result}")
    
    print("  ✓ seconds_to_time_str 测试通过")
    return True


def test_generate_srt():
    """测试 SRT 生成"""
    print("\n=== 测试 generate_srt ===")
    
    segments = [
        TranscriptSegment(0, 5, "第一句"),
        TranscriptSegment(5, 10, "第二句"),
        TranscriptSegment(10, 15, "第三句"),
    ]
    
    srt_content = generate_srt(segments)
    
    assert "1\n00:00:00,000 --> 00:00:05,000" in srt_content, "应包含第一句"
    assert "第二句" in srt_content, "应包含第二句"
    assert "第三句" in srt_content, "应包含第三句"
    
    print("  SRT 内容预览:")
    print(srt_content[:200])
    print("  ✓ generate_srt 测试通过")
    return True


def test_highlight_class():
    """测试 Highlight 类"""
    print("\n=== 测试 Highlight 类 ===")
    
    highlight = Highlight(time="00:05:00", seconds=300, content="测试要点")
    
    assert highlight.time == "00:05:00"
    assert highlight.seconds == 300
    assert highlight.content == "测试要点"
    
    print("  ✓ Highlight 类测试通过")
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("工具函数测试套件")
    print("=" * 50)
    
    all_passed = True
    all_passed &= test_sanitize_filename()
    all_passed &= test_safe_write_text()
    all_passed &= test_format_time_for_srt()
    all_passed &= test_seconds_to_time_str()
    all_passed &= test_generate_srt()
    all_passed &= test_highlight_class()
    
    print("\n" + "=" * 50)
    if all_passed:
        print("✓ 所有测试通过")
    else:
        print("✗ 部分测试失败")
    print("=" * 50)
