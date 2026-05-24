"""文件工具模块"""

import shutil
from pathlib import Path


def sanitize_filename(title: str, max_length: int = 100) -> str:
    """
    安全化文件名，移除非法字符

    Args:
        title: 原始标题
        max_length: 最大长度

    Returns:
        str: 安全化的文件名
    """
    import re

    if not title:
        return "untitled"

    # 替换全角字符为半角
    fullwidth_chars = {
        '｜': '|', '／': '/', '＼': '\\', '：': ':', '＊': '*',
        '？': '?', '＜': '<', '＞': '>', '｜': '|', '＂': '"',
    }
    for full, half in fullwidth_chars.items():
        title = title.replace(full, half)

    # 移除 Windows 和 macOS 的非法字符
    illegal_chars = '<>:"/\\|?*'
    for char in illegal_chars:
        title = title.replace(char, '_')

    # 移除控制字符
    title = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', title)

    # 移除前后空格和点
    title = title.strip(' .')

    # 如果为空，使用默认名称
    if not title:
        return "untitled"

    # 限制长度
    return title[:max_length]


def safe_write_text(
    file_path: Path,
    content: str,
    encoding: str = "utf-8"
) -> tuple[bool, str]:
    """
    安全地写入文本文件

    Args:
        file_path: 目标文件路径
        content: 要写入的内容
        encoding: 文件编码

    Returns:
        Tuple[bool, str]: (是否成功, 消息)
    """
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding=encoding)
        return True, f"文件已写入: {file_path}"
    except PermissionError as e:
        return False, f"权限错误: {e}"
    except OSError as e:
        return False, f"IO错误: {e}"
    except Exception as e:
        return False, f"写入失败: {e}"


def safe_copy_file(
    source: Path,
    destination: Path
) -> tuple[bool, str]:
    """
    安全地复制文件

    Args:
        source: 源文件路径
        destination: 目标文件路径

    Returns:
        Tuple[bool, str]: (是否成功, 消息)
    """
    try:
        if not source.exists():
            return False, f"源文件不存在: {source}"

        destination.parent.mkdir(parents=True, exist_ok=True)

        if source.is_symlink():
            # 复制链接指向的实际文件
            shutil.copy2(source.resolve(), destination)
        else:
            shutil.copy2(source, destination)

        return True, f"文件已复制: {destination}"
    except PermissionError as e:
        return False, f"权限错误: {e}"
    except OSError as e:
        return False, f"IO错误: {e}"
    except Exception as e:
        return False, f"复制失败: {e}"


def safe_create_symlink(
    target: Path,
    link_path: Path
) -> tuple[bool, str]:
    """
    安全地创建符号链接

    Args:
        target: 链接指向的目标路径
        link_path: 符号链接的路径

    Returns:
        Tuple[bool, str]: (是否成功, 消息)
    """
    try:
        link_path.parent.mkdir(parents=True, exist_ok=True)

        # 如果链接已存在，先删除
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()

        # 创建符号链接
        link_path.symlink_to(target.resolve())
        return True, f"符号链接已创建: {link_path} -> {target}"
    except PermissionError as e:
        return False, f"权限错误: {e}"
    except OSError as e:
        return False, f"系统错误: {e}"
    except Exception as e:
        return False, f"创建失败: {e}"
