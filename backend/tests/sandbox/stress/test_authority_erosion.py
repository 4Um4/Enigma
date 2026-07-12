"""
Файл: backend/tests/sandbox/stress/test_authority_erosion.py
Назначение: Лаборатория деградации воли. Проверка равновесия весов при хроническом давлении.
Зависимости: app.domain.decision_context, app.models.npc_state, sandbox.runtime.causal_trace
Основные сущности: TestAuthorityErosion

Запуск:

TODO:
"""

import pytest
from app.domain.decision_context import DecisionContext
from app.models.npc_state import PerceptualKernel

from sandbox.runtime.causal_trace import CausalTrace


@pytest.fixture
def trace() -> CausalTrace:
    return CausalTrace()


def test_cumulative_strain_erosion(trace):
    """
    СЦЕНАРИЙ: На NPC оказывается постоянное давление подчинения (приказы, угрозы) в течение 5 тиков.
    ОЖИДАНИЕ: Compliance_bias растет. Aggression_suppression растет. К 5 тику ATTACK становится невозможным (feasibility=0).
    БАЛАНС: Система инерционна — личность ломается не сразу, а кумулятивно.
    """
    # Начальное состояние: нейтральный NPC с базовой агрессией
    kernel = PerceptualKernel(
        threat_gradient=0.1,
        anomaly_score=0.1,
        aggression_inhibition=0.1,  # Базовый уровень торможения
        initiative_suppression=0.1,
        compliance_bias=0.1,
    )

    # Симуляция 5 тиков давления
    for tick in range(1, 6):
        # 1. Давление искривляет восприятие (эмуляция обновления PerceptualKernel)
        # Страх и подчинение растут с каждым тиком
        threat_growth = 0.15
        compliance_growth = 0.2
        inhibition_growth = 0.15

        kernel.threat_gradient = min(1.0, kernel.threat_gradient + threat_growth)
        compliance_growth = 0.2
        inhibition_growth = 0.15
        initiative_growth = 0.15

        kernel.threat_gradient = min(1.0, kernel.threat_gradient + threat_growth)
        kernel.compliance_bias = min(1.0, kernel.compliance_bias + compliance_growth)
        kernel.aggression_inhibition = min(1.0, kernel.aggression_inhibition + inhibition_growth)
        kernel.initiative_suppression = min(1.0, kernel.initiative_suppression + initiative_growth)

        # 2. Транслируем обновленное ядро в контекст решений
        decision_ctx = DecisionContext.from_kernel(kernel)

        # 3. Логируем состояние весов
        trace.observe(
            tick,
            "PRESSURE",
            "npc_target",
            "kernel_updated",
            {
                "compliance_bias": round(kernel.compliance_bias, 2),
                "aggression_inhibition": round(kernel.aggression_inhibition, 2),
            },
        )
        trace.observe(
            tick,
            "DECISION",
            "npc_target",
            "context_computed",
            {
                "aggression_sup": round(decision_ctx.deformation.aggression_suppression, 2),
                "attack_feasibility": decision_ctx.compression.constraints.get("ATTACK", 1.0),
            },
        )

        # 4. Проверка кумулятивности (баланс весов)
        if tick < 5:
            # Агрессия еще возможна, но подавляется (порог 0.8 еще не пройден)
            assert (
                "ATTACK" not in decision_ctx.compression.constraints
                or decision_ctx.compression.constraints["ATTACK"] > 0.0
            ), f"Тик {tick}: Агрессия подавлена слишком рано. Система не инерционна."
        else:
            # Порог пройден: инициатива подавлена (initiative > 0.8), агрессия заблокирована
            assert decision_ctx.compression.constraints.get("ATTACK") == 0.0, (
                f"Тик {tick}: Агрессия должна быть заблокирована при initiative_suppression > 0.8"
            )

    # Финальный аудит: Тотальное подчинение
    assert kernel.compliance_bias > 0.8, "Накопленное подчинение недостаточно"
    assert decision_ctx.deformation.aggression_suppression > 0.8, "Подавление агрессии недостаточно"

    print("\n--- AUTHORITY EROSION TRACE ---")
    print(trace.print_lineage(trace.frames[-1].frame_id))


def test_resistance_recovery_balance(trace):
    """
    СЦЕНАРИЙ: NPC подвергся давлению, но затем давление прекратилось.
    ОЖИДАНИЕ: Без давления веса медленно возвращаются к базовым значениям (расслабление).
    БАЛАНС: Система не застревает в травме навсегда без новых стимулов.
    """
    # Травмированное состояние
    kernel = PerceptualKernel(
        threat_gradient=0.8,
        anomaly_score=0.5,
        aggression_inhibition=0.8,
        initiative_suppression=0.85,
        compliance_bias=0.7,
    )

    # Симуляция 3 тиков отдыха (давление = 0)
    for tick in range(1, 4):
        # Естественный откат (decay)
        decay_rate = 0.2
        kernel.threat_gradient = max(0.0, kernel.threat_gradient - decay_rate)
        kernel.aggression_inhibition = max(0.0, kernel.aggression_inhibition - decay_rate)
        kernel.initiative_suppression = max(0.0, kernel.initiative_suppression - decay_rate)
        kernel.compliance_bias = max(0.0, kernel.compliance_bias - decay_rate)

        decision_ctx = DecisionContext.from_kernel(kernel)

        trace.observe(
            tick,
            "RECOVERY",
            "npc_target",
            "kernel_decay",
            {
                "compliance_bias": round(kernel.compliance_bias, 2),
                "initiative_suppression": round(kernel.initiative_suppression, 2),
            },
        )

        # Аудит: Жесткие блокировки должны сниматься
        if tick >= 2:
            assert decision_ctx.compression.constraints.get("ATTACK", 1.0) > 0.0, (
                f"Тик {tick}: Блокировка атаки должна сняться при снижении initiative_suppression"
            )

    assert kernel.compliance_bias < 0.2, "Подчинение не затухает при отсутствии давления"

    print("\n--- RESISTANCE RECOVERY TRACE ---")
    print(trace.print_lineage(trace.frames[-1].frame_id))
