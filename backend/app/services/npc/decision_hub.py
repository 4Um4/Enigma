from __future__ import annotations

# backend/app/services/npc/decision_hub.py
"""
R2.2 — DecisionHub: чистая функция принятия решений NPC.

Принципы:
  - DecisionHub = READ ONLY. Никаких мутаций.
  - Принимает NPCState + NPCPersonality + контекст события.
  - Возвращает DecisionResult — что сделать и какие дельты применить.
  - StateApplicator применяет результат атомарно.
  - LLM не участвует. Всё — Python.
"""


import logging
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from app.services.npc.kernel_rng import KernelRNG

logger = logging.getLogger(__name__)

# Целевая архитектура данных (L0/L2)
from app.core.constants import (
    COMMITMENT_BASE_THRESHOLD,
    COMMITMENT_BONUS_K,
    COMMITMENT_K,
    INTENT_DECAY_RATE,
    INTENT_EXHAUSTION_RATE,
    INTENT_INERTIA_MAX_TICKS,
    INTENT_INERTIA_WEIGHT,
    INTENT_SATURATION_TICKS,
    MIN_INTENT_SCORE,
    PROVOCATION_THREAT_THRESHOLD,
    REACTIVE_URGENCY_THRESHOLD,
    SCORE_NOISE_RANGE,
    SWITCHING_COST_AGE_K,
    SWITCHING_COST_BASE,
    SWITCHING_COST_EMOTION_K,
    SWITCHING_COST_IDENTITY_K,
)
from app.domain.communication import CommunicationIntent, ExposureLevel
from app.domain.vital_state import LifeStatus, evaluate_vital_state, is_conscious
from app.models.behavior_mask import BehaviorMask
from app.models.npc_profile import NPCProfileL0

# Легаси-типы, всё ещё используемые в логике (Enum'ы и контракты результатов)
from app.models.npc_state import (
    EmotionTag,
    Intent,
    NPCState,
    WillState,
)

# StateDeltas — канонический контракт мутаций (Устав §2.3)
from app.models.state_delta import StateDeltas
from app.services.economy.opportunity_engine import (
    OpportunityContext,
    OpportunityEngine,
    OpportunityResult,
)
from app.services.events.event_types import EventType
from app.services.npc.decision.risk import perceive_risk
from app.services.npc.decision.social_deltas import SocialDeltaEngine

# ── Проактивные интенты: доступны только при WORLD_TICK ──────────────────────
PROACTIVE_INTENTS: frozenset[str] = frozenset(
    {
        Intent.BLOCK_PATH,
        Intent.AMBUSH,
        Intent.SEEK_ALLY,
        Intent.OFFER_JOB,
        Intent.REQUEST_SERVICE,
        Intent.SPREAD_RUMOR,
        Intent.CALL_FOR_HELP,
        Intent.CHANGE_ROLE,
        Intent.TALK,  # S118 FIX: Диалоги теперь проактивны (TZ §4.1)
    }
)

