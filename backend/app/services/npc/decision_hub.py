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

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Целевая архитектура данных (L0/L2)
from app.models.npc_profile import NPCProfileL0
from app.models.npc_state import NPCState

# Легаси-типы, всё ещё используемые в логике (Enum'ы и контракты результатов)
from app.models.npc_state import (
    EmotionTag,
    Intent,
    NarrativeFact,
    WillState,
)
from app.services.events.event_types import EventType
from app.models.behavior_mask import BehaviorMask

from app.core.constants import (
    SCORE_NOISE_RANGE,
    INTENT_INERTIA_MAX_TICKS,
    INTENT_INERTIA_WEIGHT,
    INTENT_SATURATION_TICKS,
    INTENT_DECAY_RATE,
    INTENT_EXHAUSTION_RATE,
    MIN_INTENT_SCORE,
    COMMITMENT_BASE_THRESHOLD,
    COMMITMENT_K,
    COMMITMENT_BONUS_K,
    SWITCHING_COST_BASE,
    SWITCHING_COST_AGE_K,
    SWITCHING_COST_EMOTION_K,
    SWITCHING_COST_IDENTITY_K,
    REACTIVE_URGENCY_THRESHOLD,
    PROVOCATION_THREAT_THRESHOLD,
)
from app.services.economy.opportunity_engine import (
    OpportunityContext,
    OpportunityEngine,
    OpportunityResult,
)


# ── Проактивные интенты: доступны только при WORLD_TICK ──────────────────────
PROACTIVE_INTENTS: frozenset = frozenset({
    Intent.BLOCK_PATH, Intent.AMBUSH, Intent.SEEK_ALLY,
    Intent.OFFER_JOB, Intent.REQUEST_SERVICE, Intent.SPREAD_RUMOR,
    Intent.CALL_FOR_HELP, Intent.CHANGE_ROLE,
})

# Роли, которым доступны перехватывающие/засадные интенты
# Остальные (торговцы, трактирщики, ремесленники) — заблокированы
COMBAT_CAPABLE_ROLES: frozenset = frozenset({
    "стражник", "охранник", "наёмник", "телохранитель",
    "вор", "бандит", "убийца", "наёмный убийца",
    "солдат", "воин", "рыцарь", "варвар", "головорез",
})


# ─────────────────────────────────────────────────────────────────────────────
# DecisionResult — только данные, никаких мутаций
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StateDeltas:
    """Дельты которые StateApplicator применит к NPCState атомарно."""
    stress_delta:           float = 0.0
    stress_delta_effective: float = 0.0
    emotion_delta:          float = 0.0
    emotion_tag:     Optional[EmotionTag] = None
    trust_delta:     float = 0.0
    fear_delta:      float = 0.0
    trait_updates:   Dict[str, float] = field(default_factory=dict)
    new_trauma:      Optional[str] = None
    
    # --- Причинность: источник дельты (Шаг A.3) ---
    source:          str = "unknown"   # event_type или "break_system", "life_engine"
    
    # --- R6.4: Команды для системы слома ---
    identity_integrity_delta:   float = 0.0
    pressure_resistance_delta:  float = 0.0
    will_state_override: Optional[WillState] = None



@dataclass
class DecisionResult:
    """
    Результат DecisionHub.compute() — read-only контракт.
    StateApplicator читает это и применяет изменения атомарно.
    """
    npc_id:          str
    intent:          Intent
    intent_target:   Optional[str]
    score:           float                          # итоговый score победившего intent
    scores_trace:    Dict[str, float]               # все scores для калибровки R4.2
    deltas:          StateDeltas
    narrative_fact:  Optional[NarrativeFact] = None # новый факт для narrative_cache
    explanation_mode: bool = False                  # True если intent=EXPLAIN




