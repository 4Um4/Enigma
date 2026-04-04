# backend/app/services/npc/state_applicator.py
"""
R2.3 — StateApplicator: единственный модуль с правом записи в NPCState.

Принципы:
  - DecisionHub возвращает DecisionResult (read-only)
  - StateApplicator применяет его атомарно — всё или ничего
  - Если применение падает — NPCState не тронут (старые данные целы)
  - RelationshipStore обновляется здесь, а не в DecisionHub
  - python_engines.py подключается через NPCStateAdapter (инкрементально)
"""

from __future__ import annotations

import copy
import logging
from typing import Optional

from app.services.npc.npc_state import (
    EmotionTag,
    Intent,
    NPCPersonality,
    NPCState,
    NarrativeFact,
    WillState,
)
from app.services.npc.decision_hub import DecisionResult, StateDeltas
from app.services.memory.relationship_store import RelationshipStore

logger = logging.getLogger(__name__)

# Максимальное количество NarrativeFacts в кэше одного NPC
_MAX_NARRATIVE_CACHE = 10

# Порог стресса для перехода в will_state=BROKEN
_STRESS_BROKEN_THRESHOLD = 80.0

# Скорость decay active_traits за тик (умножается на strength)
_TRAIT_DECAY_RATE = 0.05


class StateApplicator:
    """
    Атомарно применяет DecisionResult к NPCState.

    Контракт:
      - на вход: текущий NPCState (неизменённый) + DecisionResult
      - на выход: новый NPCState (старый не мутируется)
      - при ошибке: возвращает оригинальный NPCState без изменений
    """

    def __init__(self, relationship_store: RelationshipStore) -> None:
        self._rel_store = relationship_store

    def apply(
        self,
        state:        NPCState,
        result:       DecisionResult,
        campaign_id:  str,
        current_tick: int = 0,
    ) -> NPCState:
        """
        Применяет DecisionResult атомарно.
        Возвращает новый NPCState — оригинал не мутируется.
        """
        # Глубокая копия — атомарность через замену целиком
        new_state = copy.deepcopy(state)

        try:
            self._apply_intent(new_state, result, current_tick)
            self._apply_deltas(new_state, result.deltas, campaign_id)
            self._apply_narrative(new_state, result.narrative_fact)
            self._apply_will_break(new_state)
            self._apply_trait_decay(new_state)
            return new_state

        except Exception as e:
            # Если что-то пошло не так — возвращаем оригинал нетронутым
            logger.error(
                f"[STATE_APPLICATOR] Ошибка применения для '{state.npc_id}': {e}. "
                f"Возвращаем оригинальный state."
            )
            return state

    def apply_tick_recovery(
        self,
        state:       NPCState,
        is_sleeping: bool = False,
    ) -> NPCState:
        """
        Восстановление стресса за тик — вызывается LifeEngine.
        Отдельный метод: не связан с DecisionResult.
        """
        new_state = copy.deepcopy(state)
        recovery = 15.0 if is_sleeping else 5.0
        new_state.stress = max(0.0, new_state.stress - recovery)
        return new_state

    # ─────────────────────────────────────────────────────────────────────────
    # Внутренние методы применения
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_intent(
        self,
        state:        NPCState,
        result:       DecisionResult,
        current_tick: int,
    ) -> None:
        """Обновляет intent с учётом инерции и счётчика duration."""
        new_intent = result.intent

        if state.intent == new_intent:
            # Intent не изменился — увеличиваем duration
            state.intent_duration += 1
        else:
            # Intent сменился — фиксируем момент смены
            state.intent           = new_intent
            state.intent_target    = result.intent_target
            state.intent_formed_at = current_tick
            state.intent_duration  = 0
            state.last_intent_change = current_tick

    def _apply_deltas(
        self,
        state:       NPCState,
        deltas:      StateDeltas,
        campaign_id: str,
    ) -> None:
        """Применяет числовые дельты к state и RelationshipStore."""
        # Стресс
        if deltas.stress_delta != 0.0:
            state.stress = max(0.0, min(100.0,
                state.stress + deltas.stress_delta
            ))

        # Эмоция
        if deltas.emotion_delta != 0.0:
            state.emotion_delta = max(-100.0, min(100.0,
                state.emotion_delta + deltas.emotion_delta
            ))
        if deltas.emotion_tag is not None:
            state.emotion = deltas.emotion_tag

        # Traits overlay
        for trait, value in deltas.trait_updates.items():
            state.active_traits[trait] = max(0.0, min(1.0, value))

        # Травма
        if deltas.new_trauma:
            state.trauma_markers.add(deltas.new_trauma)

        # Отношения — пишем в RelationshipStore, не в NPCState напрямую
        if deltas.trust_delta != 0.0 or deltas.fear_delta != 0.0:
            self._rel_store.update(
                campaign_id = campaign_id,
                source      = state.npc_id,
                target      = state.intent_target or "player",
                delta       = {
                    "trust": deltas.trust_delta,
                    "fear":  deltas.fear_delta,
                },
            )
            # Обновляем кэш в NPCState из свежих данных
            fresh = self._rel_store.get_pair(
                campaign_id, state.npc_id,
                state.intent_target or "player"
            )
            state.relationship_cache.update(fresh)

    def _apply_narrative(
        self,
        state:  NPCState,
        fact:   Optional[NarrativeFact],
    ) -> None:
        """
        Добавляет новый NarrativeFact в кэш.
        Хранит top-N по importance — старые вытесняются.
        """
        if fact is None:
            return

        current = list(state.narrative_cache)
        current.append(fact)

        # Сортируем по importance, оставляем top-N
        current.sort(key=lambda f: f.importance, reverse=True)
        state.narrative_cache = tuple(current[:_MAX_NARRATIVE_CACHE])

    def _apply_will_break(self, state: NPCState) -> None:
        """
        Проверяет порог стресса и меняет will_state если нужно.
        Дублирующая логика из psyche_engine.apply_stress — теперь здесь.
        """
        if (
            state.stress >= _STRESS_BROKEN_THRESHOLD
            and state.will_state == WillState.FREE
        ):
            state.will_state = WillState.BROKEN
            state.trauma_markers.add("will_broken")
            logger.info(
                f"[STATE_APPLICATOR] NPC '{state.npc_id}' сломан. "
                f"stress={state.stress:.1f} >= {_STRESS_BROKEN_THRESHOLD}"
            )

    def _apply_trait_decay(self, state: NPCState) -> None:
        """
        Decay active_traits к нулю каждый тик.
        Базовая personality не затронута — только overlay.
        Traits с strength < 0.01 удаляются.
        """
        to_remove = []
        for trait, strength in state.active_traits.items():
            new_strength = strength - _TRAIT_DECAY_RATE
            if new_strength < 0.01:
                to_remove.append(trait)
            else:
                state.active_traits[trait] = round(new_strength, 4)
        for trait in to_remove:
            del state.active_traits[trait]