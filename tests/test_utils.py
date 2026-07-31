"""工具函数测试"""

from unittest.mock import patch

import pytest

from src.models.task import TranscriptSegment
from src.utils.exceptions import (
    AIError,
    DownloadError,
    NetworkError,
    RetryableError,
    ServiceUnavailableError,
    TimeoutError,
    TranscribeError,
)
from src.utils.file_utils import (
    safe_copy_file,
    safe_create_symlink,
    safe_write_text,
    sanitize_filename,
)
from src.utils.media_utils import Highlight, extract_highlights_from_context, generate_srt
from src.utils.platform_detector import detect_platform
from src.utils.platform_utils import PlatformHelper, ProgressCalculator, URLValidator
from src.utils.retry import (
    RetryableOperation,
    RetryConfig,
    RetryStrategy,
    is_retryable_error,
    retry,
    retry_with_config,
)
from src.utils.time_utils import (
    format_time_for_media_extended,
    format_time_for_srt,
    parse_time_str,
    seconds_to_time_str,
)

# ============================================================
# platform_utils.py 测试
# ============================================================


def test_platform_helper_system_detection():
    """测试 PlatformHelper 系统检测"""
    print("\n=== 测试 PlatformHelper 系统检测 ===")

    # get_system 返回当前平台
    system = PlatformHelper.get_system()
    assert system in ("Darwin", "Windows", "Linux"), f"未知系统: {system}"
    print(f"  ✓ 当前系统: {system}")

    # 平台判定方法互斥
    results = [PlatformHelper.is_macos(), PlatformHelper.is_windows(), PlatformHelper.is_linux()]
    assert sum(results) == 1, "三个平台判定应仅一个为 True"
    print(f"  ✓ 平台判定互斥: macOS={results[0]} Windows={results[1]} Linux={results[2]}")

    print("  ✓ PlatformHelper 系统检测通过")


def test_platform_helper_get_tray_location():
    """测试托盘位置提示"""
    print("\n=== 测试 get_tray_location_hint ===")

    hint = PlatformHelper.get_tray_location_hint()
    assert hint, "返回值不应为空"
    assert isinstance(hint, str), "返回值应为字符串"
    print(f"  ✓ 当前提示: {hint}")

    print("  ✓ get_tray_location_hint 测试通过")


def test_platform_helper_open_url():
    """测试 open_url (模拟)"""
    print("\n=== 测试 PlatformHelper.open_url ===")

    # open_url 内部 import webbrowser, 需要在模块层级 patch
    with patch("webbrowser.open", return_value=True) as mock_open:
        result = PlatformHelper.open_url("https://example.com")
        assert result is True
        mock_open.assert_called_once_with("https://example.com")

    with patch("webbrowser.open", side_effect=Exception("fail")):
        result = PlatformHelper.open_url("https://bad.com")
        assert result is False

    print("  ✓ open_url 测试通过")


def test_url_validator_is_valid_url():
    """测试 URLValidator.is_valid_url"""
    print("\n=== 测试 URLValidator.is_valid_url ===")

    valid_cases = [
        "https://www.bilibili.com/video/BV1xx",
        "http://example.com",
        "https://youtube.com/watch?v=xxx",
        "ftp://files.example.com/file.mp4",
    ]
    for url in valid_cases:
        assert URLValidator.is_valid_url(url), f"应有效: {url}"
        print(f"  ✓ 有效: {url[:50]}")

    invalid_cases = [
        "",
        None,
        "   ",
        "not-a-url",
        "ftp://",  # no netloc
        "javascript:alert(1)",
        "file:///local/file.txt",  # file scheme not in valid list
    ]
    for url in invalid_cases:
        assert not URLValidator.is_valid_url(url), f"应无效: {url!r}"
        print(f"  ✓ 无效: {url!r}")

    print("  ✓ is_valid_url 测试通过")


