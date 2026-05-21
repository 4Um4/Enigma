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
                # NPC dicts используют "id", не "npc_id" — проверяем оба ключа
                npc_id_val = n.get("npc_id") or n.get("id") or ""
                if target_ref in npc_name or target_ref in npc_id_val.lower():
                    target_id = npc_id_val
                    logger.info(f"[DIRECTIVE_RESOLVE] Resolved target_ref '{target_ref}' to ID '{target_id}'")
                    break
                    
        if not target_id:
            return []

        # 2. Находим цель в npc_states (если доступно)
        target_dict = next((n for n in npc_states if n.get("npc_id") == target_id or n.get("id") == target_id), None)
        if not target_dict:
            # S28: В player turn npc_states пуст. Используем fallback, т.к. ID уже известен.
            logger.info(f"[DIRECTIVE_NO_STATE] NPC {target_id} state not loaded, using base fear 0.1")
            target_dict = {"social_stats": {"fear_of_player": 0.1}}

        # 3. Вычисление AuthorityPressure (Внешняя сила волеизъявления)
        # ADR-057: Источник и контекст определяют давление, а не только "страх цели".
        # Чистый commitment (голос) — это шум без социальной поддержки, поэтому * 0.4.
        source_authority = max(
            payload.get("social_pressure", 0.0),
            payload.get("physical_force", 0.0),
            payload.get("commitment_level", 0.0) * 0.4
        )
        if source_authority == 0.0:
            source_authority = 0.1  # Минимальный фоллбэк

        # context_modifier: социальный контекст (MVP: наличие физической силы/оружия)
        context_modifier = 1.0
        if payload.get("physical_force", 0.0) > 0.3 or payload.get("social_pressure", 0.0) > 0.3:
            context_modifier = 1.5  # Угроза или статус усиливают авторитет

        authority_pressure = source_authority * context_modifier

        # 4. Вычисление Legitimacy (Внутренняя готовность цели)
        # Страх (принуждение) + доверие (авторитет). Это капстор на стороне цели.
        target_fear = target_dict.get("social_stats", {}).get("fear_of_player", 0.1)
        target_trust = target_dict.get("social_stats", {}).get("trust", 0.1)
        legitimacy = max(target_fear, target_trust / 100.0) # trust 0-100, fear 0-1
        
        # 5. Физика подчинения: AuthorityPressure и Legitimacy образуют два независимых вектора
        BASE_RECEPTIVITY = 0.3
        # Вектор 1: Истинное подчинение (проекция авторитета на страх/доверие)
        obedience_intensity = authority_pressure * legitimacy
        # Вектор 2: Вынужденная реакция на давление (даже без уважения приходится реагировать)
        irritation_intensity = authority_pressure * BASE_RECEPTIVITY * (1.0 - legitimacy)
        
        total_pressure = obedience_intensity + irritation_intensity
        # Легитимность пробивает порог -> истинное подчинение. Иначе -> раздраженная конфронтация.
        is_obedience = legitimacy > 0.1

        # 5.1 Генерация PsychologicalPressure (искривление пространства полезности)
        pressure = PsychologicalPressure(
            fear=obedience_intensity * 0.4, # Страх отказа
            dominance_shift=-total_pressure, # Подчинение доминированию
            directive_obedience=total_pressure # Давление подчинения
        )

        logger.warning(f"[DIRECTIVE_INTERPRET] Target={target_id}, Action={semantic_action}, TotalPressure={total_pressure:.2f}, Obedience={obedience_intensity:.2f}, Irritation={irritation_intensity:.2f}, is_obedience={is_obedience}")

        # 6. Конвертация давления в StateDeltas (для StateApplicator)
        if is_obedience:
            # Вектор ПОДЧИНЕНИЯ: страх/уважение пробили порог легитимности
            emotion_delta = StateDeltas(
                npc_id=target_id,
                domain=DeltaDomain.EMOTION,
                payload=EmotionPayload(
                    stress_delta=total_pressure * 20.0,
                    emotion_tag="submissive_fear" if total_pressure > 0.6 else "unease"
                ),
                source="directive_interpretation"
            )
            
            social_delta = StateDeltas(
                npc_id=target_id,
                domain=DeltaDomain.SOCIAL,
                payload=SocialPayload(
                    fear_delta=total_pressure * 10.0 # Увеличиваем страх перед источником
                ),
                source="directive_interpretation"
            )
        else:
            # Вектор РАЗДРАЖЕНИЯ: давление заставляет реагировать, но без уважения
            # Вор подходит, чтобы послать игрока, а не чтобы подчиняться
            emotion_delta = StateDeltas(
                npc_id=target_id,
                domain=DeltaDomain.EMOTION,
                payload=EmotionPayload(
                    stress_delta=total_pressure * 10.0,
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
        if is_obedience:
            # Вектор ПОДЧИНЕНИЯ: подавление агрессии, смещение к approach
            identity_delta = StateDeltas(
                npc_id=target_id,
                domain=DeltaDomain.IDENTITY,
                payload=IdentityPayload(
                    aggression_inhibition_delta=total_pressure * 0.6,  # Подавление агрессии
                    compliance_bias_delta=total_pressure * 0.5,       # Смещение к подчинению/approach
                    initiative_suppression_delta=total_pressure * 0.05,
                    recent_directive_data={
                        "source": getattr(event, 'source', event.payload.get('source', 'player')),
                        "salience": total_pressure,
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
                    aggression_inhibition_delta=total_pressure * 0.3, # Слабый контроль гнева
                    compliance_bias_delta=total_pressure * 0.5,       # Идёт, чтобы высказать/конфронтировать
                    initiative_suppression_delta=0.0,
                    recent_directive_data={
                        "source": getattr(event, 'source', event.payload.get('source', 'player')),
                        "salience": total_pressure,
                        "interrupts_routine": True, # Прерывает бытовуху, чтобы отреагировать
                        "is_obedience": False
                    }
                ),
                source="directive_interpretation"
            )
        
        return [emotion_delta, social_delta, identity_delta]