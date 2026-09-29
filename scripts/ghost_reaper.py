# -*- coding: utf-8 -*-
"""
path: scripts/ghost_reaper.py
Назначение: KILLER_SPIRIT (санкция Мастера) — обнаружение и точечное
    устранение осиротевших backend-связок ENIGMA (llama-server:8181 +
    uvicorn app.main:app:8000), чей родитель-ланчер умер, не убив детей
    (долг TZ-GHOST-1: ланчер не делает cleanup при выходе).
    Убивает ТОЛЬКО при трёх доказанных признаках ОДНОВРЕМЕННО:
      1) сигнатура связки (llama-server | uvicorn app.main:app);
      2) принадлежность этому репозиторию (путь в cmdline или cwd);
      3) сиротство: НЕТ ни одного живого предка вне связки
         (живой ланчер/родитель = живой владелец = щадить всегда).
    Посторонние python-процессы (pytest, DriftLab, зонды, чужие проекты)
    не совпадают с сигнатурой — неприкосновенны по построению.
    Никогда не поднимает исключений наружу (деградация канала, не тика):
    все отказы печатаются громко и попадают в report["fault"].
Зависимости: psutil (6.x, venv), os, sys, time, typing. Без app.* —
    модуль автономен от ядра и импортируется чем угодно.
Основные сущности: reap(dry_run, verbose) -> ReaperReport,
    BUNDLE-сигнатуры, CLI (dry-run по умолчанию, --reap = устранение).
Запуск: python scripts/ghost_reaper.py          (dry-run: только вердикты)
        python scripts/ghost_reaper.py --reap   (реальное устранение)
Интеграция: backend/tests/IPT.py — INV-GHOST-REAPER (начало + конец).
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List, Optional

try:
    import psutil
except ImportError:  # pragma: no cover — psutil обязан быть в venv
    psutil = None  # type: ignore[assignment]

REAPER_TAG = "[KILLER_SPIRIT]"

# Корень репозитория (scripts/..) в нижнем регистре — маркер "наш" процесс.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).lower()


def _safe_info(proc: "psutil.Process") -> Optional[Dict[str, Any]]:
    """Снимок процесса без исключений (мертвец/доступ — None)."""
    try:
        return {
            "pid": proc.pid,
            "name": (proc.name() or "").lower(),
            "cmdline": " ".join(proc.cmdline() or []),
            "cwd": proc.cwd() or "",
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None


def _is_bundle(info: Dict[str, Any]) -> bool:
    """Признак 1 — сигнатура связки ENIGMA."""
    if "llama-server" in info["name"]:
        return True
    if info["name"].startswith("python") and "uvicorn" in info["cmdline"] and "app.main:app" in info["cmdline"]:
        return True
    return False


def _is_ours(info: Dict[str, Any]) -> bool:
    """Признак 2 — принадлежность репозиторию (cmdline или cwd внутри корня)."""
    low = info["cmdline"].lower() + " " + info["cwd"].lower()
    return _REPO_ROOT in low


def _live_owner_outside(proc: "psutil.Process", bundle_pids: set, self_pids: set) -> Optional[str]:
    """Признак 3 — сиротство. Возвращает причину пощады ИЛИ None (= сирота).

    Идём вверх по родителям: родитель == мы сами -> пощадить (self-tree);
    родитель в связке -> продолжаем выше; родитель жив и ВНЕ связки ->
    пощадить (живой владелец: запущенная игра/ланчер/чужая сессия);
    родитель мёртв -> цепочка обрывается дальше.
    """
    visited = set()
    cur = proc
    for _ in range(64):  # защита от циклов в графе процессов
        try:
            parent = cur.parent()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None  # родитель недоступен и мёртв по факту — сирота
        if parent is None:
            return None  # цепочка кончилась смертью — сирота
        if parent.pid in visited:
            return f"цикл предков на pid={parent.pid}"
        visited.add(parent.pid)
        if parent.pid in self_pids:
            return "дерево текущего процесса"
        if parent.pid not in bundle_pids:
            try:
                parent.name()  # зонд живости
                return f"живой владелец pid={parent.pid}"
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                continue  # мёртвый предок — идём выше
        cur = parent
    return "глубина цепочки предков > 64"


def reap(dry_run: bool = True, verbose: bool = True) -> Dict[str, List[Any]]:
    """Главный вход KILLER_SPIRIT. Никогда не бросает исключений.

    dry_run=True — только вердикты (SPARE/KILL) без убийства.
    Возвращает report: killed / spared / fault (списки с причинами).
    """
    report: Dict[str, List[Any]] = {"killed": [], "spared": [], "fault": []}
    if psutil is None:
        report["fault"].append("psutil недоступен — KILLER_SPIRIT пропущен")
        if verbose:
            print(f"{REAPER_TAG} FAULT: psutil недоступен, пропуск")
        return report

    self_pids = {os.getpid(), os.getppid()}

    # Сбор связки: сигнатура + принадлежность репозиторию
    bundle: List[Dict[str, Any]] = []
    for proc in psutil.process_iter():
        if proc.pid in self_pids:
            continue
        info = _safe_info(proc)
        if info is None:
            continue
        if _is_bundle(info) and _is_ours(info):
            info["proc"] = proc
            bundle.append(info)

    if not bundle:
        if verbose:
            print(f"{REAPER_TAG} чисто: призрачных связок не найдено")
        return report

    bundle_pids = {b["pid"] for b in bundle}

    # Вердикты
    orphans: List[Dict[str, Any]] = []
    for b in bundle:
        reason = _live_owner_outside(b["proc"], bundle_pids, self_pids)
        if reason is None:
            orphans.append(b)
        else:
            report["spared"].append({"pid": b["pid"], "name": b["name"], "reason": reason})
            if verbose:
                print(f"{REAPER_TAG} SPARE pid={b['pid']} {b['name']}: {reason}")

    if not orphans:
        if verbose:
            print(f"{REAPER_TAG} щажу всё: сирот нет ({len(report['spared'])} живых владельцев)")
        return report

    # Порядок убийства: корни первыми (uvicorn-родитель раньше reload-воркера,
    # иначе --reload переродит воркера). Глубина = число предков внутри связки.
    def _depth(b: Dict[str, Any]) -> int:
        d, cur, seen = 0, b["proc"], set()
        while True:
            try:
                parent = cur.parent()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return d
            if parent is None or parent.pid in seen:
                return d
            if parent.pid not in bundle_pids:
                return d
            seen.add(parent.pid)
            cur, d = parent, d + 1

    for b in sorted(orphans, key=_depth):
        label = f"pid={b['pid']} {b['name']}"
        if dry_run:
            report["killed"].append({"pid": b["pid"], "name": b["name"], "reason": "DRY-RUN: сирота+сигнатура"})
            if verbose:
                print(f"{REAPER_TAG} KILL(dry) {label}: сирота, сигнатура связки")
            continue
        try:
            b["proc"].kill()
            psutil.wait_procs([b["proc"]], timeout=5)
            report["killed"].append({"pid": b["pid"], "name": b["name"], "reason": "сирота+сигнатура"})
            if verbose:
                print(f"{REAPER_TAG} KILL {label}: сирота, сигнатура связки")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired) as exc:
            report["fault"].append({"pid": b["pid"], "error": repr(exc)})
            if verbose:
                print(f"{REAPER_TAG} FAULT {label}: {exc!r}")

    if verbose:
        mode = "dry-run" if dry_run else "REAP"
        print(
            f"{REAPER_TAG} {mode}: убито={len(report['killed'])} "
            f"пощажено={len(report['spared'])} отказов={len(report['fault'])}"
        )
    return report


if __name__ == "__main__":
    _dry = "--reap" not in sys.argv
    if _dry:
        print(f"{REAPER_TAG} режим dry-run (реальное устранение: --reap)")
    _rep = reap(dry_run=_dry)
    # Код выхода 0 всегда: уборщик не должен ломать скриптовые цепочки
    sys.exit(0)