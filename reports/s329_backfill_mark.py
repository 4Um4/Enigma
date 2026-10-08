"""
path: /project/reports/s329_backfill_mark.py
Назначение: S329-хвост (вердикт Мастера, ветка «явно пометить»): binding UNPROVEN.
    Замена ТОЛЬКО фрагмента 'коммит: <SHA>' в строке S329, якорь-верификация до/после.
Запуск: python reports/s329_backfill_mark.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
F = ROOT / "docs" / "MUTATIONS.md"

_raw = F.read_bytes()
_bom = _raw.startswith(b"\xef\xbb\xbf")
text = _raw.decode("utf-8-sig" if _bom else "utf-8")

OLD = "коммит: <SHA>"
NEW = ("коммит: UNPROVEN — единого S329-коммита нет (авторский docs=31823f9e; "
       "код вшит dd7bfe31 [WIP-релиз V.0.5.4.2.7]; "
       "атлас O-419/манифест gen_rate вшиты 9290260e [WIP-релиз V.0.5.4.2.8])")

lines = text.splitlines(keepends=True)
_idx = [i for i, _l in enumerate(lines) if _l.startswith("- **S329**")]
assert len(_idx) == 1, f"count(S329-line)={len(_idx)}"
_i = _idx[0]
assert OLD in lines[_i] and "RE-01 G/H" in lines[_i], "якорь-фрагмент не в строке S329"
assert len(_idx) and OLD not in "".join(lines[:_i]) + "".join(lines[_i + 1:]), "OLD вне S329-строки"

lines[_i] = lines[_i].replace(OLD, NEW, 1)
text2 = "".join(lines)
assert text2.count(NEW) == 1 and text2.count(OLD) == 0
assert len(text2.splitlines()) == len(lines), "число строк изменилось"

F.write_bytes((b"\xef\xbb\xbf" if _bom else b"") + text2.encode("utf-8"))
print(f"OK: BOM={_bom}, строка S329 заменена 1:1 (+{len(NEW) - len(OLD)} симв.)")