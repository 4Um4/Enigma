# -*- coding: utf-8 -*-
"""scripts/patch_testament_ref.py — S348: упоминание Завещания в РЕЖИМ РАБОТЫ.

Основание: санкция Мастера (создание традиции писем архитекторов; точка
натыкаемости — обязательное чтение перед каждой сессией). Пара БЫЛО/СТАЛО
печатается до записи (правило S348: .md-патч скриптом предъявляет пары).
Файл ищется в корне и docs/ (путь не верифицирован чтением дерева — скрипт
разрешает сам). Одноразовый; после применения перенести в reports/.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = [ROOT / "РЕЖИМ РАБОТЫ.md", ROOT / "docs" / "РЕЖИМ РАБОТЫ.md"]


class Abort(Exception):
    """Громкий отказ (Law L4): ничего не записано."""


def req(cond, msg):
    if not cond:
        raise Abort(msg)


OLD = (
    "`reports/LAST_SESSION.md` читать ТОЛЬКО если последняя сессия завершалась "
    "запуском игры (генерируется CausalObserver при выходе; при headless-разработке "
    "устарел и чтению не подлежит).\n"
    "Без этого запрещено писать или изменять код."
)
INS = (
    "`reports/LAST_SESSION.md` читать ТОЛЬКО если последняя сессия завершалась "
    "запуском игры (генерируется CausalObserver при выходе; при headless-разработке "
    "устарел и чтению не подлежит).\n"
    "Единый архив писем архитекторов преемникам — `docs/ЗАВЕЩАНИЕ_АРХИТЕКТОРОВ.md` "
    "(живой, append-only, дух L1Chronicle): последняя воля завершивших серию агентов "
    "— уроки, предупреждения, незадокументированный формально контекст. Читать при "
    "входе в проект; завершая свою серию — оставить своё письмо; чужие не "
    "редактируются. Техзадачи передаются ТЗ приёмнику — завещание сопровождает ТЗ, "
    "не заменяя его.\n"
    "Без этого запрещено писать или изменять код."
)


def main() -> int:
    target = next((p for p in CANDIDATES if p.exists()), None)
    req(target is not None,
        "РЕЖИМ РАБОТЫ.md не найден ни в корне, ни в docs/ — пришли путь")
    print(f"[i] цель: {target.relative_to(ROOT)}")

    raw = target.read_bytes()
    bom = b""
    if raw.startswith(b"\xef\xbb\xbf"):  # урок S317: BOM
        bom, raw = raw[:3], raw[3:]
    text = raw.decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")

    hits = text.count(OLD)
    req(hits == 1,
        f"якорь найден {hits} раз (ожидался 1) — пришли регион дословно")
    print("--- БЫЛО ---")
    print(OLD)
    print("--- СТАЛО ---")
    print(INS)
    print("------------")

    text = text.replace(OLD, INS, 1)

    # стражи: полные строки
    req(text.count("docs/ЗАВЕЩАНИЕ_АРХИТЕКТОРОВ.md") == 1,
        "пост: ссылка на Завещание != 1")
    req(text.count("Без этого запрещено писать или изменять код.") == 1,
        "пост: закрывающий гейт §3 затронут")
    out = text.replace("\n", "\r\n") if crlf else text
    target.write_bytes(bom + out.encode("utf-8"))
    print(f"[ok] записано: {target.relative_to(ROOT)} (пара предъявлена выше)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Abort as e:
        print(f"\n[ABORT] {e}\nНичего не записано.", file=sys.stderr)
        sys.exit(2)
