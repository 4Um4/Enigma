#!/usr/bin/env python3
"""UX-UE-01 / L1-sibling: удаление мёртвого хелпера до коммита (гейт остаётся).

Контекст: git diff носителя = +55/-1, из них +12/-1 — гейт v3 (проверен
7 инвариантами), +43 — мёртвый _player_directive_l1_events в рабочем дереве
(добавлен ДО патча, вне патч-пакета): вызова нет нигде, ATTACK-ветка —
литеральный `...` (заглушка), докстринг обещает «переносится ДОСЛОВНО».
В коммит под реестровую S-строку не годится.

Скрипт удаляет ТОЛЬКО блок хелпера. Отказы (всегда без записи): хелпер
вызывается/упоминается вне def; структура блока неожидаема; гейт v3
не найден в файле.

Запуск из корня репо:
    python scripts/strip_dead_l1_helper.py            # dry-run: БЫЛО/СТАЛО + дифф
    python scripts/strip_dead_l1_helper.py --write    # применить (+ ast-проверка)
"""

from __future__ import annotations

import argparse
import ast
import difflib
import re
import sys
from pathlib import Path

CANDIDATES = [Path("backend/app/services/game_loop/npc_orchestration.py")]
NAME = "_player_directive_l1_events"
TOP_DEF = re.compile(r"^(?:async\s+)?def\s+\w+\(")


def _locate() -> Path:
    for p in CANDIDATES:
        if p.exists():
            return p
    print("[UE-L1-STRIP] npc_orchestration.py не найден:")
    for p in CANDIDATES:
        print(f"  - {p}")
    sys.exit(2)


def _references(backend_root: Path):
    """Все упоминания NAME по backend, кроме def-строки самого хелпера."""
    refs = []
    for py in backend_root.rglob("*.py"):
        try:
            t = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if NAME not in t:
            continue
        for i, ln in enumerate(t.splitlines(), 1):
            if NAME in ln and f"def {NAME}" not in ln:
                refs.append(f"{py}:{i}")
    return refs


def main() -> int:
    ap = argparse.ArgumentParser(
        description="UX-UE-01: удаление мёртвого L1-хелпера (гейт v3 остаётся)"
    )
    ap.add_argument("--write", action="store_true", help="применить (по умолчанию dry-run)")
    args = ap.parse_args()

    path = _locate()
    backend_root = path.parents[3]  # backend/
    with open(path, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    lines = text.splitlines(keepends=True)
    starts = [i for i, ln in enumerate(lines) if ln.strip().startswith(f"def {NAME}")]
    if not starts:
        print(f"[UE-L1-STRIP] {NAME} не найден — уже удалён. Выходим.")
        return 0
    if len(starts) > 1:
        print(f"[UE-L1-STRIP] def {NAME} встречается {len(starts)} раз — неожидаемо:")
        for i in starts:
            print(f"  {i + 1}: {lines[i].rstrip()}")
        return 2

    refs = _references(backend_root)
    if refs:
        print(f"[UE-L1-STRIP] ОТКАЗ: {NAME} упоминается вне def — не мёртвый код:")
        for r in refs:
            print(f"  {r}")
        return 2

    start = starts[0]
    end = next((j for j in range(start + 1, len(lines)) if TOP_DEF.match(lines[j])), None)
    if end is None:
        print("[UE-L1-STRIP] ОТКАЗ: следующий top-level def не найден.")
        return 2

    block = lines[start:end]
    block_text = "".join(block)
    checks = {
        "маркер докстринга S-UE/D4-sibling": "S-UE/D4-sibling" in block_text,
        "return _l1_events": "return _l1_events" in block_text,
        "эллипсис-заглушка `...`": re.search(r"^\s*\.\.\.\s*$", block_text, re.M) is not None,
        "длина блока 30-70 строк": 30 <= len(block) <= 70,
    }
    bad = [k for k, v in checks.items() if not v]
    if bad:
        print(f"[UE-L1-STRIP] ОТКАЗ: блок не похож на ожидаемый хелпер ({'; '.join(bad)}).")
        print("[UE-L1-STRIP] дамп блока для археолога:")
        for i, ln in enumerate(block, start + 1):
            print(f"  {i}: {ln.rstrip()}")
        return 2

    if "_ue_l1_readiness" not in text or "[UE-GATE-L1] L1-фиксация директивы подавлена" not in text:
        print("[UE-L1-STRIP] ОТКАЗ: гейт v3 не найден — сначала патч, потом чистка.")
        return 2

    a, b = max(0, start - 4), min(len(lines), end + 4)
    print(f"[UE-L1-STRIP] цель: {path}")
    print(f"[UE-L1-STRIP] блок хелпера: стр. {start + 1}-{end} ({len(block)} строк); гейт не трогается.")
    print()
    print("===== БЫЛО =====")
    for i in range(a, b):
        print(f"{i + 1}: {lines[i].rstrip()}")
    print()
    new_lines = lines[:start] + lines[end:]
    print("===== СТАЛО =====")
    for k, ln in enumerate(new_lines[a : b - len(block)]):
        print(f"{a + 1 + k}: {ln.rstrip()}")
    print()
    print("===== unified diff =====")
    for dl in difflib.unified_diff(
        [l.rstrip() for l in lines[a:b]],
        [l.rstrip() for l in new_lines[a : b - len(block)]],
        fromfile=f"{path.name} (БЫЛО)",
        tofile=f"{path.name} (СТАЛО)",
        lineterm="",
    ):
        print(dl)

    if not args.write:
        print()
        print("[UE-L1-STRIP] DRY-RUN: ничего не записано. Применить: python scripts/strip_dead_l1_helper.py --write")
        return 0

    try:
        ast.parse("".join(new_lines))
    except SyntaxError as e:
        print(f"[UE-L1-STRIP] ОТКАЗ: синтаксическая ошибка после удаления: {e}")
        return 2
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("".join(new_lines))
    print()
    print(f"[UE-L1-STRIP] ЗАПИСАНО: мёртвый хелпер удалён ({len(block)} строк). Гейт v3 не тронут.")
    print("[UE-L1-STRIP] далее: git diff --stat → ожидание +12/-1; инварианты → 7 passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())