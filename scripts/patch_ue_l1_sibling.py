#!/usr/bin/env python3
"""UX-UE-01 / L1-sibling v3: readiness-гейт на commit L1-фиксации директив.

Носитель ПОДТВЕРЖДЁН археологией оператора (дамп A/B/C):
    backend/app/services/game_loop/npc_orchestration.py   (пакет game_loop, НЕ npc)

Верифицированная структура файла (номера строк на момент дампа):
    ~42-67   модульный билдер player-L1 TraitDriftEvent (fast-path SHI-FIX CAUSAL):
             стр. 56: _sem_action = getattr(_params, "semantic_action", "").upper()
             стр. 57: _target_id = shared_context.player_target_id or ""
             стр. 67: TraitDriftEvent(...)
    ~296-315 вызов быстрого пути директив (накапливает _l1_events для сиблингов)
    ~343-400 ATTACK-дрейф (attack -0.9 / damage -0.5), гейтится [UE-GATE-L1]
             "attack/damage-дрифт подавлен" (стр. 377) — ТОЛЬКО эта ветка
    402-410  commit-блок — ЕДИНСТВЕННЫЙ выход и эмиттер [L1_FIXATION] в бэкенде

Утечка (живой лог run_terminal_mvp, тик 40/41, readiness=PARTIAL, raw=
'Не угрожать Торнину' / 'Держаться подальше от Торнина'): сиблинги MOVE/THREATEN/
PERSUADE/GIVE попадают в _l1_events БЕЗ гейта → commit при non-RESOLVED.

Мини-дифф v3 — гейт на единственном выходе (текст блока верифицирован дословно):
    перед `if _l1_events:` вставляется чтение _ue_l1_readiness
    (дефолт "RESOLVED": контексты без intent_resolution не меняют поведение) +
    warning-if подавления ([UE-GATE-L1], паритет с остальными гейтами);
    заголовок усиливается: `if _l1_events and _ue_l1_readiness == "RESOLVED":`.
    Тело try-блока не трогается; RESOLVED → поведение байт-в-байт прежнее.

Запуск из корня репо:
    python scripts/patch_ue_l1_sibling.py            # dry-run: БЫЛО/СТАЛО + дифф
    python scripts/patch_ue_l1_sibling.py --write    # применить (+ ast-проверка)

Отказы (всегда без записи): файл не найден; якорь исчез; несколько якорей без
--line; shared_context не в области видимости функции (пришлёшь дамп — адаптирую).

Скоуп: только этот файл + backend/tests/sandbox/micro/test_ue_d4_l1_sibling_red.py (v3).
frontend/* не трогаем (D61/COV-2).
"""

from __future__ import annotations

import argparse
import ast
import difflib
import re
import sys
from pathlib import Path

