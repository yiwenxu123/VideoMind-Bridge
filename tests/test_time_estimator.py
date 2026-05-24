"""处理时间预估功能测试"""

import sys
from pathlib import Path

from src.services.time_estimator import ProcessingTimeEstimator, TimeEstimate


def test_format_duration():
    """测试时长格式化"""
    print("\n=== 测试时长格式化 ===")

    test_cases = [
        (30, "30秒"),
        (60, "1分钟"),
        (90, "1分30秒"),
        (3600, "1小时"),
        (3660, "1小时1分"),
        (7200, "2小时"),
    ]

    for seconds, expected in test_cases:
        result = ProcessingTimeEstimator._format_duration(seconds)
        assert result == expected, f"{seconds}s -> 期望 {expected}, 实际 {result}"
        print(f"  ✓ {seconds}s -> {result}")


def test_estimate_processing_time():
    """测试处理时间预估"""
    print("\n=== 测试处理时间预估 ===")

    estimator = ProcessingTimeEstimator()

    modes = ["full", "download_only", "transcribe_only"]
    video_duration = 600  # 10分钟视频

    for mode in modes:
        estimate = estimator.estimate_processing_time(mode, video_duration)
        print(f"  {mode}: {estimate.message}")
        assert estimate.confidence in ("high", "medium", "low", "none"), f"{mode} 置信度应为有效值"


def test_estimate_remaining_time():
    """测试剩余时间预估"""
    print("\n=== 测试剩余时间预估 ===")

    estimator = ProcessingTimeEstimator()

    task_id = "test_task_001"
    estimator.record_task_start(task_id)

    progress_points = [0.0, 0.25, 0.5, 0.75]
    video_duration = 600

    for progress in progress_points:
        estimate = estimator.estimate_remaining_time(
            task_id=task_id,
            mode="full",
            video_duration=video_duration,
            current_progress=progress,
        )
        print(f"  进度 {progress*100:.0f}%: {estimate.message}")


def test_default_ratios():
    """测试默认比例"""
    print("\n=== 测试默认处理比例 ===")

    estimator = ProcessingTimeEstimator()

    for mode, ratio in estimator.DEFAULT_RATIOS.items():
        video_duration = 600
        expected_time = video_duration * ratio
        formatted = estimator._format_duration(int(expected_time))
        print(f"  {mode}: {ratio}x -> {formatted}")
        assert ratio > 0, f"{mode} 比例应大于0"


def main():
    """运行所有测试"""
    print("=" * 50)
    print("处理时间预估功能测试套件")
    print("=" * 50)

    test_format_duration()
    test_estimate_processing_time()
    test_estimate_remaining_time()
    test_default_ratios()

    print("\n" + "=" * 50)
    print("✓ 所有测试通过")
    print("=" * 50)

    return 0


if __name__ == "__main__":
    sys.exit(main())
