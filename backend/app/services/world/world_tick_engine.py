# backend/app/services/world/world_tick_engine.py
"""
Фаза 3.4 — WorldTickEngine: проактивный цикл NPC между ходами игрока.

Принципы:
  - Вызывается из game_loop после обработки действия игрока.
  - Для каждого major NPC в локации: DecisionHub(event_type="world_tick").
  - LLM НЕ участвует. Только Python.
  - Результат: список ProactiveDecision для внедрения в SceneOutcome.
  - NPC может: блокировать путь, искать союзника, предложить работу,
    распространить слух, позвать на помощь, сменить роль.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.constants import (
    MIN_PROACTIVE_SCORE,
    PROACTIVE_INTENT_PENALTY,
    WORLD_TICK_EVERY_TURNS,
)
from app.models.npc_state import Intent, NPCStateL2, WillState
from app.models.npc_profile import NPCProfileL0
from app.services.events.event_types import EventType

logger = logging.getLogger(__name__)


@dataclass
class ProactiveDecision:
    """Результат проактивного решения NPC."""
    npc_id: str
    intent: Intent
    intent_target: Optional[str]
    score: float
    reason: str                     # для debug/tracing
    deltas_dict: Dict[str, Any]     # дельты для StateApplicator


@dataclass
class WorldTickResult:
    """Результат полного тика мира."""
    triggered: bool
    tick_number: int
    decisions: List[ProactiveDecision]
    events: List[dict]              # события для EventBus/SceneContinuity


class WorldTickEngine:
    """
    Движок проактивных действий NPC.

    Контракт:
    - НЕ пишет состояние напрямую.
    - Возвращает список ProactiveDecision.
    - Вызывающий (game_loop) решает: применять ли, публиковать ли события.
    - DecisionHub вызывается с event_type=WORLD_TICK.
    """

    def __init__(self) -> None:
        self._turn_counter: Dict[str, int] = {}  # campaign_id → turn count

    def should_tick(self, campaign_id: str) -> bool:
        """Проверяет, пора ли запускать проактивный тик."""
        current = self._turn_counter.get(campaign_id, 0) + 1
        self._turn_counter[campaign_id] = current
        return current % WORLD_TICK_EVERY_TURNS == 0

    def get_tick_number(self, campaign_id: str) -> int:
        return self._turn_counter.get(campaign_id, 0)

    def compute_proactive_decisions(
        self,
        campaign_id: str,
        location: str,
        npc_data: List[Tuple[str, NPCStateL2, NPCProfileL0]],
        scene_state: Dict[str, Any],
        social_modifiers: Optional[Dict[str, Dict[str, float]]] = None,
        reputation_modifiers: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> WorldTickResult:
        """
        Вычисляет проактивные решения для всех major NPC в локации.

        npc_data: список (npc_id, state_l2, profile_l0) — только major NPC.
        social_modifiers: {npc_id: {intent: modifier}} от SocialEngine.
        reputation_modifiers: {npc_id: {intent: modifier}} от ReputationEngine.
        """
        from app.services.npc.decision_hub import DecisionHub, EventContext as HubEventContext

        tick_num = self.get_tick_number(campaign_id)
        decisions: List[ProactiveDecision] = []
        events: List[dict] = []

        hub = DecisionHub()

        # Множество проактивных интентов — только они учитываются из world_tick
        proactive_intents: set = {
            Intent.BLOCK_PATH, Intent.AMBUSH, Intent.SEEK_ALLY,
            Intent.OFFER_JOB, Intent.REQUEST_SERVICE, Intent.SPREAD_RUMOR,
            Intent.CALL_FOR_HELP, Intent.CHANGE_ROLE,
        }

        for npc_id, state_l2, profile_l0 in npc_data:
            # Пропускаем: мёртвых, сломанных
            if state_l2.hp <= 0:
                continue
            if state_l2.will_state == WillState.BROKEN:
                continue

            # Формируем EventContext для world_tick
            tick_event = HubEventContext(
                event_type=EventType.WORLD_TICK,
                actor_id=npc_id,
                success=True,
                intensity=0.3,  # низкая — нет внешнего стимула
                distance=0.0,
                witness_count=0,
                location=location,
                scene_flags=set(scene_state.get("active_flags", [])),
                scene_facts=[],
            )

            # Собираем модификаторы из SocialEngine + ReputationEngine
            npc_social = (social_modifiers or {}).get(npc_id, {})
            npc_reputation = (reputation_modifiers or {}).get(npc_id, {})
            combined = {**npc_social, **npc_reputation}

            try:
                result = hub.compute(
                    state=state_l2,
                    personality=profile_l0,
                    event=tick_event,
                    scene_state=scene_state,
                    social_modifiers=combined if combined else None,
                )

                # Только проактивные интенты проходят
                if result.intent not in proactive_intents:
                    continue

                effective_score = result.score - PROACTIVE_INTENT_PENALTY

                if effective_score >= MIN_PROACTIVE_SCORE:
                    decision = ProactiveDecision(
                        npc_id=npc_id,
                        intent=result.intent,
                        intent_target=result.intent_target,
                        score=effective_score,
                        reason=f"world_tick#{tick_num}: {result.intent.value} (raw={result.score:.3f})",
                        deltas_dict={
                            "stress_delta": result.deltas.stress_delta,
                            "emotion_tag": result.deltas.emotion_tag,
                        },
                    )
                    decisions.append(decision)

                    events.append({
                        "type": "proactive_action",
                        "npc_id": npc_id,
                        "intent": result.intent.value,
                        "target": result.intent_target,
                        "score": effective_score,
                    })

                    logger.info(
                        f"[WORLD_TICK] {npc_id}: {result.intent.value} "
                        f"(score={effective_score:.3f}, target={result.intent_target})"
                    )

            except Exception as e:
                logger.warning(f"[WORLD_TICK] Error for {npc_id}: {e}")
                continue

        return WorldTickResult(
            triggered=True,
            tick_number=tick_num,
            decisions=decisions,
            events=events,
        )