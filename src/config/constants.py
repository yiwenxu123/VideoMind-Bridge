"""应用配置常量 - 集中管理所有默认配置值"""

from pathlib import Path


class Defaults:
    """默认值常量"""

    # Whisper 模型
    WHISPER_MODEL = "small"

    # AI 引擎和模型
    AI_ENGINE = "DeepSeek-V3"
    AI_MODEL = "deepseek-chat"

    # 视频下载
    DOWNLOAD_VIDEO = True
    VIDEO_QUALITY = "best"

    # 输出目录
    OUTPUT_DIR = Path.home() / "Downloads" / "VideoMind"

    # Obsidian 默认子文件夹
    OBSIDIAN_SUBFOLDER = "00 Inbox/Videos"

    # 处理模式
    PROCESSING_MODE = "full"  # download_only, transcribe_only, full


class ProgressWeights:
    """进度权重分配"""

    DOWNLOAD = 0.30      # 下载占 30%
    TRANSCRIBE = 0.50    # 转录占 50%
    AI_PROCESSING = 0.15 # AI 处理占 15%
    EXPORT = 0.05        # 导出占 5%


class UIConfig:
    """UI 配置常量"""

    # 窗口
    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 800
    MIN_WIDTH = 800
    MIN_HEIGHT = 600

    # 任务列表
    MAX_TASK_HISTORY = 50


class RetryConfig:
    """重试配置"""

    MAX_RETRIES = 3
    RETRY_DELAY = 1.0      # 初始重试延迟（秒）
    RETRY_BACKOFF = 2.0    # 指数退避因子


class TimeoutConfig:
    """超时配置"""

    API_TIMEOUT = 120.0    # API 调用超时
    DOWNLOAD_TIMEOUT = 300.0  # 下载超时
    TEST_CONNECTION_TIMEOUT = 30.0  # 连接测试超时


class SupportedFormats:
    """支持的格式"""

    VIDEO_QUALITIES = ["best", "worst", "720p", "1080p", "4k"]

    WHISPER_MODELS = ["tiny", "base", "small", "medium", "large"]

    AI_ENGINES = [
        "DeepSeek-V3",
        "智谱 AI",
        "Moonshot AI",
        "MiniMax",
        "豆包",
        "本地 Ollama"
    ]

    AI_MODELS = {
        "DeepSeek-V3": ["deepseek-chat", "deepseek-reasoner"],
        "智谱 AI": ["glm-4.7", "glm-4.7-Flash"],
        "Moonshot AI": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k", "kimi-latest"],
        "MiniMax": ["MiniMax-Text-01", "abab6.5-chat", "minmax-2.1"],
        "豆包": ["doubao-1.6-pro", "doubao-1.6-lite", "doubao-1.6-flash"],
        "本地 Ollama": ["llama2", "mistral", "qwen"]
    }


class APIEndpoints:
    """API 端点配置"""

    DEEPSEEK = "https://api.deepseek.com/v1"
    ZHIPU = "https://open.bigmodel.cn/api/paas/v4"
    MOONSHOT = "https://api.moonshot.cn/v1"
    MINIMAX = "https://api.minimax.chat/v1"
    DOUBAO = "https://ark.cn-beijing.volces.com/api/v3"
    OLLAMA = "http://localhost:11434/v1"

    DEFAULTS = {
        "deepseek": DEEPSEEK,
        "zhipu": ZHIPU,
        "moonshot": MOONSHOT,
        "minimax": MINIMAX,
        "doubao": DOUBAO,
        "ollama": OLLAMA,
    }


class ExportConfig:
    """导出配置"""

    # 文件名模板
    FILENAME_TEMPLATE = "{title}_{timestamp}"

    # 支持的导出格式
    FORMATS = {
        "markdown": ".md",
        "json": ".json",
        "txt": ".txt",
        "srt": ".srt"
    }


