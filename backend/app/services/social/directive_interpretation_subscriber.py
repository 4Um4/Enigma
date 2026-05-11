# path: backend/app/services/social/directive_interpretation_subscriber.py
"""
Назначение: Трансформатор социальной воли в давление (ADR-036).
Вычисляет легитимность приказа, цену отказа и генерирует PsychologicalPressure.
НЕ ЗНАЕТ о MovementIntent. Искривляет только utility-space цели.
Зависимости: app.domain.events, app.models.cfrm
Основные сущности: DirectiveInterpretationSubscriber


TODO
"""

import logging
from typing import List, Optional
from app.domain.events import EventDTO
from app.models.cfrm import PsychologicalPressure
from app.models.delta_payloads import EmotionPayload, SocialPayload
from app.models.state_delta import StateDeltas, DeltaDomain

logger = logging.getLogger(__name__)

class DirectiveInterpretationSubscriber:
    """Интерпретирует речевые акты (приказы, угрозы) как социальное давление."""

    def handle(self, event: EventDTO, npc_states: List[dict]) -> List[StateDeltas]:
        """Обрабатывает событие речи игрока."""
        payload = event.payload
        semantic_action = payload.get("semantic_action")
        target_id = payload.get("target_id")
        
        # 1. Фильтр: работаем только с директивными речевыми актами
        if not semantic_action or semantic_action not in ("MOVE", "THREATEN", "PERSUADE", "GIVE"):
            return []
        if not target_id:
            return []

        # 2. Находим цель в npc_states
        target_dict = next((n for n in npc_states if n.get("npc_id") == target_id), None)
        if not target_dict:
            return []

        # 3. Вычисление Social Interpretation (MVP: берем напрямую из social_pressure в payload)
        # В будущем: учет статуса, вооруженности, прошлого насилия
        base_social_force = payload.get("social_pressure", 0.5)

        # 4. Вычисление Psychological Cost of Refusal (MVP: на основе страха цели)
        target_fear = target_dict.get("social_stats", {}).get("fear_of_player", 0.1)
        
        # Интенсивность давления = сила приказа * готовность подчиниться (страх)
        obedience_intensity = base_social_force * (0.5 + target_fear)

        # 5. Генерация PsychologicalPressure (искривление пространства полезности)
        pressure = PsychologicalPressure(
            fear=obedience_intensity * 0.4, # Страх отказа
            dominance_shift=-obedience_intensity, # Подчинение доминированию
            directive_obedience=obedience_intensity # Давление подчинения
        )

        logger.warning(f"[DIRECTIVE_INTERPRET] Target={target_id}, Action={semantic_action}, ObediencePressure={obedience_intensity:.2f}")

        # 6. Конвертация давления в StateDeltas (для StateApplicator)
        # Эмоциональный отклик (страх, стресс)
        emotion_delta = StateDeltas(
            npc_id=target_id,
            domain=DeltaDomain.EMOTION,
            payload=EmotionPayload(
                stress_delta=obedience_intensity * 20.0,
                emotion_tag="submissive_fear" if obedience_intensity > 0.6 else "unease"
            ),
            source="directive_interpretation"
        )
        
        # Социальный отклик (подчинение)
        social_delta = StateDeltas(
            npc_id=target_id,
            domain=DeltaDomain.SOCIAL,
            payload=SocialPayload(
                fear_delta=obedience_intensity * 10.0 # Увеличиваем страх перед источником
            ),
            source="directive_interpretation"
        )

        return [emotion_delta, social_delta]