CANDIDATES = [
    Path("backend/app/services/game_loop/npc_orchestration.py"),
]
GUARD = "_ue_l1_readiness"
CONTEXT_MARK = "commit_tick_buffer"
COMMIT_RE = re.compile(r"^(?P<indent>[ \t]*)if _l1_events[ \t]*:(?P<tail>.*)$")
DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+\w+\(")
# bare-имя shared_context: не 'xxx.shared_context', не в составе идентификатора
SC_RE = re.compile(r"(?<![\w.])shared_context\b")


def _locate(args) -> Path:
    if args.path:
        p = Path(args.path)
        if p.exists():
            return p
        print(f"[UE-L1-PATCH] --path {args.path} не существует")
        sys.exit(2)
    for p in CANDIDATES:
        if p.exists():
            return p
    print("[UE-L1-PATCH] npc_orchestration.py не найден:")
    for p in CANDIDATES:
        print(f"  - {p}")
    sys.exit(2)


def _find_commits(lines):
    """Все `if _l1_events:`, за которыми в окне 6 строк — commit_tick_buffer."""
    out = []
    for i, ln in enumerate(lines):
        m = COMMIT_RE.match(ln)
        if m and CONTEXT_MARK in "".join(lines[i : i + 6]):
            out.append(i)
    return out


def _enclosing_def(lines, idx):
    for j in range(idx, -1, -1):
        if DEF_RE.match(lines[j]):
            return j
    return 0


def _guard_lines(indent: str) -> list:
    return [
        f'{indent}_ue_l1_ir = getattr(shared_context, "intent_resolution", None)  # noqa: ENIGMA002',
        f'{indent}_ue_l1_params = getattr(getattr(_ue_l1_ir, "original_intent", None), "parameters", None)  # noqa: ENIGMA002',
        f'{indent}{GUARD} = getattr(_ue_l1_params, "intent_readiness", "RESOLVED")  # noqa: ENIGMA002',
        f'{indent}if _l1_events and {GUARD} != "RESOLVED":',
        f'{indent}    logger.warning(',
        f'{indent}        "[UE-GATE-L1] L1-фиксация директивы подавлена "',
        f'{indent}        "(intent_readiness=%s): sem=%s target=%s tick=%s — попытка ≠ событие",',
        f'{indent}        {GUARD},',
        f'{indent}        _sem_action,',
        f'{indent}        _target_id,',
        f'{indent}        _tick,',
        f'{indent}    )',
    ]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="UX-UE-01 L1-sibling v3: readiness-гейт на commit L1-фиксации"
    )
    ap.add_argument("--write", action="store_true", help="применить (по умолчанию dry-run)")
    ap.add_argument("--line", type=int, default=None, help="номер commit-строки (1-based), если якорей несколько")
    ap.add_argument("--path", default=None, help="явный путь к npc_orchestration.py")
    args = ap.parse_args()

    path = _locate(args)
    with open(path, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    if GUARD in text:
        print(f"[UE-L1-PATCH] {path} уже пропатчен ({GUARD} присутствует) — выходим.")
        return 0

    lines = text.splitlines(keepends=True)
    commits = _find_commits(lines)
    if not commits:
        print("[UE-L1-PATCH] commit-блок `if _l1_events:` + commit_tick_buffer не найден — файл отрефакторен?")
        print("[UE-L1-PATCH] дамп для археолога (все _l1_events / l1_chronicle / L1_FIXATION):")
        for i, ln in enumerate(lines):
            if "_l1_events" in ln or "l1_chronicle" in ln or "L1_FIXATION" in ln:
                print(f"  {i + 1}: {ln.rstrip()}")
        return 2
    if len(commits) > 1 and args.line is None:
        print("[UE-L1-PATCH] commit-блоков несколько — укажи --line N:")
        for i in commits:
            print(f"  {i + 1}: {lines[i].rstrip()}")
        return 2
    idx = (args.line - 1) if args.line is not None else commits[0]
    if idx not in commits:
        print(f"[UE-L1-PATCH] --line {args.line} не commit-блок. Валидные: {[i + 1 for i in commits]}")
        return 2

    m = COMMIT_RE.match(lines[idx])
    indent = m.group("indent")
    tail = m.group("tail").strip()
    eol = "\r\n" if lines[idx].endswith("\r\n") else "\n"

    def_idx = _enclosing_def(lines, idx)
    seg = "".join(lines[def_idx:idx])
    if not SC_RE.search(seg):
        print(
            f"[UE-L1-PATCH] ОТКАЗ: bare-имя shared_context не найдено в функции "
            f"(стр. {def_idx + 1}-{idx + 1}) — вставка стала бы NameError."
        )
        print("[UE-L1-PATCH] пришли дамп (сигнатура + окружение), адаптирую гейт под фактический контекст:")
        print(f'  Get-Content "{path}" | Select-Object -Index (({def_idx})..({idx + 5}))')
        return 2

    new_header = f'{indent}if _l1_events and {GUARD} == "RESOLVED":' + (f" {tail}" if tail else "")
    guard = [ln + eol for ln in _guard_lines(indent)]

    print(f"[UE-L1-PATCH] цель: {path}")
    print(f"[UE-L1-PATCH] commit-блок: стр. {idx + 1}; функция начинается: стр. {def_idx + 1}")
    print()

    a, b = max(0, idx - 6), min(len(lines), idx + 12)
    print("===== БЫЛО =====")
    for i in range(a, b):
        print(f"{i + 1}: {lines[i].rstrip()}")
    print()
    print("===== СТАЛО =====")
    ng = len(guard)
    for k, ln in enumerate(_guard_lines(indent)):
        print(f"{idx + 1 + k}: [+] {ln}")
    print(f"{idx + 1 + ng}: [~] {new_header}")
    for i in range(idx + 1, b):
        print(f"{i + 1 + ng}:    {lines[i].rstrip()}")
    print()

    new_lines = lines[:idx] + guard + [new_header + eol] + lines[idx + 1 :]

    print("===== unified diff =====")
    old_show = [ln.rstrip() for ln in lines[a:b]]
    new_show = [ln.rstrip() for ln in new_lines[a : b + ng]]
    for dl in difflib.unified_diff(
        old_show, new_show, fromfile=f"{path.name} (БЫЛО)", tofile=f"{path.name} (СТАЛО)", lineterm=""
    ):
        print(dl)

    if not args.write:
        print()
        print("[UE-L1-PATCH] DRY-RUN: ничего не записано. Применить: python scripts/patch_ue_l1_sibling.py --write")
        return 0

    try:
        ast.parse("".join(new_lines))
    except SyntaxError as e:
        print(f"[UE-L1-PATCH] ОТКАЗ: синтаксическая ошибка после трансформации: {e}")
        return 2
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("".join(new_lines))
    print()
    print(f"[UE-L1-PATCH] ЗАПИСАНО: {path} (+{ng} строк гейта перед стр. {idx + 1}, заголовок усилен).")
    print("[UE-L1-PATCH] далее: cd backend && python -m pytest tests/sandbox/micro/test_ue_d4_l1_sibling_red.py -v")
    return 0


if __name__ == "__main__":
    sys.exit(main())