"""Prompt 模板系统 - 支持多种摘要风格"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from jinja2 import BaseLoader, Environment

logger = logging.getLogger(__name__)


class TemplateStyle(str, Enum):
    """模板风格类型"""
    DEFAULT = "default"           # 默认风格
    ACADEMIC = "academic"         # 学术风格
    QUICK = "quick"               # 速览风格
    ACTION = "action"             # 行动项风格
    TRANSLATION = "translation"   # 翻译风格
    QNA = "qna"                   # 问答风格
    XIAOHONGSHU = "xiaohongshu"   # 小红书风格


@dataclass
class PromptTemplate:
    """Prompt 模板定义"""
    id: str                       # 唯一标识
    name: str                     # 显示名称
    description: str              # 描述
    template: str                 # Jinja2 模板内容
    style: TemplateStyle          # 模板风格
    variables: list[str] = field(default_factory=list)  # 模板变量列表
    is_default: bool = False      # 是否为默认模板
    is_builtin: bool = True       # 是否为内置模板
    created_at: str | None = None  # 创建时间
    updated_at: str | None = None  # 更新时间

    def render(self, **kwargs) -> str:
        """渲染模板"""
        env = Environment(loader=BaseLoader())
        template = env.from_string(self.template)
        return template.render(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "template": self.template,
            "style": self.style.value,
            "variables": self.variables,
            "is_default": self.is_default,
            "is_builtin": self.is_builtin,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromptTemplate":
        """从字典创建"""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            template=data["template"],
            style=TemplateStyle(data.get("style", "default")),
            variables=data.get("variables", []),
            is_default=data.get("is_default", False),
            is_builtin=data.get("is_builtin", True),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


class PromptTemplateManager:
    """Prompt 模板管理器"""

    def __init__(self, storage_path: Path | None = None):
        """
        初始化模板管理器

        Args:
            storage_path: 模板存储路径，默认 ~/.config/VideoMind/prompts/
        """
        if storage_path is None:
            storage_path = Path.home() / ".config" / "VideoMind" / "prompts"

        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._templates: dict[str, PromptTemplate] = {}
        self._load_builtin_templates()
        self._load_custom_templates()

    def _load_builtin_templates(self) -> None:
        """加载内置模板"""
        builtin_templates = self._create_builtin_templates()
        for template in builtin_templates:
            self._templates[template.id] = template

    def _load_custom_templates(self) -> None:
        """从文件加载自定义模板"""
        custom_file = self.storage_path / "custom_templates.yaml"
        if custom_file.exists():
            try:
                with open(custom_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if data and isinstance(data, dict):
                    for template_data in data.get("templates", []):
                        try:
                            template = PromptTemplate.from_dict(template_data)
                            template.is_builtin = False
                            self._templates[template.id] = template
                        except Exception as e:
                            logger.error(f"加载自定义模板失败: {e}")
            except Exception as e:
                logger.error(f"加载自定义模板文件失败: {e}")

    def _save_custom_templates(self) -> bool:
        """保存自定义模板到文件"""
        try:
            custom_templates = [
                t.to_dict() for t in self._templates.values()
                if not t.is_builtin
            ]

            data = {"templates": custom_templates}

            custom_file = self.storage_path / "custom_templates.yaml"
            with open(custom_file, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False)

            return True
        except Exception as e:
            logger.error(f"保存自定义模板失败: {e}")
            return False

    def _create_builtin_templates(self) -> list[PromptTemplate]:
        """创建内置模板"""
        from datetime import datetime
        now = datetime.now().isoformat()

        return [
            PromptTemplate(
                id="default",
                name="默认风格",
                description="标准摘要风格，适合大多数场景",
                template=self._default_template(),
                style=TemplateStyle.DEFAULT,
                variables=["title", "transcript"],
                is_default=True,
                is_builtin=True,
                created_at=now,
                updated_at=now,
            ),
            PromptTemplate(
                id="academic",
                name="学术风格",
                description="严谨学术风格，强调概念和论证",
                template=self._academic_template(),
                style=TemplateStyle.ACADEMIC,
                variables=["title", "transcript"],
                is_builtin=True,
                created_at=now,
                updated_at=now,
            ),
            PromptTemplate(
                id="quick",
                name="速览风格",
                description="简洁快速，适合快速了解内容",
                template=self._quick_template(),
                style=TemplateStyle.QUICK,
                variables=["title", "transcript"],
                is_builtin=True,
                created_at=now,
                updated_at=now,
            ),
            PromptTemplate(
                id="action",
                name="行动项风格",
                description="聚焦可执行的行动建议",
                template=self._action_template(),
                style=TemplateStyle.ACTION,
                variables=["title", "transcript"],
                is_builtin=True,
                created_at=now,
                updated_at=now,
            ),
            PromptTemplate(
                id="translation",
                name="翻译风格",
                description="双语对照，适合外语学习",
                template=self._translation_template(),
                style=TemplateStyle.TRANSLATION,
                variables=["title", "transcript"],
                is_builtin=True,
                created_at=now,
                updated_at=now,
            ),
            PromptTemplate(
                id="qna",
                name="问答风格",
                description="以问答形式呈现核心内容",
                template=self._qna_template(),
                style=TemplateStyle.QNA,
                variables=["title", "transcript"],
                is_builtin=True,
                created_at=now,
                updated_at=now,
            ),
        ]

    def get_template(self, template_id: str) -> PromptTemplate | None:
        """获取指定模板"""
        return self._templates.get(template_id)

    def get_default_template(self) -> PromptTemplate:
        """获取默认模板"""
        for template in self._templates.values():
            if template.is_default:
                return template

        # 如果没有设置默认，返回第一个
        return next(iter(self._templates.values()))

    def get_all_templates(self) -> list[PromptTemplate]:
        """获取所有模板"""
        return list(self._templates.values())

    def get_templates_by_style(self, style: TemplateStyle) -> list[PromptTemplate]:
        """按风格获取模板"""
        return [t for t in self._templates.values() if t.style == style]

    def create_template(
        self,
        name: str,
        description: str,
        template: str,
        style: TemplateStyle = TemplateStyle.DEFAULT,
        variables: list[str] | None = None,
        set_as_default: bool = False
    ) -> PromptTemplate:
        """创建自定义模板"""
        # 生成唯一 ID
        import uuid
        from datetime import datetime
        template_id = f"custom_{uuid.uuid4().hex[:8]}"

        new_template = PromptTemplate(
            id=template_id,
            name=name,
            description=description,
            template=template,
            style=style,
            variables=variables or ["title", "transcript"],
            is_default=set_as_default,
            is_builtin=False,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        # 如果设为默认，取消其他模板的默认状态
        if set_as_default:
            for t in self._templates.values():
                t.is_default = False

        self._templates[template_id] = new_template
        self._save_custom_templates()

        return new_template

    def update_template(
        self,
        template_id: str,
        name: str | None = None,
        description: str | None = None,
        template: str | None = None,
        style: TemplateStyle | None = None,
        set_as_default: bool | None = None
    ) -> bool:
        """更新模板"""
        if template_id not in self._templates:
            return False

        existing = self._templates[template_id]

        # 内置模板不允许修改核心内容
        if existing.is_builtin and template is not None:
            logger.warning("内置模板不允许修改模板内容")
            return False

        if name is not None:
            existing.name = name
        if description is not None:
            existing.description = description
        if template is not None:
            existing.template = template
        if style is not None:
            existing.style = style

        if set_as_default is not None:
            if set_as_default:
                for t in self._templates.values():
                    t.is_default = False
                existing.is_default = True
            else:
                existing.is_default = False

        from datetime import datetime
        existing.updated_at = datetime.now().isoformat()

        self._save_custom_templates()
        return True

    def delete_template(self, template_id: str) -> bool:
        """删除模板（仅自定义模板）"""
        if template_id not in self._templates:
            return False

        template = self._templates[template_id]
        if template.is_builtin:
            print("内置模板不能删除")
            return False

        del self._templates[template_id]
        self._save_custom_templates()
        return True

    def set_default_template(self, template_id: str) -> bool:
        """设置默认模板"""
        if template_id not in self._templates:
            return False

        for t in self._templates.values():
            t.is_default = False

        self._templates[template_id].is_default = True
        self._save_custom_templates()
        return True

    def preview_template(self, template_id: str, **kwargs) -> str:
        """预览模板渲染结果"""
        template = self.get_template(template_id)
        if not template:
            return "模板不存在"

        # 使用示例数据预览
        preview_data = {
            "title": kwargs.get("title", "示例视频标题"),
            "transcript": kwargs.get("transcript", "[00:00:00] 这是示例转录内容\n[00:01:30] 示例要点一\n[00:03:45] 示例要点二"),
        }

        return template.render(**preview_data)

    def export_template(self, template_id: str, output_path: Path) -> bool:
        """导出模板到文件"""
        template = self.get_template(template_id)
        if not template:
            return False

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(template.to_dict(), f, allow_unicode=True)
            return True
        except Exception as e:
            logger.error(f"导出模板失败: {e}")
            return False

    def import_template(self, file_path: Path) -> PromptTemplate | None:
        """从文件导入模板"""
        try:
            with open(file_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if isinstance(data, dict):
                template = PromptTemplate.from_dict(data)
                template.is_builtin = False
                template.id = f"imported_{template.id}"
                self._templates[template.id] = template
                self._save_custom_templates()
                return template
        except Exception as e:
            logger.error(f"导入模板失败: {e}")

        return None

    # ========== 内置模板定义 ==========

    def _default_template(self) -> str:
        """默认模板"""
        return """请分析以下视频转录内容，生成结构化摘要和时间轴。

