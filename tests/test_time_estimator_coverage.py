"""覆盖 ProcessingTimeEstimator 缺失路径的测试"""
from datetime import datetime, timedelta
from unittest import mock

import pytest

from src.services.time_estimator import (
    ProcessingTimeEstimator,
    estimate_processing_time,
    format_time_remaining,
    get_time_estimator,
)


@pytest.fixture
def estimator():
    est = ProcessingTimeEstimator()
    est.db = mock.MagicMock()
    est.db.get_processing_stats_count.return_value = 0
    return est


class TestRecordTaskComplete:
    """record_task_complete 测试"""

    def test_unknown_task_id_logs_warning(self, estimator):
        estimator.record_task_complete("unknown", "full", "bilibili", 120)
        estimator.db.save_processing_stats.assert_not_called()

    def test_saves_stats_and_cleans_up(self, estimator):
        estimator._task_start_times["task-1"] = datetime.now() - timedelta(seconds=30)
        estimator.record_task_complete("task-1", "full", "bilibili", 120)
        estimator.db.save_processing_stats.assert_called_once()
        assert "task-1" not in estimator._task_start_times


class TestEstimateProcessingTime:
    """estimate_processing_time 置信度路径"""

    def test_high_confidence(self, estimator):
        estimator.db.get_average_processing_ratio.return_value = 2.0
        estimator.db.get_processing_stats_count.return_value = 15
        result = estimator.estimate_processing_time("full", 120)
        assert result.confidence == "high"
        assert "15 次" in result.message

    def test_medium_confidence(self, estimator):
        estimator.db.get_average_processing_ratio.return_value = 2.0
        estimator.db.get_processing_stats_count.return_value = 7
        result = estimator.estimate_processing_time("full", 120)
        assert result.confidence == "medium"

    def test_low_confidence(self, estimator):
        estimator.db.get_average_processing_ratio.return_value = 2.0
        estimator.db.get_processing_stats_count.return_value = 2
        result = estimator.estimate_processing_time("full", 120)
        assert result.confidence == "low"

    def test_none_confidence_no_history(self, estimator):
        estimator.db.get_average_processing_ratio.return_value = None
        result = estimator.estimate_processing_time("full", 120)
        assert result.confidence == "none"
        assert "默认" in result.message

    def test_total_seconds_calculation(self, estimator):
        estimator.db.get_average_processing_ratio.return_value = 1.5
        estimator.db.get_processing_stats_count.return_value = 1
        result = estimator.estimate_processing_time("full", 120)
        assert result.total_seconds == 180


class TestEstimateRemainingTime:
    """estimate_remaining_time 测试"""

    def test_zero_progress_returns_total(self, estimator):
        estimator.db.get_average_processing_ratio.return_value = 2.0
        estimator.db.get_processing_stats_count.return_value = 1
        result = estimator.estimate_remaining_time("task-1", "full", 120, 0)
        assert result.remaining_seconds == 240

    def test_complete_progress(self, estimator):
        estimator.db.get_average_processing_ratio.return_value = 2.0
        result = estimator.estimate_remaining_time("task-1", "full", 120, 1.0)
        assert result.remaining_seconds == 0
        assert "即将完成" in result.message

    def test_with_elapsed_time_based_estimate(self, estimator):
        estimator.db.get_average_processing_ratio.return_value = 2.0
        estimator._task_start_times["task-1"] = datetime.now() - timedelta(seconds=20)
        result = estimator.estimate_remaining_time("task-1", "full", 120, 0.5)
        assert result.remaining_seconds < 240
        assert result.confidence == "high"

    def test_without_elapsed_uses_default(self, estimator):
        estimator.db.get_average_processing_ratio.return_value = 2.0
        result = estimator.estimate_remaining_time("task-1", "full", 120, 0.5)
        assert result.remaining_seconds == 120

    def test_remaining_less_than_60_seconds(self, estimator):
        estimator.db.get_average_processing_ratio.return_value = 0.1
        result = estimator.estimate_remaining_time("task-1", "full", 60, 0.5)
        assert "秒" in result.message

    def test_remaining_more_than_hour(self, estimator):
        estimator.db.get_average_processing_ratio.return_value = 5.0
        estimator._task_start_times["task-1"] = datetime.now() - timedelta(hours=2)
        result = estimator.estimate_remaining_time("task-1", "full", 3600, 0.3)
        assert "小时" in result.message

    def test_remaining_between_60_and_3600(self, estimator):
        estimator.db.get_average_processing_ratio.return_value = 2.0
        result = estimator.estimate_remaining_time("task-1", "full", 60, 0.3)
        assert "分" in result.message


class TestGetEstimatedRatio:
    """_get_estimated_ratio 测试"""

    def test_with_platform_returns_platform_ratio(self, estimator):
        estimator.db.get_average_processing_ratio.side_effect = lambda mode, platform=None: {
            ("full", "bilibili"): 1.5,
            ("full", None): 2.0,
        }.get((mode, platform))
        ratio = estimator._get_estimated_ratio("full", "bilibili")
        assert ratio == 1.5

    def test_without_platform_falls_back(self, estimator):
        estimator.db.get_average_processing_ratio.return_value = 2.0
        ratio = estimator._get_estimated_ratio("full")
        assert ratio == 2.0

    def test_platform_no_data_falls_back(self, estimator):
        def side_effect(mode, platform=None):
            if platform:
                return None
            return 2.0
        estimator.db.get_average_processing_ratio.side_effect = side_effect
        ratio = estimator._get_estimated_ratio("full", "bilibili")
        assert ratio == 2.0


class TestGlobalFunctions:
    """全局便捷函数测试"""

    def test_get_time_estimator_singleton(self):
        import src.services.time_estimator as te
        saved = te._estimator_instance
        te._estimator_instance = None
        try:
            e1 = get_time_estimator()
            e2 = get_time_estimator()
            assert e1 is e2
        finally:
            te._estimator_instance = saved

    def test_estimate_processing_time_convenience(self):
        with mock.patch("src.services.time_estimator.get_time_estimator") as mock_get:
            mock_est = mock.MagicMock()
            mock_get.return_value = mock_est
            estimate_processing_time("full", 120)
            mock_est.estimate_processing_time.assert_called_once_with("full", 120, None)

    def test_format_time_remaining(self):
        assert "30" in format_time_remaining(30)


class TestFormatDuration:
    """_format_duration 边界测试"""

    @pytest.mark.parametrize("seconds,expected_substr", [
        (30, "秒"),
        (90, "分"),
        (130, "分"),
        (3660, "小时"),
        (7200, "小时"),
    ])
    def test_format_duration_various(self, seconds, expected_substr):
        result = ProcessingTimeEstimator._format_duration(seconds)
        assert expected_substr in result
