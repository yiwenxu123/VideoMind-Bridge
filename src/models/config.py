"""配置数据模型"""

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class AIEngine(StrEnum):
    """AI 引擎类型"""
    DEEPSEEK = "DeepSeek-V3"
    OLLAMA = "Ollama"


@dataclass
class AIConfig:
    """AI 配置"""
    engine: AIEngine = AIEngine.DEEPSEEK
    model: str = "deepseek-chat"
    api_key: str = ""  # 明文存储，实际使用时会加密
    base_url: str = "https://api.deepseek.com"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 120

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # 将 Enum 转换为字符串
        if isinstance(self.engine, AIEngine):
            data['engine'] = self.engine.value
        else:
            data['engine'] = str(self.engine)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AIConfig":
        # 处理 engine 字段，从字符串转换为枚举
        engine = data.get("engine", AIEngine.DEEPSEEK)
        if isinstance(engine, str):
            try:
                engine = AIEngine(engine)
            except ValueError:
                engine = AIEngine.DEEPSEEK
        return cls(
            engine=engine,
            model=data.get("model", "deepseek-chat"),
            api_key=data.get("api_key", ""),
            base_url=data.get("base_url", "https://api.deepseek.com"),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens", 4096),
            timeout=data.get("timeout", 120)
        )


@dataclass
class DownloadConfig:
    """下载配置"""
    output_dir: str = str(Path.home() / "Downloads" / "VideoMind")
    video_quality: str = "1080p"
    download_video: bool = True
    organize_by: str = "date"  # date, title, flat

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DownloadConfig":
        return cls(**data)


@dataclass
class TranscribeConfig:
    """转录配置"""
    whisper_model: str = "small"
    language: str | None = None  # None 表示自动检测

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscribeConfig":
        return cls(
            whisper_model=data.get("whisper_model", "small"),
            language=data.get("language")
        )


@dataclass
class AsrBackendConfig:
    """单个 ASR 后端配置"""
    enabled: bool = True
    model: str = ""
    options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "model": self.model,
            "options": dict(self.options),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AsrBackendConfig":
        return cls(
            enabled=bool(data.get("enabled", True)),
            model=str(data.get("model", "") or ""),
            options=dict(data.get("options", {}) or {}),
        )


