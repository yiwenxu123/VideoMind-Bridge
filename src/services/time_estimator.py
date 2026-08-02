"""处理时间预估服务"""

from dataclasses import dataclass
from datetime import datetime

from ..utils import get_logger
from .task_database import get_task_database

logger = get_logger(__name__)


@dataclass
class TimeEstimate:
    """时间预估结果"""
    total_seconds: int  # 预估总处理时间（秒）
    remaining_seconds: int  # 预估剩余时间（秒）
    confidence: str  # 置信度: "high", "medium", "low", "none"
    message: str  # 显示消息


class ProcessingTimeEstimator:
    """处理时间预估器"""

    # 默认处理时间比例（处理时间 / 视频时长）
    DEFAULT_RATIOS = {
        "full": 2.0,  # 完整处理：视频时长的 2 倍
        "download_only": 0.5,  # 仅下载：视频时长的 0.5 倍
        "transcribe_only": 1.5,  # 仅转录：视频时长的 1.5 倍
    }

    # 最小置信度样本数
    HIGH_CONFIDENCE_MIN_SAMPLES = 10
    MEDIUM_CONFIDENCE_MIN_SAMPLES = 5

    def __init__(self):
        self.db = get_task_database()
        self._task_start_times: dict[str, datetime] = {}  # 任务开始时间记录

    def record_task_start(self, task_id: str):
        """记录任务开始时间"""
        self._task_start_times[task_id] = datetime.now()
        logger.debug(f"记录任务开始时间: {task_id}")

    def record_task_complete(
        self,
        task_id: str,
        mode: str,
        platform: str,
        video_duration: int
    ):
        """
        记录任务完成，保存处理时间统计

        Args:
            task_id: 任务ID
            mode: 处理模式
            platform: 视频平台
            video_duration: 视频时长（秒）
        """
        if task_id not in self._task_start_times:
            logger.warning(f"未找到任务开始时间记录: {task_id}")
            return

        start_time = self._task_start_times[task_id]
        processing_time = (datetime.now() - start_time).total_seconds()

        # 保存到数据库
        self.db.save_processing_stats(
            mode=mode,
            platform=platform,
            duration_seconds=video_duration,
            processing_time_seconds=processing_time
        )

        # 清理记录
        del self._task_start_times[task_id]

        logger.debug(f"任务完成统计: {mode}, {video_duration}s 视频, 处理耗时 {processing_time:.1f}s")

    def estimate_processing_time(
        self,
        mode: str,
        video_duration: int,
        platform: str | None = None
    ) -> TimeEstimate:
        """
        预估处理时间

        Args:
            mode: 处理模式 ("full", "download_only", "transcribe_only")
            video_duration: 视频时长（秒）
            platform: 视频平台（可选）

        Returns:
            TimeEstimate: 时间预估结果
        """
        # 尝试获取历史平均比例
        ratio = self._get_estimated_ratio(mode, platform)

        if ratio is None:
            # 无历史数据，使用默认值
            ratio = self.DEFAULT_RATIOS.get(mode, 2.0)
            confidence = "none"
            confidence_msg = "（基于默认估算）"
        else:
            # 根据样本数量确定置信度
            sample_count = self.db.get_processing_stats_count(mode)
            if sample_count >= self.HIGH_CONFIDENCE_MIN_SAMPLES:
                confidence = "high"
                confidence_msg = f"（基于 {sample_count} 次历史记录）"
            elif sample_count >= self.MEDIUM_CONFIDENCE_MIN_SAMPLES:
                confidence = "medium"
                confidence_msg = f"（基于 {sample_count} 次历史记录）"
            else:
                confidence = "low"
                confidence_msg = f"（基于 {sample_count} 次历史记录）"

        # 计算预估时间
        estimated_seconds = int(video_duration * ratio)

        # 格式化时间显示
        time_str = self._format_duration(estimated_seconds)

        return TimeEstimate(
            total_seconds=estimated_seconds,
            remaining_seconds=estimated_seconds,
            confidence=confidence,
            message=f"预计处理时间: {time_str} {confidence_msg}"
        )

    def estimate_remaining_time(
        self,
        task_id: str,
        mode: str,
        video_duration: int,
        current_progress: float,
        platform: str | None = None
    ) -> TimeEstimate:
        """
        预估剩余时间

        Args:
            task_id: 任务ID
            mode: 处理模式
            video_duration: 视频时长（秒）
            current_progress: 当前进度 (0.0 - 1.0)
            platform: 视频平台（可选）

        Returns:
            TimeEstimate: 时间预估结果
        """
        # 获取总预估时间
        total_estimate = self.estimate_processing_time(mode, video_duration, platform)

        if current_progress <= 0:
            return total_estimate

        if current_progress >= 1.0:
            return TimeEstimate(
                total_seconds=total_estimate.total_seconds,
                remaining_seconds=0,
                confidence=total_estimate.confidence,
                message="即将完成..."
            )

        # 基于实际进度重新估算
        elapsed_time = 0.0
        if task_id in self._task_start_times:
            elapsed_time = (datetime.now() - self._task_start_times[task_id]).total_seconds()

        if elapsed_time > 10:  # 至少运行 10 秒后才基于实际进度估算
            # 根据已用时间和进度计算剩余时间
            estimated_total = elapsed_time / current_progress
            remaining = estimated_total * (1 - current_progress)
            confidence = "high"  # 基于实际进度，置信度较高
        else:
            # 使用历史平均估算
            remaining = total_estimate.total_seconds * (1 - current_progress)
            confidence = total_estimate.confidence

        remaining = max(0, int(remaining))

        # 格式化显示
        if remaining < 60:
            time_str = f"{remaining}秒"
        elif remaining < 3600:
            time_str = f"{remaining // 60}分{remaining % 60}秒"
        else:
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            time_str = f"{hours}小时{minutes}分"

        return TimeEstimate(
            total_seconds=total_estimate.total_seconds,
            remaining_seconds=remaining,
            confidence=confidence,
            message=f"剩余时间: {time_str}"
        )

    def _get_estimated_ratio(self, mode: str, platform: str | None = None) -> float | None:
        """获取预估的处理时间比例"""
        # 首先尝试获取平台特定的比例
        if platform:
            ratio = self.db.get_average_processing_ratio(mode, platform)
            if ratio is not None:
                return ratio

        # 退回到通用比例
        return self.db.get_average_processing_ratio(mode)

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """格式化时长显示"""
        if seconds < 60:
            return f"{seconds}秒"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            if secs > 0:
                return f"{minutes}分{secs}秒"
            return f"{minutes}分钟"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            if minutes > 0:
                return f"{hours}小时{minutes}分"
            return f"{hours}小时"


# 全局预估器实例
_estimator_instance: ProcessingTimeEstimator | None = None


def get_time_estimator() -> ProcessingTimeEstimator:
    """获取时间预估器单例实例"""
    global _estimator_instance
    if _estimator_instance is None:
        _estimator_instance = ProcessingTimeEstimator()
    return _estimator_instance


# 便捷函数
def estimate_processing_time(
    mode: str,
    video_duration: int,
    platform: str | None = None
) -> TimeEstimate:
    """便捷函数：预估处理时间"""
    return get_time_estimator().estimate_processing_time(mode, video_duration, platform)


def format_time_remaining(seconds: int) -> str:
    """便捷函数：格式化剩余时间"""
    return ProcessingTimeEstimator._format_duration(seconds)
