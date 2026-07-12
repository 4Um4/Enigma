"""
path: backend/tests/sandbox/SUPERBOX/behavior_laboratory.py
Назначение: Лаборатория экономики решений DecisionHub.
Измеряет покупательную способность трейтов, эмоций и отношений в реальном скоринге.
Зависимости: app.models.npc_state, app.services.npc.decision_hub

Запуск: cd backend; python -m tests.sandbox.SUPERBOX.behavior_laboratory; cd ..
"""

from app.models.npc_state import (
    NPCIdentityL1,
)


def run_trait_economy_probe():
    """
    Измеряет: какой вес active_traits реально способен
    открыть SURVIVAL домен в Viability Gate?

    Сценарий: Угроза = 0.2 (ниже базового порога 0.3).
    Без шрама -> ROUTINE доступен -> NPC работает.
    С шрамом "traumatized" -> порог снижается -> SURVIVAL доминирует -> NPC бежит.
    """
    from app.domain.movement import IntentDomain
    from app.services.npc.life_engine import LifeEngine

    print("\n[PROBE] Инициализация Trait Viability Gate Probe...")

    engine = LifeEngine()

    # 1. Тестовая угроза (ниже базового порога 0.3)
    test_threat = 0.2

    # 2. Замер базовой линии (БЕЗ шрама) — ROUTINE должен быть доступен
    npc_baseline = {
        "npc_id": "guard_probe",
        "perceptual_kernel": {"threat_gradient": test_threat},
        "identity": NPCIdentityL1(npc_id="guard_probe", active_traits={}),
    }

    viable_baseline = engine._compute_viability_mask(npc_baseline)
    print(f"[PROBE] Базовая линия (без шрама, threat={test_threat}): Доступные домены = {viable_baseline}")
    routine_available_baseline = IntentDomain.ROUTINE in viable_baseline

    # 3. Сканирование порога (наращивание веса "traumatized")
    print("\n[PROBE] Сканирование влияния 'traumatized' на Viability Gate...")
    print(f"{'Вес':<8} | {'ROUTINE доступен?':<18} | {'SURVIVAL доступен?':<20} | {'Порог':<8}")
    print("-" * 60)

    flip_point = None

    for w_int in range(0, 21, 4):  # От 0.0 до 2.0 с шагом 0.4
        w = w_int / 10.0
        npc_scarred = {
            "npc_id": "guard_probe",
            "perceptual_kernel": {"threat_gradient": test_threat},
            "identity": NPCIdentityL1(npc_id="guard_probe", active_traits={"traumatized": w}),
        }

        viable = engine._compute_viability_mask(npc_scarred)
        routine_available = IntentDomain.ROUTINE in viable
        survival_available = IntentDomain.SURVIVAL in viable
        threshold = 0.3 - (w * 0.25)

        print(f"{w:<8.1f} | {str(routine_available):<18} | {str(survival_available):<20} | {threshold:<8.2f}")

        if not routine_available and routine_available_baseline and flip_point is None:
            flip_point = w

    # 4. Вердикт
    if flip_point is not None:
        print(f"\n[PROBE] ✔ ТОЧКА ПЕРЕЛОМА: Вес 'traumatized' = {flip_point:.1f} закрывает ROUTINE домен.")
        print(f"[PROBE] Это значит, что шрам с весом >= {flip_point:.1f} способен перевести NPC в режим SURVIVAL.")
        print(f"[PROBE] NPC физически не сможет 'выбрать' работу при угрозе {test_threat}.")
    else:
        print("\n[PROBE] ✪ ПРОВАЛ: Вес 'traumatized' до 2.0 не способен закрыть ROUTINE домен.")
        print("[PROBE] Viability Gate не реагирует на Trait.")

    return flip_point


if __name__ == "__main__":
    run_trait_economy_probe()
