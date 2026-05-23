"""API数据模型"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from ..models.task import ProcessingMode, ExportTarget, TaskStatus


class APIError(BaseModel):
    """API错误响应"""
    error: str = Field(..., description="错误类型")
    message: str = Field(..., description="错误信息")
    details: Optional[Dict[str, Any]] = Field(None, description="详细错误信息")


class TaskCreateRequest(BaseModel):
    """创建任务请求"""
    url: HttpUrl = Field(..., description="视频链接")
    mode: ProcessingMode = Field(default=ProcessingMode.FULL, description="处理模式")
    targets: List[ExportTarget] = Field(
        default=[ExportTarget.LOCAL],
        description="导出目标列表"
    )
    ai_provider: Optional[str] = Field(None, description="AI提供商名称")
    ai_prompt: Optional[str] = Field(None, description="自定义Prompt模板")
    cookies_from_browser: Optional[str] = Field(
        None, description="浏览器名称（chrome/safari/firefox，国内平台需要）"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://www.bilibili.com/video/BV1xx411c7mD",
                "mode": "full",
                "targets": ["local", "obsidian"],
                "ai_provider": "deepseek",
            }
        }


class TaskResponse(BaseModel):
    """任务响应"""
    id: UUID = Field(..., description="任务ID")
    url: str = Field(..., description="视频链接")
    status: TaskStatus = Field(..., description="任务状态")
    mode: ProcessingMode = Field(..., description="处理模式")
    targets: List[ExportTarget] = Field(..., description="导出目标")
    progress: float = Field(..., ge=0.0, le=100.0, description="进度百分比")
    current_step: str = Field(..., description="当前步骤")
    title: Optional[str] = Field(None, description="视频标题")
    author: Optional[str] = Field(None, description="视频作者")
    platform: Optional[str] = Field(None, description="视频平台")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    error_msg: Optional[str] = Field(None, description="错误信息")
    summary: Optional[str] = Field(None, description="AI摘要")
    output_files: List[str] = Field(default=[], description="输出文件路径列表")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "url": "https://www.bilibili.com/video/BV1xx411c7mD",
                "status": "processing",
                "mode": "full",
                "targets": ["local"],
                "progress": 45.5,
                "current_step": "正在生成AI摘要...",
                "title": "示例视频标题",
                "author": "UP主名称",
                "platform": "bilibili",
            }
        }


class TaskListResponse(BaseModel):
    """任务列表响应"""
    total: int = Field(..., description="总任务数")
    tasks: List[TaskResponse] = Field(..., description="任务列表")
    page: int = Field(default=1, description="当前页码")
    page_size: int = Field(default=20, description="每页数量")


class ProgressUpdate(BaseModel):
    """进度更新消息（WebSocket）"""
    task_id: UUID = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    progress: float = Field(..., ge=0.0, le=100.0, description="进度百分比")
    current_step: str = Field(..., description="当前步骤描述")
    message: Optional[str] = Field(None, description="附加消息")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "downloading",
                "progress": 35.0,
                "current_step": "正在下载视频...",
                "message": "已下载 35MB / 100MB",
            }
        }


class TaskSearchRequest(BaseModel):
    """任务搜索请求"""
    keyword: str = Field(..., min_length=1, description="搜索关键词")
    limit: int = Field(default=20, ge=1, le=100, description="返回数量限制")


class ExportRequest(BaseModel):
    """导出请求"""
    task_id: UUID = Field(..., description="任务ID")
    targets: List[ExportTarget] = Field(..., description="导出目标列表")


class SystemStatusResponse(BaseModel):
    """系统状态响应"""
    version: str = Field(..., description="API版本")
    status: str = Field(..., description="系统状态")
    active_tasks: int = Field(..., description="活动任务数")
    queued_tasks: int = Field(..., description="排队任务数")
    completed_tasks: int = Field(..., description="已完成任务数")
    failed_tasks: int = Field(..., description="失败任务数")


class ConfigResponse(BaseModel):
    """配置响应"""
    default_output_dir: str = Field(..., description="默认输出目录")
    supported_platforms: List[str] = Field(..., description="支持的平台列表")
    supported_ai_providers: List[str] = Field(..., description="支持的AI提供商")
    supported_export_targets: List[str] = Field(..., description="支持的导出目标")
    ai_enabled: bool = Field(default=False, description="AI功能是否已启用")