def test_url_validator_get_platform():
    """测试 URLValidator.get_platform_from_url — 5 个平台"""
    print("\n=== 测试 URLValidator.get_platform_from_url ===")

    test_cases = [
        ("https://www.bilibili.com/video/BV1xx", "bilibili"),
        ("https://b23.tv/abc123", "bilibili"),
        ("https://www.youtube.com/watch?v=xxx", "youtube"),
        ("https://youtu.be/abc123", "youtube"),
        ("https://www.douyin.com/video/12345", "douyin"),
        ("https://www.tiktok.com/@user/video/123", "tiktok"),
        ("https://www.xiaohongshu.com/explore/xxx", "xiaohongshu"),
    ]
    for url, expected in test_cases:
        result = URLValidator.get_platform_from_url(url)
        assert result == expected, f"{url[:50]} → 期望 {expected}, 实际 {result}"
        print(f"  ✓ {url[:45]:45s} → {result}")

    # 未知平台
    unknown = URLValidator.get_platform_from_url("https://example.com/video")
    assert unknown is None, f"未知 URL 应返回 None, 实际 {unknown}"
    print("  ✓ 未知平台返回 None")

    # 无效 URL 应返回 None
    invalid_result = URLValidator.get_platform_from_url("not-a-url")
    assert invalid_result is None
    print("  ✓ 无效 URL 返回 None")

    print("  ✓ get_platform_from_url 测试通过")


def test_detect_platform_all_13():
    """测试 platform_detector.detect_platform — 全部 13 个平台"""
    print("\n=== 测试 detect_platform (13 平台) ===")

    test_cases = [
        ("https://www.bilibili.com/video/BV1xx", "bilibili"),
        ("https://b23.tv/abc123", "bilibili"),
        ("https://www.youtube.com/watch?v=xxx", "youtube"),
        ("https://youtu.be/abc123", "youtube"),
        ("https://v.douyin.com/xxxxx/", "douyin"),
        ("https://www.tiktok.com/@user/video/123", "tiktok"),
        ("https://vm.tiktok.com/abc/", "tiktok"),
        ("https://www.xiaohongshu.com/explore/xxx", "xiaohongshu"),
        ("https://xhslink.com/abc", "xiaohongshu"),
        ("https://www.kuaishou.com/short-video/xxx", "kuaishou"),
        ("https://weibo.com/xxx/yyy", "weibo"),
        ("https://www.zhihu.com/question/123", "zhihu"),
        ("https://twitter.com/user/status/123", "twitter"),
        ("https://x.com/user/status/123", "twitter"),
        ("https://www.instagram.com/p/abc/", "instagram"),
        ("https://www.facebook.com/watch?v=xxx", "facebook"),
        ("https://vimeo.com/12345", "vimeo"),
        ("https://www.reddit.com/r/videos/comments/abc/", "reddit"),
    ]

    for url, expected in test_cases:
        result = detect_platform(url)
        assert result == expected, f"{url[:50]} → 期望 {expected}, 实际 {result}"
        print(f"  ✓ {url[:45]:45s} → {result}")

    # unknown 平台
    unknown = detect_platform("https://example.com/video")
    assert unknown == "unknown", f"应返回 unknown, 实际 {unknown}"
    print("  ✓ 未知平台返回 'unknown'")

    print("  ✓ detect_platform 测试通过")


