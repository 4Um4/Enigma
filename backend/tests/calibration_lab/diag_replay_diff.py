"""
path: backend/tests/calibration_lab/diag_replay_diff.py
Назначение: Одноразовый диагностический зонд (Правила Фикса Багов,
    ЧАСТЬ VIII.5) для локализации недетерминизма replay (красный M0-AC-004):
    два прогона одного конфига, послойное сравнение — первый расходящийся
    тик, первый расходящийся NPC, точные пути расходящихся полей (глубокий
    диф), счётчики L1/NaN. Разделяет гипотезы: расхождение НА t=0
    (глобальный перенос состояния между прогонами) vs в СЕРЕДИНЕ
    (async/wall-clock контаминация) vs только метаданные времени
    (сравнение слишком строгое).

Запуск: cd backend; python tests/calibration_lab/diag_replay_diff.py [ticks]; cd ..

Зависимости: app.services.calibration.experiment_runner (path-hack ниже).
Основные сущности: deep_diff, main.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List, Optional

# Скрипт запускается по пути: добавляем backend/ в sys.path
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PRESETS_DIR = _REPO_ROOT / "config" / "calibration" / "test_presets"


def deep_diff(
    a: Any,
    b: Any,
    path: str = "",
    out: Optional[List[str]] = None,
    limit: int = 60,
) -> List[str]:
    """Собирает пути расходящихся листьев (до limit)."""
    if out is None:
        out = []
    if len(out) >= limit:
        return out
    if type(a) is not type(b):
        out.append(f"{path}: TYPE {type(a).__name__} != {type(b).__name__}")
        return out
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b), key=str):
            if len(out) >= limit:
                return out
            if k not in a:
                out.append(f"{path}.{k}: ONLY_IN_RUN2={b[k]!r}")
            elif k not in b:
                out.append(f"{path}.{k}: ONLY_IN_RUN1={a[k]!r}")
            else:
                deep_diff(a[k], b[k], f"{path}.{k}", out, limit)
    elif isinstance(a, (list, tuple)):
        if len(a) != len(b):
            out.append(f"{path}: LEN {len(a)} != {len(b)}")
        for i in range(min(len(a), len(b))):
            if len(out) >= limit:
                return out
            deep_diff(a[i], b[i], f"{path}[{i}]", out, limit)
    else:
        if a != b:
            out.append(f"{path}: {a!r} != {b!r}")
    return out


def main() -> None:
    ticks = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    from app.services.calibration.experiment_runner import (
        ExperimentConfig,
        ExperimentRunner,
    )
    from app.services.events.event_bus import get_event_bus

    cfg = ExperimentConfig(
        preset_path=str(_PRESETS_DIR / "enigma_golden.yaml"),
        campaign_id="Open_road",
        duration_ticks=ticks,
    )
    runner = ExperimentRunner()
    r1 = runner.run(cfg)
    get_event_bus().clear()
    r2 = runner.run(cfg)

    print(f"[DIAG] ticks={ticks}")
    print(f"[DIAG] l1_event_count: run1={r1.l1_event_count} run2={r2.l1_event_count}")
    print(f"[DIAG] nan_count: run1={r1.nan_count} run2={r2.nan_count}")
    print(f"[DIAG] statuses run1={r1.statuses} run2={r2.statuses}")

    diverged = False
    for t in range(len(r1.npc_captures)):
        c1 = {n.get("id", n.get("npc_id", "?")): n for n in r1.npc_captures[t]}
        c2 = {n.get("id", n.get("npc_id", "?")): n for n in r2.npc_captures[t]}
        if set(c1) != set(c2):
            print(
                f"[DIAG] TICK {t}: множества NPC различны: "
                f"only1={sorted(set(c1) - set(c2))} only2={sorted(set(c2) - set(c1))}"
            )
            diverged = True
            break
        per_npc = {}
        for npc_id in sorted(c1):
            d = deep_diff(c1[npc_id], c2[npc_id])
            if d:
                per_npc[npc_id] = d
        if per_npc:
            diverged = True
            marker = (
                "  ← t=0: ПЕРЕНОС НАЧАЛЬНОГО СОСТОЯНИЯ МЕЖДУ ПРОГОНАМИ (H1)"
                if t == 0
                else "  ← расхождение с середины (H2-кандидат)"
            )
            print(f"[DIAG] FIRST DIVERGENT TICK = {t}{marker}")
            for npc_id, d in per_npc.items():
                print(f"  [{npc_id}] {len(d)} расходящихся путей, первые 12:")
                for line in d[:12]:
                    print(f"    {line}")
            break
    if not diverged:
        print("[DIAG] npc_captures идентичны покадрово")

    for t in range(len(r1.rel_captures)):
        d = deep_diff(r1.rel_captures[t], r2.rel_captures[t])
        if d:
            print(f"[DIAG] rel_captures расходятся на тике {t}, первые 12:")
            for line in d[:12]:
                print(f"    {line}")
            break
    else:
        print("[DIAG] rel_captures идентичны покадрово")


if __name__ == "__main__":
    main()