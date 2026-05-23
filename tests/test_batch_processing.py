"""批量处理功能测试"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.gui.widgets.url_input import URLInputWidget
from PySide6.QtWidgets import QApplication


def test_url_extraction():
    """测试 URL 提取功能"""
    print("\n=== 测试 URL 提取功能 ===")

    import re

    # 测试文本包含各种格式的 URL
    test_cases = [
        {
            "name": "标准链接",
            "input": "https://www.bilibili.com/video/BV1xx411c7mD",
            "expected_count": 1
        },
        {
            "name": "多平台链接",
            "input": """
https://www.bilibili.com/video/BV1xx411c7mD
https://www.youtube.com/watch?v=dQw4w9WgXcQ
https://www.xiaohongshu.com/explore/123456
https://www.douyin.com/video/123456
            """,
            "expected_count": 4
        },
        {
            "name": "混合文本",
            "input": """
看看这个视频：https://www.bilibili.com/video/BV1xx
还有这个 https://www.youtube.com/watch?v=abc123 也不错
无效链接: not-a-url
            """,
            "expected_count": 2
        },
        {
            "name": "短链接",
            "input": "https://b23.tv/xxxxx\nhttps://youtu.be/xxxxx",
            "expected_count": 2
        }
    ]

    url_pattern = r'https?://(?:[^\s<>"\']+\.)?(?:bilibili\.com|b23\.tv|youtube\.com|youtu\.be|xiaohongshu\.com|xhs\.link|douyin\.com|iesdouyin\.com|tiktok\.com)[^\s<>"\']*'

    all_passed = True
    for case in test_cases:
        urls = re.findall(url_pattern, case["input"], re.IGNORECASE)
        actual_count = len(urls)

        if actual_count == case["expected_count"]:
            print(f"  ✓ {case['name']}: 提取到 {actual_count} 个 URL")
        else:
            print(f"  ✗ {case['name']}: 期望 {case['expected_count']} 个，实际 {actual_count} 个")
            all_passed = False

    return all_passed


def test_valid_platform_filtering():
    """测试平台过滤功能"""
    print("\n=== 测试平台过滤功能 ===")

    valid_platforms = [
        'bilibili.com', 'b23.tv',
        'youtube.com', 'youtu.be',
        'xiaohongshu.com', 'xhs.link',
        'douyin.com', 'iesdouyin.com',
        'tiktok.com'
    ]

    test_urls = [
        ("https://www.bilibili.com/video/BV1xx", True),
        ("https://b23.tv/xxxxx", True),
        ("https://www.youtube.com/watch?v=xxx", True),
        ("https://youtu.be/xxxxx", True),
        ("https://www.xiaohongshu.com/explore/123", True),
        ("https://www.douyin.com/video/123", True),
        ("https://www.tiktok.com/@user/video/123", True),
        ("https://www.google.com", False),
        ("https://www.baidu.com", False),
        ("not-a-url", False),
    ]

    all_passed = True
    for url, expected_valid in test_urls:
        url_lower = url.lower()
        is_valid = any(platform in url_lower for platform in valid_platforms)

        if is_valid == expected_valid:
            status = "✓" if expected_valid else "✓"
            print(f"  {status} {url[:50]}... -> {'有效' if is_valid else '无效'}")
        else:
            print(f"  ✗ {url[:50]}... -> 期望 {'有效' if expected_valid else '无效'}，实际 {'有效' if is_valid else '无效'}")
            all_passed = False

    return all_passed


def main():
    """运行所有测试"""
    print("=" * 50)
    print("批量处理功能测试套件")
    print("=" * 50)

    all_passed = True

    # 运行测试
    all_passed &= test_url_extraction()
    all_passed &= test_valid_platform_filtering()

    print("\n" + "=" * 50)
    if all_passed:
        print("✓ 所有测试通过")
    else:
        print("✗ 部分测试失败")
    print("=" * 50)

    return 0 if all_passed else 1


if __name__ == "__main__":
    # 创建 QApplication 实例（某些 Qt 功能需要）
    app = QApplication(sys.argv)
    sys.exit(main())
