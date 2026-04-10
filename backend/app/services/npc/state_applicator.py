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

# Целевая архитектура данных (L2)
from app.services.npc.npc_state import NPCStateL2  # алиас для NPCState (L2)

# Легаси-типы, используемые в логике (Enum'ы и контракты)
from app.services.npc.npc_state import (
    EmotionTag,
    Intent,
    NarrativeFact,
    WillState,
)
from app.services.npc.decision_hub import DecisionResult, StateDeltas
from app.services.npc.break_progress_engine import BreakDeltas
from app.services.npc.math_utils import apply_saturation
from app.services.memory.relationship_store import RelationshipStore

logger = logging.getLogger(__name__)

# Максимальное количество NarrativeFacts в кэше одного NPC
_MAX_NARRATIVE_CACHE = 10

# Константы порогов удалены. Логика порогов перенесена в BreakProgressEngine.

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
        state:        NPCStateL2,
        result:       DecisionResult,
        campaign_id:  str,
        current_tick: int = 0,
    ) -> NPCStateL2:
        """
        Применяет DecisionResult атомарно.
        Параметр personality УДАЛЁН — он уже использован в DecisionHub.
        Возвращает новый NPCState — оригинал не мутируется.
        """
        # Глубокая копия — атомарность через замену целиком
        new_state = copy.deepcopy(state)
        
        # Debug: проверяем что deepcopy не сломал объект
        if not hasattr(new_state, 'intent_duration'):
            print(f"[STATE_APPLICATOR] deepcopy сломал объект {state.npc_id}! type={type(new_state)}, attrs={list(vars(new_state).keys()) if hasattr(new_state, '__dict__') else 'no __dict__'}")
            return state

        try:
            self._apply_intent(new_state, result, current_tick)
            self._apply_progress(new_state, result.deltas)  # счётчик реального прогресса
            self._apply_deltas(new_state, result.deltas, campaign_id)
            self._apply_narrative(new_state, result.narrative_fact)

            # --- ИСПРАВЛЕНО: работаем с new_state и result.deltas ---
            d = result.deltas
            
            # Применяем психологические изменения (R6.1)
            new_state.identity_integrity = max(0.0, min(1.0, new_state.identity_integrity + d.identity_integrity_delta))
            new_state.pressure_resistance = max(0.0, min(2.0, new_state.pressure_resistance + d.pressure_resistance_delta))

            # Прямое переопределение воли (R6.4)
            if d.will_state_override:
                new_state.will_state = d.will_state_override
                if d.will_state_override == WillState.BROKEN:
                    new_state.trauma_markers.add("will_broken")

            self._apply_trait_decay(new_state)
            return new_state

        except Exception as e:
            # Если что-то пошло не так — возвращаем оригинал нетронутым
            logger.error(
                f"[STATE_APPLICATOR] Ошибка применения для '{state.npc_id}': {e}. "
                f"Возвращаем оригинальный state."
            )
            return state


    def apply_break(
        self,
        state:        NPCState,
        break_deltas: BreakDeltas,
        campaign_id:  str,
    ) -> NPCState:
        """
        Применяет дельты слома независимо от DecisionResult.
        Вызывается в python_engines ДО _decision_hub.compute() — для всех NPC,
        включая тех, на кого не направлено действие игрока.
        Атомарность: deepcopy + возврат оригинала при ошибке.
        """
        new_state = copy.deepcopy(state)
        try:
            new_state.identity_integrity = max(0.0, min(1.0,
                new_state.identity_integrity + break_deltas.identity_integrity_delta
            ))
            new_state.pressure_resistance = max(0.0, min(2.0,
                new_state.pressure_resistance + break_deltas.pressure_resistance_delta
            ))
            if break_deltas.will_state_override is not None:
                new_state.will_state = break_deltas.will_state_override
                if break_deltas.will_state_override == WillState.BROKEN:
                    new_state.trauma_markers.add("will_broken")
            return new_state
        except Exception as e:
            logger.error(
                f"[STATE_APPLICATOR] apply_break ошибка для '{state.npc_id}': {e}. "
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
            # Intent сменился — мягкий сброс: сохраняем 30% прогресса для цепочек
            state.intent           = new_intent
            state.intent_target    = result.intent_target
            state.intent_formed_at = current_tick
            state.intent_duration  = 0
            state.intent_progress_ticks = int(state.intent_progress_ticks * 0.3)
            state.last_intent_change = current_tick


    def _apply_progress(
        self,
        state:  NPCStateL2,
        deltas: "StateDeltas",
    ) -> None:
        """
        Обновляет счётчик тиков реального прогресса.
        Прогресс = значимое изменение мира (отношения, психика, черты).
        Стресс не считается — он шум, а не результат.
        """
        has_progress = (
            abs(deltas.trust_delta) > 0.01
            or abs(deltas.fear_delta) > 0.01
            or abs(deltas.identity_integrity_delta) > 0.01
            or bool(deltas.trait_updates)
        )
        if has_progress:
            # Потолок: прогресс не может превышать duration
            state.intent_progress_ticks = min(
                state.intent_progress_ticks + 1,
                state.intent_duration,
            )


    def _apply_deltas(
        self,
        state:       NPCState,
        deltas:      StateDeltas,
        campaign_id: str,
    ) -> None:
        """Применяет числовые дельты к state и RelationshipStore."""
        # Стресс
        if deltas.stress_delta != 0.0:
            old = state.stress
            state.stress, effective = apply_saturation(
                current=old,
                delta=deltas.stress_delta,
                min_val=0.0,
                max_val=100.0,
            )
            deltas.stress_delta_effective = effective
            logger.debug(
                f"[APPLY] {state.npc_id}: stress {old:.1f} → {state.stress:.1f} "
                f"(wanted {deltas.stress_delta:+.1f}, applied {effective:+.1f})"
            )

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
