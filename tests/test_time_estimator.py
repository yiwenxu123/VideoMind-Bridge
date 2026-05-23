"""处理时间预估功能测试"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

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

    all_passed = True
    for seconds, expected in test_cases:
        result = ProcessingTimeEstimator._format_duration(seconds)
        if result == expected:
            print(f"  ✓ {seconds}s -> {result}")
        else:
            print(f"  ✗ {seconds}s -> 期望 {expected}, 实际 {result}")
            all_passed = False

    return all_passed


def test_estimate_processing_time():
    """测试处理时间预估"""
    print("\n=== 测试处理时间预估 ===")

    estimator = ProcessingTimeEstimator()

    # 测试不同模式
    modes = ["full", "download_only", "transcribe_only"]
    video_duration = 600  # 10分钟视频

    for mode in modes:
        estimate = estimator.estimate_processing_time(mode, video_duration)
        print(f"  {mode}: {estimate.message}")
        print(f"    预估总时间: {estimate.total_seconds}秒")
        print(f"    置信度: {estimate.confidence}")

    return True


def test_estimate_remaining_time():
    """测试剩余时间预估"""
    print("\n=== 测试剩余时间预估 ===")

    estimator = ProcessingTimeEstimator()

    # 模拟任务
    task_id = "test_task_001"
    estimator.record_task_start(task_id)

    # 模拟进度更新
    progress_points = [0.0, 0.25, 0.5, 0.75]
    video_duration = 600  # 10分钟视频

    for progress in progress_points:
        estimate = estimator.estimate_remaining_time(
            task_id=task_id,
            mode="full",
            video_duration=video_duration,
            current_progress=progress
        )
        print(f"  进度 {progress*100:.0f}%: {estimate.message}")

    return True


def test_default_ratios():
    """测试默认比例"""
    print("\n=== 测试默认处理比例 ===")

    estimator = ProcessingTimeEstimator()

    for mode, ratio in estimator.DEFAULT_RATIOS.items():
        # 10分钟视频
        video_duration = 600
        expected_time = video_duration * ratio
        formatted = estimator._format_duration(int(expected_time))
        print(f"  {mode}: {ratio}x -> {formatted}")

    return True


def main():
    """运行所有测试"""
    print("=" * 50)
    print("处理时间预估功能测试套件")
    print("=" * 50)

    all_passed = True

    all_passed &= test_format_duration()
    all_passed &= test_estimate_processing_time()
    all_passed &= test_estimate_remaining_time()
    all_passed &= test_default_ratios()

    print("\n" + "=" * 50)
    if all_passed:
        print("✓ 所有测试通过")
    else:
        print("✗ 部分测试失败")
    print("=" * 50)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