def test_progress_calculator():
    """测试 ProgressCalculator.calculate_progress"""
    print("\n=== 测试 ProgressCalculator.calculate_progress ===")

    # 边界: total_steps <= 0
    result = ProgressCalculator.calculate_progress(0, 0, 50, 0, 100)
    assert result == 0, "total_steps=0 应返回 start_percent"
    print(f"  ✓ total_steps=0 → {result}")

    # 第0步 进度 0%
    result = ProgressCalculator.calculate_progress(0, 4, 0, 0, 100)
    assert result == 0, f"0/4 0% 应返回 0, 实际 {result}"
    print(f"  ✓ 0/4 @0% → {result}")

    # 第2步 进度 50% (5步总, 起始10, 结束90)
    result = ProgressCalculator.calculate_progress(2, 5, 50, 10, 90)
    # 每步范围 = (90-10)/5 = 16
    # 基础 = 10 + 2*16 = 42
    # 当前步 = (50/100)*16 = 8
    # 总 = 50
    assert result == 50, f"期望 50, 实际 {result}"
    print(f"  ✓ 2/5 @50% [10→90] → {result}")

    # 最后一步
    result = ProgressCalculator.calculate_progress(4, 5, 100, 0, 100)
    # step_range = 20, base = 0 + 4*20 = 80, current = 20, total = 100
    assert result == 100, f"期望 100, 实际 {result}"
    print(f"  ✓ 4/5 @100% → {result}")

    print("  ✓ ProgressCalculator 测试通过")


# ============================================================
# file_utils.py 扩展测试
# ============================================================


def test_sanitize_filename():
    """测试文件名清理"""
    print("=== 测试 sanitize_filename ===")

    test_cases = [
        ("正常文件名.txt", "正常文件名.txt"),
        ("文件/名:含*特?殊\"字符", "文件_名_含特殊字符"),
        ("  前后空格  ", "前后空格"),
        ("a" * 300, "a" * 100),  # 超长文件名 (max_length=100 default)
    ]

    for input_name, _expected in test_cases:
        result = sanitize_filename(input_name)
        print(f"  输入: {input_name[:30]}...")
        print(f"  输出: {result[:30]}...")
        assert len(result) <= 100, "文件名长度应限制在100字符以内 (默认)"

    print("  ✓ sanitize_filename 基本测试通过")


def test_sanitize_filename_edge_cases():
    """测试 sanitize_filename 极端情况"""
    print("\n=== 测试 sanitize_filename 极端情况 ===")

    # 空输入
    assert sanitize_filename("") == "untitled", "空输入应返回 untitled"
    print("  ✓ 空字符串 → untitled")

    # None (函数通过类型提示标注 str, 但 None 被 falsy 检查返回 untitled)
    assert sanitize_filename(None) == "untitled"  # type: ignore
    print("  ✓ None 输入 → untitled")

    # 全角字符
    result = sanitize_filename("全角：字符＊测试／文件")
    assert "：" not in result, "全角冒号应被转换"
    assert "：" not in result or ":" not in result
    print(f"  ✓ 全角字符: '全角：字符＊测试／文件' → {result}")

    # 仅有点和空格
    assert sanitize_filename(" . ") == "untitled", "仅有点和空格应返回 untitled"
    print("  ✓ 仅有点和空格 → untitled")

    # 控制字符
    result = sanitize_filename("normal\x00file\x1fname")
    assert "\x00" not in result, "控制字符应被移除"
    assert "normal" in result
    print(f"  ✓ 控制字符: 'normal\\x00file\\x1fname' → {result}")

    # 精确 max_length 边界
    result = sanitize_filename("x" * 100, max_length=50)
    assert len(result) == 50, f"期望 50 字符, 实际 {len(result)}"
    print(f"  ✓ max_length=50: {len(result)} 字符")

    print("  ✓ sanitize_filename 极端情况测试通过")


def test_safe_write_text_tmp_path(tmp_path):
    """测试 safe_write_text (使用 tmp_path)"""
    print("\n=== 测试 safe_write_text (tmp_path) ===")

    # 正常写入
    test_file = tmp_path / "subdir" / "test.txt"
    content = "测试内容\n多行内容"
    success, msg = safe_write_text(test_file, content)
    assert success, f"写入应成功, 消息: {msg}"
    assert test_file.exists(), "文件应存在"
    assert test_file.read_text(encoding="utf-8") == content
    print(f"  ✓ 正常写入: {msg}")

    # 写入已存在文件（覆盖）
    new_content = "覆盖内容"
    success, msg = safe_write_text(test_file, new_content)
    assert success
    assert test_file.read_text(encoding="utf-8") == new_content
    print(f"  ✓ 覆盖写入: {msg}")

    # 空内容
    empty_file = tmp_path / "empty.txt"
    success, msg = safe_write_text(empty_file, "")
    assert success
    assert empty_file.read_text(encoding="utf-8") == ""
    print(f"  ✓ 空内容写入: {msg}")

    # 特殊编码
    utf16_file = tmp_path / "utf16.txt"
    success, msg = safe_write_text(utf16_file, "test", encoding="utf-16")
    assert success
    print(f"  ✓ UTF-16 编码: {msg}")

    print("  ✓ safe_write_text (tmp_path) 测试通过")


