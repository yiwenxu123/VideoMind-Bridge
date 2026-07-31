"""PromptTemplate 和 PromptTemplateManager 测试"""

from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import yaml

from src.services.prompt_template import (
    PromptTemplate,
    PromptTemplateManager,
    TemplateStyle,
    get_prompt_template_manager,
)


class TestPromptTemplate:
    """PromptTemplate 数据类测试"""

    def test_render_basic(self):
        """render 基本功能"""
        template = PromptTemplate(
            id="test",
            name="Test",
            description="A test template",
            template="{{ title }}: {{ content }}",
            style=TemplateStyle.DEFAULT,
        )
        result = template.render(title="Hello", content="World")
        assert result == "Hello: World"

    def test_render_missing_variable_renders_empty(self):
        """缺失变量渲染为空字符串"""
        template = PromptTemplate(
            id="test",
            name="Test",
            description="A test template",
            template="{{ title }} - {{ missing }}",
            style=TemplateStyle.DEFAULT,
        )
        result = template.render(title="Hello")
        assert "Hello" in result

    def test_to_dict_contains_all_fields(self):
        """to_dict 包含所有字段"""
        template = PromptTemplate(
            id="t1",
            name="Test",
            description="Desc",
            template="{{ title }}",
            style=TemplateStyle.ACADEMIC,
            variables=["title"],
            is_default=True,
            is_builtin=True,
            created_at="2024-01-01",
            updated_at="2024-01-02",
        )
        d = template.to_dict()
        assert d["id"] == "t1"
        assert d["name"] == "Test"
        assert d["description"] == "Desc"
        assert d["template"] == "{{ title }}"
        assert d["style"] == "academic"
        assert d["variables"] == ["title"]
        assert d["is_default"] is True
        assert d["is_builtin"] is True
        assert d["created_at"] == "2024-01-01"
        assert d["updated_at"] == "2024-01-02"

    def test_from_dict_creates_instance(self):
        """from_dict 创建 PromptTemplate 实例"""
        data: dict[str, Any] = {
            "id": "imported",
            "name": "Imported",
            "description": "Imported template",
            "template": "Hello {{ name }}",
            "style": "quick",
            "variables": ["name"],
        }
        template = PromptTemplate.from_dict(data)
        assert template.id == "imported"
        assert template.name == "Imported"
        assert template.style == TemplateStyle.QUICK
        assert template.render(name="World") == "Hello World"

    def test_from_dict_default_style(self):
        """from_dict 默认 style 为 default"""
        data: dict[str, Any] = {
            "id": "t2",
            "name": "T2",
            "description": "Desc",
            "template": "{{ x }}",
        }
        template = PromptTemplate.from_dict(data)
        assert template.style == TemplateStyle.DEFAULT

    def test_from_dict_default_builtin(self):
        """from_dict 默认 is_builtin 为 True"""
        data: dict[str, Any] = {
            "id": "t3",
            "name": "T3",
            "description": "Desc",
            "template": "{{ x }}",
        }
        template = PromptTemplate.from_dict(data)
        assert template.is_builtin is True


class TestPromptTemplateManagerInit:
    """PromptTemplateManager 初始化测试"""

    def test_default_storage_path_created(self, tmp_path):
        """默认路径自动创建目录"""
        storage = tmp_path / ".videomind" / "prompts"
        manager = PromptTemplateManager(storage_path=storage)
        assert storage.exists()
        assert manager.storage_path == storage

    def test_custom_storage_path(self, tmp_path):
        """自定义存储路径"""
        custom = tmp_path / "custom_prompts"
        manager = PromptTemplateManager(storage_path=custom)
        assert custom.exists()

    def test_loads_builtin_templates(self, tmp_path):
        """初始化加载内置模板"""
        manager = PromptTemplateManager(storage_path=tmp_path / "p")
        templates = manager.get_all_templates()
        assert len(templates) == 6  # default, academic, quick, action, translation, qna

    def test_loads_custom_templates(self, tmp_path):
        """加载自定义模板文件"""
        custom_file = tmp_path / "prompts" / "custom_templates.yaml"
        custom_file.parent.mkdir(parents=True)
        custom_data = {
            "templates": [
                {
                    "id": "my_custom",
                    "name": "My Custom",
                    "description": "User created",
                    "template": "Custom: {{ title }}",
                    "style": "default",
                }
            ]
        }
        with open(custom_file, "w") as f:
            yaml.dump(custom_data, f)

        manager = PromptTemplateManager(storage_path=tmp_path / "prompts")
        t = manager.get_template("my_custom")
        assert t is not None
        assert t.name == "My Custom"
        assert t.is_builtin is False


