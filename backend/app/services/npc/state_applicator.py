from __future__ import annotations

# backend/app/services/npc/state_applicator.py
"""
R2.3 — StateApplicator: единственный модуль с правом записи в NPCState.

Назначение: атомарно применять изменения к NPCState на основе DecisionResult.
Контракт:   - на вход: текущий NPCState (неизменённый) + DecisionResult
            - на выход: новый NPCState (старый не мутируется)
            - при ошибке: возвращает оригинальный NPCState без изменений

Принципы:
  - DecisionHub возвращает DecisionResult (read-only)
  - StateApplicator применяет его атомарно — всё или ничего
  - Если применение падает — NPCState не тронут (старые данные целы)
  - RelationshipStore обновляется здесь, а не в DecisionHub
  - python_engines.py подключается через NPCStateAdapter (инкрементально)

(ProactiveDecision.deltas_dict мигрировано в StateDeltas)
"""


import copy
import logging
from dataclasses import asdict
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.npc.resolution_engine import ResolutionOutcome

from app.core.constants import TRAIT_DECAY_RATE
from app.domain.vital_state import LifeStatus, evaluate_vital_state
from app.models.delta_payloads import (
    EconomicPayload,
    EmotionPayload,
    IdentityPayload,
    PerceptionPayload,
    PhysiologyPayload,
    SocialPayload,
    WillConflictPayload,
)
from app.models.event_resolution import StateChange