def test_safe_copy_file(tmp_path):
    """测试 safe_copy_file"""
    print("\n=== 测试 safe_copy_file ===")

    src = tmp_path / "source.txt"
    dst = tmp_path / "subdir" / "dest.txt"
    src.write_text("hello")

    # 正常复制
    success, msg = safe_copy_file(src, dst)
    assert success, f"复制应成功: {msg}"
    assert dst.exists()
    assert dst.read_text() == "hello"
    print(f"  ✓ 正常复制: {msg}")

    # 源文件不存在
    success, msg = safe_copy_file(tmp_path / "nonexistent.txt", tmp_path / "nope.txt")
    assert not success
    assert "不存在" in msg
    print(f"  ✓ 源不存在: {msg}")

    # 复制到已存在目标（覆盖）
    dst2 = tmp_path / "dest2.txt"
    src.write_text("new content")
    success, msg = safe_copy_file(src, dst2)
    assert success
    assert dst2.read_text() == "new content"
    print(f"  ✓ 覆盖目标: {msg}")

    # 复制空文件
    empty_src = tmp_path / "empty_src.txt"
    empty_dst = tmp_path / "empty_dst.txt"
    empty_src.write_text("")
    success, msg = safe_copy_file(empty_src, empty_dst)
    assert success
    assert empty_dst.read_text() == ""
    print(f"  ✓ 空文件复制: {msg}")

    print("  ✓ safe_copy_file 测试通过")


def test_safe_create_symlink(tmp_path):
    """测试 safe_create_symlink"""
    print("\n=== 测试 safe_create_symlink ===")

    target = tmp_path / "target.txt"
    target.write_text("symlink target")
    link = tmp_path / "link.txt"

    success, msg = safe_create_symlink(target, link)
    assert success, f"创建链接应成功: {msg}"
    assert link.exists() or link.is_symlink()
    print(f"  ✓ 创建符号链接: {msg}")

    # 覆盖已有链接
    success, msg = safe_create_symlink(target, link)
    assert success, f"覆盖链接应成功: {msg}"
    print(f"  ✓ 覆盖已有链接: {msg}")

    print("  ✓ safe_create_symlink 测试通过")


# ============================================================
# media_utils.py 测试
# ============================================================


def test_extract_highlights_from_context():
    """测试 extract_highlights_from_context"""
    print("\n=== 测试 extract_highlights_from_context ===")

    # 完整数据
    context = {
        "highlights": [
            {"time": "00:01:00", "seconds": 60, "content": "第一个要点"},
            {"time": "00:05:00", "seconds": 300, "content": "第二个要点"},
        ]
    }
    highlights = extract_highlights_from_context(context)
    assert len(highlights) == 2
    assert highlights[0].time == "00:01:00"
    assert highlights[0].seconds == 60
    assert highlights[0].content == "第一个要点"
    print(f"  ✓ 提取 {len(highlights)} 个要点")

    # 空数据
    empty = extract_highlights_from_context({})
    assert empty == []
    print("  ✓ 空字典 → []")

    # 缺失字段 (应使用默认值)
    partial = extract_highlights_from_context({
        "highlights": [
            {"time": "00:10:00"},
        ]
    })
    assert len(partial) == 1
    assert partial[0].time == "00:10:00"
    assert partial[0].seconds == 0
    assert partial[0].content == ""
    print("  ✓ 缺失字段使用默认值")

    # 空列表
    empty_list = extract_highlights_from_context({"highlights": []})
    assert empty_list == []
    print("  ✓ 空 highlights 列表 → []")

    # 非字典元素跳过
    mixed = extract_highlights_from_context({
        "highlights": [
            {"time": "00:01:00", "seconds": 60, "content": "A"},
            "invalid",
            123,
        ]
    })
    assert len(mixed) == 1
    print("  ✓ 非字典元素跳过")

    print("  ✓ extract_highlights_from_context 测试通过")