# Роли, которым доступны перехватывающие/засадные интенты
# Остальные (торговцы, трактирщики, ремесленники) — заблокированы
COMBAT_CAPABLE_ROLES: frozenset[str] = frozenset(
    {
        "стражник",
        "охранник",
        "наёмник",
        "телохранитель",
        "вор",
        "бандит",
        "убийца",
        "наёмный убийца",
        "солдат",
        "воин",
        "рыцарь",
        "варвар",
        "головорез",
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# DecisionResult — только данные, никаких мутаций
# ─────────────────────────────────────────────────────────────────────────────

# StateDeltas импортирован из канонического модуля (app.models.state_delta)
# Обратная совместимость: from app.services.npc.decision_hub import StateDeltas — работает
__all_reexport__ = ["StateDeltas"]


@dataclass
class DecisionResult:
    """
    Результат DecisionHub.compute() — read-only контракт.
    StateApplicator читает это и применяет изменения атомарно.
    """

    npc_id: str
    intent: Intent
    intent_target: Optional[str]
    score: float  # итоговый score победившего intent
    scores_trace: Dict[str, float]  # все scores для калибровки R4.2
    deltas: List[StateDeltas]  # ADR-013: Каноничный v2 (Domain-Tagged Payloads)
    narrative_fact: Optional[str] = None  # текстовое описание для scene_outcome_builder
    explanation_mode: bool = False  # True если intent=EXPLAIN


@dataclass
class AgentAction:
    """Агрегат: gameplay-решение + опциональная речь (Устав 2.2).

    Наследует все поля DecisionResult через .decision.
    StateApplicator, ReactionResolver — берут .decision (обратная совместимость).
    DialogueEngine — берёт .communication (если есть).
    """

    decision: DecisionResult
    communication: Optional[CommunicationIntent] = None

    # Делегируем часто используемые поля — потребители не заметят
    @property
    def npc_id(self) -> str:
        return self.decision.npc_id

    @property
    def intent(self) -> Intent:
        return self.decision.intent

    @property
    def score(self) -> float:
        return self.decision.score

    @property
    def deltas(self) -> List[StateDeltas]:
        return self.decision.deltas

    @staticmethod
    def _get_rel_value(state: Any, target_id: str, attr: str) -> Optional[float]:
        """Precedence Contract: Graph (SSOT) > Scalar (Legacy) > Vacuum (None).
        Возвращает None, если отношение UNKNOWN (запись отсутствует).
        Возвращает float, если отношение известно (даже если это 0.0 - нейтралитет).
        """
        # 1. Graph Model (ADR-121 SSOT)
        _graph_val = state.relationship_cache.get(target_id, {}).get(attr)
        if _graph_val is not None:
            return float(_graph_val)
        # 2. Legacy Scalar Model (Pre-ADR-121)
        _scalar_val = state.relationship_cache.get(attr)
        if _scalar_val is not None:
            return float(_scalar_val)
        # 3. Vacuum (Нет знания об отношении)
        return None

    @property
    def intent_target(self) -> Optional[str]:
        return self.decision.intent_target

    @property
    def scores_trace(self) -> Dict[str, float]:
        return self.decision.scores_trace

    @property
    def narrative_fact(self) -> Optional[str]:
        return self.decision.narrative_fact

    @property
    def explanation_mode(self) -> bool:
        return self.decision.explanation_mode


# ─────────────────────────────────────────────────────────────────────────────
# EventContext — что произошло в мире
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class EventContext:
    """
    Контекст события для DecisionHub.
    Формируется в game_loop из EventDTO + SceneState.
    """

    event_type: EventType
    actor_id: str
    success: bool = True
    intensity: float = 1.0  # кап 1.5 применяется в __post_init__
    distance: float = 3.0
    witness_count: int = 1
    location: str = ""
    day: int = 0
    # GAP10 FIX: ID цели события. Без этого DecisionHub даёт бонус APPROACH всем NPC в зоне.
    target_id: Optional[str] = None
    # ADR-ACTION-BRIDGE: Каноническая семантика из IntentCompressor (closed-world lattice)
    semantic_action: Optional[str] = None
    # Видимые маркеры угрозы — что NPC воспринимает, не реальные stats игрока
    visible_threat_markers: List[str] = field(default_factory=list)
    # Текущая активность цели — для контекстной релевантности
    target_routine: str = "working"
    # Факты сцены — NPC помнит что происходило в локации (не только текущее действие)
    scene_flags: Set[str] = field(default_factory=set)
    scene_facts: List[str] = field(default_factory=list)
    # Payload от phase_1_input (semantic_action, target_id и т.д.)
    payload: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Кап интенсивности — защита от баговых значений из EventBus
        self.intensity = min(self.intensity, 1.5)


# ─────────────────────────────────────────────────────────────────────────────
# DecisionHub
# ─────────────────────────────────────────────────────────────────────────────


class DecisionHub:
    """
    Ядро интеллекта NPC. Чистая функция — читает, считает, возвращает.

    Формула score():
      score(action) =
          (drive_weight × context_relevance)
        + emotion_weight
        + relationship_modifier
        - (fear × risk)
        + intent_inertia        ← инерция текущего intent
        + noise                 ← ±10% рандом
    """

    def __init__(
        self,
        rng: Optional["KernelRNG"] = None,
        seed: Optional[int] = None,
    ) -> None:
        """Инициализация DecisionHub с детерминированным источником RNG.

        Args:
            rng: Экземпляр KernelRNG (предпочтительно). Если передан, используется как источник RNG.
                 Должен быть привязан к (tick, npc_id) для воспроизводимости (replay determinism).
            seed: Устаревший параметр seed. Используется ТОЛЬКО если rng is None.
                  Оставлен для обратной совместимости с тестами.

        KERNEL-ISOLATION: в production ВСЕГДА передаётся rng (не seed).
        seed=None + rng=None → недетерминированно (ТОЛЬКО ДЛЯ DEBUG).
        """
        # Тип _rng: KernelRNG (prod) или random.Random (legacy/debug)
        self._rng: Union["KernelRNG", random.Random]
        if rng is not None:
            self._rng = rng
        else:
            # Легаси-путь или debug. random.Random(None) → недетерминированно.
            self._rng = random.Random(seed)

        self._social_delta_engine = SocialDeltaEngine()
        self._last_redirect = 0.0  # инициализация scoring component
        self._last_dominant_drive = (
            "neutral"  # redirect direction: control/fear/neutral
        )

    # Вербальные интенты — для них строится CommunicationIntent (Устав 2.2)
    _VERBAL_INTENTS: Set[str] = {
        Intent.TALK.value,
        Intent.WARN.value,
        Intent.TRADE.value,
        Intent.REQUEST_SERVICE.value,
        Intent.OFFER_JOB.value,
        Intent.SPREAD_RUMOR.value,
        Intent.CALL_FOR_HELP.value,
        Intent.INTIMIDATE.value,
        Intent.EXPLAIN.value,
        Intent.APPROACH.value,
        Intent.CHANGE_ROLE.value,
    }

    @staticmethod
    def _get_rel_value(state: Any, target_id: str, attr: str) -> Optional[float]:
        """Precedence Contract: Graph (SSOT) > Scalar (Legacy) > Vacuum (None).
        S69: Унифицированный accessor для чтения relationship_cache.
        """
        # 1. Graph Model (ADR-121 SSOT)
        _graph_val = state.relationship_cache.get(target_id, {}).get(attr)
        if _graph_val is not None:
            return float(_graph_val)
        # 2. Legacy Scalar Model (Pre-ADR-121)
        _scalar_val = state.relationship_cache.get(attr)
        if _scalar_val is not None:
            return float(_scalar_val)
        # 3. Vacuum (Нет знания об отношении)
        return None

    def _build_communication(
        self,
        npc_id: str,
        intent_value: str,
        intent_target: Optional[str],
        topic: Optional[str],
        emotion_value: str,
        scores: Optional[Dict[str, float]] = None,
    ) -> Optional[CommunicationIntent]:
        """Создаёт CommunicationIntent для вербального intent (Устав 2.2).

        Возвращает None для невербальных intent (FLEE, ATTACK, IDLE...).
        """
        if intent_value not in self._VERBAL_INTENTS:
            return None
        # Тема: из фазы 4 или фоллбэк по intent
        _topic = topic or intent_value
        # Трассировка скоринга: показываем топ-3 интента и их финальный вес
        _top_intents = (
            sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
            if scores is not None
            else []
        )
        logger.info(
            f"[TRACE][DECISION_SCORE] npc={npc_id} winner={intent_value} "
            f"top3={[(i, round(s, 2)) for i, s in _top_intents]}"
        )

        return CommunicationIntent(
            speaker=npc_id,
            audience=intent_target or "all",
            topic=_topic,
            intent_type=intent_value,
            emotional_state=emotion_value,
            exposure_level=ExposureLevel.from_semantic("normal"),
        )

    def compute(
        self,
        state: NPCState,
        personality: NPCProfileL0,
        event: EventContext,
        effective_drives: "EffectiveDrives",  # L3-P2: Единственный источник истины драйвов
        scene_state: Optional[Dict[str, Any]] = None,
        opportunity_ctx: Optional[OpportunityContext] = None,
        identity: Optional["NPCIdentityL1"] = None,
        eco_modifiers: Optional[Dict[str, float]] = None,
        social_modifiers: Optional[Dict[str, float]] = None,
        reputation_modifiers: Optional[Dict[str, float]] = None,
        drive_modifiers: Optional[Dict[str, float]] = None,
        contract_modifiers: Optional[Dict[str, float]] = None,
        npc_memory_modifiers: Optional[Dict[str, float]] = None,
        reflex_constraints: Optional[Dict] = None,
        topic: Optional[str] = None,
        decision_ctx: Optional["DecisionContext"] = None,  # S28: Каузальная деформация
        spatial_query: Optional[Any] = None,  # S96: Для SocialTargetResolver
        all_npc_ids: Optional[List[str]] = None,  # S96: Для SocialTargetResolver
    ) -> AgentAction:
        """
        Основной метод. READ ONLY — state не мутируется.
        Принимает state уже после применения BreakProgressEngine
        (game_loop вызывает apply_break через StateApplicator перед compute).
        Возвращает DecisionResult для StateApplicator.
        """
        # ── Vital State Guard: мёртвые и без сознания не принимают решения ──
        # ЕДИНСТВЕННАЯ точка блокировки DecisionHub.
        # evaluate_vital_state — единственный владелец решения о жизни/смерти.
        # is_conscious — единственный владелец решения о сознании.
        _body = getattr(state, "body_state", None) or {}
        _life_status = evaluate_vital_state(_body)
        if _life_status == LifeStatus.DEAD or not is_conscious(_body):
            return AgentAction(
                decision=DecisionResult(
                    npc_id=state.npc_id,
                    intent=Intent.IDLE,
                    intent_target=None,
                    score=0.0,
                    scores_trace={"veto": _life_status.value},
                    deltas=[],
                ),
            )

        # Игрок спросил "почему?" → специальный режим объяснения
        if event.event_type == "player_asks_why":
            return self._explain_mode(state, personality, event)

        # R6.3 — оцениваем момент скрытого действия до фильтрации интентов.
        # OpportunityContext=None → inactive() без ошибки, backward-compatible.
        # OpportunityEngine требует контекст и строку will_state, а не весь state
        opportunity = OpportunityEngine().calculate(
            ctx=opportunity_ctx or OpportunityContext(),
            will_state=state.will_state.value
            if hasattr(state.will_state, "value")
            else str(state.will_state),
        )

        # L1 черты: только из NPCIdentityL1
        active_traits: Dict[str, float] = identity.active_traits if identity else {}
        possible = self._get_possible_intents(
            state, personality, event, opportunity, effective_drives=effective_drives
        )
        scores, components_trace = self._score_all(
            state,
            personality,
            event,
            possible,
            opportunity,
            active_traits,
            decision_ctx=decision_ctx,
            effective_drives=effective_drives,
        )

        # ADR-036 + ADR-ACTION-BRIDGE: Физика Власти. Читаем семантику напрямую из EventContext.
        # Мост action_to_intent гарантирует нормализацию ActionType.MOVE → Intent.APPROACH.
        from app.domain.action_intent_bridge import action_to_intent

        _sa_pop = getattr(event, "semantic_action", None)
        _tid_pop = getattr(event, "target_id", None)
        _expected_intent = action_to_intent(_sa_pop)

        # ADR-036 + ADR-ACTION-BRIDGE: Физика Власти. Читаем семантику из EventContext.payload.
        # Мост action_to_intent гарантирует нормализацию ActionType.MOVE → Intent.APPROACH.
        from app.domain.action_intent_bridge import action_to_intent

        _payload_pop = getattr(event, "payload", {}) or {}
        _sa_pop = (
            _payload_pop.get("semantic_action")
            if isinstance(_payload_pop, dict)
            else None
        )
        _tid_pop = (
            _payload_pop.get("target_id") if isinstance(_payload_pop, dict) else None
        )
        _expected_intent = action_to_intent(_sa_pop)

        if (
            _expected_intent == Intent.APPROACH.value
            and _tid_pop == state.npc_id
            and Intent.APPROACH.value in scores
        ):
            _fear_raw = DecisionHub._get_rel_value(state, "player", "fear")
            # L3-P2: Воля определяется текущей проекцией, не архетипом
            _will_pop = effective_drives.get("control", 0.5)
            _kernel_pop = getattr(state, "perceptual_kernel", None)
            _threat_pop = _kernel_pop.threat_gradient if _kernel_pop else 0.0

            # §ENIGMA-004: Epistemic Isolation.
            # Вакуум НЕ мутирует state (нет паранойи). Вакуум снижает легитимность приказа.
            if _fear_raw is not None:
                # ФАКТ: Известный страх генерирует социальную легитимность
                _obedience_legitimacy = (_fear_raw / 100.0) * (1.0 - _will_pop)
                _epistemic_mode = "FACT"
            else:
                # ВАКУУМ: Транзиентный inference pressure.
                # Незнакомец не имеет авторитета, но вызывает микрозамешательство (0.05).
                _obedience_legitimacy = 0.05 * (1.0 - _will_pop)
                _epistemic_mode = "VACUUM"

            _obed_pop = _obedience_legitimacy + 0.1 + (_threat_pop * 0.5)
            _boost_pop = _obed_pop * 2.0
            _current_approach = scores.get(Intent.APPROACH.value, 0.0)
            scores[Intent.APPROACH.value] = round(_current_approach + _boost_pop, 4)

            # Epistemic Drift Monitor (Phase 4 diagnostic)
            logger.debug(
                f"[PHYSICS_OF_POWER] npc={state.npc_id} mode={_epistemic_mode} action={_sa_pop} → intent={_expected_intent} boost={_boost_pop:.3f} legit={_obedience_legitimacy:.3f} will={_will_pop:.3f} threat={_threat_pop:.3f} approach={scores[Intent.APPROACH.value]:.3f}"
            )

        # Фаза 2.4-ECO: экономические модификаторы (опционально)
        if eco_modifiers:
            for intent, modifier in eco_modifiers.items():
                if intent in scores:
                    scores[intent] = round(scores[intent] + modifier, 4)

        # Фаза 3.2: социальные модификаторы (ревность, защита, страх)
        if social_modifiers:
            for intent, modifier in social_modifiers.items():
                if intent in scores:
                    scores[intent] = round(scores[intent] + modifier, 4)

        # Фаза 3.5: репутационные модификаторы (фракции влияют на уверенность)
        if reputation_modifiers:
            for intent, modifier in reputation_modifiers.items():
                if intent in scores:
                    scores[intent] = round(scores[intent] + modifier, 4)

        # Фаза 4-ROLE.2: модификаторы от временных драйвов (vengeance, greed, desperation)
        if drive_modifiers:
            for intent, modifier in drive_modifiers.items():
                if intent in scores:
                    scores[intent] = round(scores[intent] + modifier, 4)

        # Этап 6: невыполненные контракты → повышают приоритет remind/demand
        if contract_modifiers:
            for intent, modifier in contract_modifiers.items():
                if intent in scores:
                    scores[intent] = round(scores[intent] + modifier, 4)

        # Этап 7: NPC-NPC память → модификаторы от recall о целевом NPC
        if npc_memory_modifiers:
            for intent, modifier in npc_memory_modifiers.items():
                if intent in scores:
                    scores[intent] = round(scores[intent] + modifier, 4)

        # ── Причинный слой: ReflexConstraints (ограничения от рефлекса) ──
        # НЕ блокирует полностью — ограничивает через penalties и allowed_intents
        if reflex_constraints:
            allowed = reflex_constraints.get("allowed_intents", [])
            penalties = reflex_constraints.get("penalties", {})
            # Штрафы к запрещённым/трудным интентам
            for intent_str, penalty in penalties.items():
                if intent_str in scores:
                    scores[intent_str] = round(scores[intent_str] + penalty, 4)
            # Жёсткая фильтрация: убрать интенты вне allowed (если specified)
            if allowed:
                scores = {k: v for k, v in scores.items() if k in allowed}

        # ── S28: Каузальная деформация пространства решений ──
        if decision_ctx:
            # ФАЗА 1: Feasibility Filtering (Удаление невозможных действий)
            # Если feasibility = 0.0, действие вырезается из пула кандидатов
            for intent_str, feasibility in decision_ctx.compression.constraints.items():
                if intent_str in scores and feasibility <= 0.0:
                    del scores[intent_str]  # Жесткий пропуск (skip candidate)

            # ФАЗА 2: Utility Deformation (Искривление доступного ландшафта)
            deformation = decision_ctx.deformation
            # Каузальный след: логирование искривления utility-space для Observability (ТЗ Спринт 29, Приоритет 0)
            logger.debug(
                f"[DECISION_CTX] applied deformation: aggression_sup={deformation.aggression_suppression:.2f}, initiative_sup={deformation.initiative_suppression:.2f}, compliance_bias={deformation.compliance_bias:.2f}"
            )
            if deformation.aggression_suppression > 0:
                attack_sup = 1.0 - deformation.aggression_suppression
                if "ATTACK" in scores:
                    scores["ATTACK"] = round(scores["ATTACK"] * attack_sup, 4)
                if "INTIMIDATE" in scores:
                    scores["INTIMIDATE"] = round(scores["INTIMIDATE"] * attack_sup, 4)

            if deformation.initiative_suppression > 0:
                init_sup = 1.0 - deformation.initiative_suppression
                # Подавление инициативы бьет по всем активным действиям, кроме пассивных (OBSERVE, FLEE)
                for active_intent in ["ATTACK", "INTIMIDATE", "APPROACH", "TALK"]:
                    if active_intent in scores:
                        scores[active_intent] = round(
                            scores[active_intent] * init_sup, 4
                        )

            if deformation.escape_salience > 0:
                escape_amp = 1.0 + deformation.escape_salience
                if "FLEE" in scores:
                    scores["FLEE"] = round(scores["FLEE"] * escape_amp, 4)

            if deformation.compliance_bias > 0:
                comply_amp = 1.0 + deformation.compliance_bias
                if "APPROACH" in scores:
                    scores["APPROACH"] = round(scores["APPROACH"] * comply_amp, 4)

        # ── Причинный слой: Physical state (чтение изменённого мира) ──
        # DecisionHub ВИДИТ: hp, conditions, wounds, threats — не "пытались атаковать"
        _hp = getattr(state, "hp", 0)
        _max_hp = getattr(state, "max_hp", 0)
        _conditions = getattr(state, "conditions", {})
        _threat_acc = getattr(state, "threat_accumulator", None)
        _wounds = getattr(state, "wounds", [])

        # Низкое HP → усиление FLEE
        if _max_hp > 0 and _hp < _max_hp * 0.3:
            scores[Intent.FLEE] = round(scores.get(Intent.FLEE, 0.0) + 0.3, 4)

        # Bleeding → усиление защитных интентов
        if "bleeding" in _conditions:
            scores[Intent.FLEE] = round(scores.get(Intent.FLEE, 0.0) + 0.15, 4)
            scores[Intent.HELP] = round(scores.get(Intent.HELP, 0.0) + 0.1, 4)

        # Stunned → принудительный IDLE (но не lock — constraint выше уже ограничил)
        if "stunned" in _conditions:
            for intent_key in list(scores.keys()):
                if intent_key != Intent.IDLE:
                    scores[intent_key] = round(scores[intent_key] * 0.1, 4)
            scores[Intent.IDLE] = round(scores.get(Intent.IDLE, 0.0) + 0.5, 4)

        # Prone → штраф к атаке и бегу
        if "prone" in _conditions or getattr(state, "posture", "") == "prone":
            scores[Intent.ATTACK] = round(scores.get(Intent.ATTACK, 0.0) - 0.5, 4)
            scores[Intent.FLEE] = round(scores.get(Intent.FLEE, 0.0) - 0.3, 4)

        # Threat accumulation → модификатор от конкретного источника
        if _threat_acc and _threat_acc.total > 30:
            _threat_mod = min(0.4, _threat_acc.total / 100.0)
            scores[Intent.FLEE] = round(scores.get(Intent.FLEE, 0.0) + _threat_mod, 4)
            # Высокая угроза → отчаянная атака возможна
            if _threat_acc.total > 50:
                scores[Intent.ATTACK] = round(
                    scores.get(Intent.ATTACK, 0.0) + (_threat_acc.total - 50) / 100.0, 4
                )

        # Wounds → штраф к эффективности (шрамы болят)
        if _wounds:
            _wound_penalty = min(0.2, len(_wounds) * 0.05)
            for intent_key in scores:
                scores[intent_key] = round(scores[intent_key] - _wound_penalty, 4)

        # ADR-O-112: Пост-хок буст самообороны. Провокация насилием конвертирует
        # страх в ярость — ATTACK должен быть конкурентоспособен с FLEE.
        _et = event.event_type
        _et_val = _et.value if hasattr(_et, "value") else str(_et)
        _is_violence = _et in (
            "player_attacks",
            "PLAYER_ATTACKED",
            "combat",
            "capture",
        ) or _et_val in ("player_attacks", "PLAYER_ATTACKED", "combat", "capture")
        if _is_violence:
            # GAP10 FIX: Самозащита — ТОЛЬКО для цели атаки.
            # Свидетели должны бояться, а не нападать.
            _is_target = event.target_id is not None and event.target_id == state.npc_id
            if _is_target and Intent.ATTACK.value in scores:
                _self_defense = 1.0 + event.intensity
                _attack_score_pre = scores.get(Intent.ATTACK.value, 0.0)
                scores[Intent.ATTACK.value] = round(
                    _attack_score_pre * _self_defense, 4
                )

                # Ослабляем FLEE при прямой атаке ТОЛЬКО если ATTACK действительно валиден.
                # Иначе fear_early_exit убил ATTACK, и штраф к FLEE парализует NPC (он не бьёт и не бежит).
                if (
                    _attack_score_pre > 0.0
                    and Intent.FLEE.value in scores
                    and scores.get(Intent.FLEE.value, 0.0) > 0
                ):
                    scores[Intent.FLEE.value] = round(
                        scores.get(Intent.FLEE.value, 0.0) * 0.6, 4
                    )
            elif not _is_target:
                # Свидетель насилия: бегство предпочтительнее атаки
                if Intent.FLEE.value in scores:
                    scores[Intent.FLEE.value] = round(
                        scores.get(Intent.FLEE.value, 0.0)
                        * (1.0 + event.intensity * 0.3),
                        4,
                    )

        if not scores:
            # Защита от ValueError: если все интенты отфильтрованы — IDLE
            return AgentAction(
                decision=DecisionResult(
                    npc_id=state.npc_id,
                    intent=Intent.IDLE,
                    intent_target=None,
                    score=0.0,
                    scores_trace={"fallback": "no_available_intents"},
                    deltas=[],
                ),
            )

        # ── Commitment: бонус к текущему + стоимость смены ──
        commitment = self._get_commitment(state)
        threshold = self._commitment_threshold(commitment)
        current_intent_str_pre = state.intent.value if state.intent else None

        if current_intent_str_pre and current_intent_str_pre in scores:
            # Бонус к текущему intent — инерция в пространстве score
            scores[current_intent_str_pre] = round(
                scores[current_intent_str_pre] + commitment * COMMITMENT_BONUS_K, 4
            )
            # Switching cost — вычитается из всех остальных
            # ПУТЬ А: Проброс L3 в инерцию личности
            cost = self._switching_cost(
                state, personality, commitment, effective_drives=effective_drives
            )
            for k in scores:
                if k != current_intent_str_pre:
                    scores[k] = round(scores[k] - cost, 4)

        best_candidate_str, best_score = max(
            scores.items(), key=lambda x: x[1]
        )  # (str, float)

        # ── Commitment Model: порог смены intent ──
        threshold = self._commitment_threshold(commitment)

        # Текущий score (если intent есть и он в кандидатах)
        current_intent_str = state.intent.value if state.intent else None
        current_score = (
            scores.get(current_intent_str, 0.0) if current_intent_str else 0.0
        )
        pressure = best_score - current_score  # >0 значит новый лучше

        # Reactive urgency: высокая тревога → принудительная смена
        fear_value = state.stress if hasattr(state, "stress") else 0.0
        force_switch = fear_value > REACTIVE_URGENCY_THRESHOLD

        # ── Pressure Accumulation: накопление давления по парам ──
        # Ключ ВСЕГДА (str, str) — best_candidate_str из scores
        acc_key = (
            (current_intent_str, best_candidate_str) if current_intent_str else None
        )
        accumulated = 0.0
        if acc_key:
            accumulated = state.pressure_accumulator.get(acc_key, 0.0)
            if pressure > 0:
                accumulated = min(accumulated + pressure, 1.0)
            else:
                accumulated *= 0.85
            state.pressure_accumulator[acc_key] = accumulated

        # 7.4: WHY-лог. Чтение capture-based трассировки (чистая функция).
        _why_comps = components_trace.get(best_candidate_str, {})
        _why_fmt = {
            k: round(v, 3) for k, v in _why_comps.items() if isinstance(v, (int, float))
        }
        _threat_total = _threat_acc.total if _threat_acc else 0.0

        logger.debug(
            f"[WHY][DECISION] npc={state.npc_id} | "
            f"winner={best_candidate_str} ({best_score:.3f}) | "
            f"threat={_threat_total:.1f} | "
            f"comps={_why_fmt} | "
            f"current={current_intent_str} ({current_score:.3f}) | "
            f"threshold={threshold:.3f} | pressure={pressure:.3f} | "
            f"accumulated={accumulated:.3f} | force_switch={force_switch}"
        )

        # ── Решение: сменить или удержать ──
        switched = False
        if force_switch or pressure >= threshold or accumulated >= threshold:
            switched = True
            best_intent = Intent(best_candidate_str)
        elif state.intent and state.intent != Intent.IDLE:
            best_intent = state.intent
            best_score = current_score
            if current_intent_str not in scores:
                best_intent = Intent.IDLE
                best_score = 0.0
        else:
            # Текущий intent отсутствует или IDLE — берём лучший кандидат
            best_intent = Intent(best_candidate_str)

        # Reset accumulator при смене (защита от hysteresis lock)
        if switched and acc_key:
            state.pressure_accumulator[acc_key] = 0.0

        if best_score < MIN_INTENT_SCORE:
            best_intent = Intent.IDLE
            best_score = 0.0

        intent_target = self._resolve_target(
            best_intent,
            event,
            state,
            spatial_query=spatial_query,
            all_npc_ids=all_npc_ids or [],
        )
        deltas = self._compute_deltas(state, personality, event, best_intent)
        narrative = None  # факт создаётся через MemoryManager.apply(), не здесь

        # В scores_trace попадают ТОЛЬКО числа для калибровки R4.2.
        # Строки (причины срабатывания) отсекаются.
        opp_trace = {
            f"opp_{k}": v
            for k, v in opportunity.score_trace.items()
            if isinstance(v, (int, float))
        }

        logger.info(
            f"[DECISION_HUB] {state.npc_id}: intent={best_intent} score={round(best_score, 3)} event={event.event_type}"
        )
        _decision = DecisionResult(
            npc_id=state.npc_id,
            intent=Intent(best_intent),
            intent_target=intent_target,
            score=round(best_score, 4),
            scores_trace={
                **{k: round(v, 4) for k, v in scores.items()},
                **opp_trace,
                # break_stage виден в state.identity_integrity — трейс через snapshot()
            },
            deltas=deltas,
            narrative_fact=narrative,
        )
        _communication = self._build_communication(
            npc_id=state.npc_id,
            intent_value=best_intent
            if isinstance(best_intent, str)
            else best_intent.value,
            intent_target=intent_target,
            topic=topic,
            emotion_value=state.emotion.value
            if hasattr(state.emotion, "value")
            else str(state.emotion),
            scores=scores,
        )
        return AgentAction(decision=_decision, communication=_communication)

    # ─────────────────────────────────────────────────────────────────────────
    # Action Space — enum + фильтр доступности (решение №4)
    # ─────────────────────────────────────────────────────────────────────────

    def _get_possible_intents(
        self,
        state: NPCState,
        personality: NPCPersonality,
        event: EventContext,
        opportunity: OpportunityResult,
        effective_drives: Optional["EffectiveDrives"] = None,
    ) -> List[str]:
        from app.services.events.event_types import EventType

        # Проактивные интенты — ТОЛЬКО при world_tick, не при реакциях на игрока
        _is_proactive_tick = event.event_type == EventType.WORLD_TICK

        all_intents = [
            i.value for i in Intent if i not in (Intent.IDLE, Intent.EXPLAIN)
        ]

        filtered = []
        for intent in all_intents:
            # Фильтруем проактивные интенты при реактивных событиях
            if not _is_proactive_tick and intent in PROACTIVE_INTENTS:
                continue
            if self._is_intent_available(
                intent,
                state,
                personality,
                opportunity,
                effective_drives=effective_drives,
            ):
                filtered.append(intent)

        filtered.append(Intent.IDLE.value)
        return filtered

    def _is_intent_available(
        self,
        intent: str,
        state: NPCState,
        personality: NPCPersonality,
        opportunity: OpportunityResult,
        effective_drives: Optional["EffectiveDrives"] = None,
    ) -> bool:
        """
        Фильтр доступности intent по состоянию NPC.
        R6.3: BROKEN NPC с активной маской получает скрытые интенты
        при достаточном opportunity_score.
        """
        if state.will_state == WillState.BROKEN:
            # Базовые интенты: всегда доступны сломленному NPC
            if intent in (Intent.FLEE.value, Intent.OBSERVE.value, Intent.TALK.value):
                return True
            # Скрытые интенты: разблокируются только через OpportunityEngine
            return intent in opportunity.unlocked_intents

        if state.will_state == WillState.LOYAL:
            if intent == Intent.ATTACK.value:
                return False
        if state.stress >= 90.0:
            # Стресс-реакция зависит от доминирующего драйва, не от порога
            # Трусливый (fear доминирует) → ограничен до безопасных
            # Смелый (desire доминирует) → действует по природе
            # Контролирующий (control доминирует) → удерживает стабильность
            # STEP A: L3 обязателен. Фоллбек на L0 (drives_base) удалён (Инвариант L3-P2).
            # Если L3 нет — это pipeline fault, обрабатываемый на уровне выше.
            drives = dict(effective_drives.values)
            fear = drives.get("fear", 0.25)
            desire = drives.get("desire", 0.25)
            control = drives.get("control", 0.25)
            max_drive = max(fear, desire, control)
            # Блокируем только если страх — доминирующий драйв
            if fear >= max_drive and fear > 0.4:
                return intent in (Intent.FLEE.value, Intent.OBSERVE.value)
            return True

        # Ролевая фильтрация: мирные роли не перехватывают и не устраивают засады
        # Пустая роль = нет данных → не блокируем (безопаснее разрешить)
        if intent in (Intent.BLOCK_PATH.value, Intent.AMBUSH.value):
            role_lower = state.current_role.lower()
            if role_lower and not any(p in role_lower for p in COMBAT_CAPABLE_ROLES):
                return False

        # R8: BehaviorMask — теперь через модификаторы в _score_all, не блокировка
        # Маска умножает score (напр. FLEE * 3.0), DecisionHub сам выбирает
        return True

    # ─────────────────────────────────────────────────────────────────────────
    # Формула score()
    # ─────────────────────────────────────────────────────────────────────────

    def _score_all(
        self,
        state: NPCState,
        personality: NPCPersonality,
        event: EventContext,
        possible: List[str],
        opportunity: OpportunityResult,
        active_traits: Dict[str, float] = None,  # L1 черты, опционально
        decision_ctx: Optional[
            "DecisionContext"
        ] = None,  # S74: Affective Field Propagation
        effective_drives: Optional["EffectiveDrives"] = None,  # L3-P2: проекция драйвов
    ) -> Dict[str, float]:
        """
        Считает score для каждого доступного intent.
        Early exit: трусливый NPC (fear > 0.6) не рассматривает агрессию.
        """
        scores: Dict[str, float] = {}
        components_trace: Dict[
            str, Dict[str, Any]
        ] = {}  # 7.4: Чистая трассировка без side-channel
        inertia = self._intent_inertia(state)
        # L3-P2: Страх определяется текущей проекцией, не архетипом
        fear_drive = effective_drives.get("fear", 0.0) if effective_drives else 0.0
        skip_aggro = fear_drive > 0.6  # early exit для трусливых NPC
        logger.debug(
            f"[DIAG_SCORE_ALL] npc={state.npc_id} fear_drive={fear_drive:.2f} skip_aggro={skip_aggro} possible={possible}"
        )

        _AGGRO_INTENTS = {Intent.ATTACK.value, Intent.INTIMIDATE.value}

        for intent_str in possible:
            # Трусливый NPC пропускает агрессию — если только
            # OpportunityEngine не разблокировал интент. Момент важнее страха.
            if skip_aggro and intent_str in _AGGRO_INTENTS:
                if intent_str not in opportunity.unlocked_intents:
                    scores[intent_str] = -1.0
                    logger.debug(
                        f"[DIAG_AGGRO_SKIP] npc={state.npc_id} intent={intent_str} reason=fear_early_exit unlocked={opportunity.unlocked_intents}"
                    )
                    continue

            components = self._score_components(
                intent_str,
                state,
                personality,
                event,
                opportunity,
                active_traits or {},
                decision_ctx=decision_ctx,
                effective_drives=effective_drives,
            )
            base = sum(v for k, v in components.items() if isinstance(v, (int, float)))
            if intent_str in (Intent.ATTACK.value, Intent.FLEE.value):
                logger.debug(
                    f"[DIAG_COMPONENTS] npc={state.npc_id} intent={intent_str} base={base:.3f} comps={ {k: (round(v, 3) if isinstance(v, (int, float)) else v) for k, v in components.items()} }"
                )

            # R8: BehaviorMask модификатор — маска умножает score, не блокирует
            mask_mod = self._behavior_mask_modifier(intent_str, state)
            if mask_mod != 1.0:
                base *= mask_mod
                components["mask"] = round(mask_mod, 3)

            noise = self._rng.uniform(-SCORE_NOISE_RANGE, SCORE_NOISE_RANGE)

            if state.intent and state.intent.value == intent_str:
                base += inertia
                components["inertia"] = round(inertia, 4)

                # Exhaustion: штраф за стагнацию (применяется после inertia bonus)
                exhaustion = self._intent_exhaustion(state)
                if exhaustion > 0:
                    base -= exhaustion
                    components["exhaustion"] = round(-exhaustion, 4)

            components["noise"] = round(noise, 4)
            # Clamp: score не уходит за физические пределы формулы
            # Верхний предел 3.0 — теоретический максимум суммы всех компонентов
            scores[intent_str] = round(max(-2.0, min(3.0, base + noise)), 4)
            components_trace[intent_str] = components

        return scores, components_trace

    def _behavior_mask_modifier(
        self,
        intent: str,
        state: NPCState,
    ) -> float:
        """
        R8 + ШАГ C.2: BehaviorMask как CONSTRAINT (ограничение), не блокировка.

        ПРИНЦИП: Маска НЕ блокирует интенты полностью. Она делает их очень трудными.
        При экстремальных обстоятельствах (OpportunityEngine +20 бонус)
        NPC МОЖЕТ преодолеть маску — но это приведёт к последствиям.

        COLLAPSE: IDLE усилен, остальные сильно подавлены (но не 0)
        FAKE_SUBMISSION: агрессия подавлена, покорность усилена
        BETRAYAL: помощь подавлена, наблюдение усилено

        Возвращает множитель: 1.0 = без изменений, 0.1 = почти невозможно.
        """
        mask = state.behavior_mask.mask
        if mask == BehaviorMask.NONE:
            return 1.0

        # Интенсификация маски: чем глубже маска, тем сильнее эффект
        intensity = state.behavior_mask.intensity
        # Constraint: минимум 0.1 (никогда не блокирует полностью)
        # При intensity=0 → 0.8, при intensity=1.0 → 0.1
        suppression = max(0.1, 0.8 - 0.7 * intensity)

        if mask == BehaviorMask.COLLAPSE:
            # Функциональный паралич — IDLE доминирует
            if intent == Intent.IDLE.value:
                return 1.0 + 1.0 * intensity  # 1.0..2.0 — усиление IDLE
            return suppression  # 0.8..0.1 — сильное подавление

        if mask == BehaviorMask.FAKE_SUBMISSION:
            # Внешняя покорность — агрессия крайне затруднена
            if intent in (
                Intent.ATTACK.value,
                Intent.INTIMIDATE.value,
                Intent.WARN.value,
            ):
                return suppression * 0.5  # 0.4..0.05 — почти невозможно, но не 0
            if intent in (Intent.TALK.value, Intent.OBSERVE.value, Intent.IDLE.value):
                return 1.0 + 0.3 * intensity  # 1.0..1.3 — усиление покорности
            return suppression

        if mask == BehaviorMask.BETRAYAL:
            # Скрытое предательство — помощь крайне затруднена
            if intent == Intent.HELP.value:
                return suppression * 0.5  # 0.4..0.05
            if intent in (Intent.OBSERVE.value, Intent.IDLE.value):
                return 1.0 + 0.3 * intensity  # 1.0..1.3
            return suppression

        return 1.0

    def _relationship_modifier(
        self,
        intent: str,
        trust: float,
        fear: float,
    ) -> float:
        """
        Отношения + страх теперь работают как в Disco Elysium:
        страх — это не просто «штраф», а полноценный drive.
        Высокий fear → сильный FLEE, слабая агрессия, паралич в социалке.
        """
        mod = 0.0

        if intent == Intent.FLEE.value:
            # Страх — главный мотиватор к бегству (даже от «друга»)
            mod += fear * 0.65
            mod -= trust * 0.25  # от друга бежать тяжелее
        elif intent in (Intent.ATTACK.value, Intent.INTIMIDATE.value):
            # Страх полностью парализует агрессию
            mod -= fear * 0.9
            mod -= trust * 0.2
        elif intent == Intent.OBSERVE.value:
            # Страх делает наблюдение более вероятным
            mod += fear * 0.40
        elif intent == Intent.APPROACH.value:
            mod += trust * 0.30
            # S28: Хардкод страха убит. Подчинение теперь — результат каузальной деформации (DecisionContext)
            # Если DecisionContext не передан (legacy fallback), страх работает как базовый модификатор
            mod += fear * 0.10  # Базовый осторожный подход (снижен с 0.45)
        else:
            # Социальные действия (TALK, TRADE, HELP и т.д.)
            mod += trust * 0.30
            mod -= fear * 0.35  # страх мешает общению

        return round(mod, 4)

    # Инициация контакта — social_outgoing модификатор
    _OUTGOING_SOCIAL = {
        Intent.TALK.value,
        Intent.TRADE.value,
        Intent.HELP.value,
        Intent.REQUEST_SERVICE.value,
        Intent.OFFER_JOB.value,
        Intent.SPREAD_RUMOR.value,
        Intent.CALL_FOR_HELP.value,
        Intent.APPROACH.value,
    }
    # Реакция на контакт — social_incoming модификатор
    _INCOMING_SOCIAL = {
        Intent.WARN.value,
        Intent.INTIMIDATE.value,
        Intent.EXPLAIN.value,
    }

    def _removed_social_satiation_modifier(
        self,
        intent: str,
        decision_ctx: Optional["DecisionContext"] = None,
    ) -> float:
        """Читает готовые модификаторы из DecisionContext.

        DecisionHub не знает про social_satiation или gregariousness.
        Он видит только число. Если decision_ctx не передан или
        поля отсутствуют (legacy path) — возвращает 0.0.
        """
        if decision_ctx is None:
            return 0.0
        outgoing = getattr(decision_ctx, "social_outgoing", 0.0) or 0.0
        incoming = getattr(decision_ctx, "social_incoming", 0.0) or 0.0
        if intent in self._OUTGOING_SOCIAL:
            return outgoing
        if intent in self._INCOMING_SOCIAL:
            return incoming
        return 0.0

    def _score_components(
        self,
        intent: str,
        state: NPCState,
        personality: NPCPersonality,
        event: EventContext,
        opportunity: OpportunityResult,
        active_traits: Dict[str, float] = None,  # L1 черты из NPCIdentityL1
        decision_ctx: Optional[
            "DecisionContext"
        ] = None,  # S74: Affective Field Propagation
        effective_drives: Optional[
            "EffectiveDrives"
        ] = None,  # ПУТЬ А: L3 проекция драйвов
    ) -> Dict[str, float]:
        """
        Возвращает словарь компонентов score — для полного trace в R4.2.
        Каждый компонент виден отдельно: что именно перевесило.
        """
        # ПУТЬ А: L3 — единственный источник драйвов для скоринга. L0 запрещён (Инвариант L3-P2).
        # Если L3 нет — скоринг идёт с дефолтными весами (.get = 0.25), а не по архетипу.
        drives = dict(effective_drives.values) if effective_drives else {}
        # ENIGMA-REL-001: Запрет прямого доступа к relationship_cache (DOUBLE TRUTH)
        # Все чтения идут через унифицированный accessor _get_rel_value (§ENIGMA-003)
        fear = (DecisionHub._get_rel_value(state, "player", "fear") or 0.0) / 100.0
        trust = (DecisionHub._get_rel_value(state, "player", "trust") or 0.0) / 100.0
        risk = perceive_risk(event, state, drives)  # L3 вместо L0

        drive_score = self._drive_relevance(
            intent,
            drives,
            event,
            state=state,
            personality=personality,
            effective_drives=effective_drives,
        )
        emotion_mod = self._emotion_modifier(
            intent,
            state.emotion,
            drives=drives,
            affective_load=decision_ctx.affective_load if decision_ctx else 0.0,
        )
        rel_mod = self._relationship_modifier(intent, trust, fear)

        # ADR-067: Приказ (MOVE) = single-target pressure. Свидетели не должны лезть в объятия.
        if intent == Intent.APPROACH.value:
            _payload = getattr(event, "payload", {})
            _is_directive = (
                isinstance(_payload, dict) and _payload.get("semantic_action") == "MOVE"
            )
            _is_target = getattr(event, "target_id", None) == state.npc_id
            if _is_directive and not _is_target:
                rel_mod -= 0.8  # Жёсткий штраф для свидетелей директивы
        trait_mod = self._trait_modifier(intent, active_traits or {})

        # Risk теперь intent-aware (Disco Elysium style)
        # Высокий fear + высокий risk = мощный FLEE, а не паралич
        if intent == Intent.FLEE.value:
            # fear уже учтён в _relationship_modifier (fear × 0.65).
            # risk_penalty использует только объективную угрозу (threat_gradient),
            # иначе fear входит в формулу дважды и FLEE побеждает все интенты.
            _kernel = getattr(state, "perceptual_kernel", None)
            _perceived_threat = _kernel.threat_gradient if _kernel else 0.0
            risk_penalty = round(_perceived_threat * risk * 0.9, 4)
        elif intent == Intent.OBSERVE.value:
            risk_penalty = round(fear * risk * 0.5, 4)  # осторожное наблюдение
        elif intent in (Intent.ATTACK.value, Intent.INTIMIDATE.value):
            # Агрессия требует явной провокации — строковое сравнение (EventContext.event_type: str)
            # Без провокации штраф -0.54 делает ATTACK хуже чем TALK/WARN
            _PROVOCATION_TYPES = {
                "player_attacks",
                "PLAYER_ATTACKED",
                "combat",
                "intimidation",
                "capture",
                "player_insults",
                "player_threatens",
            }
            # Просто количество уникальных угроз × 0.1
            threat_level = len(set(event.visible_threat_markers)) * 0.1

            # S118 FIX: Превентивная агрессия. Если NPC субъективно чувствует высокую угрозу
            # (threat_gradient > 0.5), он может атаковать первым (fight > flight), даже в idle_tick.
            _kernel_atk = getattr(state, "perceptual_kernel", None)
            _perceived_threat_atk = _kernel_atk.threat_gradient if _kernel_atk else 0.0
            _is_high_threat = _perceived_threat_atk > 0.5

            _et = event.event_type
            _et_val = _et.value if hasattr(_et, "value") else str(_et)
            is_provoked = (
                _et in _PROVOCATION_TYPES
                or _et_val in _PROVOCATION_TYPES
                or threat_level >= PROVOCATION_THREAT_THRESHOLD
                or _is_high_threat  # S118: Триггер из PerceptualKernel
            )
            logger.debug(
                f"[DIAG_RISK_ATK] npc={state.npc_id} et={_et} et_type={type(_et).__name__} et_val={_et_val} provoked={is_provoked} fear={fear:.3f} risk={risk:.3f} markers={event.visible_threat_markers} perceived_threat={_perceived_threat_atk:.2f}"
            )
            if is_provoked:
                # ADR-O-112: Провокация конвертирует страх в ярость (fight > flight)
                risk_penalty = round(fear * risk * 0.5, 4)
            else:
                risk_penalty = round((-fear * risk * 1.25 - 0.6), 4)
        else:
            risk_penalty = round(
                -fear * risk * 0.3, 4
            )  # лёгкий штраф для всего остального

        # R6.3 — буст разблокированных интентов пропорционален opportunity_score.
        # Делает скрытое действие конкурентоспособным без ломания баланса формулы.
        # Буст даётся только если интент разблокирован сломленным NPC
        opportunity_mod = (
            opportunity.score if intent in opportunity.unlocked_intents else 0.0
        )

        # Social battery modifier (предшественник Homeostasis)
        social_mod = 0.0  # ADR-O-312: social_satiation deprecated, EMA handles this via behavior_modifiers

        return {
            "drive": round(drive_score, 4),
            "emotion": round(emotion_mod, 4),
            "relationship": round(rel_mod, 4),
            "risk_penalty": risk_penalty,
            "trait": round(trait_mod, 4),
            "opportunity": round(opportunity_mod, 4),
            "social": round(social_mod, 4),
            # ADR-O-205: Проекция причины для Нарратива
            "redirect": round(self._last_redirect, 4),
            "dominant_drive": self._last_dominant_drive,
        }

    def _score_one(
        self,
        intent: str,
        state: NPCState,
        personality: NPCPersonality,
        event: EventContext,
        opportunity: OpportunityResult,
        active_traits: Dict[str, float] = None,
        decision_ctx: Optional["DecisionContext"] = None,
        effective_drives: Optional["EffectiveDrives"] = None,
    ) -> float:
        """Суммарный score без компонентов — для внутреннего использования."""
        return sum(
            self._score_components(
                intent,
                state,
                personality,
                event,
                opportunity,
                active_traits or {},
                decision_ctx=decision_ctx,
                effective_drives=effective_drives,
            ).values()
        )

    def _drive_relevance(
        self,
        intent: str,
        drives: Dict[str, float],
        event: EventContext,
        state: Optional["NPCState"] = None,
        personality: Optional["NPCPersonality"] = None,
        effective_drives: Optional[Any] = None,
    ) -> float:
        """drive_weight × context_relevance."""
        # Маппинг intent → доминирующий drive
        _INTENT_DRIVE: Dict[str, str] = {
            Intent.ATTACK.value: "control",
            Intent.INTIMIDATE.value: "control",
            Intent.REPORT.value: "control",
            Intent.WARN.value: "control",
            Intent.FLEE.value: "fear",
            Intent.OBSERVE.value: "fear",
            Intent.TRADE.value: "desire",
            Intent.HELP.value: "significance",
            Intent.TALK.value: "significance",
            Intent.IDLE.value: "fear",
            # Проактивные интенты (Фаза 3.4)
            Intent.BLOCK_PATH.value: "control",
            Intent.AMBUSH.value: "control",
            Intent.SEEK_ALLY.value: "significance",
            Intent.OFFER_JOB.value: "desire",
            Intent.REQUEST_SERVICE.value: "desire",
            Intent.SPREAD_RUMOR.value: "significance",
            Intent.CALL_FOR_HELP.value: "significance",
            Intent.CHANGE_ROLE.value: "desire",
            Intent.APPROACH.value: "desire",
        }
        drive_key = _INTENT_DRIVE.get(intent, "desire")
        drive_weight = drives.get(drive_key, 0.25)

        # context_relevance — насколько событие активирует этот drive
        context_relevance = self._context_relevance(
            intent,
            event,
            state=state,
            personality=personality,
            effective_drives=effective_drives,
        )

        return round(drive_weight * context_relevance, 4)

    def _context_relevance(
        self,
        intent: str,
        event: EventContext,
        state: Optional["NPCState"] = None,
        personality: Optional["NPCPersonality"] = None,
        effective_drives: Optional["EffectiveDrives"] = None,
    ) -> float:
        """Насколько событие релевантно данному intent. 0.0–2.0.

        S72 / §ENIGMA-S72: Значимость события = функция личности, не функция движка.
        Хардкод заменён на модуляцию через drives_base:
          fear         → реакция на насилие/угрозу
          control      → реакция на нарушение порядка (кража)
          significance → реакция на социальное давление (свидетели)
          desire       → готовность к социальному взаимодействию
        """
        # ПУТЬ А: S72 + L3. Линза реальности из текущей проекции, а не архетипа.
        # L0 запрещён. Отсутствие L3 = нейтральная линза (дефолты 0.25).
        _drives = dict(effective_drives.values) if effective_drives else {}
        _fear = _drives.get("fear", 0.25)
        _control = _drives.get("control", 0.25)
        _significance = _drives.get("significance", 0.25)
        _desire = _drives.get("desire", 0.25)

        base = 0.5  # нейтральная релевантность

        # Близкое насилие: страх определяет, насколько это угрожает (S72)
        # ADR-O-112 FIX: Добавлен "PLAYER_ATTACKED" (legacy alias) для снятия слепоты DecisionHub
        _et = event.event_type
        _et_val = _et.value if hasattr(_et, "value") else str(_et)
        _is_violence = _et in (
            "player_attacks",
            "PLAYER_ATTACKED",
            "combat",
            "capture",
        ) or _et_val in ("player_attacks", "PLAYER_ATTACKED", "combat", "capture")
        if _is_violence and event.distance <= 10.0:
            # S72: Страх модулирует реакцию на насилие.
            # fear=0.25 (нейтральный) → +0.5×intensity (как раньше)
            # fear=0.6 (параноик) → +1.2×intensity
            # fear=0.05 (храбрец) → +0.1×intensity
            if intent in (Intent.FLEE.value, Intent.WARN.value):
                base += _fear * event.intensity * 2.0
            if intent == Intent.ATTACK.value:
                # ADR-O-112: Самооборона. Меньше страха = больше готовность драться.
                # Базовый порог 0.3 гарантирует минимальную самооборону даже параноику.
                base += (0.3 + (1.0 - _fear) * 0.7) * event.intensity * 2.0

        # Кража: контроль определяет реакцию на нарушение порядка (S72)
        # control=0.25 → +0.7 (как раньше). control=0.6 → +1.68
        if event.event_type == "theft":
            if intent in (Intent.REPORT.value, Intent.WARN.value):
                base += _control * 2.8

        # Провальное действие всё равно наблюдаемо (решение EventBus)
        if not event.success:
            base *= 0.6  # провал снижает релевантность, но не до нуля

        # Свидетели: значимость определяет социальное давление (S72)
        # significance=0.25 → +0.2 (как раньше). significance=0.6 → +0.48
        if event.witness_count >= 3:
            if intent in (Intent.REPORT.value, Intent.WARN.value):
                base += _significance * 0.8

        # ADR-036: PHYSICS_OF_POWER перемещён в compute() — прямой boost к APPROACH score.
        # В _context_relevance boost размывается через drive_weight (≈0.25),
        # и APPROACH проигрывает OBSERVE/FLEE несмотря на obedience_pressure.

        # Диалог: желание определяет готовность к взаимодействию (S72)
        # desire=0.25 → как раньше. desire=0.6 → сильнее вовлечение.
        # GAP10 FIX: Бонус получают только целевые NPC, а не все в зоне слышимости.
        # ADR-130: Payload target_id fallback. При player_interacts команда
        # адресуется конкретному NPC (target_id в payload от dm_phase.py),
        # но EventContext.target_id может быть None (dm_scene_builder не пробрасывает).
        # Без этого ВСЕ NPC в зоне получают бонус APPROACH/TALK/OBSERVE.
        if event.event_type == "player_interacts":
            _effective_tid = event.target_id
            if _effective_tid is None:
                _ptid = (
                    event.payload.get("target_id")
                    if isinstance(event.payload, dict)
                    else None
                )
                if _ptid:
                    _effective_tid = _ptid
            is_targeted = _effective_tid is None or (
                state and _effective_tid == state.npc_id
            )
            if is_targeted:
                if intent in (Intent.TALK.value, Intent.OBSERVE.value):
                    base += _desire * 2.0  # desire=0.25 → +0.5
                # УБИТ ХАРДКОД: if intent == Intent.APPROACH.value: base += 0.6
                # Теперь подчинение вычисляется через Физику Власти (semantic_action=MOVE)
                if intent in (
                    Intent.REPORT.value,
                    Intent.ATTACK.value,
                    Intent.WARN.value,
                    Intent.INTIMIDATE.value,
                ):
                    base -= _desire * 1.6  # desire=0.25 → -0.4
                if intent == Intent.FLEE.value:
                    # Сильное подавление: нейтральный диалог не должен вызывать побег
                    base -= _desire * 2.8  # desire=0.25 → -0.7

        # Фаза 3.4: WorldTick — проактивные интенты получают базовый бонус
        # Реактивные интенты при world_tick подавляются (нет стимула)
        from app.services.events.event_types import EventType

        if event.event_type == EventType.WORLD_TICK:
            if intent in PROACTIVE_INTENTS:
                base += 0.4  # бонус за проактивность
                # L2.7: Буст от LifeDirection (динамический жизненный проект).
                # Читаем из state, а не из personality (L0). Кризис может сменить направление.
                _direction = getattr(state, "life_direction", "survival")
                _direction_intents = {
                    "family_builder": ["seek_ally", "help", "call_for_help"],
                    "wealth_creator": ["offer_job", "request_service", "trade"],
                    "warrior": ["ambush", "block_path", "call_for_help"],
                    "knowledge_seeker": ["request_service", "seek_ally"],
                    "ruler": ["spread_rumor", "call_for_help", "change_role"],
                    # Кризисные направления (L2.7)
                    "isolation": ["flee", "block_path"],
                    "revenge": ["ambush", "attack"],
                    "hermit": ["flee", "observe"],
                }
                _expected_intents = _direction_intents.get(_direction, [])
                if intent in _expected_intents:
                    base += _desire * 1.5 + _significance * 0.5
            else:
                base -= 0.3  # штраф за реакцию без стимула

        return min(base, 2.0)

    def _emotion_modifier(
        self,
        intent: str,
        emotion: EmotionTag,
        drives: Optional[Dict[str, float]] = None,
        affective_load: float = 0.0,
    ) -> float:
        """S74.5: Инверсия Причинности. Поле правит, тег резонирует.

        AffectField (load + velocity) — первичный драйвер деформации utility.
        EmotionTag — вторичный резонатор: усиливает сигнал, если подтверждён полем,
        или глушится, если оказался "призраком" (поле упало, а тег висит).
        Устраняет POST-HOC AFFECT MODEL и "fearful lock-in".
        """
        # 1. Непрерывная деформация поля (ПЕРВИЧНЫЙ ДРАЙВЕР)
        _field_mod = 0.0
        if affective_load > 0.05:
            # Ускорение угрозы (velocity > 0) усиливает реакцию (срочность)
            _urgency = 1.0
            _fear_drive = (drives or {}).get("fear", 0.25)
            _control_drive = (drives or {}).get("control", 0.25)

            # Нагрузка толкает к осторожности/бегству, если нет контроля
            if intent in (Intent.OBSERVE.value, Intent.WARN.value):
                _field_mod += affective_load * _fear_drive * 0.6 * _urgency
            elif intent == Intent.FLEE.value:
                _field_mod += affective_load * _fear_drive * 0.8 * _urgency
            elif intent in (Intent.ATTACK.value, Intent.INTIMIDATE.value):
                # Контроль перенаправляет энергию страха в превентивную агрессию
                _field_mod -= affective_load * _fear_drive * 0.3
                _field_mod += affective_load * _control_drive * 0.5 * _urgency

        # 2. Дискретный тег (ВТОРИЧНЫЙ РЕЗОНАТОР)
        _BASE: Dict[str, Dict[str, float]] = {
            EmotionTag.ANGRY.value: {
                Intent.ATTACK.value: +0.30,
                Intent.INTIMIDATE.value: +0.20,
                Intent.FLEE.value: -0.20,
                Intent.TRADE.value: -0.15,
            },
            EmotionTag.FEARFUL.value: {
                Intent.FLEE.value: +0.35,
                Intent.OBSERVE.value: +0.20,
                Intent.ATTACK.value: -0.25,
                Intent.TALK.value: -0.10,
            },
            EmotionTag.GRATEFUL.value: {
                Intent.HELP.value: +0.30,
                Intent.TRADE.value: +0.15,
                Intent.ATTACK.value: -0.30,
            },
            EmotionTag.SUSPICIOUS.value: {
                Intent.OBSERVE.value: +0.25,
                Intent.WARN.value: +0.15,
                Intent.TRADE.value: -0.20,
                Intent.HELP.value: -0.15,
            },
        }

        # S75: Collapse of Discrete Emotion Authority.
        # EmotionTag больше не управляет utility. AffectField + Drives = единственный закон.
        # Эмоция — лишь этикетка для UI/LLM, а не причина поведения.

        # 1. Энергия поля (непрерывная скалярная величина)
        _energy = affective_load * 1.0

        # Без энергии поля или личности — нет деформации
        if _energy < 0.01 or not drives:
            return _field_mod

        # 2. Drives = вектор направления энергии
        _fear_dev = drives.get("fear", 0.25) - 0.25
        _control_dev = drives.get("control", 0.25) - 0.25
        _significance_dev = drives.get("significance", 0.25) - 0.25
        _desire_dev = drives.get("desire", 0.25) - 0.25

        redirect = 0.0

        # 3. Распределение энергии аффекта через структуру личности
        # Энергия аффекта (нагрузка) по умолчанию = "энергия стресса/страх".
        if intent == Intent.FLEE.value:
            # Базовый инстинкт + страх; Контроль гасит бегство
            redirect = _energy * (_fear_dev + 0.25) * 0.8 - _energy * _control_dev * 0.5
        elif intent == Intent.ATTACK.value:
            # Страх гасит агрессию; Контроль перенаправляет стресс в превентивный удар
            redirect = _energy * _control_dev * 1.5 - _energy * _fear_dev * 0.3
        elif intent == Intent.OBSERVE.value:
            # Значимость и страх усиливают бдительность
            redirect = (
                _energy * (_significance_dev + 0.25) * 0.5 + _energy * _fear_dev * 0.2
            )
        elif intent == Intent.WARN.value:
            # Значимость = социальное предупреждение об угрозе
            redirect = _energy * _significance_dev * 0.7 + _energy * _fear_dev * 0.1
        elif intent == Intent.TALK.value:
            # Желание = поиск помощи/контакта при стрессе
            redirect = _energy * _desire_dev * 0.6 + _energy * _significance_dev * 0.2
        elif intent == Intent.TRADE.value:
            # Желание + значимость = попытка обменять выгоду на безопасность
            redirect = _energy * _desire_dev * 0.5 + _energy * _significance_dev * 0.3
        elif intent == Intent.HELP.value:
            # Желание + низкий страх = альтруистическая экспансия
            redirect = _energy * _desire_dev * 0.7 - _energy * _fear_dev * 0.2

        # ADR-O-205: Спасение вектора причины для Narrative Projection
        # redirect и победивший драйв передаются наверх для формирования Нарратива
        self._last_redirect = redirect
        self._last_dominant_drive = (
            "control"
            if redirect > 0 and _control_dev > _fear_dev
            else ("fear" if redirect < 0 else "neutral")
        )

        return _field_mod + redirect

    def _trait_modifier(
        self,
        intent: str,
        traits: Dict[str, float],
    ) -> float:
        """Active traits как overlay — не заменяют base, корректируют."""
        _TRAIT_INTENT: Dict[str, Dict[str, float]] = {
            "suspicious": {
                Intent.OBSERVE.value: +0.20,
                Intent.TRADE.value: -0.15,
            },
            "grateful": {
                Intent.HELP.value: +0.20,
                Intent.ATTACK.value: -0.25,
            },
            "aggressive": {
                Intent.ATTACK.value: +0.25,
                Intent.INTIMIDATE.value: +0.15,
                Intent.FLEE.value: -0.20,
            },
        }
        total = 0.0
        for trait, strength in traits.items():
            mods = _TRAIT_INTENT.get(trait, {})
            total += mods.get(intent, 0.0) * strength
        return round(total, 4)

    # Таблица видимых маркеров угрозы — что NPC видит своими глазами
    _THREAT_MARKER_VALUES: Dict[str, float] = {
        "heavy_armor": 0.20,
        "medium_armor": 0.10,
        "weapon_melee": 0.15,
        "weapon_ranged": 0.18,
        "weapon_magic": 0.25,
        "large_build": 0.08,
        "battle_wounds": 0.05,  # следы боёв на теле
    }

    def _compute_risk(self, event: EventContext, state: NPCState) -> float:
        """
        Risk из контекста — решение №7.
        Учитывает свидетелей, дистанцию и видимую силу актора.
        """
        # Социальные взаимодействия — минимальный risk (разговор не угроза)
        _et_val = (
            event.event_type.value
            if hasattr(event.event_type, "value")
            else str(event.event_type)
        )
        # ADR-091 override: "подойди" → event type "move", не "player_interacts"
        # Оба должны считаться социальными (мирными) событиями
        _social_events = {
            "player_interacts",
            "player_spoke",
            "npc_spoke",
            "help",
            "move",
            "player_moved",
        }
        base_risk = 0.1 if _et_val in _social_events else 0.3
        # Свидетели и дистанция усиливают угрозу только для агрессивных событий
        if _et_val not in _social_events:
            base_risk += min(event.witness_count * 0.08, 0.4)
            if event.distance <= 2.0:
                base_risk += 0.2
        if not event.success:
            base_risk *= 0.5

        # Видимая сила — NPC реагирует на броню и оружие, не на скрытые stats
        power_risk = sum(
            self._THREAT_MARKER_VALUES.get(m, 0.0) for m in event.visible_threat_markers
        )
        base_risk += min(power_risk, 0.5)

        # Сцена: активный бой повышает воспринимаемую угрозу
        # Входит в формулу как fear × risk — эффект зависит от характера NPC
        _scene_flags = event.scene_flags if hasattr(event, "scene_flags") else set()
        if "combat_started" in _scene_flags:
            base_risk += 0.25

        # Память: недавние важные события повышают риск
        # "Я видел как ты избил Люсю" — lingering effect через decay
        # Память и давление — только для агрессивных событий.
        # Мирный разговор не становится опаснее от того, что игрок вчера кого-то ударил.
        if _et_val not in _social_events:
            _pressure = state.relationship_cache.get("recent_pressure", 0.0)
            if _pressure > 0.01:
                base_risk += min(_pressure * 0.5, 0.3)

            _memory_penalty = 0.0
            for _m in state.narrative_cache:
                if not hasattr(_m, "importance") or _m.importance < 0.1:
                    continue
                _type = getattr(_m, "event_type", "")
                _weight = (
                    0.15
                    if _type in ("player_attacks", "combat", "intimidation", "theft")
                    else 0.05
                )
                _memory_penalty += _m.importance * _weight
            if _memory_penalty > 0.01:
                base_risk += min(_memory_penalty, 0.3)

        return min(base_risk, 1.0)

    def _intent_inertia(self, state: NPCState) -> float:
        """
        Инерция intent с условным распадом.
        Рост: до INTENT_INERTIA_MAX_TICKS — бонус растёт.
        Decay: включается только при отсутствии прогресса
               (effective_stall > INTENT_SATURATION_TICKS).
        Так NPC держит цель пока движется к ней,
        но теряет намерение если топчется на месте.
        """
        if state.intent is None or state.intent == Intent.IDLE:
            return 0.0

        duration = state.intent_duration
        progress = min(state.intent_progress_ticks, duration)

        # Рост инерции — стандартный
        ratio = min(duration / INTENT_INERTIA_MAX_TICKS, 1.0)
        base = ratio * INTENT_INERTIA_WEIGHT

        # Decay только при бесплодном намерении
        effective_stall = duration - progress
        if effective_stall > INTENT_SATURATION_TICKS:
            excess = effective_stall - INTENT_SATURATION_TICKS
            decay = excess * INTENT_DECAY_RATE
            base = max(0.0, base - decay)

        return base

    def _intent_exhaustion(self, state: NPCState) -> float:
        """Активный штраф за зависание intent без прогресса.

        ЗАЧЕМ: Decay уменьшает inertia bonus, но не делает текущий intent
        хуже альтернатив. Exhaustion — это ОТРИЦАТЕЛЬНЫЙ модификатор к score,
        который заставляет NPC отказаться от застрявшего действия.

        РАЗНИЦА С DECAY:
        - Decay: bonus 0.15 → 0.12 → 0.09 (intent чуть слабее)
        - Exhaustion: score -0.08 → -0.16 → -0.24 (intent активнее проигрывает)

        ВКЛЮЧАЕТСЯ: после INTENT_SATURATION_TICKS без прогресса.
        ПРИМЕРЫ (excess = тики сверх порога):
        - excess=1 → -0.08 (лёгкое раздражение)
        - excess=3 → -0.24 (явное разочарование)
        - excess=5 → -0.40 (принудительная смена)
        """
        if state.intent is None or state.intent == Intent.IDLE:
            return 0.0

        duration = state.intent_duration
        progress = min(state.intent_progress_ticks, duration)
        effective_stall = duration - progress

        if effective_stall <= INTENT_SATURATION_TICKS:
            return 0.0

        excess = effective_stall - INTENT_SATURATION_TICKS
        return excess * INTENT_EXHAUSTION_RATE

    def _get_commitment(self, state: NPCState) -> float:
        """Нормализованная инерция intent ∈ [0..1].

        ЗАЧЕМ: Преобразуем тики в число, которое можно подставить в формулу порога.
        0 = нет инерции (IDLE или первый тик)
        1 = максимальная инерция (держится INTENT_INERTIA_MAX_TICKS)
        """
        if state.intent is None or state.intent == Intent.IDLE:
            return 0.0

        ratio = min(state.intent_duration / INTENT_INERTIA_MAX_TICKS, 1.0)

        # Decay при отсутствии прогресса — снижает commitment
        effective_stall = state.intent_duration - min(
            state.intent_progress_ticks, state.intent_duration
        )
        if effective_stall > INTENT_SATURATION_TICKS:
            excess = effective_stall - INTENT_SATURATION_TICKS
            decay = excess * INTENT_DECAY_RATE * 2  # агрессивнее чем у inertia bonus
            ratio = max(0.0, ratio - decay)

        return round(ratio, 4)

    def _commitment_threshold(self, commitment: float) -> float:
        """Порог давления для смены intent.

        ЗАЧЕМ: Чем выше commitment — тем сложнее сменить intent.
        Формула нелинейная: commitment² даёт плавный рост в начале,
        резкий в середине — NPC "упирается".

        ПРИМЕРЫ:
        - commitment=0.0 → threshold=0.15 (лёгкая смена)
        - commitment=0.5 → threshold=0.34
        - commitment=1.0 → threshold=0.53 (очень трудно сменить)
        """
        return COMMITMENT_BASE_THRESHOLD * (1 + (commitment**2) * COMMITMENT_K)

    def _switching_cost(
        self,
        state: NPCState,
        personality: NPCPersonality,
        commitment: float,
        effective_drives: Optional["EffectiveDrives"] = None,  # ПУТЬ А: L3 проекция
    ) -> float:
        """
        Стоимость смены intent — вычитается из score всех НЕ текущих интентов.
        Три оси: возраст intent, эмоциональная вовлечённость, соответствие identity.

        ЗАЧЕМ: делает смену intent реально дорогой, а не просто трудно-порогово.
        NPC с высоким стрессом и долгим intent не бросает его при первом сигнале.
        """
        # Ось 1: возраст intent (нормализован через commitment)
        age_cost = commitment * SWITCHING_COST_AGE_K

        # Ось 2: эмоциональная вовлечённость (высокий стресс = труднее переключиться)
        emotion_cost = min(state.stress / 100.0, 1.0) * SWITCHING_COST_EMOTION_K

        # ПУТЬ А: Ось 3. Identity определяется текущей деформацией (L3), не архетипом (L0).
        # L0 оставлен как initial seed только для загрузки.
        _drives = dict(effective_drives.values) if effective_drives else {}
        current_drive = max(_drives, key=_drives.get) if _drives else ""
        _DRIVE_INTENTS = {
            "control": {
                Intent.ATTACK.value,
                Intent.WARN.value,
                Intent.INTIMIDATE.value,
                Intent.BLOCK_PATH.value,
                Intent.AMBUSH.value,
            },
            "fear": {Intent.FLEE.value, Intent.OBSERVE.value},
            "desire": {
                Intent.TRADE.value,
                Intent.TALK.value,
                Intent.OFFER_JOB.value,
                Intent.REQUEST_SERVICE.value,
                Intent.CHANGE_ROLE.value,
            },
            "significance": {
                Intent.HELP.value,
                Intent.TALK.value,
                Intent.SEEK_ALLY.value,
                Intent.SPREAD_RUMOR.value,
                Intent.CALL_FOR_HELP.value,
            },
        }
        current_intent_str = state.intent.value if state.intent else ""
        aligned = current_intent_str in _DRIVE_INTENTS.get(current_drive, set())
        identity_cost = SWITCHING_COST_IDENTITY_K if aligned else 0.0

        return round(SWITCHING_COST_BASE + age_cost + emotion_cost + identity_cost, 4)

    # ─────────────────────────────────────────────────────────────────────────
    # Вспомогательные методы
    # ─────────────────────────────────────────────────────────────────────────

    def _resolve_target(
        self,
        intent: str,
        event: EventContext,
        state: NPCState,
        spatial_query: Optional[Any] = None,
        all_npc_ids: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Определяет цель intent."""
        if all_npc_ids is None:
            all_npc_ids = []
        if intent in (Intent.IDLE.value, Intent.OBSERVE.value):
            return None
        if intent == Intent.FLEE.value:
            return event.actor_id  # Источник угрозы — от кого бежим

        from app.services.events.event_types import EventType
        from app.services.npc.social_target_resolver import SocialTargetResolver

        # Если есть явная цель (игрок атаковал/приказал) — используем её
        if event.target_id and event.event_type != EventType.WORLD_TICK:
            return event.target_id

        # S96: Все социальные и проактивные интенты используют SocialTargetResolver
        # Если NPC хочет работать с людьми (TALK, TRADE, HELP, APPROACH, SPREAD_RUMOR и т.д.), он ищет цель.
        if intent in self._VERBAL_INTENTS or intent == Intent.APPROACH.value:
            _target = SocialTargetResolver.resolve(state, spatial_query, all_npc_ids)
            if _target:
                return _target
            # Fallback на актора, если резолвер ничего не нашёл
            return event.actor_id if event.actor_id != state.npc_id else None

        # По умолчанию — актор события
        return event.actor_id

    def _compute_deltas(
        self,
        state: NPCState,
        personality: NPCPersonality,
        event: EventContext,
        intent: str,
    ) -> List[StateDeltas]:
        """R2-P1: Делегирует социальные дельты SocialDeltaEngine.

        DecisionHub больше не определяет "что значит событие".
        Модуляция личностью — внутри SocialDeltaEngine
        через RelationshipResponseProfile (drives_base → множители).

        При нейтральных drives (0.25) результат идентичен старому коду.
        Исправлен баг: player_threatens объединял два перезаписанных блока.
        """
        return self._social_delta_engine.process(
            state=state,
            personality=personality,
            event=event,
            intent=intent,
        )

    def _explain_mode(
        self,
        state: NPCState,
        personality: NPCPersonality,
        event: EventContext,
    ) -> AgentAction:
        """
        Intent.EXPLAIN — игрок спросил "почему ты так себя ведёшь?".
        DecisionHub выбирает top-2 факта из narrative_cache.
        LLM получает их в VerbalizationContext.
        """
        facts = state.get_top_narrative_facts(n=2)
        _decision = DecisionResult(
            npc_id=state.npc_id,
            intent=Intent.EXPLAIN,
            intent_target=event.actor_id,
            score=1.0,
            scores_trace={"explain": 1.0},
            deltas=[],
            narrative_fact=facts[0].summary if facts else None,
            explanation_mode=True,
        )
        _communication = self._build_communication(
            npc_id=state.npc_id,
            intent_value=Intent.EXPLAIN.value,
            intent_target=event.actor_id,
            topic="объяснение_поведения",
            emotion_value=state.emotion.value
            if hasattr(state.emotion, "value")
            else str(state.emotion),
            scores=None,
        )
        return AgentAction(decision=_decision, communication=_communication)
