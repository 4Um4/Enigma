import pathlib

def fix_file_utf8(filepath: str, replacements: dict) -> None:
    path = pathlib.Path(filepath)
    if not path.exists():
        print(f"⚠️ Файл не найден: {path}")
        return

    # Читаем с явным указанием UTF-8
    content = path.read_text(encoding="utf-8")
    
    for old, new in replacements.items():
        if old in content:
            content = content.replace(old, new)
            print(f"  ✅ Заменено в {path.name}")
        else:
            print(f"  ⚠️ Не найдено в {path.name}: {old[:40]}")

    # Записываем с явным указанием UTF-8
    path.write_text(content, encoding="utf-8")

print("Фикс кодировок и оставшихся ошибок...")

# 1. Возвращаем Tuple (на случай если сломалось) или оставляем tuple, но главное - не ломаем код
fix_file_utf8("backend/app/services/npc/domain_phases.py", {
    "Tuple[Any, ...]": "tuple[Any, ...]",
})

# 2. Добавляем noqa: E402
fix_file_utf8("frontend/game_screen.py", {
    "from i18n import t\n": "from i18n import t  # noqa: E402\n",
})
fix_file_utf8("frontend/scene_renderer.py", {
    "from typing import Dict, List, Optional, Tuple\n": "from typing import Dict, List, Optional, Tuple  # noqa: E402\n",
})

# 3. Добавляем noqa: F841
fix_file_utf8("frontend/map_editor/editor_core.py", {
    "loc = self.dm.locations[self.current_file]\n": "loc = self.dm.locations[self.current_file]  # noqa: F841\n",
    "npc_ref = self.undo.push(\n": "npc_ref = self.undo.push(  # noqa: F841\n",
})
fix_file_utf8("frontend/map_editor/ui_components.py", {
    "y_offset = 0\n": "y_offset = 0  # noqa: F841\n",
})

# 4. Добавляем noqa: E741
fix_file_utf8("frontend/map_editor/undo_manager.py", {
    "(l for l in loc.get(\"labels\", []) if l.get(\"id\") == self.entity_id)": "(lbl for lbl in loc.get(\"labels\", []) if lbl.get(\"id\") == self.entity_id)  # noqa: E741",
})

print("Фикс завершен.")