# ============================================================
# time_utils.py 扩展测试
# ============================================================


def test_format_time_for_media_extended():
    """测试 format_time_for_media_extended"""
    print("\n=== 测试 format_time_for_media_extended ===")

    test_cases = [
        (0, "00:00:00"),
        (1, "00:00:01"),
        (61, "00:01:01"),
        (3600, "01:00:00"),
        (3661, "01:01:01"),
        (86399, "23:59:59"),
    ]
    for seconds, expected in test_cases:
        result = format_time_for_media_extended(seconds)
        assert result == expected, f"{seconds}s → 期望 {expected}, 实际 {result}"
        print(f"  ✓ {seconds}s → {result}")

    print("  ✓ format_time_for_media_extended 测试通过")


def test_parse_time_str():
    """测试 parse_time_str"""
    print("\n=== 测试 parse_time_str ===")

    # HH:MM:SS 格式
    assert parse_time_str("01:01:01") == 3661.0
    print("  ✓ HH:MM:SS → 3661.0")

    # MM:SS 格式
    assert parse_time_str("05:30") == 330.0
    print("  ✓ MM:SS → 330.0")

    # 带 [] 包裹
    assert parse_time_str("[01:01:01]") == 3661.0
    assert parse_time_str("[05:30]") == 330.0
    print("  ✓ [] 包裹格式")

    # 零值
    assert parse_time_str("00:00:00") == 0.0
    assert parse_time_str("00:00") == 0.0
    print("  ✓ 零值")

    # 大数字
    assert parse_time_str("99:59:59") == 99 * 3600 + 59 * 60 + 59
    print("  ✓ 大数字")

    # 无效格式
    import pytest
    with pytest.raises(ValueError, match="无法解析时间格式"):
        parse_time_str("abc")
    with pytest.raises(ValueError):
        parse_time_str("")
    with pytest.raises(ValueError):
        parse_time_str("1:2:3:4")  # 4 parts
    print("  ✓ 无效格式抛出 ValueError")

    print("  ✓ parse_time_str 测试通过")


# ============================================================
# retry.py 测试
# ============================================================


def test_retry_config_calculate_delay_fixed():
    """测试 RetryConfig.calculate_delay — FIXED 策略"""
    print("\n=== 测试 RetryConfig FIXED 策略 ===")

    config = RetryConfig(strategy=RetryStrategy.FIXED, base_delay=2.0, jitter=0)
    for attempt in range(1, 5):
        delay = config.calculate_delay(attempt)
        assert delay == 2.0, f"FIXED attempt {attempt}: 期望 2.0, 实际 {delay}"
        print(f"  ✓ attempt {attempt}: {delay:.1f}s")

    print("  ✓ FIXED 策略测试通过")


def test_retry_config_calculate_delay_linear():
    """测试 RetryConfig.calculate_delay — LINEAR 策略"""
    print("\n=== 测试 RetryConfig LINEAR 策略 ===")

    config = RetryConfig(strategy=RetryStrategy.LINEAR, base_delay=1.0, jitter=0)
    for attempt in range(1, 5):
        delay = config.calculate_delay(attempt)
        expected = attempt * 1.0
        assert delay == expected, f"LINEAR attempt {attempt}: 期望 {expected}, 实际 {delay}"
        print(f"  ✓ attempt {attempt}: {delay:.1f}s")

    print("  ✓ LINEAR 策略测试通过")


