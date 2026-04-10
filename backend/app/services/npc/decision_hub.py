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

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Целевая архитектура данных (L0/L2)
from app.models.npc_profile import NPCProfileL0
from app.services.npc.npc_state import NPCStateL2  # алиас для NPCState (L2)

# Легаси-типы, всё ещё используемые в логике (Enum'ы и контракты результатов)
from app.services.npc.npc_state import (
    EmotionTag,
    Intent,
    NarrativeFact,
    WillState,
)
from app.services.npc.opportunity_engine import (
    OpportunityContext,
    OpportunityEngine,
    OpportunityResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# Константы формулы score()
# ─────────────────────────────────────────────────────────────────────────────

# Контролируемый рандом ±N% — NPC предсказуем, но не робот (решение №12)
SCORE_NOISE_RANGE: float = 0.10

# Максимальная инерция intent — после 10 тиков смена intent затруднена
INTENT_INERTIA_MAX_TICKS: int   = 10
INTENT_INERTIA_WEIGHT:    float = 0.20

# Распад инерции при отсутствии прогресса — после N тиков "впустую"
INTENT_SATURATION_TICKS: int   = 6   # тиков без прогресса до начала decay
INTENT_DECAY_RATE:        float = 0.03  # убывание за каждый лишний тик

# Порог страха: выше — NPC склонен к FLEE/OBSERVE вместо ATTACK
FEAR_FLEE_THRESHOLD: float = 0.65

# Минимальный score чтобы intent был выбран (иначе IDLE)
MIN_INTENT_SCORE: float = 0.15


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
    Формируется в game_loop из GameEvent + SceneState.
    """
    event_type:              str
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
        state:           NPCStateL2,
        personality:     NPCProfileL0,
        event:           EventContext,
        scene_state:     Optional[Dict[str, Any]] = None,
        opportunity_ctx: Optional[OpportunityContext] = None,
        identity:        Optional["NPCIdentityL1"] = None,
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

        # Черты из L1. Если identity не передан — берём из state (мост до полной миграции)
        active_traits: Dict[str, float] = identity.active_traits if identity else state.active_traits
        possible = self._get_possible_intents(state, personality, event, opportunity)
        scores   = self._score_all(state, personality, event, possible, opportunity, active_traits)

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

        best_intent, best_score = max(scores.items(), key=lambda x: x[1])

        if best_score < MIN_INTENT_SCORE:
            best_intent = Intent.IDLE
            best_score  = 0.0

        intent_target = self._resolve_target(best_intent, event, state)
        deltas        = self._compute_deltas(state, personality, event, best_intent)
        narrative     = self._make_narrative_fact(event, best_intent, state, deltas)

        # В scores_trace попадают ТОЛЬКО числа для калибровки R4.2.
        # Строки (причины срабатывания) отсекаются.
        opp_trace = {f"opp_{k}": v for k, v in opportunity.score_trace.items() if isinstance(v, (int, float))}

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
        all_intents = [i.value for i in Intent
                       if i not in (Intent.IDLE, Intent.EXPLAIN)]

        filtered = []
        for intent in all_intents:
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
            return intent in (Intent.FLEE.value, Intent.WARN.value,
                               Intent.OBSERVE.value)
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
            noise = self._rng.uniform(-SCORE_NOISE_RANGE, SCORE_NOISE_RANGE)

            if state.intent and state.intent.value == intent_str:
                base += inertia
                components["inertia"] = round(inertia, 4)

            components["noise"] = round(noise, 4)
            # Clamp: score не уходит за физические пределы формулы
            # Верхний предел 3.0 — теоретический максимум суммы всех компонентов
            scores[intent_str] = round(max(-2.0, min(3.0, base + noise)), 4)

        return scores

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
            risk_penalty = round(-fear * risk * 1.25, 4)    # страх полностью блокирует агрессию
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
        if event.event_type in ("combat", "capture") and event.distance <= 3.0:
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
        
        deltas = StateDeltas()

        # Стресс от насилия рядом — с saturation у границ диапазона (0-100)
        if event.event_type in ("combat", "capture") and event.distance <= 5.0:
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
                state.active_traits.get("suspicious", 0.0) + 0.15, 1.0
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