class TestPromptTemplateManagerGet:
    """模板查询方法测试"""

    @pytest.fixture
    def manager(self, tmp_path) -> PromptTemplateManager:
        return PromptTemplateManager(storage_path=tmp_path / "p")

    def test_get_template_exists(self, manager):
        t = manager.get_template("default")
        assert t is not None
        assert t.name == "默认风格"

    def test_get_template_not_exists(self, manager):
        t = manager.get_template("nonexistent")
        assert t is None

    def test_get_default_template(self, manager):
        t = manager.get_default_template()
        assert t.id == "default"

    def test_get_default_template_fallback(self, tmp_path):
        """没有默认模板时返回第一个"""
        manager = PromptTemplateManager(storage_path=tmp_path / "p2")
        # Set all to non-default
        for t in manager.get_all_templates():
            t.is_default = False
        default = manager.get_default_template()
        assert default is not None

    def test_get_all_templates(self, manager):
        templates = manager.get_all_templates()
        assert len(templates) == 6

    def test_get_templates_by_style(self, manager):
        templates = manager.get_templates_by_style(TemplateStyle.DEFAULT)
        assert len(templates) == 1
        assert templates[0].id == "default"

    def test_get_templates_by_style_empty(self, manager):
        templates = manager.get_templates_by_style(TemplateStyle.XIAOHONGSHU)
        assert len(templates) == 0


class TestPromptTemplateManagerCRUD:
    """模板 CRUD 操作测试"""

    @pytest.fixture
    def manager(self, tmp_path) -> PromptTemplateManager:
        return PromptTemplateManager(storage_path=tmp_path / "p")

    def test_create_template_basic(self, manager):
        t = manager.create_template(
            name="New",
            description="New template",
            template="Content: {{ title }}",
        )
        assert t.id.startswith("custom_")
        assert t.name == "New"
        assert t.is_builtin is False
        assert t.is_default is False

    def test_create_template_with_default(self, manager):
        t = manager.create_template(
            name="New Default",
            description="Set as default",
            template="{{ title }}",
            set_as_default=True,
        )
        assert t.is_default is True
        # Check previous default is no longer default
        default_t = manager.get_template("default")
        assert default_t is not None
        assert default_t.is_default is False

    def test_update_custom_template(self, manager):
        t = manager.create_template(name="Old", description="Old desc", template="Old: {{ title }}")
        result = manager.update_template(t.id, name="Updated", description="Updated desc")
        assert result is True
        updated = manager.get_template(t.id)
        assert updated is not None
        assert updated.name == "Updated"
        assert updated.description == "Updated desc"

    def test_update_builtin_template_rejected(self, manager):
        result = manager.update_template("default", template="Modified content")
        assert result is False
        # Verify unchanged
        t = manager.get_template("default")
        assert t is not None
        assert "请分析以下视频转录内容" in t.template

    def test_update_nonexistent_template(self, manager):
        result = manager.update_template("not_exist", name="X")
        assert result is False

    def test_delete_custom_template(self, manager):
        t = manager.create_template(name="To Delete", description="", template="{{ title }}")
        result = manager.delete_template(t.id)
        assert result is True
        assert manager.get_template(t.id) is None

    def test_delete_builtin_template_rejected(self, manager):
        result = manager.delete_template("default")
        assert result is False
        assert manager.get_template("default") is not None

    def test_delete_nonexistent_template(self, manager):
        result = manager.delete_template("not_exist")
        assert result is False

    def test_set_default_template(self, manager):
        result = manager.set_default_template("quick")
        assert result is True
        t = manager.get_template("quick")
        assert t is not None
        assert t.is_default is True
        # Previous default no longer default
        default_t = manager.get_template("default")
        assert default_t is not None
        assert default_t.is_default is False

    def test_set_default_template_nonexistent(self, manager):
        result = manager.set_default_template("not_exist")
        assert result is False

    def test_create_template_overrides_default(self, manager):
        """创建模板时设定为默认应取消其他模板的默认状态"""
        t1 = manager.create_template(name="A", description="", template="{{ title }}", set_as_default=True)
        t2 = manager.create_template(name="B", description="", template="{{ title }}", set_as_default=True)
        assert t1.is_default is False
        assert t2.is_default is True