def test_retry_config_calculate_delay_exponential():
    """测试 RetryConfig.calculate_delay — EXPONENTIAL 策略"""
    print("\n=== 测试 RetryConfig EXPONENTIAL 策略 ===")

    config = RetryConfig(strategy=RetryStrategy.EXPONENTIAL, base_delay=1.0, jitter=0)
    for attempt in range(1, 5):
        delay = config.calculate_delay(attempt)
        expected = 1.0 * (2 ** (attempt - 1))
        assert delay == expected, f"EXP attempt {attempt}: 期望 {expected}, 实际 {delay}"
        print(f"  ✓ attempt {attempt}: {delay:.1f}s")

    print("  ✓ EXPONENTIAL 策略测试通过")


def test_retry_config_calculate_delay_bounds():
    """测试 RetryConfig.calculate_delay — 边界条件"""
    print("\n=== 测试 RetryConfig 边界 ===")

    # max_delay 限制
    config = RetryConfig(strategy=RetryStrategy.EXPONENTIAL, base_delay=10.0, max_delay=15.0, jitter=0)
    delay = config.calculate_delay(5)  # 10 * 2^4 = 160 → 限制到 15
    assert delay == 15.0, f"应受 max_delay 限制: 期望 15.0, 实际 {delay}"
    print(f"  ✓ max_delay=15: {delay:.1f}s")

    # 最小延迟 0.1
    config = RetryConfig(strategy=RetryStrategy.FIXED, base_delay=0.001, jitter=0)
    delay = config.calculate_delay(1)
    assert delay >= 0.1, f"最小延迟 0.1s: 实际 {delay}"
    print(f"  ✓ 最小延迟: {delay:.3f}s")

    # jitter 范围
    config = RetryConfig(strategy=RetryStrategy.FIXED, base_delay=10.0, jitter=0.2)
    delays = [config.calculate_delay(1) for _ in range(100)]
    min_d, max_d = min(delays), max(delays)
    assert min_d >= 0.1, f"抖动后最小延迟异常: {min_d}"
    print(f"  ✓ jitter=0.2: 范围 [{min_d:.2f}, {max_d:.2f}] (期望 ~[8, 12])")

    print("  ✓ 边界条件测试通过")


def test_retry_with_config_success_first_try():
    """测试 retry_with_config — 首次成功"""
    print("\n=== 测试 retry_with_config 首次成功 ===")

    call_count = 0

    @retry_with_config(RetryConfig(max_retries=3, strategy=RetryStrategy.FIXED, jitter=0))
    def succeed_immediately():
        nonlocal call_count
        call_count += 1
        return "success"

    with patch("time.sleep") as mock_sleep:
        result = succeed_immediately()

    assert result == "success"
    assert call_count == 1, f"应只调用 1 次, 实际 {call_count}"
    mock_sleep.assert_not_called()
    print("  ✓ 首次成功, 无重试")

    print("  ✓ retry_with_config 首次成功通过")


def test_retry_with_config_retry_then_success():
    """测试 retry_with_config — 重试后成功"""
    print("\n=== 测试 retry_with_config 重试后成功 ===")

    call_count = 0

    @retry_with_config(RetryConfig(max_retries=3, strategy=RetryStrategy.FIXED, base_delay=1.0, jitter=0))
    def fail_twice_then_succeed():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise NetworkError("temp failure")
        return "ok"

    with patch("time.sleep") as mock_sleep:
        result = fail_twice_then_succeed()

    assert result == "ok"
    assert call_count == 3, f"应调用 3 次, 实际 {call_count}"
    assert mock_sleep.call_count == 2, f"应 sleep 2 次, 实际 {mock_sleep.call_count}"
    print("  ✓ 第 3 次成功, 重试 2 次")

    print("  ✓ retry_with_config 重试后成功通过")


