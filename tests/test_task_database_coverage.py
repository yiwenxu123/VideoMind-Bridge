"""覆盖 TaskDatabase 缺失错误路径和筛选路径的测试"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest

from src.models.task import (
    ExportTarget,
    ProcessingMode,
    TaskHistory,
    TaskStatus,
)
from src.services.task_database import TaskDatabase


@pytest.fixture
def db(tmp_path) -> TaskDatabase:
    return TaskDatabase(db_path=tmp_path / "test_tasks.db")


@pytest.fixture
def sample_task() -> TaskHistory:
    return TaskHistory(
        id="test-001",
        url="https://example.com/video",
        title="Test Video",
        author="Tester",
        platform="bilibili",
        mode=ProcessingMode.FULL,
        targets=[ExportTarget.LOCAL],
        status=TaskStatus.COMPLETED,
        created_at=datetime.now(),
        completed_at=datetime.now(),
        summary="A test summary",
        highlights_count=5,
        transcript_path=Path("/tmp/transcript.srt"),
        output_files=[Path("/tmp/output.md")],
        export_success_count=1,
        export_total_count=2,
    )


class TestTaskDatabaseErrorPaths:
    """数据库异常路径测试（用已关闭的数据库模拟异常）"""

    @pytest.fixture
    def closed_db(self, tmp_path) -> TaskDatabase:
        db = TaskDatabase(db_path=tmp_path / "closed.db")
        db.db_path.unlink(missing_ok=False)
        return db

    def test_save_task_exception(self, closed_db, sample_task):
        result = closed_db.save_task(sample_task)
        assert result is False

    def test_get_task_exception(self, closed_db):
        result = closed_db.get_task("nonexistent")
        assert result is None

    def test_get_task_nonexistent_returns_none(self, db):
        result = db.get_task("nonexistent")
        assert result is None

    def test_get_tasks_exception(self, closed_db):
        result = closed_db.get_tasks()
        assert result == []

    def test_search_tasks_exception(self, closed_db):
        result = closed_db.search_tasks("keyword")
        assert result == []

    def test_delete_task_exception(self, closed_db):
        result = closed_db.delete_task("test-001")
        assert result is False

    def test_clear_old_tasks_exception(self, closed_db):
        result = closed_db.clear_old_tasks(30)
        assert result == 0

    def test_get_statistics_exception(self, closed_db):
        result = closed_db.get_statistics()
        assert result == {"total": 0, "by_status": {}, "by_platform": {}}

    def test_save_processing_stats_exception(self, closed_db):
        result = closed_db.save_processing_stats("full", "bilibili", 300, 60)
        assert result is False

    def test_get_average_processing_ratio_exception(self, closed_db):
        result = closed_db.get_average_processing_ratio("full")
        assert result is None

    def test_get_processing_stats_count_exception(self, closed_db):
        result = closed_db.get_processing_stats_count("full")
        assert result == 0


class TestTaskDatabaseQueryFilters:
    """查询筛选路径测试"""

    def test_get_tasks_with_status_filter(self, db, sample_task):
        db.save_task(sample_task)
        results = db.get_tasks(status=TaskStatus.COMPLETED)
        assert len(results) == 1
        assert results[0].id == "test-001"

    def test_get_tasks_with_platform_filter(self, db, sample_task):
        db.save_task(sample_task)
        results = db.get_tasks(platform="bilibili")
        assert len(results) == 1

    def test_get_tasks_with_both_filters(self, db, sample_task):
        db.save_task(sample_task)
        results = db.get_tasks(status=TaskStatus.COMPLETED, platform="bilibili")
        assert len(results) == 1

    def test_get_tasks_no_match(self, db, sample_task):
        db.save_task(sample_task)
        results = db.get_tasks(platform="youtube")
        assert len(results) == 0


class TestTaskDatabaseClearOld:
    """清理旧记录测试"""

    def test_clear_old_tasks_removes_old(self, db, sample_task):
        old_task = TaskHistory(
            id="old-001",
            url="https://example.com/old",
            title="Old Video",
            author="Old",
            platform="youtube",
            mode=ProcessingMode.FULL,
            targets=[ExportTarget.LOCAL],
            status=TaskStatus.COMPLETED,
            created_at=datetime.now() - timedelta(days=100),
        )
        db.save_task(sample_task)
        db.save_task(old_task)
        count = db.clear_old_tasks(days=30)
        assert count == 1
        assert db.get_task("test-001") is not None
        assert db.get_task("old-001") is None

    def test_clear_old_tasks_boundary_day(self, db):
        """截止日当天 (T 分隔符 ISO 格式) 的记录应被清理"""
        task = TaskHistory(
            id="boundary-001",
            url="https://example.com/boundary",
            title="Boundary Video",
            author="Tester",
            platform="youtube",
            mode=ProcessingMode.FULL,
            targets=[ExportTarget.LOCAL],
            status=TaskStatus.COMPLETED,
            created_at=datetime.now() - timedelta(days=31),
        )
        db.save_task(task)
        count = db.clear_old_tasks(days=30)
        assert count == 1
        assert db.get_task("boundary-001") is None

    def test_clear_old_tasks_keeps_recent(self, db, sample_task):
        """近期 (T 分隔符 ISO 格式) 的记录应被保留"""
        db.save_task(sample_task)
        count = db.clear_old_tasks(days=30)
        assert count == 0
        assert db.get_task("test-001") is not None


class TestTaskDatabaseProcessingStats:
    """处理统计测试"""

    def test_save_and_get_ratio(self, db):
        db.save_processing_stats("full", "bilibili", 100, 20)
        db.save_processing_stats("full", "bilibili", 200, 40)
        ratio = db.get_average_processing_ratio("full")
        assert ratio is not None
        assert ratio == pytest.approx(0.2, rel=0.1)

    def test_get_ratio_with_platform(self, db):
        db.save_processing_stats("full", "bilibili", 100, 20)
        db.save_processing_stats("full", "youtube", 100, 10)
        ratio = db.get_average_processing_ratio("full", platform="bilibili")
        assert ratio == pytest.approx(0.2, rel=0.1)

    def test_get_ratio_no_data(self, db):
        ratio = db.get_average_processing_ratio("full")
        assert ratio is None

    def test_get_ratio_limit_only_latest(self, db):
        """LIMIT 应只统计最近 N 条记录"""
        # 先写入比例悬殊的历史记录
        db.save_processing_stats("full", "bilibili", 100, 90)   # ratio 0.9
        db.save_processing_stats("full", "bilibili", 100, 80)   # ratio 0.8
        # 最近两条比例接近 0.2
        db.save_processing_stats("full", "bilibili", 100, 20)   # ratio 0.2
        db.save_processing_stats("full", "bilibili", 100, 20)   # ratio 0.2

        ratio = db.get_average_processing_ratio("full", limit=2)
        assert ratio is not None
        assert ratio == pytest.approx(0.2, rel=0.05)

        # 全量统计应包含历史高比例记录
        ratio_all = db.get_average_processing_ratio("full")
        assert ratio_all == pytest.approx(0.525, rel=0.05)

    def test_get_processing_stats_count(self, db):
        db.save_processing_stats("full", "bilibili", 100, 20)
        db.save_processing_stats("full", "youtube", 200, 30)
        assert db.get_processing_stats_count("full") == 2

    def test_get_processing_stats_count_empty(self, db):
        assert db.get_processing_stats_count("full") == 0


class TestTaskDatabaseRowConversion:
    """_row_to_task_history 异常路径测试"""

    def test_invalid_status_uses_default(self, db):
        with db._get_connection() as conn:
            conn.execute("""
                INSERT INTO task_history (id, url, title, author, platform, mode, targets, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("inv-status", "https://x.com", "X", "", "", "full", "local", "INVALID_STATUS", datetime.now().isoformat()))
        task = db.get_task("inv-status")
        assert task is not None
        assert task.status == TaskStatus.COMPLETED

    def test_malformed_row_returns_none(self, db):
        with mock.patch.object(db, "_get_connection") as mock_conn:
            mock_cursor = mock.MagicMock()
            mock_cursor.fetchone.return_value = mock.MagicMock()
            mock_cursor.fetchone.return_value.__getitem__.side_effect = KeyError("missing field")
            mock_conn.return_value.__enter__.return_value.cursor.return_value = mock_cursor
            result = db.get_task("bad-row")
            assert result is None

    def test_search_returns_multiple_matches(self, db, sample_task):
        second = TaskHistory(
            id="test-002", url="https://x.com/other", title="Other Video",
            author="Tester", platform="youtube",
            mode=ProcessingMode.FULL, targets=[ExportTarget.LOCAL],
            status=TaskStatus.COMPLETED, created_at=datetime.now(),
        )
        db.save_task(sample_task)
        db.save_task(second)
        results = db.search_tasks("Tester")
        assert len(results) == 2

    def test_search_no_match(self, db, sample_task):
        db.save_task(sample_task)
        results = db.search_tasks("nonexistent")
        assert len(results) == 0

    def test_delete_nonexistent_returns_true(self, db):
        assert db.delete_task("not-exist") is True

    def test_save_task_without_completed_at(self, db):
        task = TaskHistory(
            id="no-complete",
            url="https://x.com",
            title="In Progress",
            author="",
            platform="",
            mode=ProcessingMode.FULL,
            targets=[ExportTarget.LOCAL],
            status=TaskStatus.PENDING,
            created_at=datetime.now(),
        )
        assert db.save_task(task) is True
        loaded = db.get_task("no-complete")
        assert loaded is not None
        assert loaded.completed_at is None
