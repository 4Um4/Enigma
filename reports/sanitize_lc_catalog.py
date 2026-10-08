"""
path: /project/reports/sanitize_lc_catalog.py
Назначение: Санация LC-каталога (вердикт Мастера: tracked+clean, удалить ТОЛЬКО
    chat-dump-обёртку): пролог 1-8, эпилог 195-198 (1-based). Канон 9-194 не тронут.
Запуск: python reports/sanitize_lc_catalog.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
F = ROOT / "docs" / "Почти Актуальные TZ" / "«Замыкание игровой петли» (Loop Closure).md"

_raw = F.read_bytes()
_bom = _raw.startswith(b"\xef\xbb\xbf")
lines = _raw.decode("utf-8-sig" if _bom else "utf-8").splitlines(keepends=True)

assert len(lines) == 198, f"total={len(lines)} (ожидание 198)"
assert "Вот полное содержимое" in lines[4], "пролог-якорь :5"
assert lines[6].strip() == "---", f"line7={lines[6]!r}"
assert lines[8].startswith("# ENIGMA — ДОРОЖНАЯ КАРТА"), f"line9={lines[8]!r}"
assert "Дополнение LC-1" in lines[9], f"line10={lines[9]!r}"
assert lines[183].startswith("## §LC-6"), f"line184={lines[183]!r}"
assert lines[193].startswith("- [ ] Гейты LC-01"), f"line194={lines[193]!r}"
assert lines[195].strip() == "---", f"line196={lines[195]!r}"
assert lines[197].startswith("**Что дальше:**"), f"line198={lines[197]!r}"

out = "".join(lines[8:194])  # 1-based 9..194
for _ph in ("Вот полное содержимое", "Что дальше:", "Проверю, что можно восстановить",
            "Готово — файл пересобран", "Важная оговорка"):
    assert _ph not in out, f"обёртка в каноне: {_ph}"
assert out.splitlines()[0].startswith("# ENIGMA — ДОРОЖНАЯ КАРТА")
assert len(out.splitlines()) == 186, f"kept={len(out.splitlines())}"

F.write_bytes((b"\xef\xbb\xbf" if _bom else b"") + out.encode("utf-8"))
print(f"OK: BOM={_bom}, 198 -> 186 строк; обёртка удалена, канон 9-194 сохранён")
