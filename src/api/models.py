"""API数据模型"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from ..core.models import SCHEMA_VERSION, CostTier


class APIError(BaseModel):
    """API错误响应"""
    error: str = Field(..., description="错误类型")
    message: str = Field(..., description="错误信息")
    details: dict[str, Any] | None = Field(None, description="详细错误信息")


class SessionStatusResponse(BaseModel):
    platform: str
    configured: bool
    source: str
    cookie_count: int = 0
    expires_at: str | None = None
    valid: bool | None = None
    last_checked: str | None = None
    error_code: str | None = None
    warning: str | None = None


class SessionsResponse(BaseModel):
    schema_version: str
    sessions: list[SessionStatusResponse] = Field(default_factory=list)


class CreatorFeedRequest(BaseModel):
    """创作者作品列表请求。"""

    url: HttpUrl = Field(..., description="创作者主页链接")
    limit: int = Field(default=20, ge=1, le=30, description="返回作品数上限")
    max_cost: CostTier = Field(
        default=CostTier.CHEAP,
        description="最大可接受成本等级",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://space.bilibili.com/123456",
                "limit": 20,
                "max_cost": "cheap",
            }
        }


class CreatorInfoResponse(BaseModel):
    id: str
    name: str
    url: str


class CreatorFeedItemResponse(BaseModel):
    id: str
    url: str
    title: str
    published_at: str | None = None
    duration_seconds: float = 0.0
    metrics: dict[str, int] | None = None
    cover_url: str | None = None


class CreatorFeedResponse(BaseModel):
    success: bool
    schema_version: str
    request_id: str
    platform: str
    source: str
    cost_tier: str
    completeness: str
    sampled: bool
    cached: bool
    fetched_at: str
    creator: CreatorInfoResponse | None = None
    items: list[CreatorFeedItemResponse] = Field(default_factory=list)
    returned_count: int
    has_more: bool
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    error_code: str | None = None
    retry_after_seconds: int | None = None


class CommentsRequest(BaseModel):
    """评论采样请求。"""

    url: HttpUrl = Field(..., description="内容链接")
    limit: int = Field(default=20, ge=1, le=50, description="返回评论总数上限")
    sort: Literal["hot", "recent"] = Field(default="hot", description="热度或最新")
    include_replies: bool = Field(default=False, description="是否展开一层二级回复")
    max_replies_per_thread: int = Field(
        default=3,
        ge=1,
        le=10,
        description="每个一级评论最多返回的回复数",
    )
    include_author: bool = Field(
        default=False,
        description="是否返回作者展示名（不返回用户 ID/头像/主页）",
    )
    max_cost: CostTier = Field(
        default=CostTier.CHEAP,
        description="最大可接受成本等级",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://www.bilibili.com/video/BV1xx411c7mD",
                "limit": 20,
                "sort": "hot",
                "include_replies": True,
                "max_replies_per_thread": 3,
                "include_author": False,
                "max_cost": "cheap",
            }
        }


class CommentAuthorResponse(BaseModel):
    display_name: str


class CommentItemResponse(BaseModel):
    id: str
    parent_id: str | None = None
    root_id: str
    text: str
    likes: int
    created_at: str | None = None
    is_reply: bool
    reply_count: int | None = None
    author: CommentAuthorResponse | None = None
    truncated: bool | None = None


class CommentsResponse(BaseModel):
    success: bool
    schema_version: str
    request_id: str
    platform: str
    source: str
    cost_tier: str
    completeness: str
    sampled: bool
    cached: bool
    fetched_at: str
    sort: str
    items: list[CommentItemResponse] = Field(default_factory=list)
    returned_count: int
    top_level_count: int
    reply_count: int
    has_more: bool
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    error_code: str | None = None
    retry_after_seconds: int | None = None


class SystemStatusResponse(BaseModel):
    """系统状态响应"""
    version: str = Field(..., description="API版本")
    status: str = Field(..., description="系统状态")
    active_tasks: int = Field(..., description="活动任务数")
    queued_tasks: int = Field(..., description="排队任务数")
    completed_tasks: int = Field(..., description="已完成任务数")
    failed_tasks: int = Field(..., description="失败任务数")


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
    available_engines: list[str] = Field(default=["DeepSeek-V3", "Ollama"], description="可用引擎列表")


class SettingsUpdateRequest(BaseModel):
    """设置更新请求"""
    ai_engine: str | None = Field(None, description="AI 引擎")
    ai_model: str | None = Field(None, description="模型名称")
    ai_base_url: str | None = Field(None, description="API 地址")
    ai_api_key: str | None = Field(None, description="API Key（传入时更新密钥环）")
    ai_temperature: float | None = Field(None, ge=0.0, le=2.0, description="温度参数")
    ai_max_tokens: int | None = Field(None, ge=1, le=128000, description="最大 Token 数")
    ai_timeout: int | None = Field(None, ge=10, le=300, description="超时时间（秒）")
    output_dir: str | None = Field(None, description="输出目录")
    download_quality: str | None = Field(None, description="下载画质")
    whisper_model: str | None = Field(None, description="Whisper 模型")
    save_srt: bool | None = Field(None, description="保存 SRT 字幕")
    save_transcript: bool | None = Field(None, description="保存纯文本转录")
    save_markdown: bool | None = Field(None, description="保存 Markdown")
    obsidian_enabled: bool | None = Field(None, description="启用 Obsidian 导出")
    obsidian_vault_path: str | None = Field(None, description="Obsidian Vault 路径")
    obsidian_subfolder: str | None = Field(None, description="笔记保存的子文件夹")


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
    keys: list[KeyDetail] = Field(..., description="Key 列表")


class KeysListResponse(BaseModel):
    """提取器 Key 列表响应"""
    groups: dict[str, KeyGroup] = Field(..., description="按分组排列的 Key 状态")


class KeyUpdateRequest(BaseModel):
    """提取器 Key 更新请求"""
    name: str = Field(..., description="Key 标识 (如 dashscope_key, tikhub)")
    value: str = Field(..., min_length=1, description="API Key 值")


class KeyDeleteRequest(BaseModel):
    """提取器 Key 删除请求"""
    name: str = Field(..., description="Key 标识")


class ConfigResponse(BaseModel):
    """配置响应"""
    default_output_dir: str = Field(..., description="默认输出目录")
    supported_platforms: list[str] = Field(..., description="支持的平台列表")
    supported_ai_providers: list[str] = Field(..., description="支持的AI提供商")
    supported_export_targets: list[str] = Field(..., description="支持的导出目标")
    ai_enabled: bool = Field(default=False, description="AI功能是否已启用")


class ExtractAsrInfo(BaseModel):
    """ASR 元信息（method=asr 时出现）"""

    provider: str | None = None
    model: str | None = None
    model_version: str | None = None


class ExtractAttempt(BaseModel):
    """失败时逐提取器的尝试明细"""

    extractor: str | None = None
    error_code: str | None = None
    error: str | None = None


class ExtractResponse(BaseModel):
    """`POST /api/v1/extract` 的响应契约（见 docs/CONTRACT.md §3）。

    2026-11-24 新增：此前该端点没有 response_model，OpenAPI 里的 schema 是空的，
    外部调用方只能读源码猜字段。加这个模型是为了**文档化和校验**，两条刻意设计：

    1. `extra="allow"` —— 新增字段不必回来改模型，也不会因为忘加而被序列化吞掉。
       契约里那句「只增不减」必须由代码保证，而不是靠注释。
    2. 除 `success` 外全部有默认值 —— 内部异常时的错误信封（success/url/error/error_code）
       也要能通过校验；否则「已降级的失败」会被 response_model 变成 500，比不加模型更糟。

    字段语义以 docs/CONTRACT.md 为准；这里只声明形状，不重复解释成功/完整的正交性。
    """

    model_config = ConfigDict(extra="allow")

    success: bool = Field(..., description="是否拿到了东西（不是内容是否完整）")
    schema_version: str = Field(SCHEMA_VERSION, description="契约版本，目前 1.0")
    platform: str | None = Field(None, description="链接所属平台，永不是提取器名")
    title: str = Field("", description="标题")
    content: str = Field("", description="正文（可能为空）")
    language: str | None = Field(None, description="语言")
    duration_seconds: float = Field(0.0, description="视频时长（秒），图文为 0")
    cost_tier: str | None = Field(None, description="free/cheap/paid/expensive/premium")
    source: str = Field("", description="实际产出它的链路，如 douyin_asr")
    url: str = Field("", description="回显的请求 URL")
    completeness: str = Field("unknown", description="full | meta | none | unknown")
    method: str = Field("", description="subtitle | asr | page | desc | manual")
    request_id: str | None = Field(None, description="请求追踪 ID")
    segments: list[dict[str, Any]] | None = Field(None, description="时间轴分段")
    asr: ExtractAsrInfo | None = Field(None, description="ASR 元信息")
    attempts: list[ExtractAttempt] | None = Field(None, description="失败时逐提取器明细")
    error: str | None = Field(None, description="人类可读说明")
    error_code: str | None = Field(None, description="可机读的失败/部分原因")
