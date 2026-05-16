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
from app.models.delta_payloads import EmotionPayload, SocialPayload, IdentityPayload
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

        # S28: Резолв цели. Если ID нет, ищем по имени из target_reference
        target_ref = payload.get("target_reference", "").lower()
        if not target_id and target_ref:
            for n in npc_states:
                npc_name = n.get("name", "").lower()
                npc_id = n.get("npc_id", "").lower()
                if target_ref in npc_name or target_ref in npc_id:
                    target_id = n.get("npc_id")
                    logger.info(f"[DIRECTIVE_RESOLVE] Resolved target_ref '{target_ref}' to ID '{target_id}'")
                    break
                    
        if not target_id:
            return []

        # 2. Находим цель в npc_states (если доступно)
        target_dict = next((n for n in npc_states if n.get("npc_id") == target_id), None)
        if not target_dict:
            # S28: В player turn npc_states пуст. Используем fallback, т.к. ID уже известен.
            logger.info(f"[DIRECTIVE_NO_STATE] NPC {target_id} state not loaded, using base fear 0.1")
            target_dict = {"social_stats": {"fear_of_player": 0.1}}

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
        
        # S28: Топологический отклик (деформация пространства решений)
        identity_delta = StateDeltas(
            npc_id=target_id,
            domain=DeltaDomain.IDENTITY,
            payload=IdentityPayload(
                aggression_inhibition_delta=obedience_intensity * 0.6,  # Подавление агрессии
                compliance_bias_delta=obedience_intensity * 0.5,       # Смещение к подчинению/approach
                initiative_suppression_delta=obedience_intensity * 0.05, # Легкое торможение (инерция), НЕ паралич
                # ADR-056: Attention Capture — прерывает routine, повышает salience
                recent_directive_data={
                    "source": event.source,
                    "salience": obedience_intensity,
                    "interrupts_routine": True
                }
            ),
            source="directive_interpretation"
        )
        
        return [emotion_delta, social_delta, identity_delta]

        return [emotion_delta, social_delta]