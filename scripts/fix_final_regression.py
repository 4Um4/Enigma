import pathlib
import re

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

print("Финальный откат регрессий...")

# 1. Возвращаем loc в editor_core.py
fix_file("frontend/map_editor/editor_core.py", {
    "_loc = self.dm.locations[self.current_file]": "loc = self.dm.locations[self.current_file]",
})

# 2. Возвращаем y_offset в ui_components.py
fix_file("frontend/map_editor/ui_components.py", {
    "_y_offset = 0": "y_offset = 0",
})

# 3. Возвращаем npc_ref в editor_core.py
fix_file("frontend/map_editor/editor_core.py", {
    "_npc_ref = self.undo.push(": "npc_ref = self.undo.push(",
})

# 4. Возвращаем lbl_item обратно в l (генераторы)
fix_file("frontend/map_editor/editor_core.py", {
    "(lbl_item for lbl_item in loc.get(\"labels\", []) if lbl_item.get(\"id\") == eid)": "(l for l in loc.get(\"labels\", []) if l.get(\"id\") == eid)  # noqa: E741",
    "(lbl_item for lbl_item in loc[\"labels\"] if lbl_item[\"id\"] == obj_key)": "(l for l in loc[\"labels\"] if l[\"id\"] == obj_key)  # noqa: E741",
})
fix_file("frontend/map_editor/undo_manager.py", {
    "(lbl_item for lbl_item in loc.get(\"labels\", []) if lbl_item.get(\"id\") == self.entity_id)": "(l for l in loc.get(\"labels\", []) if l.get(\"id\") == self.entity_id)  # noqa: E741",
})

# 5. Чиним from __future__ в event_types.py
path = pathlib.Path("backend/app/services/events/event_types.py")
if path.exists():
    content = path.read_text(encoding="utf-8")
    if "from __future__ import annotations" not in content.split("\n")[0]:
        content = content.replace("from __future__ import annotations\n", "")
        content = "from __future__ import annotations\n" + content
        path.write_text(content, encoding="utf-8")
        print("✅ Исправлен event_types.py")

print("Откат завершен. Теперь нужно вручную добавить noqa к переменным и импортам.")