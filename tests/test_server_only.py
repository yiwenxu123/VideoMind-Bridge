"""服务端轻装契约：API/MCP/CLI 不得在导入时拉起 GUI 依赖。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_server_modules_do_not_import_pyside6():
    code = (
        "import sys;"
        "import src.api.server, src.mcp.server, src.cli;"
        "gui = sorted(m for m in sys.modules if m.startswith('PySide6'));"
        "assert not gui, gui;"
        "print('ok')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout
