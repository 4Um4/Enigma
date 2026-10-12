# -*- coding: utf-8 -*-
"""scripts/patch_d61_scenario_fix3.py — COV-2/D61: fix3 живого сценария (v3).

Хроника ABORT (класс «страж-счётчик», 5-й случай): v1 — магическое число
`check( == 32` (факт 36); v2 — счётчик идентификатора `_stab_t0 == 2`
(факт 3), провозглашая в том же докстринге запрет на счётчики. v3: стражи —
ТОЛЬКО полные строки кода (вставленные строки уникальны by construction)
и относительная проверка (число check( не изменилось). Правило доведено
до буквы: голые идентификаторы в стражах не матчатся никогда.

Суть fix3 (прогоны 00:20/00:34/18:36: RED p0_status_online, URLError
timed out на fast-пробе): /health в окне загрузки отвечает >1с (3с-проба
GREEN, 1с timeout), после загрузки <1с (g4_status_online GREEN той же
пробой после lifecycle-рестарта). Лечение: g0 поллит fast-пробу до online,
бюджет 120с (каждый прогон = SPAWN: atexit гасит lifecycle-сервер g8;
загрузка модели до ~90с), длительность — в obs-артефакт. Прод-семантика
не тронута: unconfirmed на старте легален по доктрине §3.5 (без модалки,
watcher доберёт дебаунсом).
Одноразовый; после применения перенести в reports/.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P_SCN = (ROOT / "backend" / "tests" / "sandbox" / "SUPERBOX" / "scenarios"
         / "d61_llm_outage_doctrine_test.py")


class Abort(Exception):
    """Громкий отказ (Law L4): ничего не записано."""


def req(cond, msg):
    if not cond:
        raise Abort(msg)


OLD = (
    '    if not check("p0_llm_online", _llm_alive(), "health не отвечает после самоподъёма"):\n'
    '        return False\n'
    '    from app.services.llm.router import initialize_router'
)
NEW = (
    '    if not check("p0_llm_online", _llm_alive(), "health не отвечает после самоподъёма"):\n'
    '        return False\n'
    '    # Стабилизация /health после спавна (прогоны 00:20/00:34/18:36:\n'
    '    # _llm_alive 3с GREEN -> fast-проба 1с timeout — /health отвечает\n'
    '    # в окне загрузки >1с; после загрузки <1с, g4_status_online GREEN\n'
    '    # той же пробой). Ждём, пока fast-проба станет online (её гейтит\n'
    '    # p0_status_online). Бюджет 120с: каждый прогон = SPAWN (atexit\n'
    '    # гасит lifecycle-сервер g8), загрузка модели до ~90с. Прод-семантика\n'
    '    # не тронута: unconfirmed на старте легален по доктрине §3.5.\n'
    '    _stab_t0 = time.time()\n'
    '    _stab_deadline = _stab_t0 + 120.0\n'
    '    while time.time() < _stab_deadline:\n'
    '        _online, _why = _health_online_fast()\n'
    '        if _online:\n'
    '            break\n'
    '        time.sleep(1.0)\n'
    '    _obs("p0_stabilize_sec", round(time.time() - _stab_t0, 1))\n'
    '    from app.services.llm.router import initialize_router'
)


def main() -> int:
    raw = P_SCN.read_bytes()
    bom = b""
    if raw.startswith(b"\xef\xbb\xbf"):  # урок S317: BOM
        bom, raw = raw[:3], raw[3:]
    text = raw.decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")

    req(text.count(OLD) == 1,
        f"якорь найден {text.count(OLD)} раз (ожидался 1) — пришли регион дословно.")
    checks_before = text.count("check(")
    text = text.replace(OLD, NEW, 1)
    print("[ok] хунк g0-стабилизации применён")

    # ---------- стражи write-пути (v3: ТОЛЬКО полные строки + относит.) --
    req(text.count("check(") == checks_before,
        f"пост: хунк изменил число check( {checks_before} -> "
        f"{text.count('check(')} (гейты не добавляются)")
    req(text.count("    _stab_t0 = time.time()") == 1,
        "пост: строка старта стабилизации != 1")
    req(text.count("    _stab_deadline = _stab_t0 + 120.0") == 1,
        "пост: строка дедлайна != 1")
    req(text.count('    _obs("p0_stabilize_sec", round(time.time() - _stab_t0, 1))') == 1,
        "пост: строка obs != 1")
    req(text.count('check("p0_status_online"') == 1, "пост: p0-гейт != 1")
    try:
        compile(text, str(P_SCN), "exec")
    except SyntaxError as e:
        raise Abort(f"компиляция не прошла (запись отменена): {e}")
    print("[ok] компиляция в памяти: GREEN; стражи v3 пройдены")

    out = text.replace("\n", "\r\n") if crlf else text
    P_SCN.write_bytes(bom + out.encode("utf-8"))
    print(f"[ok] записано: {P_SCN}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Abort as e:
        print(f"\n[ABORT] {e}\nНичего не записано.", file=sys.stderr)
        sys.exit(2)
