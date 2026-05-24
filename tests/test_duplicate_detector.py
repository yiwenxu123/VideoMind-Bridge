"""重复检测器测试"""

import sys
from pathlib import Path
from datetime import datetime

from src.services.duplicate_detector import (
    DuplicateDetector, get_duplicate_detector, ProcessingStatus
)


def test_duplicate_detector_singleton():
    """测试 DuplicateDetector 单例模式"""
    print("\n=== 测试 DuplicateDetector 单例 ===")
    
    detector1 = get_duplicate_detector()
    detector2 = get_duplicate_detector()
    
    assert detector1 is detector2, "应该是同一个实例"
    print("  ✓ DuplicateDetector 是单例")


def test_add_and_check_record():
    """测试添加和检查记录"""
    print("\n=== 测试添加和检查记录 ===")
    
    detector = DuplicateDetector()
    
    url = "https://bilibili.com/video/BV_test_001"
    
    # 添加记录
    detector.add_record(
        url=url,
        title="测试视频",
        mode="full",
        status=ProcessingStatus.COMPLETED
    )
    
    # 检查重复
    record = detector.check_duplicate(url)
    assert record is not None, "应能检测到重复"
    assert record.title == "测试视频"
    print("  ✓ 重复检测成功")


def test_update_status():
    """测试更新状态"""
    print("\n=== 测试更新状态 ===")
    
    detector = DuplicateDetector()
    
    url = "https://bilibili.com/video/BV_test_002"
    
    # 添加记录
    detector.add_record(
        url=url,
        title="测试视频2",
        mode="full",
        status=ProcessingStatus.PENDING
    )
    
    # 更新状态
    detector.update_status(
        url=url,
        status=ProcessingStatus.COMPLETED,
        output_dir="/test/output"
    )
    
    # 验证更新
    record = detector.check_duplicate(url)
    assert record.status == ProcessingStatus.COMPLETED
    print("  ✓ 状态更新成功")


def test_get_recent_tasks():
    """测试获取最近任务"""
    print("\n=== 测试获取最近任务 ===")
    
    detector = DuplicateDetector()
    
    # 添加几条记录
    for i in range(3):
        detector.add_record(
            url=f"https://test.com/video{i}",
            title=f"测试视频 {i}",
            mode="full",
            status=ProcessingStatus.COMPLETED
        )
    
    # 获取最近任务
    recent = detector.get_recent_records(limit=2)
    assert len(recent) <= 2, "应返回不超过限制数量的任务"
    print(f"  ✓ 获取到 {len(recent)} 条最近任务")
    


if __name__ == "__main__":
    print("=" * 50)
    print("重复检测器测试套件")
    print("=" * 50)
    
    all_passed = True
    all_passed &= test_duplicate_detector_singleton()
    all_passed &= test_add_and_check_record()
    all_passed &= test_update_status()
    all_passed &= test_get_recent_tasks()
    
    print("\n" + "=" * 50)
    if all_passed:
        print("✓ 所有测试通过")
    else:
        print("✗ 部分测试失败")
    print("=" * 50)
