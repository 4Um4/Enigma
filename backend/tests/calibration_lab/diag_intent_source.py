"""
path: backend/tests/calibration_lab/diag_intent_source.py
Назначение: Одноразовый диагностический зонд (ЧАСТЬ VIII.5): 150-тиковый
    прогон golden — вердикт DEBT-INTENT-SOURCE. Если NPC с intent = 0 на
    длинной сессии при живых диалогах (l1/social события > 0) — источник
    интентов (npc["intent"] в get_npc_states) мёртв для метрик diversity/
    loop: требуется археология писателя (state_applicator → npc_dict).
    Попутно: полный снимок метрик M0 на длинной сессии (подготовка AC).
Запуск:
    cd backend; python tests/calibration_lab/diag_intent_source.py [ticks]; cd ..
Зависимости: app.services.calibration.experiment_runner.
Основные сущности: main.
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

_REPO_ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    ticks = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    from app.services.calibration.experiment_runner import (
        ExperimentConfig,
        ExperimentRunner,
    )

    result = ExperimentRunner().run(
        ExperimentConfig(
            preset_path=str(
                _REPO_ROOT / "config" / "calibration" / "test_presets" / "enigma_golden.yaml"
            ),
            duration_ticks=ticks,
        )
    )
    per_tick = [
        sum(1 for n in tick if n.get("intent") is not None)
        for tick in result.npc_captures
    ]
    total_intents = sum(per_tick)
    l1 = result.l1_event_count
    events = sum(result.events_per_tick)
    print(f"[DIAG_INT] ticks={ticks}")
    print(f"[DIAG_INT] NPC с intent по тикам: первые 20 = {per_tick[:20]}")
    print(f"[DIAG_INT] сумма интентов={total_intents}, l1={l1}, bus_events={events}")
    print(f"[DIAG_INT] metrics={ {k: (round(v, 4) if v is not None else None) for k, v in result.metrics.items()} }")
    if total_intents == 0 and (l1 > 0 or events > 0):
        print(
            "[DIAG_INT] ВЕРДИКТ: DEBT-INTENT-SOURCE ПОДТВЕРЖДЁН — мир активен "
            "(l1/events > 0), но npc['intent'] не наблюдаем в снапшоте загрузчика."
        )
    elif total_intents > 0:
        print("[DIAG_INT] ВЕРДИКТ: источник жив — метрики diversity/loop валидны.")
    else:
        print(
            "[DIAG_INT] ВЕРДИКТ: мир пассивен (нет ни интентов, ни событий) — "
            "вопрос сценариев idle-контура, не источника."
        )
    # Ключи первого NPC: где МОГ бы жить intent (для археологии при вердикте-баге)
    sample = result.npc_captures[-1][0] if result.npc_captures else {}
    print(f"[DIAG_INT] ключи npc-дикта: {sorted(sample.keys())}")


if __name__ == "__main__":
    main()