# Целевая архитектура данных (L2)
# Легаси-типы, используемые в логике (Enum'ы и контракты)
from app.models.npc_state import (
    MAX_ACTIVE_DRIVES,
    NPCState,
    TemporaryDrive,
    WillState,
)
from app.models.physical import (
    Condition,
    DamageType,
    PhysicalOutcome,
    Wound,
    WoundSeverity,
)
from app.models.psychological import CausalEntry
from app.models.state_delta import DeltaDomain, StateDeltas
from app.services.memory.relationship_store import RelationshipStore
from app.services.npc.decision_hub import DecisionResult
from app.services.npc.kernel_rng import KernelRNG
from app.services.npc.math_utils import apply_saturation
from app.services.npc.legacy_delta_adapter import LegacyStateDeltaAdapter

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

    def __init__(
        self,
        relationship_store: RelationshipStore,
        reputation_engine: Any = None,
        l1_chronicle: Optional[Any] = None, # V8-PSY-1 FIX
    ) -> None:
        self._rel_store = relationship_store
        # ReputationEngine — опциональная зависимость (DI)
        self._reputation_engine = reputation_engine
        self._l1_chronicle = l1_chronicle # V8-PSY-1 FIX

    def update_relationships(
        self,
        state: NPCState,
        campaign_id: str,
        target_id: str,
        trust_delta: float = 0.0,
        fear_delta: float = 0.0,
        debt_delta: float = 0.0,
    ) -> None:
        """Stage 0 Task 0.7: Единственный write-API для RelationshipStore.
        Обновляет SSOT и синхронно обновляет read-cache (state.relationship_cache).
        """
        _delta = {}
        if trust_delta != 0.0:
            _delta["trust"] = trust_delta
        if fear_delta != 0.0:
            _delta["fear"] = fear_delta
        if debt_delta != 0.0:
            _delta["debt"] = debt_delta
            
        if not _delta:
            return

        self._rel_store.update(
            campaign_id=campaign_id,
            source=state.npc_id,
            target=target_id,
            delta=_delta,
        )
        # P1 ARCH: Заполнение read-cache из SSOT (RelationshipStore).
        # Мутация допустима только как проекция из единственного владельца.
        fresh = self._rel_store.get_pair(campaign_id, state.npc_id, target_id)
        state.relationship_cache.setdefault(target_id, {}).update(fresh)

    def apply(
        self,
        state: NPCState,
        result: DecisionResult,
        campaign_id: str,
        current_tick: int = 0,
        resolution_outcome: Optional["ResolutionOutcome"] = None,
    ) -> NPCState:
        """
        Применяет DecisionResult атомарно.
        Параметр personality УДАЛЁН — он уже использован в DecisionHub.
        Возвращает новый NPCState — оригинал не мутируется.
        
        resolution_outcome: Спящее поле для ResolutionEngine (Фаза 2). 
        None = детерминированный путь (Фаза 0/1).
        """
        # Глубокая копия — атомарность через замену целиком
        new_state = copy.deepcopy(state)

        # Debug: проверяем что deepcopy не сломал объект
        if not hasattr(new_state, "intent_duration"):
            logger.debug(
                f"[STATE_APPLICATOR] deepcopy сломал объект {state.npc_id}! type={type(new_state)}, attrs={list(vars(new_state).keys()) if hasattr(new_state, '__dict__') else 'no __dict__'}"
            )
            return state

        try:
            self._apply_intent(new_state, result, current_tick)

            # ADR-039: Перехватываем WillConflictPayload до коллапса в v1, чтобы не потерять его
            will_conflict_for_ui = None
            for d in result.deltas:
                if d.domain == DeltaDomain.WILL and isinstance(
                    d.payload, WillConflictPayload
                ):
                    will_conflict_for_ui = d.payload
                    break

            # ADR-013: Схлопываем v2 -> v1 для легаси-методов StateApplicator.
            # В будущем StateApplicator.apply() должен нативно итерировать List[StateDeltas].
            _legacy_deltas = LegacyStateDeltaAdapter.collapse(result.deltas)

            self._apply_progress(
                new_state, _legacy_deltas
            )  # счётчик реального прогресса
            self._apply_deltas(new_state, _legacy_deltas, campaign_id)

            # --- ИСПРАВЛЕНО: работаем с new_state и result.deltas ---
            d = _legacy_deltas
            _l1_events: list[Any] = []  # C7 FIX: Инициализация списка для L1 событий

            # Применяем психологические изменения (R6.1)
            new_state.identity_integrity = max(
                0.0, min(1.0, new_state.identity_integrity + d.identity_integrity_delta)
            )
            new_state.pressure_resistance = max(
                0.0,
                min(2.0, new_state.pressure_resistance + d.pressure_resistance_delta),
            )

            # ADR-O-208: L3 (EffectiveDrives) строго эфемерна.
            # Кэширование drives_runtime через StateApplicator ЗАПРЕЩЕНО.
            # Убраны d.drives_snapshot и d.strain_snapshot (их нет в StateDeltas).

            # SHI-FIX COMMAND: Применяем IdentityPayload (compliance_bias, recent_directive)
            # к PerceptualKernel. Обрабатываем оригинальные deltas до коллапса в v1.
            from app.models.delta_payloads import IdentityPayload

            # FIX: Убран локальный импорт DeltaDomain, который вызывал UnboundLocalError.
            # Глобальный импорт в начале файла уже присутствует.
            for _orig_delta in result.deltas:
                if _orig_delta.domain == DeltaDomain.IDENTITY and isinstance(
                    _orig_delta.payload, IdentityPayload
                ):
                    if (
                        hasattr(new_state, "perceptual_kernel")
                        and new_state.perceptual_kernel
                    ):
                        _pk = new_state.perceptual_kernel
                        _pk.compliance_bias = max(
                            -1.0,
                            min(
                                1.0,
                                _pk.compliance_bias
                                + getattr(
                                    _orig_delta.payload, "compliance_bias_delta", 0.0
                                ),
                            ),
                        )
                        _pk.aggression_inhibition = max(
                            -1.0,
                            min(
                                1.0,
                                _pk.aggression_inhibition
                                + getattr(
                                    _orig_delta.payload,
                                    "aggression_inhibition_delta",
                                    0.0,
                                ),
                            ),
                        )
                        _pk.initiative_suppression = max(
                            -1.0,
                            min(
                                1.0,
                                _pk.initiative_suppression
                                + getattr(
                                    _orig_delta.payload,
                                    "initiative_suppression_delta",
                                    0.0,
                                ),
                            ),
                        )
                        if getattr(_orig_delta.payload, "recent_directive_data", None):  # noqa: ENIGMA002
                            _pk.recent_directive = (
                                _orig_delta.payload.recent_directive_data
                            )

            # Прямое переопределение воли (R6.4)
            if d.will_state_override:
                new_state.will_state = d.will_state_override
                if d.will_state_override == WillState.BROKEN:
                    new_state.trauma_markers.add("will_broken")

                    # ADR-O-208: L1 Event Sourced Identity.
                    # Слом воли больше не мутирует драйвы напрямую (убийство вандала).
                    # Он генерирует событие деформации L1, которое DriveResolver
                    # интегрирует в проекцию личности на следующем шаге.
                    from app.domain.identity_events import TraitDriftEvent

                    _l1_events.append(
                        TraitDriftEvent(
                            target_id=new_state.npc_id,
                            source_id="will_break_system",
                            effect_value=-0.15,
                            tick_id=0,  # Tick будет проставлен Orchestratorом при коммите в L1EventStream
                            event_type="will_break",
                        )
                    )

            self._apply_trait_decay(new_state)

            # ADR-039: Записываем конфликт Волы в raw dict, чтобы AvatarPresentationAssembler его увидел
            if will_conflict_for_ui and new_state.npc_id == "player":
                self._apply_delta_to_raw(
                    {
                        "npc_id": "player",
                        "will_conflict_data": {
                            "resistance": will_conflict_for_ui.resistance,
                            "embodied_vector": will_conflict_for_ui.embodied_vector,
                        },
                    },
                    StateDeltas(
                        npc_id="player",
                        domain=DeltaDomain.WILL,
                        target="player",
                        payload=will_conflict_for_ui,
                    ),
                    campaign_id,
                )

            logger.info(
                f"[STATE_APPLIED] {new_state.npc_id}: stress={new_state.stress:.1f} intent={new_state.intent}"
            )
            return new_state

        except Exception as e:
            # H-29 FIX: Не маскируем ошибку, пробрасываем выше (ADR-O-308).
            logger.error(
                f"[STATE_APPLICATOR] Ошибка применения для '{state.npc_id}': {e}. "
                f"Пробрасываем исключение.",
                exc_info=True,
            )
            raise

    def apply_physical(
        self,
        state: NPCState,
        outcome: PhysicalOutcome,
        current_tick: int = 0,
    ) -> tuple[NPCState, list[StateChange]]:
        """
        Применяет PhysicalOutcome к NPCState.
        Вызывается ДО DecisionHub — NPC видит изменённый мир.

        Returns:
            (new_state, state_changes) — стейт и список изменений для логов
        """

        new_state = copy.deepcopy(state)
        state_changes: list[StateChange] = []

        if not outcome.hit:
            return new_state, state_changes

        try:
            # 1. HP
            # ADR-HP-UNIFICATION: пишем в body_state, не в deprecated hp поле.
            old_hp = new_state.effective_hp
            _max_hp = new_state.effective_max_hp
            _new_hp = max(0.0, old_hp - outcome.damage)
            if not new_state.body_state:
                new_state.body_state = {"current_hp": _max_hp, "max_hp": _max_hp}
            new_state.body_state["current_hp"] = min(_max_hp, _new_hp)
            # Sync deprecated поле для обратной совместимости
            # ADR-HP-UNIFICATION: Пишем напрямую в body_state (SSOT)
            if new_state.body_state:
                new_state.body_state["current_hp"] = int(_new_hp)
            state_changes.append(
                StateChange(
                    target_id=new_state.npc_id,
                    field="hp",
                    delta=-outcome.damage,
                    source=outcome.damage_type.value,
                )
            )

            # 2. Threat accumulation
            if outcome.attacker_id:
                new_state.threat_accumulator.add_threat(
                    outcome.attacker_id, float(outcome.damage)
                )
                state_changes.append(
                    StateChange(
                        target_id=new_state.npc_id,
                        field=f"threat.{outcome.attacker_id}",
                        delta=float(outcome.damage),
                        source="attack",
                    )
                )

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
                    state_changes.append(
                        StateChange(
                            target_id=new_state.npc_id,
                            field=f"condition.{cond_type}",
                            delta=severity,
                            source=outcome.damage_type.value,
                        )
                    )

            # 4. Wound check — при значительном уроне или крите
            # KERNEL-ISOLATION: передаём deterministic rng.
            from app.services.npc.kernel_rng import KernelRNG

            _wound_rng = KernelRNG(
                tick=current_tick, npc_id=new_state.npc_id, salt="wound_gen"
            )
            wound = self._check_wound(outcome, new_state, current_tick, rng=_wound_rng)
            if wound:
                new_state.wounds.append(wound)
                state_changes.append(
                    StateChange(
                        target_id=new_state.npc_id,
                        field=f"wound.{wound.body_part}",
                        delta=float(wound.severity.value),
                        source=outcome.damage_type.value,
                    )
                )

            # 5. Posture change при тяжёлом ударе
            if outcome.damage >= 15 or (
                new_state.effective_max_hp > 0
                and new_state.effective_hp < new_state.effective_max_hp * 0.2
            ):
                new_state.posture = "prone"

            # 6. CausalLedger
            new_state.causal_ledger.append(
                CausalEntry(
                    npc_id=new_state.npc_id,
                    field="hp",
                    delta=-outcome.damage,
                    source=f"{outcome.damage_type.value}_from_{outcome.attacker_id}",
                    tick=current_tick,
                )
            )
            if len(new_state.causal_ledger) > 20:
                new_state.causal_ledger = new_state.causal_ledger[-20:]

            logger.debug(
                f"[PHYSICAL] {new_state.npc_id}: hp {old_hp}→{new_state.effective_hp} "
                f"({outcome.damage_type.value}), threats={len(new_state.threat_accumulator.sources)}, "
                f"wounds={len(new_state.wounds)}, conditions={list(new_state.conditions.keys())}"
            )

            return new_state, state_changes

        except Exception as e:
            # H-29 FIX: Не маскируем ошибку, пробрасываем выше (ADR-O-308).
            logger.error(
                f"[STATE_APPLICATOR] apply_physical ошибка для '{state.npc_id}': {e}. "
                f"Пробрасываем исключение."
            )
            raise

    def _check_wound(
        self,
        outcome: PhysicalOutcome,
        state: NPCState,
        tick: int,
        rng: Optional[KernelRNG] = None,
    ) -> Optional[Wound]:
        """Проверяет необходимость создания wound.

        KERNEL-ISOLATION: rng must be provided for replay determinism.
        """
        from app.services.npc.kernel_rng import KernelRNG

        if rng is None:
            rng = KernelRNG(tick=tick, npc_id=state.npc_id, salt="wound_gen")
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
        # KERNEL-ISOLATION: deterministic RNG вместо global random.
        body_parts = ["head", "torso", "arm_left", "arm_right", "leg_left", "leg_right"]
        # Бланжинг лучше попадает в торс
        if outcome.damage_type == DamageType.BLUDGEONING:
            weights = [1, 3, 2, 2, 1, 1]
        elif outcome.damage_type == DamageType.PIERCING:
            weights = [2, 2, 1, 1, 1, 1]
        else:  # slashing
            weights = [1, 2, 2, 2, 1, 1]

        body_part = rng.choices(body_parts, weights=weights, k=1)[0]

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
        state: NPCState,
        is_sleeping: bool = False,
    ) -> NPCState:
        """
        Восстановление стресса за тик — вызывается LifeEngine.
        Использует StateDeltas для унификации контракта мутаций.
        """
        recovery = 15.0 if is_sleeping else 5.0
        deltas = StateDeltas(
            # v1 backward compat
            stress_delta=-recovery,
            # v2 domain-tagged payload
            domain=DeltaDomain.EMOTION,
            payload=EmotionPayload(stress_delta=-recovery),
            source="tick_recovery",
        )
        return self.apply_deltas_only(state, deltas)

    def apply_deltas_only(
        self,
        state: NPCState,
        deltas: StateDeltas,
        campaign_id: str = "",
    ) -> NPCState:
        """
        Применяет StateDeltas без DecisionResult.
        Унифицированный метод для всех источников мутаций (tick_recovery, world_tick, etc).
        """
        new_state = copy.deepcopy(state)
        try:
            self._apply_deltas(new_state, deltas, campaign_id)
            return new_state
        except Exception as e:
            # H-29 FIX: Не маскируем ошибку, пробрасываем выше (ADR-O-308).
            logger.error(
                f"[STATE_APPLICATOR] apply_deltas_only ошибка для '{state.npc_id}': {e}. "
                f"Пробрасываем исключение."
            )
            raise

    # ─────────────────────────────────────────────────────────────────────────
    # Внутренние методы применения
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_intent(
        self,
        state: NPCState,
        result: DecisionResult,
        current_tick: int,
    ) -> None:
        """Обновляет intent с учётом инерции и счётчика duration."""
        new_intent = result.intent

        if state.intent == new_intent:
            # Intent не изменился — увеличиваем duration
            state.intent_duration += 1
        else:
            # Intent сменился — мягкий сброс: сохраняем 30% прогресса для цепочек
            state.intent = new_intent
            state.intent_target = result.intent_target
            state.intent_formed_at = current_tick
            state.intent_duration = 0
            state.intent_progress_ticks = int(state.intent_progress_ticks * 0.3)
            state.last_intent_change = current_tick

    def _apply_progress(
        self,
        state: NPCState,
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
        state: NPCState,
        deltas: StateDeltas,
        campaign_id: str,
    ) -> None:
        """Применяет числовые дельты к state и RelationshipStore."""
        # --- v2 payload extraction (с фолбэком на v1 поля) ---
        domain = deltas.domain
        npc_id = state.npc_id

        stress_delta = (
            deltas.payload.stress_delta
            if domain == DeltaDomain.EMOTION
            and isinstance(deltas.payload, EmotionPayload)
            else deltas.stress_delta
        )
        emotion_delta = (
            deltas.payload.emotion_delta
            if domain == DeltaDomain.EMOTION
            and isinstance(deltas.payload, EmotionPayload)
            else deltas.emotion_delta
        )
        emotion_tag = (
            deltas.payload.emotion_tag
            if domain == DeltaDomain.EMOTION
            and isinstance(deltas.payload, EmotionPayload)
            else deltas.emotion_tag
        )
        new_trauma = (
            deltas.payload.new_trauma
            if domain == DeltaDomain.EMOTION
            and isinstance(deltas.payload, EmotionPayload)
            else deltas.new_trauma
        )

        trust_delta = (
            deltas.payload.trust_delta
            if domain == DeltaDomain.SOCIAL
            and isinstance(deltas.payload, SocialPayload)
            else deltas.trust_delta
        )
        fear_delta = (
            deltas.payload.fear_delta
            if domain == DeltaDomain.SOCIAL
            and isinstance(deltas.payload, SocialPayload)
            else deltas.fear_delta
        )
        # social_satiation — гомеостаз социального насыщения
        # social_input_ema — континуальное поле социального входа
        _ema_delta = (
            deltas.payload.social_input_ema_delta
            if domain == DeltaDomain.SOCIAL
            and isinstance(deltas.payload, SocialPayload)
            else 0.0
        )

        # DEEP-015 FIX: Мёртвый код ExpectationStore (Reward Prediction Error) удалён.

        identity_integrity_delta = (
            deltas.payload.identity_integrity_delta
            if domain == DeltaDomain.IDENTITY
            and isinstance(deltas.payload, IdentityPayload)
            else deltas.identity_integrity_delta
        )
        pressure_resistance_delta = (
            deltas.payload.pressure_resistance_delta
            if domain == DeltaDomain.IDENTITY
            and isinstance(deltas.payload, IdentityPayload)
            else deltas.pressure_resistance_delta
        )
        will_state_override = (
            deltas.payload.will_state_override
            if domain == DeltaDomain.IDENTITY
            and isinstance(deltas.payload, IdentityPayload)
            else deltas.will_state_override
        )

        # Physiology Domain: Damage & Stress Propagation System
        hp_delta = (
            deltas.payload.hp_delta
            if domain == DeltaDomain.PHYSIOLOGY
            and isinstance(deltas.payload, PhysiologyPayload)
            else 0.0
        )
        pain_delta = (
            deltas.payload.pain_delta
            if domain == DeltaDomain.PHYSIOLOGY
            and isinstance(deltas.payload, PhysiologyPayload)
            else 0.0
        )
        fatigue_delta = (
            deltas.payload.fatigue_delta
            if domain == DeltaDomain.PHYSIOLOGY
            and isinstance(deltas.payload, PhysiologyPayload)
            else 0.0
        )
        blood_loss_delta = (
            deltas.payload.blood_loss_delta
            if domain == DeltaDomain.PHYSIOLOGY
            and isinstance(deltas.payload, PhysiologyPayload)
            else 0.0
        )
        add_injuries = (
            deltas.payload.add_injuries
            if domain == DeltaDomain.PHYSIOLOGY
            and isinstance(deltas.payload, PhysiologyPayload)
            else ()
        )
        add_statuses = (
            deltas.payload.add_statuses
            if domain == DeltaDomain.PHYSIOLOGY
            and isinstance(deltas.payload, PhysiologyPayload)
            else ()
        )
        remove_statuses = (
            deltas.payload.remove_statuses
            if domain == DeltaDomain.PHYSIOLOGY
            and isinstance(deltas.payload, PhysiologyPayload)
            else ()
        )
        shock_impulse = (
            deltas.payload.shock_impulse
            if domain == DeltaDomain.PHYSIOLOGY
            and isinstance(deltas.payload, PhysiologyPayload)
            and hasattr(deltas.payload, "shock_impulse")
            else 0.0
        )

        # PERCEPTION DOMAIN (ADR-O)
        threat_gradient_delta = (
            deltas.payload.threat_gradient_delta
            if domain == DeltaDomain.PERCEPTION
            and isinstance(deltas.payload, PerceptionPayload)
            else 0.0
        )
        uncertainty_delta_perc = (
            deltas.payload.uncertainty_delta
            if domain == DeltaDomain.PERCEPTION
            and isinstance(deltas.payload, PerceptionPayload)
            else 0.0
        )
        anomaly_score_delta_perc = (
            deltas.payload.anomaly_score_delta
            if domain == DeltaDomain.PERCEPTION
            and isinstance(deltas.payload, PerceptionPayload)
            else 0.0
        )
        # N-26 FIX: dominant_emotion_hint удалён (движок не назначает эмоцию, §S72.1).

        # Стресс
        if stress_delta != 0.0:
            old = state.stress
            state.stress, effective = apply_saturation(
                current=old,
                delta=stress_delta,
                min_val=0.0,
                max_val=100.0,
            )
            deltas.stress_delta_effective = effective
            logger.debug(
                f"[APPLY] {state.npc_id}: stress {old:.1f} → {state.stress:.1f} "
                f"(wanted {stress_delta:+.1f}, applied {effective:+.1f})"
            )

        # Эмоция
        if emotion_delta != 0.0:
            state.emotion_delta = max(
                -100.0, min(100.0, state.emotion_delta + emotion_delta)
            )
        if emotion_tag is not None:
            # SCC: StateApplicator НЕ имеет права писать S-слой в M-слой.
            # Interpretation (emotion_tag) применяется ТОЛЬКО через semantic_buffer в Phase 10.
            # Единственное исключение: affective_decay (Phase 0.5) — это легальная физика времени.
            if deltas.source != "affective_decay":
                logger.debug(
                    f"[SCC_BLOCK] npc={state.npc_id} emotion_tag={emotion_tag} blocked. S-writes to M forbidden."
                )
            else:
                from app.models.npc_state import _emotion_from_str

                _converted = (
                    _emotion_from_str(emotion_tag)
                    if isinstance(emotion_tag, str)
                    else emotion_tag
                )
                state.emotion = _converted
                logger.debug(
                    f"[SCC_PASS] npc={state.npc_id} decay emotion={_converted} applied to M."
                )

        self._apply_emotion_social_deltas(state, domain, deltas)

        self._apply_trauma_and_traits(state, deltas, new_trauma)

        # --- Физиология (Physiology Domain) ---
        if domain == DeltaDomain.PHYSIOLOGY:
            self._apply_physiology_deltas(
                state,
                hp_delta,
                pain_delta,
                fatigue_delta,
                blood_loss_delta,
                add_injuries,
                add_statuses,
                remove_statuses,
                shock_impulse,
            )

        self._apply_perception_deltas(
            state, domain, deltas, threat_gradient_delta, uncertainty_delta_perc, anomaly_score_delta_perc
        )

        # Causal Ledger — паспорт каждого изменения (Шаг 3)
        # Фаза 4-ROLE.2: emotional_impact для генерации TemporaryDrive
        _tick = getattr(state, "intent_formed_at", 0)
        _source = getattr(deltas, "source", "unknown")
        _new_entries: List[Any] = []

        if stress_delta != 0.0:
            _impact = min(1.0, abs(deltas.stress_delta_effective) / 20.0)
            _new_entries.append(
                CausalEntry(
                    npc_id=state.npc_id,
                    field="stress",
                    delta=deltas.stress_delta_effective,
                    source=_source,
                    tick=_tick,
                    emotional_impact=round(_impact, 4),
                )
            )
        if trust_delta != 0.0:
            # Негативное доверие эмоционально сильнее
            _threshold = 20.0 if trust_delta < 0 else 30.0
            _impact = min(1.0, abs(trust_delta) / _threshold)
            _new_entries.append(
                CausalEntry(
                    npc_id=state.npc_id,
                    field="trust",
                    delta=trust_delta,
                    source=_source,
                    tick=_tick,
                    emotional_impact=round(_impact, 4),
                )
            )
        if fear_delta != 0.0:
            _impact = min(1.0, abs(fear_delta) / 15.0)
            _new_entries.append(
                CausalEntry(
                    npc_id=state.npc_id,
                    field="fear",
                    delta=fear_delta,
                    source=_source,
                    tick=_tick,
                    emotional_impact=round(_impact, 4),
                )
            )

        state.causal_ledger.extend(_new_entries)
        if len(state.causal_ledger) > 20:
            state.causal_ledger = state.causal_ledger[-20:]

        # Фаза 4-ROLE.2: Генерация TemporaryDrive из сильных эмоциональных ударов
        _DRIVE_TYPE_MAP = {
            "player_attacks": "vengeance",
            "player_attack": "vengeance",
            "player_insults": "vengeance",
            "player_threatens": "desperation",
            "theft": "vengeance",
            "betrayal": "desperation",
            "help": "loyalty_surge",
            "saved_life": "loyalty_surge",
        }
        for _entry in _new_entries:
            if _entry.emotional_impact > 0.7:
                _drive_type = _DRIVE_TYPE_MAP.get(_entry.source)
                if _drive_type is None:
                    continue
                # Проверяем что такой drive ещё не активен (от того же источника)
                _existing = [
                    d
                    for d in state.temporary_drives
                    if d.drive_type == _drive_type and d.source_npc_id == _entry.source
                ]
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

        # Отношения — маршрутизация по домену v2 (фолбэк на v1 таргеты)
        if domain == DeltaDomain.REPUTATION or deltas.faction_id is not None:
            # Фракция → ReputationEngine (единственный мутатор)
            self._apply_faction_delta(deltas, campaign_id)
        elif trust_delta != 0.0 or fear_delta != 0.0:
            if self._rel_store is not None:
                # Явная маршрутизация: target (v2) → NPC→NPC/NPC→Player
                _target = (
                    deltas.target
                    or deltas.social_target
                    or deltas.intent_target
                    or state.intent_target
                    or "player"
                )
                self.update_relationships(
                    campaign_id=campaign_id,
                    source_id=state.npc_id,
                    target_id=_target,
                    trust_delta=trust_delta,
                    fear_delta=fear_delta,
                )

    def _apply_physiology_deltas(
        self,
        state: NPCState,
        hp_delta: float,
        pain_delta: float,
        fatigue_delta: float,
        blood_loss_delta: float,
        add_injuries: list,
        add_statuses: list,
        remove_statuses: list,
        shock_impulse: float,
    ) -> None:
        """Применяет дельты физиологии (HP, боль, шок) к body_state."""
        # Инициализация body_state при первом применении
        if not state.body_state:
            state.body_state = {
                "current_hp": 100.0,
                "pain": 0.0,
                "fatigue": 0.0,
                "blood_loss": 0.0,
                "consciousness": 1.0,
                "shock_impulse": 0.0,
                "injuries": [],
                "modifiers": {},
                "statuses": [],
            }

        if hp_delta != 0.0:
            _max_hp = state.body_state.get("max_hp", 100.0)
            _cur_hp = state.body_state.get("current_hp", _max_hp)
            state.body_state["current_hp"] = max(
                0.0, min(_max_hp, _cur_hp + hp_delta)
            )

        if pain_delta != 0.0:
            _cur_pain = state.body_state.get("pain", 0.0)
            state.body_state["pain"] = max(0.0, min(100.0, _cur_pain + pain_delta))

        if fatigue_delta != 0.0:
            _cur_fat = state.body_state.get("fatigue", 0.0)
            state.body_state["fatigue"] = max(
                0.0, min(100.0, _cur_fat + fatigue_delta)
            )

        if blood_loss_delta != 0.0:
            _cur_blood = state.body_state.get("blood_loss", 0.0)
            state.body_state["blood_loss"] = max(
                0.0, min(1.0, _cur_blood + blood_loss_delta)
            )

        if add_injuries:
            # Конвертируем InjuryDTO в dict для JSON-сериализации
            state.body_state.setdefault("injuries", []).extend(
                [asdict(inj) for inj in add_injuries]
            )
            logger.debug(
                f"[INJURY_APPLIED] npc={state.npc_id} total_injuries={len(state.body_state.get('injuries', []))} new={[i.damage_type for i in add_injuries]}"
            )

        if add_statuses:
            state.body_state.setdefault("statuses", []).extend(add_statuses)

        if remove_statuses:
            state.body_state["statuses"] = [
                s
                for s in state.body_state.get("statuses", [])
                if s not in remove_statuses
            ]

        # Шоковый импульс: аддитивный с потолком 1.0, decay даёт отрицательную дельту
        if shock_impulse != 0.0:
            _cur_shock = state.body_state.get("shock_impulse", 0.0)
            state.body_state["shock_impulse"] = max(
                0.0, min(1.0, _cur_shock + shock_impulse)
            )

        # ADR-124: Consciousness derivation из физиологии
        _bl = state.body_state.get("blood_loss", 0.0)
        _si = state.body_state.get("shock_impulse", 0.0)
        _physiological_consciousness = max(0.0, 1.0 - (_bl**1.5) * 2.0 - _si * 1.5)
        _cur_consciousness = state.body_state.get("consciousness", 1.0)
        if _physiological_consciousness < _cur_consciousness:
            state.body_state["consciousness"] = round(
                _physiological_consciousness, 4
            )
            logger.debug(
                f"[CONSCIOUSNESS_DROP] npc={state.npc_id} bl={_bl:.3f} shock={_si:.3f} old={_cur_consciousness:.3f} new={state.body_state['consciousness']:.3f}"
            )

        # §ENIGMA-AFFECTIVE-SOVEREIGNTY v2: PHYSIOLOGY fallback УБИТ.
        pass

        # Transitional: vital_state evaluation
        _life_status = evaluate_vital_state(state.body_state)
        state.body_state["life_status"] = _life_status.value
        if _life_status == LifeStatus.DEAD:
            logger.warning(
                f"[DEATH_CERTIFIED] npc={state.npc_id} bl={state.body_state.get('blood_loss', 0):.3f} structural={sum(float(i.get('structural_damage', 0)) for i in state.body_state.get('injuries', [])):.3f}"
            )

    def _apply_emotion_social_deltas(
        self, state: NPCState, domain: DeltaDomain, deltas: StateDeltas
    ) -> None:
        """Применяет дельты эмоций (SCC) и социального давления (EMA)."""
        # SCC: affective_load — интеграл давления. Пишется в M ТОЛЬКО через decay.
        if domain == DeltaDomain.EMOTION and isinstance(deltas.payload, EmotionPayload):
            _payload_load = getattr(deltas.payload, "affective_load", None)  # noqa: ENIGMA002
            if _payload_load is not None:
                if deltas.source in ("affective_decay", "sel_trace_commit"):
                    state.affective_load = min(1.0, max(0.0, _payload_load))
                    if deltas.source == "sel_trace_commit":
                        _payload_memory = getattr(deltas.payload, "affective_memory", None)  # noqa: ENIGMA002
                        if _payload_memory is not None:
                            state.affective_memory = _payload_memory
                    logger.debug(
                        f"[SCC_PASS] npc={state.npc_id} src={deltas.source} affective_load={_payload_load:.3f} applied to M."
                    )
                else:
                    logger.debug(
                        f"[SCC_BLOCK] npc={state.npc_id} affective_load={_payload_load:.3f} blocked. S-writes to M forbidden."
                    )

        # Field Channel: EMA — единственное динамическое социальное состояние
        _ema_delta = 0.0
        if domain == DeltaDomain.SOCIAL and isinstance(deltas.payload, SocialPayload):
            _ema_delta = getattr(deltas.payload, "social_input_ema_delta", 0.0)

        if _ema_delta != 0.0:
            state.social_input_ema = max(
                0.0, min(1.0, state.social_input_ema + _ema_delta)
            )
            logger.warning(
                f"[SOCIAL_EMA] npc={state.npc_id} delta={_ema_delta:+.3f} result={state.social_input_ema:.3f}"
            )
            if deltas.source == "sel_trace_commit" and isinstance(
                deltas.payload, EmotionPayload
            ):
                _payload_memory = getattr(deltas.payload, "affective_memory", None)  # noqa: ENIGMA002
                if _payload_memory is not None:
                    state.affective_memory = min(1.0, max(0.0, _payload_memory))

                _payload_load = getattr(deltas.payload, "affective_load", None)  # noqa: ENIGMA002
                if _payload_load is not None:
                    state.affective_load = min(1.0, max(0.0, _payload_load))
                    logger.debug(
                        f"[SEL_COMMIT] npc={state.npc_id} affective_load={_payload_load:.3f}, memory={_payload_memory:.3f} applied to M."
                    )

    def _apply_perception_deltas(
        self,
        state: NPCState,
        domain: DeltaDomain,
        deltas: StateDeltas,
        threat_gradient_delta: float,
        uncertainty_delta_perc: float,
        anomaly_score_delta_perc: float,
    ) -> None:
        """Применяет дельты восприятия и директив к PerceptualKernel."""
        # Шаг 1: инициализация PerceptualKernel (один раз, любой domain)
        if not hasattr(state, "perceptual_kernel") or state.perceptual_kernel is None:
            from app.models.npc_state import PerceptualKernel

            state.perceptual_kernel = PerceptualKernel()

        # Шаг 2: директивные perception-поля — применяются всегда (любой domain)
        _aggr_inh = getattr(deltas.payload, "aggression_inhibition_delta", 0.0)
        if _aggr_inh != 0.0:
            state.perceptual_kernel.aggression_inhibition = max(
                0.0, min(1.0, state.perceptual_kernel.aggression_inhibition + _aggr_inh)
            )
        _comp_bias = getattr(deltas.payload, "compliance_bias_delta", 0.0)
        if _comp_bias != 0.0:
            state.perceptual_kernel.compliance_bias = max(
                0.0, min(1.0, state.perceptual_kernel.compliance_bias + _comp_bias)
            )
        _init_sup = getattr(deltas.payload, "initiative_suppression_delta", 0.0)
        if _init_sup != 0.0:
            state.perceptual_kernel.initiative_suppression = max(
                0.0,
                min(1.0, state.perceptual_kernel.initiative_suppression + _init_sup),
            )
        if _recent_dir := getattr(deltas.payload, "recent_directive_data", None):  # noqa: ENIGMA002
            state.perceptual_kernel.recent_directive = _recent_dir

        # Шаг 3: PERCEPTION-специфичные поля (threat/uncertainty/anomaly)
        if domain == DeltaDomain.PERCEPTION:
            if threat_gradient_delta != 0.0:
                state.perceptual_kernel.threat_gradient = max(
                    0.0,
                    min(
                        1.0,
                        state.perceptual_kernel.threat_gradient + threat_gradient_delta,
                    ),
                )
            if uncertainty_delta_perc != 0.0:
                state.perceptual_kernel.uncertainty = max(
                    0.0,
                    min(
                        1.0,
                        state.perceptual_kernel.uncertainty + uncertainty_delta_perc,
                    ),
                )
            if anomaly_score_delta_perc != 0.0:
                state.perceptual_kernel.anomaly_score = max(
                    0.0,
                    min(
                        1.0,
                        state.perceptual_kernel.anomaly_score
                        + anomaly_score_delta_perc,
                    ),
                )

            # N-26 FIX: dominant_emotion_hint удалён (движок не назначает эмоцию, §S72.1).

    def _apply_trauma_and_traits(
        self, state: NPCState, deltas: StateDeltas, new_trauma: Optional[str]
    ) -> None:
        """Применяет накопление энергии черт и обработку травм."""
        from app.core.constants import TRAIT_ACTIVATION_RATE

        for trait, value in deltas.trait_updates.items():
            _current_energy = state.trait_activation.get(trait, 0.0)
            state.trait_activation[trait] = min(
                1.0, _current_energy + (value * TRAIT_ACTIVATION_RATE)
            )

        if new_trauma:
            state.trauma_markers.add(new_trauma)
            from app.domain.identity_events import TraitDriftEvent
            from app.services.npc.break_progress_engine import compute_mutation

            _drive_mutations = compute_mutation(state, new_trauma)
            if _drive_mutations:
                _tick = getattr(state, "intent_formed_at", 0)
                _events = [
                    TraitDriftEvent(
                        tick_id=_tick,
                        target_id=state.npc_id,
                        source_id=f"trauma:{new_trauma}",
                        effect_value=delta,
                        observation_weight=1.0,
                        event_type=f"trauma:{trait}",
                    )
                    for trait, delta in _drive_mutations.items()
                ]
                _chronicle = getattr(self, "_l1_chronicle", None)  # noqa: ENIGMA002
                if _chronicle is not None:
                    _chronicle.commit_tick_buffer(_events, _tick)
                else:
                    import logging

                    logging.getLogger(__name__).warning(
                        f"[STATE_APPLICATOR] L1Chronicle not attached to StateApplicator. "
                        f"Drive mutation for {state.npc_id} ignored (L3 strictly ephemeral)."
                    )

    def _apply_trait_decay(self, state: NPCState) -> None:
        """
        ADR-O-304: Trait Dynamics — гистерезисная модель активации/деактивации черт.
        1. Энергия активации (trait_activation) затухает каждый тик.
        2. Если энергия > THETA_UP — черта активируется в state_modifiers.
        3. Если энергия < THETA_DOWN — черта начинает обычный decay.
        4. Если энергия >= THETA_DOWN — черта удерживается (dwell_time).
        """
        from app.core.constants import THETA_DOWN, THETA_UP, TRAIT_ACTIVATION_DECAY

        # 1. Затухание энергии активации
        energy_to_remove = []
        for trait, energy in state.trait_activation.items():
            new_energy = energy - TRAIT_ACTIVATION_DECAY
            if new_energy < 0.01:
                energy_to_remove.append(trait)
            else:
                state.trait_activation[trait] = round(new_energy, 4)
        for trait in energy_to_remove:
            del state.trait_activation[trait]

        # 2. Гистерезисная активация/деактивация
        mods_to_remove = []
        for trait, strength in state.state_modifiers.items():
            energy = state.trait_activation.get(trait, 0.0)

            # Активация: энергия высокая — обновляем силу черты (поддерживаем)
            if energy >= THETA_UP:
                state.state_modifiers[trait] = 1.0  # Полная активация
            # Dwell time: энергия средняя — удерживаем черту без decay
            elif energy >= THETA_DOWN:
                pass  # Черта удерживается, decay не применяется
            # Деактивация: энергия низкая — применяем обычный decay
            else:
                new_strength = strength - TRAIT_DECAY_RATE
                if new_strength < 0.01:
                    mods_to_remove.append(trait)
                else:
                    state.state_modifiers[trait] = round(new_strength, 4)

        for trait in mods_to_remove:
            del state.state_modifiers[trait]

    # ── Фракции: ReputationEngine — единственный мутатор ──────────────

    def _apply_faction_delta(self, deltas: StateDeltas, campaign_id: str) -> None:
        """Применяет reputation_delta к фракции через ReputationEngine.

        Вызывается из _apply_deltas() — единый путь мутаций.
        """
        if self._reputation_engine is None:
            logger.debug(
                f"[STATE_APPLICATOR] reputation_delta пропущен: "
                f"no ReputationEngine (faction={deltas.target or deltas.faction_id})"
            )
            return
        self._reputation_engine.apply_deltas([deltas])

    # ── Batch-применение: единая точка для idle дельт ─────────────────

    def apply_batch(
        self,
        deltas: List[StateDeltas],
        all_npcs_raw: List[dict[str, Any]],
        campaign_id: str,
    ) -> None:
        """Единая точка применения всех накопленных дельт.

        Оркестратор вызывает вместо прямых мутаций all_npcs_raw.
        Порядок: фракции → NPC (группировка по npc_id).
        """
        if not deltas:
            return

        # Разделение: фракции (v2 domain + v1 fallback) vs NPC
        faction_deltas = [
            d
            for d in deltas
            if d.domain == DeltaDomain.REPUTATION
            or (d.domain is None and d.faction_id is not None)
        ]
        npc_deltas = [d for d in deltas if d not in faction_deltas]

        # Фракции → ReputationEngine
        if faction_deltas and self._reputation_engine:
            self._reputation_engine.apply_deltas(faction_deltas)

        # NPC: группировка по npc_id
        by_npc: Dict[str, List[StateDeltas]] = {}
        for d in npc_deltas:
            if d.npc_id:
                by_npc.setdefault(d.npc_id, []).append(d)
        if by_npc:
            _phys_npcs = [
                nid
                for nid, ds in by_npc.items()
                if any(d.domain == DeltaDomain.PHYSIOLOGY for d in ds)
            ]
            if _phys_npcs:
                logger.debug(
                    f"[APPLY_BATCH] npc_count={len(by_npc)} physiology_npcs={_phys_npcs}"
                )

        # DEBT-DET-01: Детерминированный порядок применения дельт.
        # Физика (PHYSICS_COMPOSITE) -> Когнитив (EMOTION, PERCEPTION) -> Социум (SOCIAL).
        _DOMAIN_APPLICATION_ORDER = {
            DeltaDomain.PHYSIOLOGY: 0,
            DeltaDomain.PERCEPTION: 10,
            DeltaDomain.EMOTION: 20,
            DeltaDomain.IDENTITY: 30,
            DeltaDomain.SOCIAL: 40,
            DeltaDomain.REPUTATION: 50,
            DeltaDomain.WILL: 60,
            DeltaDomain.DOPAMINE: 70,
            DeltaDomain.SPATIAL: 80,
        }
        _DEFAULT_ORDER = 100

        # Применяем через тонкий мост: Dict[str, Any] → NPCState → _apply_deltas → dict
        for npc_dict in all_npcs_raw:
            npc_id = npc_dict.get("id") or npc_dict.get("npc_id")
            if npc_id not in by_npc:
                continue
            # Сортируем дельты по домену для предсказуемого результата
            sorted_deltas = sorted(
                by_npc[npc_id],
                key=lambda d: _DOMAIN_APPLICATION_ORDER.get(d.domain if d.domain else DeltaDomain.PERCEPTION, _DEFAULT_ORDER),
            )
            for delta in sorted_deltas:
                self._apply_delta_to_raw(npc_dict, delta, campaign_id)

    def _apply_delta_to_raw(
        self,
        npc_dict: Dict[str, Any],
        deltas: StateDeltas,
        campaign_id: str,
    ) -> None:
        """Временный мост (до L1 Materialization в Orchestrator).
        Конвертирует dict → NPCState и передаёт в чистый Commit Kernel.
        """
        from app.models.npc_state import NPCStateAdapter

        # L1: Материализация (будет перенесена в Orchestrator на Этапе 5)
        state = NPCStateAdapter.from_legacy(npc_dict)

        # Stage 0 Task 0.8: SSOT Economic. 
        # Единая точка обработки EconomicPayload. 
        # Пишем прямо в npc_dict, чтобы избежать потери данных при return.
        if deltas.domain == DeltaDomain.ECONOMY and isinstance(deltas.payload, EconomicPayload):
            _money_delta = float(deltas.payload.money_delta or 0.0)
            if _money_delta != 0.0:
                if state.npc_id == "player":
                    if "body_state" not in npc_dict:
                        npc_dict["body_state"] = {}
                    npc_dict["body_state"]["money"] = float(npc_dict["body_state"].get("money", 0.0)) + _money_delta
                else:
                    npc_dict["gold"] = float(npc_dict.get("gold", 0.0)) + _money_delta
            return

        # Делегирование в Commit Kernel
        self.apply_deltas_and_commit(state, npc_dict, deltas, campaign_id)

    def apply_belief_delta(self, state: NPCState, delta: "BeliefDelta") -> None:
        """Stage 1 Task 1.6: Единственный физический write-path в state.beliefs."""
        from app.models.npc.beliefs import BeliefFragment
        state.beliefs.update(
            delta.belief_type,
            BeliefFragment(
                value=delta.new_value,
                confidence=delta.confidence,
                source=delta.source,
                timestamp=delta.timestamp,
            )
        )

    def apply_deltas_and_commit(
        self,
        state: NPCState,
        npc_dict: Dict[str, Any],
        deltas: StateDeltas,
        campaign_id: str,
    ) -> None:
        """Commit Kernel (L3/L4/L5): Чистый редьюсер, L5 пост-чек, строгий коммит.

        Никакой бизнес-логики, исправлений или try/except.
        Ошибка мутации = смерть тика (causal consistency).
        """
        import math

        from app.domain.exceptions import OntologyViolationError

        # L3: Pure fold (мутация state)
        # try/except УНИЧТОЖЕН. Если _apply_deltas падает — падает весь тик.
        self._apply_deltas(state, deltas, campaign_id)

        # L5: Post-Commit Validation Gate (No Repair Principle)
        # L5A: Structural Existence — ADR-139 Single Write Authority.
        # ADR-O-208: L3-P1. drives_runtime — эфемерный кэш. Если он пуст, валидируем L0 (drives_base).
        drives = getattr(state, "drives_runtime", None) or getattr(  # noqa: ENIGMA002
            state, "drives_base", None
        )
        if not drives or not isinstance(drives, dict):
            raise OntologyViolationError(
                f"NPC '{state.npc_id}': Нарушение структурного контракта (L5A). "
                f"drives_base и drives_runtime отсутствуют. Личность не существует."
            )

        total_mass = sum(drives.values())
        if abs(total_mass - 1.0) > 1e-6:
            raise OntologyViolationError(
                f"NPC '{state.npc_id}': Закон Сохранения Я нарушен. "
                f"Сумма драйвов = {total_mass:.6f}, ожидается 1.0"
            )

        for drive_name, value in drives.items():
            if math.isnan(value) or math.isinf(value):
                raise OntologyViolationError(
                    f"NPC '{state.npc_id}': Драйв '{drive_name}' содержит невалидное значение ({value}). "
                    f"Термоядерный распад личности."
                )
            if not (0.0 <= value <= 1.0):
                raise OntologyViolationError(
                    f"NPC '{state.npc_id}': Драйв '{drive_name}'={value:.4f} вышел за физические пределы [0, 1]. "
                    f"Нарушение онтологии мира."
                )

        # L4: Commit (проекция в транспортный формат)
        NPCState.write_to_legacy(state, npc_dict)
