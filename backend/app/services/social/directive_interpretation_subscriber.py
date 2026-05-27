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
                    target_id = n.get("npc_id") or n.get("id")
                    logger.info(f"[DIRECTIVE_RESOLVE] Resolved target_ref '{target_ref}' to ID '{target_id}'")
                    break
                    
        if not target_id:
            return []

        # 2. Находим цель в npc_states (если доступно)
        target_dict = next((n for n in npc_states if (n.get("npc_id") or n.get("id")) == target_id), None)
        if not target_dict:
            # S28: В player turn npc_states пуст. Используем fallback, т.к. ID уже известен.
            logger.info(f"[DIRECTIVE_NO_STATE] NPC {target_id} state not loaded, using base fear 0.1")
            target_dict = {"social_stats": {"fear_of_player": 0.1}}

        # 3. Вычисление Social Interpretation (MVP: берем напрямую из social_pressure в payload)
        # В будущем: учет статуса, вооруженности, прошлого насилия
        # ADR-057: Агрегация силы приказа. social_pressure может быть 0.0,
        # но physical_force или commitment_level делают приказ значимым.
        base_social_force = max(
            payload.get("social_pressure", 0.0),
            payload.get("physical_force", 0.0),
            payload.get("commitment_level", 0.0)
        )
        if base_social_force == 0.0:
            base_social_force = 0.1  # Минимальный фоллбэк, чтобы не потерять событие

        # 4. Вычисление Psychological Cost of Refusal (Legitimacy Gate ADR-057)
        # Если NPC не боится и не доверяет — это не приказ, а раздражающая просьба.
        # ADR-005: social_stats.fear_of_player — динамическое, drives.fear — базовое (seed)
        target_fear = target_dict.get("social_stats", {}).get("fear_of_player", 0.0)
        if target_fear == 0.0:
            # Fallback на drives.fear — врождённая осторожность NPC
            target_fear = target_dict.get("drives", {}).get("fear", 0.1)
        target_trust = target_dict.get("social_stats", {}).get("trust", 0.0)
        if target_trust == 0.0:
            # Fallback на psyche.loyalty_true — базовая лояльность
            target_trust = float(target_dict.get("psyche", {}).get("loyalty_true", 0.0))
        
        # Легитимность: страх (принуждение) + доверие (авторитет)
        legitimacy = max(target_fear, target_trust / 100.0) # trust 0-100, fear 0-1
        
        # L1 BRIDGE: Professional Duty (MVP для compliance_bias).
        # Обслуживающий персонал обязан подчиняться запросам MOVE (подзыв).
        # В будущем заменяется на: npc.living.core.compliance_bias
        _archetype = str(target_dict.get("_archetype", "")).lower()
        _service_archetypes = {"maid", "tavern_keeper", "servant", "waiter", "bartender"}
        if semantic_action == "MOVE" and _archetype in _service_archetypes:
            legitimacy = max(legitimacy, 0.7)  # Высокая легитимность по долгу службы
        
        if legitimacy > 0.3:
            # Приказ или просьба от авторитета → Подчинение
            obedience_intensity = base_social_force * (0.5 + legitimacy)
        else:
            # Нет легитимности → Раздражение (Irritation). NPC не подчинится, а разозлится.
            obedience_intensity = 0.0
            irritation_intensity = base_social_force * 0.5

        # 5. Генерация PsychologicalPressure (искривление пространства полезности)
        pressure = PsychologicalPressure(
            fear=obedience_intensity * 0.4, # Страх отказа
            dominance_shift=-obedience_intensity, # Подчинение доминированию
            directive_obedience=obedience_intensity # Давление подчинения
        )

        logger.warning(f"[DIRECTIVE_INTERPRET] Target={target_id}, Action={semantic_action}, ObediencePressure={obedience_intensity:.2f}")

        # 6. Конвертация давления в StateDeltas (для StateApplicator)
        if obedience_intensity > 0:
            # Эмоциональный отклик (страх, стресс) — только при легитимности
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
        else:
            # Раздражение (Irritation) — нет легитимности, нет подчинения
            emotion_delta = StateDeltas(
                npc_id=target_id,
                domain=DeltaDomain.EMOTION,
                payload=EmotionPayload(
                    stress_delta=irritation_intensity * 10.0,
                    emotion_tag="annoyance"
                ),
                source="directive_interpretation"
            )
            social_delta = StateDeltas(
                npc_id=target_id,
                domain=DeltaDomain.SOCIAL,
                payload=SocialPayload(
                    fear_delta=0.0 # Не боится, а злится
                ),
                source="directive_interpretation"
            )
        
        # S28: Топологический отклик (деформация пространства решений)
        if obedience_intensity > 0:
            # Вектор ПОДЧИНЕНИЯ: подавление агрессии, смещение к approach
            identity_delta = StateDeltas(
                npc_id=target_id,
                domain=DeltaDomain.IDENTITY,
                payload=IdentityPayload(
                    aggression_inhibition_delta=obedience_intensity * 0.6,  # Подавление агрессии
                    compliance_bias_delta=obedience_intensity * 0.5,       # Смещение к подчинению/approach
                    initiative_suppression_delta=obedience_intensity * 0.05,
                    recent_directive_data={
                        "source": getattr(event, 'source', event.payload.get('source', 'player')),
                        "salience": obedience_intensity,
                        "interrupts_routine": True,
                        "is_obedience": True
                    }
                ),
                source="directive_interpretation"
            )
        else:
            # Вектор РАЗДРАЖЕНИЯ: неохотное подчинение для конфронтации
            # Вор подходит, чтобы послать игрока, а не чтобы подчиняться
            identity_delta = StateDeltas(
                npc_id=target_id,
                domain=DeltaDomain.IDENTITY,
                payload=IdentityPayload(
                    aggression_inhibition_delta=irritation_intensity * 0.2, # Слабый контроль гнева
                    compliance_bias_delta=irritation_intensity * 0.2,       # Слабое подталкивание к подходу (чтобы подойти и высказать)
                    initiative_suppression_delta=0.0,
                    recent_directive_data={
                        "source": getattr(event, 'source', event.payload.get('source', 'player')),
                        "salience": irritation_intensity,
                        "interrupts_routine": True, # Прерывает бытовуху, чтобы отреагировать
                        "is_obedience": False
                    }
                ),
                source="directive_interpretation"
            )
        
        return [emotion_delta, social_delta, identity_delta]