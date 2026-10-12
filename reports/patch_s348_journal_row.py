# -*- coding: utf-8 -*-
"""scripts/patch_s348_journal_row.py — COV-2/S348: хвост — строка §10.

Обещана в S348 («§10-строка журнала — следующим доковым коммитом»,
прецедент backfill S334). Одна строка в таблицу §10 после хедера
(дамп снят доковым скриптом 54ac466f). Диагноз-колонка честно отражает
итерационность: 5 промежуточных RED = тайминги harness'а, не доктрина.
Одноразовый; после применения перенести в reports/.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P_ROAD = ROOT / "docs" / "ENIGMA_ROADMAP_v4_6.md"


class Abort(Exception):
    """Громкий отказ (Law L4): ничего не записано."""


def req(cond, msg):
    if not cond:
        raise Abort(msg)


OLD = ('| Дата | Шаг | Объект | Результат | Диагноз / причина |\n'
       '|------|-----|--------|-----------|-------------------|')
ROW = ('| 2026-10-12 | Б: COV-2 закрытие (S348/ADR-O-425) | SUPERBOX '
       'd61_llm_outage_doctrine (живой llama-server, kill×3/restart×3) + micro '
       'test_llm_resilience_v1 + IPT | GREEN 32/0 EXIT=0; micro 27/27; IPT 52/52; '
       'lint_flags GREEN | итерации: 6 прогонов — 5 промежуточных RED = тайминги '
       "harness'а (предусловия g0/g6), не доктрина; диагнозы в коммит-трейле "
       '0253d0ef |')


def main() -> int:
    raw = P_ROAD.read_bytes()
    bom = b""
    if raw.startswith(b"\xef\xbb\xbf"):  # урок S317: BOM
        bom, raw = raw[:3], raw[3:]
    text = raw.decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")

    req(text.count(OLD) == 1,
        f"якорь хедера §10 найден {text.count(OLD)} раз (ожидался 1)")
    req(text.count(ROW.split(" | ")[2][:40]) == 0,
        "строка d61_llm_outage_doctrine уже в журнале — двойная запись?")
    text = text.replace(OLD, OLD + "\n" + ROW, 1)

    # стражи: полная строка уникальна, хедер цел
    req(text.count(ROW) == 1, "пост: строка журнала != 1")
    req(text.count("| Дата | Шаг | Объект | Результат | Диагноз / причина |") == 1,
        "пост: хедер §10 затронут")
    save = text.replace("\n", "\r\n") if crlf else text
    P_ROAD.write_bytes(bom + save.encode("utf-8"))
    print("[ok] §10: строка S348-журнала добавлена")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Abort as e:
        print(f"\n[ABORT] {e}\nНичего не записано.", file=sys.stderr)
        sys.exit(2)