@dataclass
class AsrConfig:
    """统一 ASR 链配置（阶段 2）

    chain: 后端降级顺序；空列表视为配置错误。
    language: 默认语言，None 表示由后端自动检测。
    max_cost: 允许调用的最高成本档位；默认 premium 等价于不限制，
        以保持旧链路（本地→DashScope→阿里云）的降级行为。
    backends: 各后端的模型与专属选项；未列出的后端使用环境变量/默认值。
    """

    chain: list[str] = field(default_factory=lambda: ["faster_whisper", "dashscope"])
    language: str | None = None
    max_cost: str = "premium"
    backends: dict[str, AsrBackendConfig] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain": list(self.chain),
            "language": self.language,
            "max_cost": self.max_cost,
            "backends": {name: cfg.to_dict() for name, cfg in self.backends.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AsrConfig":
        raw_backends = data.get("backends", {}) or {}
        return cls(
            chain=list(data.get("chain", ["faster_whisper", "dashscope"])),
            language=data.get("language"),
            max_cost=str(data.get("max_cost", "premium") or "premium"),
            backends={
                name: AsrBackendConfig.from_dict(cfg if isinstance(cfg, dict) else {})
                for name, cfg in raw_backends.items()
            },
        )

    def backend_configs(self) -> dict[str, dict[str, Any]]:
        """转换为适配器消费的扁平配置：model 提升为顶层键。"""
        result: dict[str, dict[str, Any]] = {}
        for name, cfg in self.backends.items():
            if not cfg.enabled:
                continue
            data = dict(cfg.options)
            if cfg.model:
                data["model"] = cfg.model
            result[name] = data
        return result


@dataclass
class ObsidianConfig:
    """Obsidian 导出配置"""
    enabled: bool = False
    vault_path: str = ""
    subfolder: str = "Inbox/Videos"
    attachments_folder: str = "Attachments"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ObsidianConfig":
        return cls(**data)


@dataclass
class LocalExportConfig:
    """本地导出配置"""
    enabled: bool = True
    output_path: str = str(Path.home() / "Downloads" / "VideoMind")
    organize_by: str = "date"
    save_srt: bool = True
    save_transcript: bool = True
    save_markdown: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LocalExportConfig":
        return cls(**data)


@dataclass
class WebhookConfig:
    """Webhook 导出配置"""
    enabled: bool = False
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    events: list[str] = field(default_factory=lambda: ["on_completed"])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WebhookConfig":
        return cls(
            enabled=data.get("enabled", False),
            url=data.get("url", ""),
            headers=data.get("headers", {}),
            timeout=data.get("timeout", 30),
            max_retries=data.get("max_retries", 3),
            retry_delay=data.get("retry_delay", 1.0),
            events=data.get("events", ["on_completed"])
        )


@dataclass
class ExportConfig:
    """导出配置"""
    obsidian: ObsidianConfig = field(default_factory=ObsidianConfig)
    local: LocalExportConfig = field(default_factory=LocalExportConfig)
    webhook: WebhookConfig = field(default_factory=WebhookConfig)
    default_targets: list[str] = field(default_factory=lambda: ["local"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "obsidian": self.obsidian.to_dict(),
            "local": self.local.to_dict(),
            "webhook": self.webhook.to_dict(),
            "default_targets": self.default_targets
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExportConfig":
        return cls(
            obsidian=ObsidianConfig.from_dict(data.get("obsidian", {})),
            local=LocalExportConfig.from_dict(data.get("local", {})),
            webhook=WebhookConfig.from_dict(data.get("webhook", {})),
            default_targets=data.get("default_targets", ["local"])
        )


@dataclass
class UIConfig:
    """UI 配置"""
    theme: str = "system"  # light, dark, system
    language: str = "zh_CN"
    minimize_to_tray: bool = True
    show_notifications: bool = True
    window_geometry: dict[str, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UIConfig":
        return cls(**data)


@dataclass
class PerformanceConfig:
    """性能配置"""
    max_concurrent_tasks: int = 2  # 最大并发任务数
    enable_model_cache: bool = True  # 启用模型缓存
    auto_clear_cache_on_exit: bool = False  # 退出时自动清理缓存

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PerformanceConfig":
        return cls(
            max_concurrent_tasks=data.get("max_concurrent_tasks", 2),
            enable_model_cache=data.get("enable_model_cache", True),
            auto_clear_cache_on_exit=data.get("auto_clear_cache_on_exit", False)
        )


@dataclass
class AppConfig:
    """应用主配置"""
    version: str = "1"
    ai: AIConfig = field(default_factory=AIConfig)
    download: DownloadConfig = field(default_factory=DownloadConfig)
    transcribe: TranscribeConfig = field(default_factory=TranscribeConfig)
    asr: AsrConfig = field(default_factory=AsrConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "ai": self.ai.to_dict(),
            "download": self.download.to_dict(),
            "transcribe": self.transcribe.to_dict(),
            "asr": self.asr.to_dict(),
            "export": self.export.to_dict(),
            "ui": self.ui.to_dict(),
            "performance": self.performance.to_dict()
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        return cls(
            version=data.get("version", "1"),
            ai=AIConfig.from_dict(data.get("ai", {})),
            download=DownloadConfig.from_dict(data.get("download", {})),
            transcribe=TranscribeConfig.from_dict(data.get("transcribe", {})),
            asr=AsrConfig.from_dict(data.get("asr", {})),
            export=ExportConfig.from_dict(data.get("export", {})),
            ui=UIConfig.from_dict(data.get("ui", {})),
            performance=PerformanceConfig.from_dict(data.get("performance", {}))
        )

    @classmethod
    def get_default_config(cls) -> "AppConfig":
        """获取默认配置"""
        return cls()
