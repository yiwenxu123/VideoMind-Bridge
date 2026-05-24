"""Exporter 插件基类定义"""

from abc import ABC, abstractmethod

from ..models.task import ExportContext, ExportResult


class BaseExporter(ABC):
    """
    导出器基类
    
    所有导出目标（Obsidian/Local/Notion/Webhook）必须继承此类
    """

    # 显示名称
    name: str = "Base Exporter"
    # Emoji 图标
    icon: str = "📄"

    @abstractmethod
    def validate_config(self) -> tuple[bool, str]:
        """
        检查配置是否有效
        
        Returns:
            Tuple[bool, str]: (是否可用, 错误信息)
            - 配置有效时返回 (True, "")
            - 配置无效时返回 (False, "错误描述")
        """
        raise NotImplementedError()

    @abstractmethod
    def export(self, context: ExportContext) -> ExportResult:
        """
        执行导出操作
        
        Args:
            context: 导出上下文，包含所有必要的数据和文件路径
            
        Returns:
            ExportResult: 导出结果，包含成功/失败状态和相关元数据
            
        Raises:
            ExportError: 导出过程中发生错误
        """
        raise NotImplementedError()

    def get_config_schema(self) -> dict:
        """
        获取配置项的JSON Schema（可选实现）
        
        Returns:
            dict: JSON Schema 定义，用于UI动态生成配置表单
        """
        return {}
