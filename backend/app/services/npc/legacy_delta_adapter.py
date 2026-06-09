# path: backend/app/services/npc/legacy_delta_adapter.py
# Назначение: Односторонний деградационный шлюз v2 → v1.
# Позволяет legacy-коду читать плоские дельты, пока он не будет мигрирован.
# Зависимости: app.models.state_delta
# Основные сущности: LegacyStateDeltaAdapter
"""
адаптер как независимый граничный слой.

TODO: по мере миграции legacy-кода на v2 постепенно удалять этот класс и его использования.
- Сначала мигрировать scene_outcome_builder на использование v2 дельт напрямую, так как он уже работает с v2 данными.
- Затем постепенно мигрировать npc_tick_pipeline, который сложнее, так как он глубоко интегрирован и может потребовать рефакторинга для поддержки v2 дельт.
- В процессе миграции добавлять логирование использования LegacyStateDeltaAdapter для отслеживания прогресса и выявления оставшихся мест, где он используется.
- После полной миграции удалить LegacyStateDeltaAdapter и все связанные с ним предупреждения в коде.
"""

import logging
from typing import List, Set, Union

from app.models.state_delta import StateDeltas, DeltaDomain, EmotionPayload, SocialPayload
from app.models.delta_payloads import PerceptionPayload

logger = logging.getLogger(__name__)


class LegacyStateDeltaAdapter:
    """
    Схлопывает v2 доменные дельты в плоский v1 объект.
    Используется ТОЛЬКО в legacy downstream (scene_outcome_builder, npc_tick_pipeline).
    Новый код НЕ должен использовать этот класс.
    """

    @staticmethod
    def collapse(deltas: Union[List[StateDeltas], StateDeltas]) -> StateDeltas:
        # Защита от старых тестов/легаси, которые ещё передают единичный объект
        if isinstance(deltas, StateDeltas):
            return deltas
            
        if not deltas:
            return StateDeltas()

        # Берём source и target из первой дельты для контекста
        source = deltas[0].source if deltas else "legacy_collapse"
        target = deltas[0].target if deltas else None
        
        collapsed = StateDeltas(source=source, intent_target=target)
        dropped_domains: Set[str] = set()

        for d in deltas:
            if d.domain == DeltaDomain.EMOTION and isinstance(d.payload, EmotionPayload):
                collapsed.stress_delta += d.payload.stress_delta
                collapsed.emotion_delta += d.payload.emotion_delta
                # В v1 эмоция перезаписывается (last-write-wins)
                if d.payload.emotion_tag:
                    collapsed.emotion_tag = d.payload.emotion_tag
                if d.payload.new_trauma:
                    collapsed.new_trauma = d.payload.new_trauma
            elif d.domain == DeltaDomain.SOCIAL and isinstance(d.payload, SocialPayload):
                collapsed.trust_delta += d.payload.trust_delta
                collapsed.fear_delta += d.payload.fear_delta
            elif d.domain == DeltaDomain.PERCEPTION and isinstance(d.payload, PerceptionPayload):
                # S72 / §ENIGMA-004: УБИТ глобальный коллапс Vacuum → stress.
                # Неопределённость теперь обрабатывается персонально через Affective Pipeline:
                #   PerceptionPayload.uncertainty_delta → PK.uncertainty → affective_load (× drives weight)
                #     → EmotionPayload.stress_delta
                # Конвертация uncertainty → stress_delta в обход личности = нарушение
                # Закона Эпистемического Демпфирования (Vacuum — транзиентный, не глобальный).
                pass  # PERCEPTION domain: PK обновляется через StateApplicator напрямую
            else:
                # Физиология, Идентичность, Репутация — теряются при коллапсе в v1
                domain_name = d.domain.value if d.domain else "UNKNOWN"
                dropped_domains.add(domain_name)

        if dropped_domains:
            logger.warning(
                f"[LEGACY_COLLAPSE_WARNING] Dropped domains in v2->v1 adapter: {dropped_domains}. "
                f"Consumer must be migrated to v2."
            )

        return collapsed