视频标题: {{title}}

转录内容:
{{transcript}}

请按以下格式输出：

# {{title}}

## 一句话总结
[用一句话概括视频核心内容]

## 关键时间轴
从转录文本中提取 5-8 个关键时间点，格式如下：

- [00:05:23] 要点1内容
- [00:08:15] 要点2内容
- [00:12:30] 要点3内容
...

要求：
1. 每个要点必须包含具体时间戳 [HH:MM:SS] 格式
2. 时间戳要精确到秒
3. 要点要覆盖视频的核心内容
4. 语言简洁明了
"""

    def _academic_template(self) -> str:
        """学术风格模板"""
        return """请以学术分析的方式处理以下视频内容，提取核心概念、论证逻辑和学术价值。

视频标题: {{title}}

转录内容:
{{transcript}}

请按以下学术格式输出：

# {{title}}

## 核心论点
[用一句话概括视频的核心学术论点]

## 关键概念
- 概念1: [定义和解释]
- 概念2: [定义和解释]

## 论证结构
- [00:05:23] 论点1: [内容概述]
- [00:08:15] 论据1: [支持材料]
- [00:12:30] 论点2: [内容概述]

## 学术价值
[分析该内容的学术贡献和局限性]

## 延伸阅读建议
[推荐相关的学术资源或概念]

