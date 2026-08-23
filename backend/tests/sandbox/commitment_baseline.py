# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/sandbox/commitment_baseline.py
Назначение: S203.1 / Stage 2A — baseline-метрики Commitment Registry (измерительный прибор).
    Собственный цикл тиков (production-путь GameLoop.idle_tick через DriftLab) +
    диагностика движения (STATIC_WORLD / MICRO_ONLY / TRAVERSAL_FLOW) — ответ на вопрос
    «почему реестр может быть пуст»: микро-движение (LocalSteeringGoal) идёт мимо
    SSM-ветки материализации и по решению №6 вне shadow-объёма S203.1.
    Отчёт пишется в КОРНЕВОЙ reports/ (путь от __file__, не от CWD) и его
    абсолютный путь печатается крупно в конце прогона (UX: не потерять отчёт).
    Инструмент наблюдения (CAUSAL CONTRACT §11): вывод — только для LLM-архитектора.
Зависимости: app.services.action.commitment_registry (флаг),
    tests.sandbox.SUPERBOX.drift_laboratory (реальный production-контур)
Основные сущности: main
"""

import time
from collections import Counter
from pathlib import Path

from app.services.action.commitment_registry import COMMITMENT_REGISTRY_ENABLED

TICKS = 200

# Путь от __file__, не от CWD: запуск из backend/ больше не прячет отчёт
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_REPORT_DIR = _PROJECT_ROOT / "reports"


def _snapshot_positions(scene: dict) -> dict:
    """Позиции NPC (без игрока) для дифа до/после — детектор любого движения."""
    out = {}
    for npc, entry in (scene.get("npc_positions") or {}).items():
        if npc == "player":
            continue
        lp = entry.get("local_position") or {}
        out[npc] = (lp.get("x"), lp.get("y"))
    return out


def main() -> None:
    if not COMMITMENT_REGISTRY_ENABLED:
        print("[COMMITMENT_BASELINE] FLAG=OFF — включите COMMITMENT_REGISTRY_ENABLED")
        return

    from tests.sandbox.SUPERBOX.drift_laboratory import DriftConfig, DriftLaboratory

    lab = DriftLaboratory(DriftConfig())
    print("[COMMITMENT_BASELINE] setup (production-стек, изолированный temp-dir)")
    lab._setup()
    try:
        scene = (
            lab._scene_manager.get_scene_state(
                lab.config.campaign_id, lab.config.location_id
            )
            or {}
        )
        before = _snapshot_positions(scene)

        print(f"[COMMITMENT_BASELINE] running {TICKS} idle ticks...")
        real_errors = 0
        ticks_with_traversals = 0
        max_trav = 0
        for _tick in range(1, TICKS + 1):
            try:
                lab._run_idle_tick_direct()
            except Exception as e:  # real crash — не ground-truth-шум валидатора
                real_errors += 1
                print(f"  [BASELINE] idle_tick error: {type(e).__name__}: {e}")
            scene = (
                lab._scene_manager.get_scene_state(
                    lab.config.campaign_id, lab.config.location_id
                )
                or {}
            )
            travs = scene.get("active_traversals") or {}
            if travs:
                ticks_with_traversals += 1
                max_trav = max(max_trav, len(travs))

        after = _snapshot_positions(scene)
        moved = sorted(n for n in before if before[n] != after.get(n))

        terminals = [
            t for bucket in (scene.get("commitment_history") or {}).values() for t in bucket
        ]
        actives = scene.get("active_commitments") or {}

        status_counts = Counter(t.get("status") for t in terminals)
        reason_counts = Counter(
            t.get("interrupt_reason") for t in terminals if t.get("interrupt_reason")
        )
        cause_counts = Counter(t.get("cause") for t in terminals)
        superseded = reason_counts.get("SUPERSEDED_BY_NEW_MATERIALIZATION", 0)
        vanished = reason_counts.get("TRAVERSAL_VANISHED", 0)
        cross_loc = reason_counts.get("CROSS_LOCATION_TRANSFER", 0)
        npcs_hist = len(scene.get("commitment_history") or {})
        switch_rate = (len(terminals) / npcs_hist / TICKS) if npcs_hist else 0.0

        # ── Диагноз движения: почему реестр такой ──
        if ticks_with_traversals == 0 and moved:
            verdict = "MICRO_ONLY: движение есть, но БЕЗ traversal-материализаций (микро/steering — вне S203.1 shadow, решение №6)"
        elif ticks_with_traversals == 0 and not moved:
            verdict = "STATIC_WORLD: движения нет вовсе — baseline требует иного сценария/окна"
        elif ticks_with_traversals > 0 and not terminals and not actives:
            verdict = "ANOMALY: traversals были, реестр пуст — расследование зеркала!"
        else:
            verdict = "TRAVERSAL_FLOW: материализации были, реестр отражает их"

        print("\n" + "=" * 60)
        print(f"[BASELINE] N={TICKS} | real_errors={real_errors}")
        print(f"[BASELINE] ДВИЖЕНИЕ: moved={moved or 'нет'} | ticks_with_traversals={ticks_with_traversals} | max_concurrent={max_trav}")
        print(f"[BASELINE] VERDICT: {verdict}")
        print("=" * 60)
        print(f"terminals={len(terminals)} actives={len(actives)} switch_rate={switch_rate:.4f}")
        print(f"superseded={superseded} vanished={vanished} cross_loc={cross_loc}")
        print(f"statuses={dict(status_counts)}")
        print(f"reasons={dict(reason_counts)}")
        print(f"causes={dict(cause_counts)}")

        _REPORT_DIR.mkdir(exist_ok=True)
        report_path = _REPORT_DIR / "commitment_baseline.txt"
        lines = [
            f"created={time.strftime('%Y-%m-%d %H:%M:%S')} (wall-clock — метаданные отчёта, §15.2)",
            f"ticks={TICKS} real_errors={real_errors}",
            f"verdict={verdict}",
            f"moved={moved}",
            f"ticks_with_traversals={ticks_with_traversals} max_concurrent={max_trav}",
            f"terminals={len(terminals)} actives={len(actives)} switch_rate={switch_rate:.4f}",
            f"superseded={superseded} vanished={vanished} cross_loc={cross_loc}",
            f"statuses={dict(status_counts)}",
            f"reasons={dict(reason_counts)}",
            f"causes={dict(cause_counts)}",
        ]
        report_path.write_text("\n".join(lines), encoding="utf-8")

        # UX: крупная ссылка на отчёт в конце прогона — чтобы отчёт не терялся
        print("\n" + "█" * 60)
        print(f"📄 ОТЧЁТ СОХРАНЁН: {report_path.resolve()}")
        print(f"   Открыть в PowerShell: Invoke-Item \"{report_path.resolve()}\"")
        print("█" * 60)
    finally:
        lab._teardown()


if __name__ == "__main__":
    main()