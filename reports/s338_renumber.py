"""
path: /project/reports/s338_renumber.py
Назначение: Ренумбер S337→S338 (Устав 11.1.1): коллизия с параллельной CCH-3-
    сессией — их коммит d85ef720 несёт «S337» в сообщении (неизменяемо), моя
    реестр-строка 4b17821f записана при грепе max=336 (в реестре номер был
    свободен). Канон: S337 = CCH-3; S330-probe → S338. + МЕТА-примечание.
    Одноразовый; повторный запуск не имеет смысла (assert'ы).
Запуск: python reports/s338_renumber.py
"""
import re
from pathlib import Path

F = Path(__file__).resolve().parents[1] / "docs" / "MUTATIONS.md"
_raw = F.read_bytes()
_bom = _raw.startswith(b"\xef\xbb\xbf")
text = _raw.decode("utf-8-sig" if _bom else "utf-8")

# 1. Маркер моей строки: единственный S337 в реестре, контент = S330-probe
lines = text.splitlines(keepends=True)
_idx = [i for i, _l in enumerate(lines) if _l.startswith("- **S337**")]
assert len(_idx) == 1, f"count(S337-line)={len(_idx)}"
assert "S330-probe" in lines[_idx[0]], "S337-строка чужая — СТОП, не трогать"
# 2. S338 свободен в реестре
assert not re.search(r"^- \*\*S338\*\*", text, re.M), "S338 занят — СТОП, эскалация"

# 3. Ренумбер ТОЛЬКО маркера (контент строки не трогается)
lines[_idx[0]] = lines[_idx[0]].replace("- **S337**", "- **S338**", 1)

# 4. МЕТА-примечание: после последнего буллета секции «Примечания целостности»
_HDR = "**Примечания целостности номеров:**"
_h = [i for i, _l in enumerate(lines) if _HDR in _l]
assert len(_h) == 1, f"count(МЕТА-заголовок)={len(_h)}"
_j = _h[0] + 1
while _j < len(lines) and lines[_j].lstrip().startswith("- "):
    _j += 1
_NOTE = ("- Дубль S337: параллельная CCH-3-сессия (коммит d85ef720 «S337: CCH-3 "
         "step B» — номер в сообщении коммита, неизменяемо; своей реестр-строки "
         "на момент коллизии не имел) vs запись S330-probe (4b17821f; греп реестра "
         "max=336 — номер свободен на момент записи; гонка параллельных серий, "
         "прецеденты S314→S316/S324/S329). Канон: S337 = CCH-3 (d85ef720), "
         "S330-probe ренумбер → S338 (Устав 11.1.1). Скрипт "
         "reports/s337_registry_add.py — одноразовый, исполнен, не перезапускать.")
lines.insert(_j, _NOTE + "\n")
text2 = "".join(lines)

# 5. Верификация: маркеры, счётчик неизменен, число строк +1
assert text2.count("- **S338**") == 1
assert re.search(r"^- \*\*S337\*\*", text2, re.M) is None
_m = re.search(r"^Записей: (\d+)", text2, re.M)
assert _m and _m.group(1) == "221", f"МЕТА-счётчик дрейфанул: {(_m.group(1) if _m else '?')} — СТОП"
assert len(text2.splitlines()) == len(text.splitlines()) + 1

F.write_bytes((b"\xef\xbb\xbf" if _bom else b"") + text2.encode("utf-8"))
print("OK: S337→S338 (маркер), МЕТА-примечание вставлено, счётчик 221 неизменен")