class BidirectionalMap:
    """双向映射类，支持配置值和显示值互相转换"""

    def __init__(self, mapping: dict):
        """
        初始化双向映射

        Args:
            mapping: 配置值到显示值的映射字典
        """
        self._config_to_display = mapping
        self._display_to_config = {v: k for k, v in mapping.items()}

    def to_display(self, config_value: str, default: str = None) -> str:
        """配置值转显示值"""
        return self._config_to_display.get(config_value, default or config_value)

    def to_config(self, display_value: str, default: str = None) -> str:
        """显示值转配置值"""
        return self._display_to_config.get(display_value, default or display_value)

    @property
    def config_values(self):
        """获取所有配置值"""
        return list(self._config_to_display.keys())

    @property
    def display_values(self):
        """获取所有显示值"""
        return list(self._display_to_config.keys())


class ConfigMaps:
    """配置映射集合"""

    # 主题映射
    THEME = BidirectionalMap({
        "system": "跟随系统",
        "light": "浅色",
        "dark": "深色"
    })

    # 语言映射
    LANGUAGE = BidirectionalMap({
        "zh_CN": "简体中文",
        "en_US": "English"
    })

    # 组织方式映射
    ORGANIZE = BidirectionalMap({
        "date": "按日期",
        "source": "按来源",
        "none": "不组织"
    })

    # 视频质量映射
    VIDEO_QUALITY = BidirectionalMap({
        "best": "最佳质量",
        "1080p": "1080p",
        "720p": "720p",
        "480p": "480p",
        "worst": "最低质量"
    })


class HistoryConfig:
    """历史记录配置"""

    # 标题截断长度
    TITLE_MAX_LENGTH = 30
    TITLE_TRUNCATE_SUFFIX = "..."

    # 列表项尺寸
    ITEM_WIDTH = 360
    ITEM_HEIGHT = 80

    # 最大显示记录数
    MAX_DISPLAY_ITEMS = 50


class DialogConfig:
    """对话框配置"""

    # 设置对话框
    SETTINGS_WIDTH = 700
    SETTINGS_HEIGHT = 550
    SETTINGS_MIN_WIDTH = 700
    SETTINGS_MIN_HEIGHT = 550

    # Prompt 模板对话框
    TEMPLATE_DIALOG_WIDTH = 800
    TEMPLATE_DIALOG_HEIGHT = 600
    TEMPLATE_DIALOG_MIN_WIDTH = 800
    TEMPLATE_DIALOG_MIN_HEIGHT = 600

    # 预览对话框
    PREVIEW_DIALOG_WIDTH = 600
    PREVIEW_DIALOG_HEIGHT = 400

    # 列表最大宽度
    TEMPLATE_LIST_MAX_WIDTH = 250

    # 分割器默认尺寸
    SPLITTER_LEFT_SIZE = 250
    SPLITTER_RIGHT_SIZE = 550


class SliderConfig:
    """滑块配置"""

    # 温度滑块
    TEMPERATURE_MIN = 0
    TEMPERATURE_MAX = 100
    TEMPERATURE_DEFAULT = 70
    TEMPERATURE_STEP = 1


class SpinBoxConfig:
    """数值输入框配置"""

    # 最大 Token
    MAX_TOKENS_MIN = 1000
    MAX_TOKENS_MAX = 8000
    MAX_TOKENS_DEFAULT = 4096
    MAX_TOKENS_STEP = 100

    # 超时时间
    TIMEOUT_MIN = 30
    TIMEOUT_MAX = 300
    TIMEOUT_DEFAULT = 120
    TIMEOUT_STEP = 10


class ButtonConfig:
    """按钮配置"""

    # 刷新按钮
    REFRESH_BUTTON_MAX_WIDTH = 30


class DatabaseConfig:
    """数据库配置"""

    # 清空历史时的查询限制
    CLEAR_HISTORY_LIMIT = 1000


class Icons:
    """图标配置"""

    # 状态图标
    STATUS_COMPLETED = "✅"
    STATUS_FAILED = "❌"
    STATUS_CANCELLED = "🚫"
    STATUS_PENDING = "📋"

    # 平台图标
    PLATFORM_BILIBILI = "📺"
    PLATFORM_YOUTUBE = "▶️"
    PLATFORM_XIAOHONGSHU = "📕"
    PLATFORM_DEFAULT = "🌐"

    # 通用图标
    TEMPLATE = "📝"
    SETTINGS = "⚙️"
    HISTORY = "📚"
    EXPORT = "📤"
    DOWNLOAD = "⬇️"
