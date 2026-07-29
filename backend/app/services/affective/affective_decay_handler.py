"""
path: backend/app/services/affective/affective_decay_handler.py
Назначение: S74 — Непрерывное затухание аффективного интеграла (affective_load) и коллапс эмоции в idle-тиках.
Зависимости: app.models.state_delta, app.models.delta_payloads, app.services.affective.emotion_transition
Основные сущности: AffectiveDecayHandler


"""

import logging

logger = logging.getLogger(__name__)

from typing import Any, List

from app.models.delta_payloads import EmotionPayload
from app.models.state_delta import DeltaDomain, StateDeltas
from app.services.affective.emotion_transition import THRESHOLD_ANXIOUS


class AffectiveDecayHandler:
    """Phase 0.5: Непрерывное время психики (S74).

    Интеграл аффекта затухает каждый тик, даже если игрок бездействует.
    Если affective_load падает ниже порога тревоги, эмоция коллапсирует в neutral.
    Устраняет "замороженную психику" Франкенштейна.
    """

    name: str = "affective_decay"

    # Базовая скорость восстановления (совпадает с willpower=0.0 в affective_integrator)
    DEFAULT_RECOVERY_RATE = 0.05  # 5% за тик

    def handle(
        self,
        npcs: List[Any],  # List[NPCStateSnapshot]
        campaign_id: str,
        current_tick: int,
    ) -> List[StateDeltas]:
        """Чистая функция: экспоненциальное затухание аффекта + фазовый коллапс."""
        results: List[StateDeltas] = []

        # S73-DIAG: Видит ли handler живую психику?
        if npcs:
            _loads = [
                f"{n.get('npc_id')}:{n.get('affective_load', 0.0):.2f}/{n.get('emotion', '?')}"
                for n in npcs
                if n.get("npc_id") != "player"
            ]
            logger.debug(f"[AFF_DECAY] tick={current_tick} states={_loads}")

        for npc in npcs:
            npc_id = npc.get("npc_id", "")
            if not npc_id or npc_id == "player":
                continue

            load = npc.get("affective_load", 0.0)
            emotion = npc.get("emotion", "neutral")

            if load <= 0.0 and emotion == "neutral":
                continue

            # Шаг затухания интеграла
            # ADR-O-206: Физиологическое восстановление (пульс) стабильно.
            # Память (шрам) влияет на будущие реакции (через baseline в AffectiveIntegrator), а не на decay.
            new_load = max(0.0, load - self.DEFAULT_RECOVERY_RATE)

            # S73: Фазовый коллапс. Нагрузка упала — эмоция должна отвалиться.
            new_emotion = emotion
            if new_load < THRESHOLD_ANXIOUS and emotion != "neutral":
                new_emotion = "neutral"

            # Генерируем дельту, только если состояние изменилось
            if new_load != load or new_emotion != emotion:
                results.append(
                    StateDeltas(
                        npc_id=npc_id,
                        domain=DeltaDomain.EMOTION,
                        target="system",
                        payload=EmotionPayload(
                            # V8-PSY-13: stress не затухает здесь. Two-path design:
                            # stress восстанавливается через life_engine.recover_stress_tick
                            # с разными скоростями для спящих и бодрствующих.
                            stress_delta=0.0,
                            emotion_delta=0.0,
                            emotion_tag=new_emotion,
                            affective_load=new_load,
                        ),
                        source="affective_decay",
                    )
                )

        return results