# ─────────────────────────────────────────────────────────────────────────────
# EventContext — что произошло в мире
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EventContext:
    """
    Контекст события для DecisionHub.
    Формируется в game_loop из EventDTO + SceneState.
    """
    event_type:              EventType
    actor_id:                str
    success:                 bool  = True
    intensity:               float = 1.0     # кап 1.5 применяется в __post_init__
    distance:                float = 3.0
    witness_count:           int   = 1
    location:                str   = ""
    day:                     int   = 0
    # Видимые маркеры угрозы — что NPC воспринимает, не реальные stats игрока
    visible_threat_markers:  List[str] = field(default_factory=list)
    # Текущая активность цели — для контекстной релевантности
    target_routine:          str   = "working"
    # Факты сцены — NPC помнит что происходило в локации (не только текущее действие)
    scene_flags:             Set[str] = field(default_factory=set)
    scene_facts:             List[str] = field(default_factory=list)

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


    def __init__(self, seed: Optional[int] = None) -> None:
        # seed per-session — воспроизводимость при отладке (решение №12)
        self._rng = random.Random(seed)


    def compute(
        self,
        state:           NPCState,
        personality:     NPCProfileL0,
        event:           EventContext,
        scene_state:     Optional[Dict[str, Any]] = None,
        opportunity_ctx: Optional[OpportunityContext] = None,
        identity:        Optional["NPCIdentityL1"] = None,
        eco_modifiers:     Optional[Dict[str, float]] = None,
        social_modifiers:  Optional[Dict[str, float]] = None,
        reputation_modifiers: Optional[Dict[str, float]] = None,
        drive_modifiers:   Optional[Dict[str, float]] = None,
        reflex_constraints: Optional[Dict] = None,
    ) -> DecisionResult:
        """
        Основной метод. READ ONLY — state не мутируется.
        Принимает state уже после применения BreakProgressEngine
        (game_loop вызывает apply_break через StateApplicator перед compute).
        Возвращает DecisionResult для StateApplicator.
        """
        # Игрок спросил "почему?" → специальный режим объяснения
        if event.event_type == "player_asks_why":
            return self._explain_mode(state, personality, event)

        # R6.3 — оцениваем момент скрытого действия до фильтрации интентов.
        # OpportunityContext=None → inactive() без ошибки, backward-compatible.
        # OpportunityEngine требует контекст и строку will_state, а не весь state
        opportunity = OpportunityEngine().calculate(
            ctx=opportunity_ctx or OpportunityContext(),
            will_state=state.will_state.value if hasattr(state.will_state, "value") else str(state.will_state)
        )

        # L1 черты: только из NPCIdentityL1
        active_traits: Dict[str, float] = identity.active_traits if identity else {}
        possible = self._get_possible_intents(state, personality, event, opportunity)
        scores   = self._score_all(state, personality, event, possible, opportunity, active_traits)

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
                scores = {
                    k: v for k, v in scores.items()
                    if k in allowed
                }

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

        if not scores:
            # Защита от ValueError: если все интенты отфильтрованы — IDLE
            return DecisionResult(
                npc_id=state.npc_id,
                intent=Intent.IDLE,
                intent_target=None,
                score=0.0,
                scores_trace={"fallback": "no_available_intents"},
                deltas=StateDeltas(),
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
            cost = self._switching_cost(state, personality, commitment)
            for k in scores:
                if k != current_intent_str_pre:
                    scores[k] = round(scores[k] - cost, 4)

        best_candidate_str, best_score = max(scores.items(), key=lambda x: x[1])  # (str, float)

        # ── Commitment Model: порог смены intent ──
        threshold = self._commitment_threshold(commitment)
        
        # Текущий score (если intent есть и он в кандидатах)
        current_intent_str = state.intent.value if state.intent else None
        current_score = scores.get(current_intent_str, 0.0) if current_intent_str else 0.0
        pressure = best_score - current_score  # >0 значит новый лучше
        
        # Reactive urgency: высокая тревога → принудительная смена
        fear_value = state.stress if hasattr(state, 'stress') else 0.0
        force_switch = fear_value > REACTIVE_URGENCY_THRESHOLD
        
        # ── Pressure Accumulation: накопление давления по парам ──
        # Ключ ВСЕГДА (str, str) — best_candidate_str из scores
        acc_key = (current_intent_str, best_candidate_str) if current_intent_str else None
        accumulated = 0.0
        if acc_key:
            accumulated = state.pressure_accumulator.get(acc_key, 0.0)
            if pressure > 0:
                accumulated = min(accumulated + pressure, 1.0)
            else:
                accumulated *= 0.85
            state.pressure_accumulator[acc_key] = accumulated
        
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
            best_score  = 0.0

        intent_target = self._resolve_target(best_intent, event, state)
        deltas        = self._compute_deltas(state, personality, event, best_intent)
        narrative     = self._make_narrative_fact(event, best_intent, state, deltas)

        # В scores_trace попадают ТОЛЬКО числа для калибровки R4.2.
        # Строки (причины срабатывания) отсекаются.
        opp_trace = {f"opp_{k}": v for k, v in opportunity.score_trace.items() if isinstance(v, (int, float))}

        logger.debug(f"[DECISION_HUB] {state.npc_id}: intent={best_intent} score={round(best_score, 3)} event={event.event_type}")
        return DecisionResult(
            npc_id         = state.npc_id,
            intent         = Intent(best_intent),
            intent_target  = intent_target,
            score          = round(best_score, 4),
            scores_trace   = {
                **{k: round(v, 4) for k, v in scores.items()},
                **opp_trace,
                # break_stage виден в state.identity_integrity — трейс через snapshot()
            },
            deltas         = deltas,
            narrative_fact = narrative,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Action Space — enum + фильтр доступности (решение №4)
    # ─────────────────────────────────────────────────────────────────────────

    def _get_possible_intents(
        self,
        state:       NPCState,
        personality: NPCPersonality,
        event:       EventContext,
        opportunity: OpportunityResult,
    ) -> List[str]:
        from app.services.events.event_types import EventType

        # Проактивные интенты — ТОЛЬКО при world_tick, не при реакциях на игрока
        _is_proactive_tick = event.event_type == EventType.WORLD_TICK

        all_intents = [i.value for i in Intent
                       if i not in (Intent.IDLE, Intent.EXPLAIN)]

        filtered = []
        for intent in all_intents:
            # Фильтруем проактивные интенты при реактивных событиях
            if not _is_proactive_tick and intent in PROACTIVE_INTENTS:
                continue
            if self._is_intent_available(intent, state, personality, opportunity):
                filtered.append(intent)

        filtered.append(Intent.IDLE.value)
        return filtered

    def _is_intent_available(
        self,
        intent:      str,
        state:       NPCState,
        personality: NPCPersonality,
        opportunity: OpportunityResult,
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
            drives = getattr(personality, 'drives_base', {})
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
        state:        NPCState,
        personality:  NPCPersonality,
        event:        EventContext,
        possible:     List[str],
        opportunity:  OpportunityResult,
        active_traits: Dict[str, float] = None,  # L1 черты, опционально
    ) -> Dict[str, float]:
        """
        Считает score для каждого доступного intent.
        Early exit: трусливый NPC (fear > 0.6) не рассматривает агрессию.
        """
        scores: Dict[str, float] = {}
        inertia     = self._intent_inertia(state)
        fear_drive  = personality.drives_base.get("fear", 0.0)
        skip_aggro  = fear_drive > 0.6  # early exit для трусливых NPC

        _AGGRO_INTENTS = {Intent.ATTACK.value, Intent.INTIMIDATE.value}

        for intent_str in possible:
            # Трусливый NPC пропускает агрессию — если только
            # OpportunityEngine не разблокировал интент. Момент важнее страха.
            if skip_aggro and intent_str in _AGGRO_INTENTS:
                if intent_str not in opportunity.unlocked_intents:
                    scores[intent_str] = -1.0
                    continue

            components = self._score_components(intent_str, state, personality, event, opportunity, active_traits or {})
            base = sum(components.values())
            
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

        return scores

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
            if intent in (Intent.ATTACK.value, Intent.INTIMIDATE.value, Intent.WARN.value):
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
        trust:  float,
        fear:   float,
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
            mod -= trust * 0.25          # от друга бежать тяжелее
        elif intent in (Intent.ATTACK.value, Intent.INTIMIDATE.value):
            # Страх полностью парализует агрессию
            mod -= fear * 0.9
            mod -= trust * 0.2
        elif intent == Intent.OBSERVE.value:
            # Страх делает наблюдение более вероятным
            mod += fear * 0.40
        else:
            # Социальные действия (TALK, TRADE, HELP и т.д.)
            mod += trust * 0.30
            mod -= fear * 0.35           # страх мешает общению

        return round(mod, 4)

    def _score_components(
        self,
        intent:        str,
        state:         NPCState,
        personality:   NPCPersonality,
        event:         EventContext,
        opportunity:   OpportunityResult,
        active_traits: Dict[str, float] = None,  # L1 черты из NPCIdentityL1
    ) -> Dict[str, float]:
        """
        Возвращает словарь компонентов score — для полного trace в R4.2.
        Каждый компонент виден отдельно: что именно перевесило.
        """
        drives = personality.drives_base
        rel    = state.relationship_cache
        fear   = rel.get("fear", 0.0)
        trust  = rel.get("trust", 0.0)
        risk   = self._compute_risk(event, state)

        drive_score  = self._drive_relevance(intent, drives, event)
        emotion_mod  = self._emotion_modifier(intent, state.emotion)
        rel_mod      = self._relationship_modifier(intent, trust, fear)
        trait_mod    = self._trait_modifier(intent, active_traits or {})

        # Risk теперь intent-aware (Disco Elysium style)
        # Высокий fear + высокий risk = мощный FLEE, а не паралич
        if intent == Intent.FLEE.value:
            # Для FLEE: fear используется дважды — как буст (rel_mod) и как множитель риска.
            # Это намеренно: страх перед конкретным актором + опасность ситуации — разные сигналы.
            # rel_mod = fear × 0.65 (отношение к актору)
            # risk_penalty = fear × risk × 0.9 (оценка угрозы ситуации)
            risk_penalty = round(fear * risk * 0.9, 4)
        elif intent == Intent.OBSERVE.value:
            risk_penalty = round(fear * risk * 0.5, 4)      # осторожное наблюдение
        elif intent in (Intent.ATTACK.value, Intent.INTIMIDATE.value):
            # Агрессия требует явной провокации — строковое сравнение (EventContext.event_type: str)
            # Без провокации штраф -0.54 делает ATTACK хуже чем TALK/WARN
            _PROVOCATION_TYPES = {"player_attacks", "combat", "intimidation", "capture", "player_insults", "player_threatens"}
            # Просто количество уникальных угроз × 0.1
            threat_level = len(set(event.visible_threat_markers)) * 0.1
            is_provoked = (
                event.event_type in _PROVOCATION_TYPES
                or threat_level >= PROVOCATION_THREAT_THRESHOLD
            )
            provocation_gate = 1.0 if is_provoked else 0.1
            risk_penalty = round((-fear * risk * 1.25 - (1.0 - provocation_gate) * 0.6), 4)
        else:
            risk_penalty = round(-fear * risk * 0.3, 4)     # лёгкий штраф для всего остального

        # R6.3 — буст разблокированных интентов пропорционален opportunity_score.
        # Делает скрытое действие конкурентоспособным без ломания баланса формулы.
        # Буст даётся только если интент разблокирован сломленным NPC
        opportunity_mod = opportunity.score if intent in opportunity.unlocked_intents else 0.0

        return {
            "drive":        round(drive_score, 4),
            "emotion":      round(emotion_mod, 4),
            "relationship": round(rel_mod, 4),
            "risk_penalty": risk_penalty,
            "trait":        round(trait_mod, 4),
            "opportunity":  round(opportunity_mod, 4),
        }

    def _score_one(
        self,
        intent:      str,
        state:       NPCState,
        personality: NPCPersonality,
        event:       EventContext,
        opportunity: OpportunityResult,  # Добавлен недостающий параметр
    ) -> float:
        """Суммарный score без компонентов — для внутреннего использования."""
        return sum(self._score_components(intent, state, personality, event, opportunity).values())

    def _drive_relevance(
        self,
        intent:  str,
        drives:  Dict[str, float],
        event:   EventContext,
    ) -> float:
        """drive_weight × context_relevance."""
        # Маппинг intent → доминирующий drive
        _INTENT_DRIVE: Dict[str, str] = {
            Intent.ATTACK.value:     "control",
            Intent.INTIMIDATE.value: "control",
            Intent.REPORT.value:     "control",
            Intent.WARN.value:       "control",
            Intent.FLEE.value:       "fear",
            Intent.OBSERVE.value:    "fear",
            Intent.TRADE.value:      "desire",
            Intent.HELP.value:       "significance",
            Intent.TALK.value:       "significance",
            Intent.IDLE.value:       "fear",
            # Проактивные интенты (Фаза 3.4)
            Intent.BLOCK_PATH.value:    "control",
            Intent.AMBUSH.value:        "control",
            Intent.SEEK_ALLY.value:     "significance",
            Intent.OFFER_JOB.value:     "desire",
            Intent.REQUEST_SERVICE.value: "desire",
            Intent.SPREAD_RUMOR.value:  "significance",
            Intent.CALL_FOR_HELP.value: "significance",
            Intent.CHANGE_ROLE.value:   "desire",
        }
        drive_key = _INTENT_DRIVE.get(intent, "desire")
        drive_weight = drives.get(drive_key, 0.25)

        # context_relevance — насколько событие активирует этот drive
        context_relevance = self._context_relevance(intent, event)

        return round(drive_weight * context_relevance, 4)

    def _context_relevance(self, intent: str, event: EventContext) -> float:
        """Насколько событие релевантно данному intent. 0.0–2.0."""
        base = 0.5  # нейтральная релевантность

        # Близкое насилие делает побег и предупреждение более релевантными
        if event.event_type in ("player_attacks", "combat", "capture") and event.distance <= 3.0:
            if intent in (Intent.FLEE.value, Intent.WARN.value):
                base += 0.8 * event.intensity
            if intent == Intent.ATTACK.value:
                base += 0.5 * event.intensity

        # Кража активирует донос и предупреждение
        if event.event_type == "theft":
            if intent in (Intent.REPORT.value, Intent.WARN.value):
                base += 0.7

        # Провальное действие всё равно наблюдаемо (решение EventBus)
        if not event.success:
            base *= 0.6  # провал снижает релевантность, но не до нуля

        # Много свидетелей повышает социальное давление
        if event.witness_count >= 3:
            if intent in (Intent.REPORT.value, Intent.WARN.value):
                base += 0.2

        # Диалог активирует разговорные интенты, подавляет нелогичные
        if event.event_type == "player_interacts":
            if intent in (Intent.TALK.value, Intent.OBSERVE.value):
                base += 0.5
            if intent in (Intent.REPORT.value, Intent.ATTACK.value, Intent.WARN.value, Intent.INTIMIDATE.value):
                base -= 0.4
            if intent == Intent.FLEE.value:
                # Сильное подавление: нейтральный диалог не должен вызывать побег
                # даже при низком доверии (rel_mod компенсируется контекстом)
                base -= 0.7

        # Фаза 3.4: WorldTick — проактивные интенты получают базовый бонус
        # Реактивные интенты при world_tick подавляются (нет стимула)
        from app.services.events.event_types import EventType
        if event.event_type == EventType.WORLD_TICK:
            if intent in PROACTIVE_INTENTS:
                base += 0.4  # бонус за проактивность
            else:
                base -= 0.3  # штраф за реакцию без стимула

        return min(base, 2.0)

    def _emotion_modifier(self, intent: str, emotion: EmotionTag) -> float:
        """Эмоция смещает вероятность intent."""
        _EMOTION_INTENT_MOD: Dict[str, Dict[str, float]] = {
            EmotionTag.ANGRY.value: {
                Intent.ATTACK.value:     +0.30,
                Intent.INTIMIDATE.value: +0.20,
                Intent.FLEE.value:       -0.20,
                Intent.TRADE.value:      -0.15,
            },
            EmotionTag.FEARFUL.value: {
                Intent.FLEE.value:       +0.35,
                Intent.OBSERVE.value:    +0.20,
                Intent.ATTACK.value:     -0.25,
                Intent.TALK.value:       -0.10,
            },
            EmotionTag.GRATEFUL.value: {
                Intent.HELP.value:       +0.30,
                Intent.TRADE.value:      +0.15,
                Intent.ATTACK.value:     -0.30,
            },
            EmotionTag.SUSPICIOUS.value: {
                Intent.OBSERVE.value:    +0.25,
                Intent.WARN.value:       +0.15,
                Intent.TRADE.value:      -0.20,
                Intent.HELP.value:       -0.15,
            },
        }
        mods = _EMOTION_INTENT_MOD.get(emotion.value, {})
        return mods.get(intent, 0.0)

    def _trait_modifier(
        self,
        intent: str,
        traits: Dict[str, float],
    ) -> float:
        """Active traits как overlay — не заменяют base, корректируют."""
        _TRAIT_INTENT: Dict[str, Dict[str, float]] = {
            "suspicious": {
                Intent.OBSERVE.value: +0.20,
                Intent.TRADE.value:   -0.15,
            },
            "grateful": {
                Intent.HELP.value:    +0.20,
                Intent.ATTACK.value:  -0.25,
            },
            "aggressive": {
                Intent.ATTACK.value:      +0.25,
                Intent.INTIMIDATE.value:  +0.15,
                Intent.FLEE.value:        -0.20,
            },
        }
        total = 0.0
        for trait, strength in traits.items():
            mods = _TRAIT_INTENT.get(trait, {})
            total += mods.get(intent, 0.0) * strength
        return round(total, 4)

    # Таблица видимых маркеров угрозы — что NPC видит своими глазами
    _THREAT_MARKER_VALUES: Dict[str, float] = {
        "heavy_armor":    0.20,
        "medium_armor":   0.10,
        "weapon_melee":   0.15,
        "weapon_ranged":  0.18,
        "weapon_magic":   0.25,
        "large_build":    0.08,
        "battle_wounds":  0.05,   # следы боёв на теле
    }

    def _compute_risk(self, event: EventContext, state: NPCState) -> float:
        """
        Risk из контекста — решение №7.
        Учитывает свидетелей, дистанцию и видимую силу актора.
        """
        base_risk = 0.3
        base_risk += min(event.witness_count * 0.08, 0.4)
        if event.distance <= 2.0:
            base_risk += 0.2
        if not event.success:
            base_risk *= 0.5

        # Видимая сила — NPC реагирует на броню и оружие, не на скрытые stats
        power_risk = sum(
            self._THREAT_MARKER_VALUES.get(m, 0.0)
            for m in event.visible_threat_markers
        )
        base_risk += min(power_risk, 0.5)

        # Сцена: активный бой повышает воспринимаемую угрозу
        # Входит в формулу как fear × risk — эффект зависит от характера NPC
        _scene_flags = event.scene_flags if hasattr(event, "scene_flags") else set()
        if "combat_started" in _scene_flags:
            base_risk += 0.25

        # Память: недавние важные события повышают риск
        # "Я видел как ты избил Люсю" — lingering effect через decay
        _pressure = state.relationship_cache.get("recent_pressure", 0.0)
        if _pressure > 0.01:
            base_risk += min(_pressure * 0.5, 0.3)

        # R1: Смысловая память — EventMemory с decay importance
        # Насилие 3 тика назад: importance=0.6 → risk+=0.09 (лёгкая настороженность)
        # Насилие 1 тик назад: importance=0.95 → risk+=0.14 (заметное влияние)
        _memory_penalty = 0.0
        for _m in state.narrative_cache:
            if not hasattr(_m, "importance") or _m.importance < 0.1:
                continue
            _type = getattr(_m, "event_type", "")
            _weight = 0.15 if _type in ("player_attacks", "combat", "intimidation", "theft") else 0.05
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
        base  = ratio * INTENT_INERTIA_WEIGHT

        # Decay только при бесплодном намерении
        effective_stall = duration - progress
        if effective_stall > INTENT_SATURATION_TICKS:
            excess = effective_stall - INTENT_SATURATION_TICKS
            decay  = excess * INTENT_DECAY_RATE
            base   = max(0.0, base - decay)

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
        effective_stall = state.intent_duration - min(state.intent_progress_ticks, state.intent_duration)
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
        return COMMITMENT_BASE_THRESHOLD * (1 + (commitment ** 2) * COMMITMENT_K)

    def _switching_cost(
        self,
        state:       NPCState,
        personality: NPCPersonality,
        commitment:  float,
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

        # Ось 3: соответствие identity (если intent совпадает с доминирующим drive)
        current_drive = max(personality.drives_base, key=personality.drives_base.get) if personality.drives_base else ""
        _DRIVE_INTENTS = {
            "control":      {Intent.ATTACK.value, Intent.WARN.value, Intent.INTIMIDATE.value, Intent.BLOCK_PATH.value, Intent.AMBUSH.value},
            "fear":         {Intent.FLEE.value, Intent.OBSERVE.value},
            "desire":       {Intent.TRADE.value, Intent.TALK.value, Intent.OFFER_JOB.value, Intent.REQUEST_SERVICE.value, Intent.CHANGE_ROLE.value},
            "significance": {Intent.HELP.value, Intent.TALK.value, Intent.SEEK_ALLY.value, Intent.SPREAD_RUMOR.value, Intent.CALL_FOR_HELP.value},
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
        intent:  str,
        event:   EventContext,
        state:   NPCState,
    ) -> Optional[str]:
        """Определяет цель intent."""
        if intent in (Intent.IDLE.value, Intent.OBSERVE.value):
            return None
        if intent == Intent.FLEE.value:
            return None
        # Фаза 3.4: Проактивные интенты при world_tick не имеют явной цели
        # (actor_id = сам NPC). DM определит цель из контекста сцены.
        from app.services.events.event_types import EventType
        if event.event_type == EventType.WORLD_TICK and intent in PROACTIVE_INTENTS:
            return None
        # По умолчанию — актор события
        return event.actor_id

    def _compute_deltas(
        self,
        state:       NPCState,
        personality: NPCPersonality,
        event:       EventContext,
        intent:      str,
    ) -> StateDeltas:
        """
        Вычисляет дельты состояния с учётом saturation (diminishing returns).
        StateApplicатор применит их атомарно.
        """
        from app.services.npc.math_utils import apply_saturation
        
        deltas = StateDeltas(source=event.event_type)

        # Стресс и гнев от оскорблений — провокация без физического насилия
        if event.event_type == "player_insults":
            raw_stress = 12.0 * event.intensity
            _, deltas.stress_delta = apply_saturation(
                current=state.stress, delta=raw_stress
            )
            deltas.emotion_tag = EmotionTag.ANGRY
            deltas.emotion_delta = round(15.0 * event.intensity, 2)
            raw_trust = -8.0 * event.intensity
            _, deltas.trust_delta = apply_saturation(
                current=state.relationship_cache.get("trust", 0.0),
                delta=raw_trust,
                min_val=-100.0,
                max_val=100.0,
            )
            raw_fear = -5.0 * event.intensity
            _, deltas.fear_delta = apply_saturation(
                current=state.relationship_cache.get("fear", 0.0),
                delta=raw_fear,
                min_val=-100.0,
                max_val=100.0,
            )

        # Стресс от прямых угроз — "замолчи", "на колени", "сдохнешь"
        elif event.event_type == "player_threatens":
            raw_stress = 10.0 * event.intensity
            _, deltas.stress_delta = apply_saturation(
                current=state.stress, delta=raw_stress
            )
            deltas.emotion_tag = EmotionTag.ANGRY
            deltas.emotion_delta = round(12.0 * event.intensity, 2)
            raw_trust = -5.0 * event.intensity
            _, deltas.trust_delta = apply_saturation(
                current=state.relationship_cache.get("trust", 0.0),
                delta=raw_trust,
                min_val=-100.0,
                max_val=100.0,
            )
            # Угроза повышает страх перед игроком (меньше чем атака, но ощутимо)
            raw_fear = 4.0 * event.intensity
            _, deltas.fear_delta = apply_saturation(
                current=state.relationship_cache.get("fear", 0.0),
                delta=raw_fear,
                min_val=-100.0,
                max_val=100.0,
            )

        # Стресс от косвенных угроз — "жена видел с незнакомцем"
        elif event.event_type == "player_threatens_indirect":
            raw_stress = 8.0 * event.intensity
            _, deltas.stress_delta = apply_saturation(
                current=state.stress, delta=raw_stress
            )
            deltas.emotion_tag = EmotionTag.FEARFUL
            deltas.emotion_delta = round(10.0 * event.intensity, 2)
            raw_trust = -6.0 * event.intensity
            _, deltas.trust_delta = apply_saturation(
                current=state.relationship_cache.get("trust", 0.0),
                delta=raw_trust,
                min_val=-100.0,
                max_val=100.0,
            )
            # Косвенная угроза — страх ниже прямой, но присутствует
            raw_fear = 2.5 * event.intensity
            _, deltas.fear_delta = apply_saturation(
                current=state.relationship_cache.get("fear", 0.0),
                delta=raw_fear,
                min_val=-100.0,
                max_val=100.0,
            )

        # Стресс от физического насилия — player_attacks из Router
        elif event.event_type == "player_attacks":
            raw_stress = 18.0 * event.intensity
            _, deltas.stress_delta = apply_saturation(
                current=state.stress, delta=raw_stress
            )
            deltas.emotion_tag = EmotionTag.FEARFUL
            deltas.emotion_delta = round(20.0 * event.intensity, 2)
            raw_trust = -10.0 * event.intensity
            _, deltas.trust_delta = apply_saturation(
                current=state.relationship_cache.get("trust", 0.0),
                delta=raw_trust,
                min_val=-100.0,
                max_val=100.0,
            )
            raw_fear = 8.0 * event.intensity
            _, deltas.fear_delta = apply_saturation(
                current=state.relationship_cache.get("fear", 0.0),
                delta=raw_fear,
                min_val=-100.0,
                max_val=100.0,
            )

        # Стресс от насилия рядом (combat/capture от других источников)
        elif event.event_type in ("combat", "capture") and event.distance <= 5.0:
            raw_stress = 15.0 * event.intensity
            _, deltas.stress_delta = apply_saturation(
                current=state.stress, delta=raw_stress
            )

        # Эмоциональная реакция (пока без saturation — нет жёсткого максимума)
        emotion_map = {
            "combat":      (EmotionTag.FEARFUL,   +20.0),
            "theft":       (EmotionTag.ANGRY,      +15.0),
            "intimidation":(EmotionTag.FEARFUL,    +18.0),
            "help":        (EmotionTag.GRATEFUL,   +12.0),
            "dialogue_key":(EmotionTag.NEUTRAL,    +5.0),
            "player_insults":(EmotionTag.ANGRY,    +15.0),
            "player_threatens":(EmotionTag.ANGRY, +12.0),
            "player_threatens_indirect":(EmotionTag.FEARFUL, +10.0),
            "player_attacks":(EmotionTag.FEARFUL, +20.0),
            "player_interacts":(EmotionTag.NEUTRAL, +2.0),
        }
        for key, (tag, delta) in emotion_map.items():
            if key in event.event_type:
                deltas.emotion_tag   = tag
                deltas.emotion_delta = round(delta * event.intensity, 2)
                break

        # Отношения: доверие и страх — с saturation (пределы -100..100)
        if event.event_type in ("combat", "intimidation"):
            raw_trust = -10.0 * event.intensity
            _, deltas.trust_delta = apply_saturation(
                current=state.relationship_cache.get("trust", 0.0), 
                delta=raw_trust, 
                min_val=-100.0, 
                max_val=100.0
            )
            
            raw_fear = +8.0 * event.intensity
            _, deltas.fear_delta = apply_saturation(
                current=state.relationship_cache.get("fear", 0.0), 
                delta=raw_fear, 
                min_val=-100.0, 
                max_val=100.0
            )
        elif event.event_type == "help":
            deltas.trust_delta = round(+12.0 * event.intensity, 2)
            deltas.fear_delta  = round(-5.0  * event.intensity, 2)

        # Trait: подозрительность от неудачных попыток
        if not event.success and event.event_type in ("theft", "intimidation"):
            deltas.trait_updates["suspicious"] = min(
                state.state_modifiers.get("suspicious", 0.0) + 0.15, 1.0
            )
        
        return deltas

    def _make_narrative_fact(
        self,
        event:   EventContext,
        intent:  str,
        state:   NPCState,
        deltas:  StateDeltas,
    ) -> Optional[NarrativeFact]:
        """
        Создаёт NarrativeFact если событие достаточно важное.
        Важность считается по реальному влиянию на веса (Память.md #4), 
        а не по абстрактному event.intensity.
        """
        # Δweights = сумма абсолютных изменений ключевых метрик
        delta_weights = abs(deltas.trust_delta) + abs(deltas.fear_delta) + abs(deltas.stress_delta)
        
        # Эмоциональный импакт (нормализация: max emotion_delta ~20.0 -> 0-1)
        emotional_intensity = abs(deltas.emotion_delta) / 20.0 if deltas.emotion_delta else 0.0
        
        # Травма — всегда значимое событие для идентичности
        identity_impact = 0.3 if deltas.new_trauma else 0.0
        
        # Итоговая важность: взвешенная сумма компонентов
        importance = min(delta_weights * 0.01 + emotional_intensity * 0.5 + identity_impact * 0.2, 1.0)
        
        if importance < 0.3:
            return None

        emotion_str = deltas.emotion_tag.value if deltas.emotion_tag else "neutral"
        return NarrativeFact(
            event_type  = event.event_type,
            target_id   = event.actor_id,
            emotion_tag = emotion_str,
            day         = event.day,
            importance  = round(importance, 4),
        )

    def _explain_mode(
        self,
        state:       NPCState,
        personality: NPCPersonality,
        event:       EventContext,
    ) -> DecisionResult:
        """
        Intent.EXPLAIN — игрок спросил "почему ты так себя ведёшь?".
        DecisionHub выбирает top-2 факта из narrative_cache.
        LLM получает их в VerbalizationContext.
        """
        facts = state.get_top_narrative_facts(n=2)
        return DecisionResult(
            npc_id           = state.npc_id,
            intent           = Intent.EXPLAIN,
            intent_target    = event.actor_id,
            score            = 1.0,
            scores_trace     = {"explain": 1.0},
            deltas           = StateDeltas(),
            narrative_fact   = facts[0] if facts else None,
            explanation_mode = True,
        )
