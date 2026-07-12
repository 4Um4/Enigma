import pathlib

p = pathlib.Path("frontend/map_editor/undo_manager.py")
c = p.read_text(encoding="utf-8")
c = c.replace(
    '(lbl for lbl in loc.get("labels", []) if lbl.get("id") == self.entity_id)  # noqa: E741,',
    '(l for l in loc.get("labels", []) if l.get("id") == self.entity_id),  # noqa: E741'
)
p.write_text(c, encoding="utf-8")
print("✅ Синтаксис undo_manager.py исправлен.")