"""自定义异常类 - 统一错误处理"""


class VideoMindError(Exception):
    """VideoMind Bridge 基础异常类"""
    
    def __init__(self, message: str, error_code: str = None, details: dict = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.details = details or {}
    
    def __str__(self):
        if self.details:
            return f"[{self.error_code}] {self.message} - Details: {self.details}"
        return f"[{self.error_code}] {self.message}"


class DownloadError(VideoMindError):
    """下载相关错误"""
    
    ERROR_CODES = {
        "NETWORK_ERROR": "网络连接失败",
        "VIDEO_NOT_FOUND": "视频不存在或已被删除",
        "AGE_RESTRICTED": "视频有年龄限制",
        "REGION_BLOCKED": "视频在您的地区不可用",
        "RATE_LIMITED": "下载频率受限，请稍后再试",
        "DOWNLOAD_FAILED": "下载过程中发生错误",
        "INVALID_URL": "无效的视频链接",
        "UNSUPPORTED_PLATFORM": "不支持的视频平台",
    }
    
    def __init__(self, message: str, error_code: str = "DOWNLOAD_FAILED", details: dict = None):
        super().__init__(message, error_code, details)


class TranscribeError(VideoMindError):
    """转录相关错误"""
    
    ERROR_CODES = {
        "AUDIO_EXTRACTION_FAILED": "音频提取失败",
        "MODEL_LOAD_FAILED": "转录模型加载失败",
        "TRANSCRIBE_FAILED": "转录过程中发生错误",
        "LANGUAGE_NOT_SUPPORTED": "不支持的语言",
        "AUDIO_TOO_SHORT": "音频太短，无法转录",
        "AUDIO_TOO_LONG": "音频太长，超出处理限制",
    }
    
    def __init__(self, message: str, error_code: str = "TRANSCRIBE_FAILED", details: dict = None):
        super().__init__(message, error_code, details)


class AIError(VideoMindError):
    """AI 服务相关错误"""
    
    ERROR_CODES = {
        "API_KEY_INVALID": "API Key 无效或已过期",
        "RATE_LIMIT_EXCEEDED": "API 调用频率超限",
        "QUOTA_EXHAUSTED": "API 额度已用完",
        "MODEL_NOT_FOUND": "模型不存在或不可用",
        "TIMEOUT": "AI 服务请求超时",
        "NETWORK_ERROR": "AI 服务网络错误",
        "CONTENT_FILTERED": "内容被 AI 服务过滤",
        "GENERATION_FAILED": "内容生成失败",
    }
    
    def __init__(self, message: str, error_code: str = "GENERATION_FAILED", details: dict = None):
        super().__init__(message, error_code, details)


class ExportError(VideoMindError):
    """导出相关错误"""
    
    ERROR_CODES = {
        "OUTPUT_DIR_NOT_WRITABLE": "输出目录不可写",
        "FILE_WRITE_FAILED": "文件写入失败",
        "OBSIDIAN_VAULT_NOT_FOUND": "Obsidian Vault 路径不存在",
        "TEMPLATE_RENDER_FAILED": "模板渲染失败",
        "EXPORT_FAILED": "导出过程中发生错误",
    }
    
    def __init__(self, message: str, error_code: str = "EXPORT_FAILED", details: dict = None):
        super().__init__(message, error_code, details)


class ConfigError(VideoMindError):
    """配置相关错误"""
    
    ERROR_CODES = {
        "CONFIG_FILE_CORRUPTED": "配置文件损坏",
        "CONFIG_SAVE_FAILED": "配置保存失败",
        "CONFIG_LOAD_FAILED": "配置加载失败",
        "INVALID_CONFIG_VALUE": "无效的配置值",
    }
    
    def __init__(self, message: str, error_code: str = "CONFIG_ERROR", details: dict = None):
        super().__init__(message, error_code, details)


class ValidationError(VideoMindError):
    """数据验证错误"""
    
    ERROR_CODES = {
        "INVALID_URL": "无效的 URL",
        "INVALID_PATH": "无效的路径",
        "REQUIRED_FIELD_MISSING": "必填字段缺失",
        "INVALID_FORMAT": "格式无效",
    }
    
    def __init__(self, message: str, error_code: str = "VALIDATION_ERROR", details: dict = None):
        super().__init__(message, error_code, details)


class RetryableError(VideoMindError):
    """可重试的错误基类"""
    
    def __init__(self, message: str, error_code: str = "RETRYABLE_ERROR", 
                 details: dict = None, retry_count: int = 0, max_retries: int = 3):
        super().__init__(message, error_code, details)
        self.retry_count = retry_count
        self.max_retries = max_retries
    
    def can_retry(self) -> bool:
        """检查是否可以重试"""
        return self.retry_count < self.max_retries
    
    def increment_retry(self) -> "RetryableError":
        """增加重试计数"""
        self.retry_count += 1
        return self


class NetworkError(RetryableError):
    """网络相关错误（可重试）"""
    
    def __init__(self, message: str = "网络错误", error_code: str = "NETWORK_ERROR",
                 details: dict = None, retry_count: int = 0, max_retries: int = 3):
        super().__init__(message, error_code, details, retry_count, max_retries)


class ServiceUnavailableError(RetryableError):
    """服务不可用错误（可重试）"""
    
    def __init__(self, message: str = "服务暂时不可用", error_code: str = "SERVICE_UNAVAILABLE",
                 details: dict = None, retry_count: int = 0, max_retries: int = 3):
        super().__init__(message, error_code, details, retry_count, max_retries)


class TimeoutError(RetryableError):
    """超时错误（可重试）"""
    
    def __init__(self, message: str = "请求超时", error_code: str = "TIMEOUT",
                 details: dict = None, retry_count: int = 0, max_retries: int = 3):
        super().__init__(message, error_code, details, retry_count, max_retries)
