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
    allow_downgrade: bool = Field(
        default=False,
        description="AI服务不可用时是否降级为转录存档模式"
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


class AIModelInfo(BaseModel):
    """AI 模型信息"""
    engine: str = Field(..., description="引擎名称")
    model: str = Field(..., description="模型名称")
    is_available: bool = Field(default=False, description="是否可用（有 API Key 配置）")
    api_key_configured: bool = Field(default=False, description="API Key 是否已配置")


class SettingsResponse(BaseModel):
    """设置响应"""
    ai_engine: str = Field(default="DeepSeek-V3", description="AI 引擎")
    ai_model: str = Field(default="deepseek-chat", description="模型名称")
    ai_base_url: str = Field(default="https://api.deepseek.com", description="API 地址")
    ai_api_key_configured: bool = Field(default=False, description="API Key 是否已配置")
    ai_temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="温度参数")
    ai_max_tokens: int = Field(default=4096, ge=1, le=128000, description="最大 Token 数")
    ai_timeout: int = Field(default=120, ge=10, le=300, description="超时时间（秒）")
    output_dir: str = Field(default="", description="输出目录")
    download_quality: str = Field(default="1080p", description="下载画质")
    whisper_model: str = Field(default="small", description="Whisper 模型")
    save_srt: bool = Field(default=True, description="保存 SRT 字幕")
    save_transcript: bool = Field(default=True, description="保存纯文本转录")
    save_markdown: bool = Field(default=True, description="保存 Markdown")
    obsidian_enabled: bool = Field(default=False, description="启用 Obsidian 导出")
    obsidian_vault_path: str = Field(default="", description="Obsidian Vault 路径")
    obsidian_subfolder: str = Field(default="Inbox/Videos", description="笔记保存的子文件夹")
    available_engines: List[str] = Field(default=["DeepSeek-V3", "Ollama"], description="可用引擎列表")


class SettingsUpdateRequest(BaseModel):
    """设置更新请求"""
    ai_engine: Optional[str] = Field(None, description="AI 引擎")
    ai_model: Optional[str] = Field(None, description="模型名称")
    ai_base_url: Optional[str] = Field(None, description="API 地址")
    ai_api_key: Optional[str] = Field(None, description="API Key（传入时更新密钥环）")
    ai_temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="温度参数")
    ai_max_tokens: Optional[int] = Field(None, ge=1, le=128000, description="最大 Token 数")
    ai_timeout: Optional[int] = Field(None, ge=10, le=300, description="超时时间（秒）")
    output_dir: Optional[str] = Field(None, description="输出目录")
    download_quality: Optional[str] = Field(None, description="下载画质")
    whisper_model: Optional[str] = Field(None, description="Whisper 模型")
    save_srt: Optional[bool] = Field(None, description="保存 SRT 字幕")
    save_transcript: Optional[bool] = Field(None, description="保存纯文本转录")
    save_markdown: Optional[bool] = Field(None, description="保存 Markdown")
    obsidian_enabled: Optional[bool] = Field(None, description="启用 Obsidian 导出")
    obsidian_vault_path: Optional[str] = Field(None, description="Obsidian Vault 路径")
    obsidian_subfolder: Optional[str] = Field(None, description="笔记保存的子文件夹")


class KeyDetail(BaseModel):
    """提取器 Key 详情"""
    name: str = Field(..., description="Key 标识")
    label: str = Field(..., description="显示名称")
    env: str = Field(..., description="环境变量名")
    configured: bool = Field(..., description="是否已配置")


class KeyGroup(BaseModel):
    """提取器 Key 组"""
    label: str = Field(..., description="组显示名称")
    all_configured: bool = Field(..., description="组内所有 Key 是否均已配置")
    keys: List[KeyDetail] = Field(..., description="Key 列表")


class KeysListResponse(BaseModel):
    """提取器 Key 列表响应"""
    groups: Dict[str, KeyGroup] = Field(..., description="按分组排列的 Key 状态")


class KeyUpdateRequest(BaseModel):
    """提取器 Key 更新请求"""
    name: str = Field(..., description="Key 标识 (如 coze, tikhub)")
    value: str = Field(..., min_length=1, description="API Key 值")


class KeyDeleteRequest(BaseModel):
    """提取器 Key 删除请求"""
    name: str = Field(..., description="Key 标识")


class ConfigResponse(BaseModel):
    """配置响应"""
    default_output_dir: str = Field(..., description="默认输出目录")
    supported_platforms: List[str] = Field(..., description="支持的平台列表")
    supported_ai_providers: List[str] = Field(..., description="支持的AI提供商")
    supported_export_targets: List[str] = Field(..., description="支持的导出目标")
    ai_enabled: bool = Field(default=False, description="AI功能是否已启用")
