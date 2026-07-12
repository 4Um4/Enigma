import pathlib

def fix_file(filepath: str, replacements: dict) -> None:
    path = pathlib.Path(filepath)
    if not path.exists():
        print(f"⚠️ Файл не найден: {path}")
        return

    content = path.read_text(encoding="utf-8")
    for old, new in replacements.items():
        if old in content:
            content = content.replace(old, new)
            print(f"  ✅ Заменено в {path.name}")
        else:
            print(f"  ⚠️ Не найдено в {path.name}: {old[:40]}")

    path.write_text(content, encoding="utf-8")

print("Фикс критических ошибок...")

# 1. Восстанавливаем импорт Tuple в domain_phases.py
fix_file("backend/app/services/npc/domain_phases.py", {
    "from typing import Any": "from typing import Any, Tuple",
})

# 2. Исправляем синтаксис в editor_core.py (возвращаем запятую на место)
fix_file("frontend/map_editor/editor_core.py", {
    "if l.get(\"id\") == eid)  # noqa: E741, None)": "if l.get(\"id\") == eid), None)  # noqa: E741",
    "if l[\"id\"] == obj_key)  # noqa: E741, None)": "if l[\"id\"] == obj_key), None)  # noqa: E741",
})

# 3. Исправляем синтаксис в undo_manager.py
fix_file("frontend/map_editor/undo_manager.py", {
    "if l.get(\"id\") == self.entity_id)  # noqa: E741,": "if l.get(\"id\") == self.entity_id),",
})

# 4. Добавляем noqa: E402 к многострочным импортам
fix_file("frontend/game_screen.py", {
    "from game_types import (": "from game_types import (  # noqa: E402",
    "from constants import (": "from constants import (  # noqa: E402",
})

fix_file("frontend/scene_renderer.py", {
    "from game_types import (": "from game_types import (  # noqa: E402",
    "from constants import (": "from constants import (  # noqa: E402",
})

print("Фикс завершен.")