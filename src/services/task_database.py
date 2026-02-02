"""任务历史数据库 - SQLite 持久化存储"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from ..models.task import TaskHistory, ProcessingMode, ExportTarget, TaskStatus
from ..utils import get_logger

logger = get_logger(__name__)


class TaskDatabase:
    """任务历史数据库管理器"""

    def __init__(self, db_path: Optional[Path] = None):
        """
        初始化数据库

        Args:
            db_path: 数据库文件路径，默认为 ~/.config/VideoMind/tasks.db
        """
        if db_path is None:
            db_path = Path.home() / ".config" / "VideoMind" / "tasks.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 初始化数据库
        self._init_database()

    @contextmanager
    def _get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _init_database(self):
        """初始化数据库表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 创建任务历史表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_history (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    author TEXT,
                    platform TEXT,
                    mode TEXT NOT NULL,
                    targets TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_msg TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    summary TEXT,
                    highlights_count INTEGER DEFAULT 0,
                    transcript_path TEXT,
                    output_files TEXT,
                    export_success_count INTEGER DEFAULT 0,
                    export_total_count INTEGER DEFAULT 0
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON task_history(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at ON task_history(created_at DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_platform ON task_history(platform)
            """)

            logger.info(f"数据库初始化完成: {self.db_path}")

    def save_task(self, task: TaskHistory) -> bool:
        """
        保存任务历史记录

        Args:
            task: 任务历史对象

        Returns:
            是否保存成功
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT OR REPLACE INTO task_history (
                        id, url, title, author, platform, mode, targets, status,
                        error_msg, created_at, completed_at, summary, highlights_count,
                        transcript_path, output_files, export_success_count, export_total_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task.id,
                    task.url,
                    task.title,
                    task.author,
                    task.platform,
                    task.mode.value,
                    ",".join([t.value for t in task.targets]),
                    task.status.value,
                    task.error_msg,
                    task.created_at.isoformat(),
                    task.completed_at.isoformat() if task.completed_at else None,
                    task.summary,
                    task.highlights_count,
                    str(task.transcript_path) if task.transcript_path else None,
                    ",".join([str(p) for p in task.output_files]),
                    task.export_success_count,
                    task.export_total_count,
                ))

                logger.debug(f"任务历史已保存: {task.id}")
                return True

        except Exception as e:
            logger.error(f"保存任务历史失败: {e}")
            return False

    def get_task(self, task_id: str) -> Optional[TaskHistory]:
        """
        获取单个任务历史记录

        Args:
            task_id: 任务ID

        Returns:
            任务历史对象，如果不存在则返回 None
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT * FROM task_history WHERE id = ?
                """, (task_id,))

                row = cursor.fetchone()
                if row:
                    return self._row_to_task_history(row)
                return None

        except Exception as e:
            logger.error(f"获取任务历史失败: {e}")
            return None

    def get_tasks(
        self,
        status: Optional[TaskStatus] = None,
        platform: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[TaskHistory]:
        """
        获取任务历史列表

        Args:
            status: 按状态筛选
            platform: 按平台筛选
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            任务历史列表
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                query = "SELECT * FROM task_history WHERE 1=1"
                params = []

                if status:
                    query += " AND status = ?"
                    params.append(status.value)

                if platform:
                    query += " AND platform = ?"
                    params.append(platform)

                query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                cursor.execute(query, params)

                rows = cursor.fetchall()
                return [task for task in [self._row_to_task_history(row) for row in rows] if task is not None]

        except Exception as e:
            logger.error(f"获取任务历史列表失败: {e}")
            return []

    def search_tasks(self, keyword: str, limit: int = 50) -> List[TaskHistory]:
        """
        搜索任务历史

        Args:
            keyword: 搜索关键词
            limit: 返回数量限制

        Returns:
            匹配的任务历史列表
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT * FROM task_history
                    WHERE title LIKE ? OR author LIKE ? OR url LIKE ? OR summary LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit))

                rows = cursor.fetchall()
                return [task for task in [self._row_to_task_history(row) for row in rows] if task is not None]

        except Exception as e:
            logger.error(f"搜索任务历史失败: {e}")
            return []

    def delete_task(self, task_id: str) -> bool:
        """
        删除任务历史记录

        Args:
            task_id: 任务ID

        Returns:
            是否删除成功
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    DELETE FROM task_history WHERE id = ?
                """, (task_id,))

                logger.debug(f"任务历史已删除: {task_id}")
                return True

        except Exception as e:
            logger.error(f"删除任务历史失败: {e}")
            return False

    def clear_old_tasks(self, days: int = 30) -> int:
        """
        清理旧的任务历史记录

        Args:
            days: 保留最近几天的记录

        Returns:
            清理的记录数量
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                cutoff_date = datetime.now().isoformat()

                cursor.execute("""
                    DELETE FROM task_history
                    WHERE created_at < datetime('now', '-' || ? || ' days')
                """, (days,))

                count = cursor.rowcount
                logger.info(f"已清理 {count} 条旧的任务历史记录")
                return count

        except Exception as e:
            logger.error(f"清理旧任务历史失败: {e}")
            return 0

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取任务统计信息

        Returns:
            统计信息字典
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 总任务数
                cursor.execute("SELECT COUNT(*) FROM task_history")
                total = cursor.fetchone()[0]

                # 各状态任务数
                cursor.execute("""
                    SELECT status, COUNT(*) FROM task_history GROUP BY status
                """)
                status_counts = {row[0]: row[1] for row in cursor.fetchall()}

                # 各平台任务数
                cursor.execute("""
                    SELECT platform, COUNT(*) FROM task_history GROUP BY platform
                """)
                platform_counts = {row[0]: row[1] for row in cursor.fetchall()}

                return {
                    "total": total,
                    "by_status": status_counts,
                    "by_platform": platform_counts,
                }

        except Exception as e:
            logger.error(f"获取任务统计信息失败: {e}")
            return {"total": 0, "by_status": {}, "by_platform": {}}

    def _row_to_task_history(self, row: sqlite3.Row) -> Optional[TaskHistory]:
        """将数据库行转换为 TaskHistory 对象"""
        try:
            # 处理状态值（兼容旧数据）
            status_value = row["status"]
            try:
                status = TaskStatus(status_value)
            except ValueError:
                # 如果状态值无效，默认为 COMPLETED
                logger.warning(f"无效的状态值: {status_value}，使用默认值")
                status = TaskStatus.COMPLETED

            return TaskHistory(
                id=row["id"],
                url=row["url"],
                title=row["title"],
                author=row["author"] or "",
                platform=row["platform"] or "",
                mode=ProcessingMode(row["mode"]),
                targets=[ExportTarget(t) for t in row["targets"].split(",") if t],
                status=status,
                error_msg=row["error_msg"],
                created_at=datetime.fromisoformat(row["created_at"]),
                completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
                summary=row["summary"],
                highlights_count=row["highlights_count"] or 0,
                transcript_path=Path(row["transcript_path"]) if row["transcript_path"] else None,
                output_files=[Path(p) for p in row["output_files"].split(",") if p] if row["output_files"] else [],
                export_success_count=row["export_success_count"] or 0,
                export_total_count=row["export_total_count"] or 0,
            )
        except Exception as e:
            logger.error(f"转换任务历史记录失败: {e}")
            return None


# 全局数据库实例
_db_instance: Optional[TaskDatabase] = None


def get_task_database() -> TaskDatabase:
    """获取任务数据库单例实例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = TaskDatabase()
    return _db_instance
