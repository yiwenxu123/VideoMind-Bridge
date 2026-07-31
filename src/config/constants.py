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

    # Obsidian 默认子文件夹 (与 models/config.py ExportConfig.obsidian.subfolder 默认值一致)
    OBSIDIAN_SUBFOLDER = "Inbox/Videos"

    # 处理模式
    PROCESSING_MODE = "full"  # download_only, transcribe_only, full


class ProgressWeights:
    """进度权重分配"""

    DOWNLOAD = 0.30      # 下载占 30%
    TRANSCRIBE = 0.50    # 转录占 50%
    AI_PROCESSING = 0.15 # AI 处理占 15%
    EXPORT = 0.05        # 导出占 5%


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

    def to_display(self, config_value: str, default: str | None = None) -> str:
        return self._config_to_display.get(config_value, default or config_value)

    def to_config(self, display_value: str, default: str | None = None) -> str:
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

    # 组织方式映射 (与 local_exporter 支持的 organize_by 对齐)
    ORGANIZE = BidirectionalMap({
        "date": "按日期",
        "title": "按标题",
        "flat": "不组织"
    })

    # 视频质量映射
    VIDEO_QUALITY = BidirectionalMap({
        "best": "最佳质量",
        "1080p": "1080p",
        "720p": "720p",
        "480p": "480p",
        "worst": "最低质量"
    })
