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
from app.models.npc_state import NPCStateL2  # алиас для NPCState (L2)
from app.core.constants import TRAIT_DECAY_RATE, NARRATIVE_CACHE_MAX

# Легаси-типы, используемые в логике (Enum'ы и контракты)
from app.models.npc_state import (
    EmotionTag,
    Intent,
    NarrativeFact,
    TemporaryDrive,
    WillState,
    MAX_ACTIVE_DRIVES,
    MAX_DRIVE_AGE,
)
from app.models.psychological import CausalEntry
from app.models.physical import (
    Condition,
    DamageType,
    PhysicalOutcome,
    ThreatAccumulator,
    Wound,
    WoundSeverity,
)
from app.models.event_resolution import StateChange
from app.services.npc.decision_hub import DecisionResult, StateDeltas
from app.services.npc.break_progress_engine import BreakDeltas
from app.services.npc.math_utils import apply_saturation
from app.services.memory.relationship_store import RelationshipStore

logger = logging.getLogger(__name__)

# Константы порогов удалены. Логика порогов перенесена в BreakProgressEngine.

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
            print(f"[STATE_APPLIED] {new_state.npc_id}: stress={new_state.stress:.1f} intent={new_state.intent}")
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


    def apply_physical(
        self,
        state: NPCStateL2,
        outcome: PhysicalOutcome,
        current_tick: int = 0,
    ) -> tuple[NPCStateL2, list[StateChange]]:
        """
        Применяет PhysicalOutcome к NPCState.
        Вызывается ДО DecisionHub — NPC видит изменённый мир.
        
        Returns:
            (new_state, state_changes) — стейт и список изменений для логов
        """
        from dataclasses import replace
        
        new_state = copy.deepcopy(state)
        state_changes: list[StateChange] = []
        
        if not outcome.hit:
            return new_state, state_changes
        
        try:
            # 1. HP
            old_hp = new_state.hp
            new_state.hp = max(0, new_state.hp - outcome.damage)
            state_changes.append(StateChange(
                target_id=new_state.npc_id,
                field="hp",
                delta=-outcome.damage,
                source=outcome.damage_type.value,
            ))
            
            # 2. Threat accumulation
            if outcome.attacker_id:
                new_state.threat_accumulator.add_threat(
                    outcome.attacker_id, float(outcome.damage)
                )
                state_changes.append(StateChange(
                    target_id=new_state.npc_id,
                    field=f"threat.{outcome.attacker_id}",
                    delta=float(outcome.damage),
                    source="attack",
                ))
            
            # 3. Conditions из damage type
            for cond_type in outcome.potential_conditions:
                # Не дублируем если уже есть
                if cond_type not in new_state.conditions:
                    severity = min(1.0, outcome.damage / 20.0)  # нормализация
                    duration = 3 if cond_type in ("bleeding",) else 1
                    decay = 0.05 if cond_type == "bleeding" else 0.1
                    new_state.conditions[cond_type] = Condition(
                        type=cond_type,
                        severity=round(severity, 4),
                        duration_ticks=duration,
                        decay_per_tick=decay,
                        tick_applied=current_tick,
                    )
                    state_changes.append(StateChange(
                        target_id=new_state.npc_id,
                        field=f"condition.{cond_type}",
                        delta=severity,
                        source=outcome.damage_type.value,
                    ))
            
            # 4. Wound check — при значительном уроне или крите
            wound = self._check_wound(outcome, new_state, current_tick)
            if wound:
                new_state.wounds.append(wound)
                state_changes.append(StateChange(
                    target_id=new_state.npc_id,
                    field=f"wound.{wound.body_part}",
                    delta=wound.severity.value,
                    source=outcome.damage_type.value,
                ))
            
            # 5. Posture change при тяжёлом ударе
            if outcome.damage >= 15 or (
                new_state.max_hp > 0 and new_state.hp < new_state.max_hp * 0.2
            ):
                new_state.posture = "prone"
            
            # 6. CausalLedger
            new_state.causal_ledger.append(CausalEntry(
                npc_id=new_state.npc_id,
                field="hp",
                delta=-outcome.damage,
                source=f"{outcome.damage_type.value}_from_{outcome.attacker_id}",
                tick=current_tick,
            ))
            if len(new_state.causal_ledger) > 20:
                new_state.causal_ledger = new_state.causal_ledger[-20:]
            
            print(
                f"[PHYSICAL] {new_state.npc_id}: hp {old_hp}→{new_state.hp} "
                f"({outcome.damage_type.value}), threats={len(new_state.threat_accumulator.sources)}, "
                f"wounds={len(new_state.wounds)}, conditions={list(new_state.conditions.keys())}"
            )
            
            return new_state, state_changes
            
        except Exception as e:
            logger.error(
                f"[STATE_APPLICATOR] apply_physical ошибка для '{state.npc_id}': {e}. "
                f"Возвращаем оригинальный state."
            )
            return state, state_changes
    
    def _check_wound(
        self,
        outcome: PhysicalOutcome,
        state: NPCState,
        tick: int,
    ) -> Optional[Wound]:
        """Проверяет необходимость создания wound."""
        if not outcome.hit or outcome.damage <= 0:
            return None
        
        # Критический удар → гарантированный wound
        if outcome.critical:
            severity = WoundSeverity.SEVERE
        elif outcome.damage >= 20:
            severity = WoundSeverity.SEVERE
        elif outcome.damage >= 10:
            severity = WoundSeverity.MODERATE
        else:
            severity = None
        
        if severity is None:
            return None
        
        # Persistent при тяжёлых ранах
        persistent = severity in (WoundSeverity.SEVERE, WoundSeverity.CRIPPLING)
        
        # Выбор части тела (упрощённый рандом)
        import random
        body_parts = ["head", "torso", "arm_left", "arm_right", "leg_left", "leg_right"]
        # Бланжинг лучше попадает в торс
        if outcome.damage_type == DamageType.BLUDGEONING:
            weights = [1, 3, 2, 2, 1, 1]
        elif outcome.damage_type == DamageType.PIERCING:
            weights = [2, 2, 1, 1, 1, 1]
        else:  # slashing
            weights = [1, 2, 2, 2, 1, 1]
        
        body_part = random.choices(body_parts, weights=weights, k=1)[0]
        
        heal_ticks = 0 if persistent else max(10, 50 - outcome.damage)
        
        return Wound(
            body_part=body_part,
            severity=severity,
            cause=f"{outcome.damage_type.value}_hit",
            tick_received=tick,
            persistent=persistent,
            heal_ticks=heal_ticks,
        )


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
            state.state_modifiers[trait] = max(0.0, min(1.0, value))

        # Травма
        if deltas.new_trauma:
            state.trauma_markers.add(deltas.new_trauma)

        # Causal Ledger — паспорт каждого изменения (Шаг 3)
        # Фаза 4-ROLE.2: emotional_impact для генерации TemporaryDrive
        _tick = getattr(state, "intent_formed_at", 0)
        _source = getattr(deltas, "source", "unknown")
        _new_entries: list = []

        if deltas.stress_delta != 0.0:
            _impact = min(1.0, abs(deltas.stress_delta_effective) / 20.0)
            _new_entries.append(CausalEntry(
                npc_id=state.npc_id, field="stress",
                delta=deltas.stress_delta_effective,
                source=_source, tick=_tick,
                emotional_impact=round(_impact, 4),
            ))
        if deltas.trust_delta != 0.0:
            # Негативное доверие эмоционально сильнее
            _threshold = 20.0 if deltas.trust_delta < 0 else 30.0
            _impact = min(1.0, abs(deltas.trust_delta) / _threshold)
            _new_entries.append(CausalEntry(
                npc_id=state.npc_id, field="trust",
                delta=deltas.trust_delta,
                source=_source, tick=_tick,
                emotional_impact=round(_impact, 4),
            ))
        if deltas.fear_delta != 0.0:
            _impact = min(1.0, abs(deltas.fear_delta) / 15.0)
            _new_entries.append(CausalEntry(
                npc_id=state.npc_id, field="fear",
                delta=deltas.fear_delta,
                source=_source, tick=_tick,
                emotional_impact=round(_impact, 4),
            ))

        state.causal_ledger.extend(_new_entries)
        if len(state.causal_ledger) > 20:
            state.causal_ledger = state.causal_ledger[-20:]

        # Фаза 4-ROLE.2: Генерация TemporaryDrive из сильных эмоциональных ударов
        _DRIVE_TYPE_MAP = {
            "player_attacks": "vengeance", "player_attack": "vengeance",
            "player_insults": "vengeance", "player_threatens": "desperation",
            "theft": "vengeance", "betrayal": "desperation",
            "help": "loyalty_surge", "saved_life": "loyalty_surge",
        }
        for _entry in _new_entries:
            if _entry.emotional_impact > 0.7:
                _drive_type = _DRIVE_TYPE_MAP.get(_entry.source)
                if _drive_type is None:
                    continue
                # Проверяем что такой drive ещё не активен (от того же источника)
                _existing = [d for d in state.temporary_drives
                             if d.drive_type == _drive_type and d.source_npc_id == _entry.source]
                if _existing:
                    continue
                _new_drive = TemporaryDrive(
                    drive_type=_drive_type,
                    urgency=round(_entry.emotional_impact, 4),
                    reason=f"{_entry.source}: {_entry.field}{_entry.delta:+.1f}",
                    source_npc_id=_entry.source,
                    tick_born=_tick,
                )
                state.temporary_drives.append(_new_drive)
                logger.info(
                    f"[DRIVE] {state.npc_id}: new {_drive_type} "
                    f"(urgency={_entry.emotional_impact:.2f}, src={_entry.source})"
                )
        # Cap: MAX_ACTIVE_DRIVES — FIFO удаление старых
        if len(state.temporary_drives) > MAX_ACTIVE_DRIVES:
            state.temporary_drives = state.temporary_drives[-MAX_ACTIVE_DRIVES:]

        # Отношения — пишем в RelationshipStore, не в NPCState напрямую
        if deltas.trust_delta != 0.0 or deltas.fear_delta != 0.0:
            if self._rel_store is not None:
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
        state.narrative_cache = tuple(current[:NARRATIVE_CACHE_MAX])


    def _apply_trait_decay(self, state: NPCState) -> None:
        """
        Decay state_modifiers к нулю каждый тик.
        Базовая personality не затронута — только overlay.
        Модификаторы с strength < 0.01 удаляются.
        """
        to_remove = []
        for trait, strength in state.state_modifiers.items():
            new_strength = strength - TRAIT_DECAY_RATE
            if new_strength < 0.01:
                to_remove.append(trait)
            else:
                state.state_modifiers[trait] = round(new_strength, 4)
        for trait in to_remove:
            del state.state_modifiers[trait]