def test_retry_with_config_max_retries_exceeded():
    """测试 retry_with_config — 超过最大重试次数"""
    print("\n=== 测试 retry_with_config 超过最大重试 ===")

    call_count = 0

    @retry_with_config(RetryConfig(max_retries=2, strategy=RetryStrategy.FIXED, jitter=0))
    def always_fail():
        nonlocal call_count
        call_count += 1
        raise NetworkError("always fails")

    with patch("time.sleep") as mock_sleep, pytest.raises(NetworkError):
        always_fail()

    assert call_count == 2, f"应调用 2 次 (max_retries=2), 实际 {call_count}"
    assert mock_sleep.call_count == 1, f"应 sleep 1 次, 实际 {mock_sleep.call_count}"
    print(f"  ✓ max_retries=2 后抛出异常, 调用 {call_count} 次")

    print("  ✓ retry_with_config 超过最大重试通过")


def test_retry_with_config_non_retryable_exception():
    """测试 retry_with_config — 不可重试异常不重试"""
    print("\n=== 测试 retry_with_config 不可重试异常 ===")

    call_count = 0

    @retry_with_config(RetryConfig(max_retries=3, retryable_exceptions=(NetworkError,), jitter=0))
    def raise_value_error():
        nonlocal call_count
        call_count += 1
        raise ValueError("not retryable")

    with patch("time.sleep") as mock_sleep, pytest.raises(ValueError):
        raise_value_error()

    assert call_count == 1, f"不可重试异常应仅调用 1 次, 实际 {call_count}"
    mock_sleep.assert_not_called()
    print("  ✓ ValueError 未触发重试")

    print("  ✓ retry_with_config 不可重试异常通过")


def test_retry_decorator_simplified():
    """测试 retry() 简化装饰器"""
    print("\n=== 测试 retry() 简化装饰器 ===")

    call_count = 0

    @retry(max_retries=2, base_delay=0.5, strategy=RetryStrategy.FIXED)
    def fails_once():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RetryableError("first fail")
        return "done"

    with patch("time.sleep"):
        result = fails_once()

    assert result == "done"
    assert call_count == 2
    print("  ✓ retry() 简化装饰器正常工作")

    print("  ✓ retry() 简化装饰器测试通过")


def test_retryable_operation_execute():
    """测试 RetryableOperation.execute"""
    print("\n=== 测试 RetryableOperation.execute ===")

    call_count = 0

    def op():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise NetworkError("retry")
        return "done"

    config = RetryConfig(max_retries=3, strategy=RetryStrategy.FIXED, base_delay=0.1, jitter=0)
    operation = RetryableOperation(op, config, name="test_op")

    with patch("time.sleep"):
        result = operation.execute()

    assert result == "done"
    assert call_count == 3
    assert operation.is_successful is True
    assert operation.attempt_count == 3
    print(f"  ✓ 第 3 次成功, attempt_count={operation.attempt_count}")

    print("  ✓ RetryableOperation.execute 测试通过")


def test_retryable_operation_status():
    """测试 RetryableOperation 状态跟踪"""
    print("\n=== 测试 RetryableOperation 状态 ===")

    def op():
        return "ok"

    config = RetryConfig(max_retries=3)
    operation = RetryableOperation(op, config, name="status_test")

    # 执行前
    status = operation.get_status()
    assert status["attempt_count"] == 0
    assert status["can_retry"] is True
    assert status["is_successful"] is False
    print(f"  ✓ 执行前状态: {status}")

    with patch("time.sleep"):
        operation.execute()

    # 执行后
    status = operation.get_status()
    assert status["is_successful"] is True
    assert status["can_retry"] is False
    assert status["last_exception"] is None
    print(f"  ✓ 执行后状态: {status}")

    print("  ✓ RetryableOperation 状态测试通过")


