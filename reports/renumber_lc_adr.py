# path: reports/renumber_lc_adr.py
# Одноразовая миграция (LC-IMPL-1): ADR-O-420 → первый свободный ≥421 в 4
# файлах сессии. Самопроверка: (1) номер свободен в живом атласе ДО замены;
# (2) замены применены и старый токен исчез; (3) номер всё ещё свободен
# ПОСЛЕ замены (параллельные сессии быстрые — S331/S332 закрыты в окне).
# BOM-прозрачность (урок ×11): чтение utf-8-sig, запись с сохранением BOM.
# EOL не мутируются (byte-level write-back).

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "docs" / "ADR (Architecture Decision Records).md"
TARGETS = [
    "backend/app/domain/idle_projection.py",
    "backend/app/services/game_loop/idle_event_projection.py",
    "backend/tests/micro/test_idle_event_projection.py",
    "backend/tests/micro/test_fe_events_channel_no_deltas.py",
]
OLD = "ADR-O-420"


def _taken() -> set:
    text = ATLAS.read_text(encoding="utf-8-sig")
    return {int(m) for m in re.findall(r"ADR-O-(\d{3})", text)}


def _pick_new() -> int:
    taken = _taken()
    cand = 421  # предпочтительный (commit D уже ссылается на O-421)
    while cand in taken:
        cand += 1
    return cand


def _rw(path: str, new: str) -> tuple:
    p = ROOT / path
    raw = p.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    n = text.count(OLD)
    data = text.replace(OLD, new).encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    p.write_bytes(data)
    return n, bom


def main() -> None:
    taken_before = _taken()
    new_num = _pick_new()
    new = f"ADR-O-{new_num:03d}"
    print(f"[RENUM] атлас ДО: max O-{max(taken_before):03d}; O-421 занят: {421 in taken_before}")
    print(f"[RENUM] выбран: {new}")
    total = 0
    for t in TARGETS:
        n, bom = _rw(t, new)
        total += n
        print(f"[RENUM] {t}: замен={n}, BOM={bom}")
    # верификация 1: старый токен исчез, новый присутствует ровно total раз
    leftovers = sum((ROOT / t).read_text(encoding="utf-8-sig").count(OLD) for t in TARGETS)
    news = sum((ROOT / t).read_text(encoding="utf-8-sig").count(new) for t in TARGETS)
    # верификация 2: номер всё ещё свободен в атласе ПОСЛЕ замены
    taken_after = _taken()
    print(f"[RENUM] верификация: остатки {OLD}={leftovers} (ожид. 0); {new}={news} (ожид. {total}); "
          f"атлас ПОСЛЕ: {new} занят: {new_num in taken_after}")
    assert leftovers == 0, f"остались вхождения {OLD}"
    assert news == total, "число вхождений нового токена не совпало"
    assert new_num not in taken_after, f"{new} оказался занят в атласе после замены"
    print(f"[RENUM] OK — {total} замен на {new}; к коммиту")


if __name__ == "__main__":
    main()
