"""pytest 共享配置：把 scripts/ 加入导入路径。

脚本按"可被 OpenClaw 侧调用"的方式编写，因此不用包结构，直接路径注入。
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

ROOT = Path(__file__).resolve().parent.parent