class TestPromptTemplateManagerMisc:
    """杂项功能测试"""

    @pytest.fixture
    def manager(self, tmp_path) -> PromptTemplateManager:
        return PromptTemplateManager(storage_path=tmp_path / "p")

    def test_preview_template_exists(self, manager):
        result = manager.preview_template("default")
        assert "示例视频标题" in result

    def test_preview_template_not_exists(self, manager):
        result = manager.preview_template("not_exist")
        assert result == "模板不存在"

    def test_preview_template_custom_kwargs(self, manager):
        result = manager.preview_template("default", title="定制标题", transcript="定制内容")
        assert "定制标题" in result
        assert "定制内容" in result

    def test_export_template_success(self, manager, tmp_path):
        output = tmp_path / "exported.yaml"
        result = manager.export_template("default", output)
        assert result is True
        assert output.exists()
        with open(output) as f:
            data = yaml.safe_load(f)
        assert data["id"] == "default"

    def test_export_template_not_exists(self, manager, tmp_path):
        result = manager.export_template("not_exist", tmp_path / "x.yaml")
        assert result is False

    @mock.patch("src.services.prompt_template.logger")
    def test_export_template_io_error(self, mock_logger, manager):
        """导出到无效路径时返回 False 并记录错误"""
        result = manager.export_template("default", Path("/nonexistent_dir/file.yaml"))
        assert result is False

    def test_import_template_success(self, manager, tmp_path):
        import_file = tmp_path / "import.yaml"
        data = {
            "id": "imported_from_file",
            "name": "Imported",
            "description": "Imported from file",
            "template": "Imported: {{ title }}",
            "style": "academic",
        }
        with open(import_file, "w") as f:
            yaml.dump(data, f)

        t = manager.import_template(import_file)
        assert t is not None
        assert t.id.startswith("imported_imported")
        assert t.is_builtin is False
        # Verify saved
        assert manager.get_template(t.id) is not None

    def test_import_template_invalid_file(self, manager, tmp_path):
        import_file = tmp_path / "invalid.yaml"
        import_file.write_text("not: valid: yaml: [")
        result = manager.import_template(import_file)
        assert result is None

    def test_import_template_not_yaml_dict(self, manager, tmp_path):
        """导入非 dict 内容返回 None"""
        import_file = tmp_path / "list.yaml"
        with open(import_file, "w") as f:
            yaml.dump(["just", "a", "list"], f)
        result = manager.import_template(import_file)
        assert result is None


class TestGlobalManager:
    """全局 get_prompt_template_manager 测试"""

    def test_singleton_behavior(self, tmp_path):
        import src.services.prompt_template as pt

        saved = pt._template_manager
        pt._template_manager = None
        try:
            with mock.patch("src.services.prompt_template.PromptTemplateManager") as MockMgr:
                MockMgr.return_value = mock.sentinel.mgr
                m1 = get_prompt_template_manager()
                m2 = get_prompt_template_manager()
                assert m1 is m2
        finally:
            pt._template_manager = saved
