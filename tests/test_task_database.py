"""任务数据库测试"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.task_database import TaskDatabase, get_task_database
from src.models.task import TaskHistory, TaskStatus, ProcessingMode, ExportTarget


def test_task_database_singleton():
    """测试 TaskDatabase 单例模式"""
    print("\n=== 测试 TaskDatabase 单例 ===")
    
    db1 = get_task_database()
    db2 = get_task_database()
    
    assert db1 is db2, "应该是同一个实例"
    print("  ✓ TaskDatabase 是单例")
    
    return True


def test_save_and_get_task():
    """测试保存和获取任务"""
    print("\n=== 测试保存和获取任务 ===")
    
    db = TaskDatabase()
    
    # 创建测试任务
    task = TaskHistory(
        id="test_task_001",
        url="https://test.com/video",
        title="测试视频标题",
        author="测试作者",
        platform="bilibili",
        mode=ProcessingMode.FULL,
        targets=[ExportTarget.LOCAL],
        status=TaskStatus.COMPLETED,
        created_at=datetime.now(),
        completed_at=datetime.now(),
        highlights_count=5
    )
    
    # 保存任务
    result = db.save_task(task)
    assert result is True, "保存应成功"
    print("  ✓ 任务保存成功")
    
    # 获取任务
    retrieved = db.get_task("test_task_001")
    assert retrieved is not None, "应能获取到任务"
    assert retrieved.title == "测试视频标题"
    assert retrieved.platform == "bilibili"
    print("  ✓ 任务获取成功")
    
    # 清理
    db.delete_task("test_task_001")
    
    return True


def test_get_tasks_pagination():
    """测试分页获取任务"""
    print("\n=== 测试分页获取任务 ===")
    
    db = TaskDatabase()
    
    # 创建多个测试任务
    for i in range(5):
        task = TaskHistory(
            id=f"test_pagination_{i}",
            url=f"https://test.com/video{i}",
            title=f"测试视频 {i}",
            author="测试作者",
            platform="bilibili",
            mode=ProcessingMode.FULL,
            targets=[ExportTarget.LOCAL],
            status=TaskStatus.COMPLETED,
            created_at=datetime.now()
        )
        db.save_task(task)
    
    # 测试分页
    page1 = db.get_tasks(limit=2, offset=0)
    page2 = db.get_tasks(limit=2, offset=2)
    
    assert len(page1) == 2, "第一页应有2条"
    assert len(page2) == 2, "第二页应有2条"
    print(f"  ✓ 分页获取成功: 第1页{len(page1)}条, 第2页{len(page2)}条")
    
    # 清理
    for i in range(5):
        db.delete_task(f"test_pagination_{i}")
    
    return True


def test_search_tasks():
    """测试搜索任务"""
    print("\n=== 测试搜索任务 ===")
    
    db = TaskDatabase()
    
    # 创建测试任务
    task = TaskHistory(
        id="test_search_001",
        url="https://bilibili.com/video/BV123",
        title="Python 教程视频",
        author="编程老师",
        platform="bilibili",
        mode=ProcessingMode.FULL,
        targets=[ExportTarget.LOCAL],
        status=TaskStatus.COMPLETED,
        created_at=datetime.now()
    )
    db.save_task(task)
    
    # 搜索
    results = db.search_tasks("Python")
    assert len(results) > 0, "应能找到包含 Python 的任务"
    print(f"  ✓ 搜索 'Python' 找到 {len(results)} 条结果")
    
    results = db.search_tasks("不存在的词")
    assert len(results) == 0, "不存在的词应返回空"
    print("  ✓ 搜索不存在的词返回空")
    
    # 清理
    db.delete_task("test_search_001")
    
    return True


def test_get_statistics():
    """测试获取统计信息"""
    print("\n=== 测试获取统计信息 ===")
    
    db = TaskDatabase()
    
    stats = db.get_statistics()
    
    assert "total" in stats
    assert "by_status" in stats
    assert "by_platform" in stats
    print(f"  ✓ 统计信息: 总计 {stats.get('total', 0)} 条")
    
    return True


def test_processing_stats():
    """测试处理时间统计"""
    print("\n=== 测试处理时间统计 ===")
    
    db = TaskDatabase()
    
    # 保存处理统计
    result = db.save_processing_stats(
        mode="full",
        platform="bilibili",
        duration_seconds=600,
        processing_time_seconds=1200.0
    )
    assert result is True
    print("  ✓ 处理时间统计保存成功")
    
    # 获取平均比例
    ratio = db.get_average_processing_ratio("full")
    assert ratio is not None
    print(f"  ✓ 平均处理比例: {ratio:.2f}x")
    
    # 获取记录数
    count = db.get_processing_stats_count("full")
    assert count > 0
    print(f"  ✓ 统计记录数: {count}")
    
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("任务数据库测试套件")
    print("=" * 50)
    
    all_passed = True
    all_passed &= test_task_database_singleton()
    all_passed &= test_save_and_get_task()
    all_passed &= test_get_tasks_pagination()
    all_passed &= test_search_tasks()
    all_passed &= test_get_statistics()
    all_passed &= test_processing_stats()
    
    print("\n" + "=" * 50)
    if all_passed:
        print("✓ 所有测试通过")
    else:
        print("✗ 部分测试失败")
    print("=" * 50)
