# path: /project/backend/app/services/npc/disclosure_decision.py
# Назначение: M1/P5.1 — решающая функция: KNOWER → RECIPIENT disclosure.
#   Чистая; детерминированная; без LLM; без RNG; без player-центризма.
#   Пороги — V1_CALIBRATION_DEFAULTS (не игровые истины; Calibration Lab).
# Зависимости: app.domain.disclosure, app.models.npc_state, KnowledgeItem
# Основные сущности: decide_disclosure, V1_CALIBRATION_DEFAULTS

from __future__ import annotations

from app.domain.disclosure import (
    DisclosureContext,
    DisclosureLevel,
    DisclosureOutcome,
    SocialTarget,
)
from app.models.npc_state import NPCState
from app.services.npc.knowledge_retrieval import KnowledgeItem

# ── V1 Calibration Defaults (НЕ игровые истины) ──────────────────────────
# Мастер: пороги — calibration candidates; будущий владелец — Calibration
# Lab (ADR-O-361-паттерн). Значения выбраны консервативно для MVP-Таверны;
# пере-калибровка = правка этих констант (не кода логики).
V1_T_REVEAL = 50.0    # trust ≥ 50 → возможен REVEAL
V1_T_PARTIAL = 20.0   # trust ≥ 20 → возможен PARTIAL
V1_P_MIN = 2.0        # накопленное давление ≥ 2 → REVEAL/PARTIAL разблокированы
V1_S_HIGH = 70.0      # stress ≥ 70 → HINT (трещина)
V1_P_MAX = 5.0        # давление ≥ 5 → HINT (трещина от настойчивости)
V1_F_HIGH = 60.0      # fear ≥ 60 → REDIRECT (уход от темы)
V1_FRACTION_PARTIAL = 0.5  # доля канон-текста при PARTIAL


def decide_disclosure(
    source_npc: NPCState,
    recipient: SocialTarget,
    relationship: dict[str, float],
    item: KnowledgeItem,
    context: DisclosureContext,
) -> DisclosureOutcome:
    """Disclosure is a directed social decision between agents, not an
    NPC→Player mechanic (Мастер). Universal KNOWER → RECIPIENT.

    Чистая функция: одинаковые входы → одинаковый вердикт (A/A).
    Не мутирует source_npc/relationship/item (L-P4/L-P5-гварды).

    Пороговая лестница (первое совпадение = вердикт; детерминированная):
    1. REVEAL:   trust ≥ T_REVEAL ∧ pressure_amount ≥ P_MIN
    2. PARTIAL:  trust ≥ T_PARTIAL ∧ pressure_amount ≥ P_MIN
    3. HINT:     stress ≥ S_HIGH ∨ pressure_amount ≥ P_MAX
    4. REDIRECT: fear ≥ F_HIGH
    5. DENY:     иначе (default; знание не передаётся)
    """
    trust = relationship.get("trust", 0.0)
    fear = relationship.get("fear", 0.0)
    stress = source_npc.stress
    pressure = context.pressure_amount

    # 1. REVEAL: высокий trust + достаточное давление
    if trust >= V1_T_REVEAL and pressure >= V1_P_MIN:
        return DisclosureOutcome(
            level=DisclosureLevel.REVEAL,
            secret_id=item.secret_id,
            fraction=1.0,
        )

    # 2. PARTIAL: умеренный trust + достаточное давление
    if trust >= V1_T_PARTIAL and pressure >= V1_P_MIN:
        return DisclosureOutcome(
            level=DisclosureLevel.PARTIAL,
            secret_id=item.secret_id,
            fraction=V1_FRACTION_PARTIAL,
        )

    # 3. HINT: стресс-трещина или давление-трещина
    if stress >= V1_S_HIGH or pressure >= V1_P_MAX:
        return DisclosureOutcome(
            level=DisclosureLevel.HINT,
            secret_id=item.secret_id,
            fraction=0.0,
        )

    # 4. REDIRECT: страх → уход от темы
    if fear >= V1_F_HIGH:
        return DisclosureOutcome(
            level=DisclosureLevel.REDIRECT,
            secret_id=item.secret_id,
            fraction=0.0,
        )

    # 5. DENY: default — знание не передаётся
    return DisclosureOutcome(
        level=DisclosureLevel.DENY,
        secret_id=item.secret_id,
        fraction=0.0,
    )
