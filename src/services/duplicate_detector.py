"""重复处理检测服务"""

import hashlib
import yaml
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
from enum import Enum


class ProcessingStatus(str, Enum):
    """处理状态"""
    PENDING = "pending"      # 处理中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    CANCELLED = "cancelled"  # 已取消


@dataclass
class ProcessingRecord:
    """处理记录"""
    url: str
    url_hash: str
    title: str
    mode: str
    status: ProcessingStatus
    processed_at: datetime
    output_dir: Optional[str] = None
    obsidian_note_path: Optional[str] = None
    task_id: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "url_hash": self.url_hash,
            "title": self.title,
            "mode": self.mode,
            "status": self.status.value,
            "processed_at": self.processed_at.isoformat(),
            "output_dir": self.output_dir,
            "obsidian_note_path": self.obsidian_note_path,
            "task_id": self.task_id,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProcessingRecord":
        return cls(
            url=data["url"],
            url_hash=data["url_hash"],
            title=data["title"],
            mode=data["mode"],
            status=ProcessingStatus(data.get("status", "completed")),
            processed_at=datetime.fromisoformat(data["processed_at"]),
            output_dir=data.get("output_dir"),
            obsidian_note_path=data.get("obsidian_note_path"),
            task_id=data.get("task_id"),
            error_message=data.get("error_message"),
        )


class DuplicateDetector:
    """重复处理检测器"""

    def __init__(self, storage_path: Optional[Path] = None):
        """
        初始化检测器

        Args:
            storage_path: 存储文件路径，默认 ~/.config/VideoMind/processed_urls.yaml
        """
        if storage_path is None:
            storage_path = Path.home() / ".config" / "VideoMind" / "processed_urls.yaml"

        self.storage_path = storage_path
        self._records: Dict[str, ProcessingRecord] = {}
        self._load_records()

    def _load_records(self) -> None:
        """从文件加载记录"""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data and isinstance(data, dict):
                    for url_hash, record_data in data.items():
                        try:
                            self._records[url_hash] = ProcessingRecord.from_dict(record_data)
                        except Exception as e:
                            print(f"加载处理记录失败: {e}")
            except Exception as e:
                print(f"加载处理记录文件失败: {e}")

    def _save_records(self) -> bool:
        """保存记录到文件"""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {url_hash: record.to_dict() for url_hash, record in self._records.items()}
            with open(self.storage_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False)
            return True
        except Exception as e:
            print(f"保存处理记录失败: {e}")
            return False

    @staticmethod
    def _compute_url_hash(url: str) -> str:
        """计算 URL 的哈希值"""
        # 标准化 URL（移除 tracking 参数）
        normalized_url = url.split("?")[0].rstrip("/")
        return hashlib.sha256(normalized_url.encode()).hexdigest()[:16]

    def check_duplicate(self, url: str) -> Optional[ProcessingRecord]:
        """
        检查 URL 是否已处理过

        Args:
            url: 视频 URL

        Returns:
            ProcessingRecord: 如果已处理过，返回记录；否则返回 None
        """
        url_hash = self._compute_url_hash(url)
        record = self._records.get(url_hash)

        if record and record.status == ProcessingStatus.COMPLETED:
            return record
        return None

    def add_record(
        self,
        url: str,
        title: str,
        mode: str,
        status: ProcessingStatus = ProcessingStatus.PENDING,
        output_dir: Optional[str] = None,
        obsidian_note_path: Optional[str] = None,
        task_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> ProcessingRecord:
        """
        添加处理记录

        Args:
            url: 视频 URL
            title: 视频标题
            mode: 处理模式
            status: 处理状态
            output_dir: 输出目录
            obsidian_note_path: Obsidian 笔记路径
            task_id: 任务 ID
            error_message: 错误信息

        Returns:
            ProcessingRecord: 创建的记录
        """
        url_hash = self._compute_url_hash(url)
        record = ProcessingRecord(
            url=url,
            url_hash=url_hash,
            title=title,
            mode=mode,
            status=status,
            processed_at=datetime.now(),
            output_dir=output_dir,
            obsidian_note_path=obsidian_note_path,
            task_id=task_id,
            error_message=error_message,
        )
        self._records[url_hash] = record
        self._save_records()
        return record

    def update_status(
        self,
        url: str,
        status: ProcessingStatus,
        output_dir: Optional[str] = None,
        obsidian_note_path: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        更新处理状态

        Args:
            url: 视频 URL
            status: 新状态
            output_dir: 输出目录
            obsidian_note_path: Obsidian 笔记路径
            error_message: 错误信息

        Returns:
            bool: 是否更新成功
        """
        url_hash = self._compute_url_hash(url)
        if url_hash in self._records:
            record = self._records[url_hash]
            record.status = status
            record.processed_at = datetime.now()
            if output_dir is not None:
                record.output_dir = output_dir
            if obsidian_note_path is not None:
                record.obsidian_note_path = obsidian_note_path
            if error_message is not None:
                record.error_message = error_message
            return self._save_records()
        return False

    def remove_record(self, url: str) -> bool:
        """
        删除处理记录

        Args:
            url: 视频 URL

        Returns:
            bool: 是否删除成功
        """
        url_hash = self._compute_url_hash(url)
        if url_hash in self._records:
            del self._records[url_hash]
            return self._save_records()
        return False

    def get_all_records(self) -> List[ProcessingRecord]:
        """获取所有处理记录"""
        return list(self._records.values())

    def get_recent_records(self, limit: int = 10) -> List[ProcessingRecord]:
        """
        获取最近的处理记录

        Args:
            limit: 返回记录数量

        Returns:
            List[ProcessingRecord]: 记录列表
        """
        records = sorted(
            self._records.values(),
            key=lambda r: r.processed_at,
            reverse=True
        )
        return records[:limit]

    def clear_all_records(self) -> bool:
        """清空所有记录"""
        self._records.clear()
        return self._save_records()


# 全局检测器实例
_duplicate_detector: Optional[DuplicateDetector] = None


def get_duplicate_detector() -> DuplicateDetector:
    """获取全局重复处理检测器实例"""
    global _duplicate_detector
    if _duplicate_detector is None:
        _duplicate_detector = DuplicateDetector()
    return _duplicate_detector