要求：
1. 使用学术化、严谨的语言
2. 突出概念定义和逻辑关系
3. 每个时间点标注精确到秒
4. 分析要有批判性思维
"""

    def _quick_template(self) -> str:
        """速览风格模板"""
        return """请快速总结以下视频的核心内容，适合快速浏览。

视频标题: {{title}}

转录内容:
{{transcript}}

请按以下简洁格式输出：

# {{title}}

## 核心要点
[一句话总结]

## 关键时间轴（3-5个）
- [00:05:23] 要点1
- [00:08:15] 要点2
- [00:12:30] 要点3

## 适合人群
[谁应该看这支视频]

要求：
1. 极度简洁，每个要点不超过15字
2. 只保留最核心的3-5个时间点
3. 30秒内能读完
"""

    def _action_template(self) -> str:
        """行动项风格模板"""
        return """请从以下视频中提取可执行的行动建议和实践步骤。

视频标题: {{title}}

转录内容:
{{transcript}}

请按以下行动导向格式输出：

# {{title}}

## 核心行动建议
[最重要的1-3个行动建议]

## 实施步骤
- [00:05:23] 步骤1: [具体行动]
- [00:08:15] 步骤2: [具体行动]
- [00:12:30] 步骤3: [具体行动]

## 所需资源
[执行需要的工具、时间、技能]

## 预期成果
[执行后能获得什么]

## 常见陷阱
[需要避免的错误]

要求：
1. 每个建议必须具体可执行
2. 包含明确的时间节点
3. 提供实用的操作细节
"""

    def _translation_template(self) -> str:
        """翻译风格模板"""
        return """请对以下视频内容进行双语摘要，适合语言学习。

视频标题: {{title}}

转录内容:
{{transcript}}

请按以下双语格式输出：

# {{title}}

## 核心概念 | Key Concepts
- 概念1 | Concept 1: [双语解释]
- 概念2 | Concept 2: [双语解释]

## 关键表达 | Key Expressions
- [00:05:23] 原文表达 | Original: [原句]
  中文翻译 | Translation: [翻译]
  语言点 | Language Point: [语法/词汇解析]

## 实用句型 | Useful Patterns
1. 句型1 | Pattern 1: [例句]
   用法 | Usage: [使用场景]

## 词汇表 | Vocabulary
- 词汇1 (词性): [释义]
- 词汇2 (词性): [释义]

要求：
1. 双语对照呈现
2. 标注重点词汇和表达
3. 提供语言学习价值
"""

    def _qna_template(self) -> str:
        """问答风格模板"""
        return """请将以下视频内容转换为问答形式，便于复习和测试理解。

视频标题: {{title}}

转录内容:
{{transcript}}

请按以下问答格式输出：

# {{title}}

## 核心问题
Q: 这支视频主要讲什么？
A: [一句话回答]

## 详细问答

### 问题1: [具体问题]
- 时间: [00:05:23]
- 答案: [详细回答]
- 关键引用: [原文关键句]

### 问题2: [具体问题]
- 时间: [00:08:15]
- 答案: [详细回答]
- 关键引用: [原文关键句]

## 思考题
1. [开放性问题1]
2. [开放性问题2]

## 自测题
1. [具体知识点问题]
   A) 选项A  B) 选项B  C) 选项C

要求：
1. 问题要覆盖视频的核心内容
2. 答案要准确且引用原文
3. 包含不同难度的问题
"""


# 全局模板管理器实例
_template_manager: PromptTemplateManager | None = None


def get_prompt_template_manager() -> PromptTemplateManager:
    """获取全局模板管理器实例"""
    global _template_manager
    if _template_manager is None:
        _template_manager = PromptTemplateManager()
    return _template_manager