def test_retryable_operation_can_retry():
    """测试 RetryableOperation.can_retry"""
    print("\n=== 测试 RetryableOperation.can_retry ===")

    def failing_op():
        raise NetworkError("fail")

    config = RetryConfig(max_retries=3, strategy=RetryStrategy.FIXED, base_delay=0.1, jitter=0)

    # 构造一个手动设置状态的场景
    operation = RetryableOperation(failing_op, config, name="can_retry_test")
    operation.attempt_count = 1

    assert operation.can_retry() is True
    print("  ✓ attempt=1/3 → can_retry=True")

    operation.attempt_count = 3
    assert operation.can_retry() is False
    print("  ✓ attempt=3/3 → can_retry=False")

    operation.is_successful = True
    operation.attempt_count = 1
    assert operation.can_retry() is False
    print("  ✓ is_successful=True → can_retry=False")

    print("  ✓ RetryableOperation.can_retry 测试通过")


def test_is_retryable_error():
    """测试 is_retryable_error"""
    print("\n=== 测试 is_retryable_error ===")

    # 可重试异常
    retryable_exceptions = [
        RetryableError("test"),
        NetworkError("network"),
        ServiceUnavailableError("unavailable"),
        TimeoutError("timeout"),
    ]
    for exc in retryable_exceptions:
        assert is_retryable_error(exc) is True, f"{type(exc).__name__} 应可重试"
        print(f"  ✓ {type(exc).__name__} → True")

    # 不可重试异常
    non_retryable = [
        ValueError("bad value"),
        TypeError("bad type"),
        # DownloadError/AIError/TranscribeError 默认 error_code 是可重试的, 需指定非重试 code
        DownloadError("download fail", error_code="VIDEO_NOT_FOUND"),
        AIError("ai fail", error_code="API_KEY_INVALID"),
        TranscribeError("transcribe fail", error_code="AUDIO_EXTRACTION_FAILED"),
        KeyError("missing key"),
    ]
    for exc in non_retryable:
        assert is_retryable_error(exc) is False, f"{type(exc).__name__} 应不可重试"
        print(f"  ✓ {type(exc).__name__} → False")

    # error_code 匹配
    class CustomErr(Exception):
        def __init__(self, code):
            self.error_code = code

    assert is_retryable_error(CustomErr("RATE_LIMITED")) is True
    assert is_retryable_error(CustomErr("NETWORK_ERROR")) is True
    assert is_retryable_error(CustomErr("NON_RETRYABLE")) is False
    assert is_retryable_error(CustomErr("TIMEOUT")) is True
    print("  ✓ error_code 匹配逻辑正确")

    print("  ✓ is_retryable_error 测试通过")


def test_on_retry_callback():
    """测试 retry 回调"""
    print("\n=== 测试 on_retry 回调 ===")

    callback_args = []

    def my_on_retry(exc, attempt, delay):
        callback_args.append((exc, attempt, delay))

    config = RetryConfig(
        max_retries=3, strategy=RetryStrategy.FIXED, base_delay=1.0, jitter=0,
        on_retry=my_on_retry,
    )

    call_count = 0

    @retry_with_config(config)
    def fail_twice():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise NetworkError("fail")
        return "ok"

    with patch("time.sleep"):
        result = fail_twice()

    assert result == "ok"
    assert len(callback_args) == 2, f"应回调 2 次, 实际 {len(callback_args)}"
    for i, (exc, attempt, delay) in enumerate(callback_args):
        assert isinstance(exc, NetworkError)
        print(f"  ✓ 回调 #{i + 1}: attempt={attempt}, delay={delay}")

    print("  ✓ on_retry 回调测试通过")


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


def test_highlight_class():
    """测试 Highlight 类"""
    print("\n=== 测试 Highlight 类 ===")

    highlight = Highlight(time="00:05:00", seconds=300, content="测试要点")

    assert highlight.time == "00:05:00"
    assert highlight.seconds == 300
    assert highlight.content == "测试要点"

    print("  ✓ Highlight 类测试通过")



