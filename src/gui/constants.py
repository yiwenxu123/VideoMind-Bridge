"""GUI 专属常量 - 界面布局、图标、对话框配置

从 src/config/constants.py 解耦而来，仅包含 GUI/UI 相关常量。
"""

class UIConfig:
    """UI 配置常量"""

    # 窗口
    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 800
    MIN_WIDTH = 800
    MIN_HEIGHT = 600

    # 任务列表
    MAX_TASK_HISTORY = 50


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
