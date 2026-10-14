"""path: /frontend/map_editor/tests/conftest.py

Назначение: пути импорта для pytest-контура редактора — два корня
    (map_editor для его модулей, frontend для world_context), та же
    конвенция, что у editor_launcher.
Зависимости: только стандартная библиотека.
"""

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_ME_ROOT = _TESTS_DIR.parent  # frontend/map_editor
_FE_ROOT = _ME_ROOT.parent    # frontend
for _path in (str(_ME_ROOT), str(_FE_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)
