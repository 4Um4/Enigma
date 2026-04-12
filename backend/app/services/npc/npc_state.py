# backend/app/services/npc/npc_state.py
"""
Единый источник типов NPC. Жёсткие write-контракты:
  L0 NPCPersonality   — write: NEVER (frozen dataclass)
  L1 NPCIdentityL1    — write: ONLY ResonanceEngine
  L2 NPCState         — write: ONLY StateApplicator
  EventMemory         — write: ONLY MemoryManager

R2.1 — NPCState: единый источник правды о динамическом состоянии NPC.
NPCState — центральный узел всей психики.

Принципы:
  - NPCPersonality (frozen) — static, загружается из JSON один раз
  - NPCState (mutable) — dynamic, меняется через StateApplicator
  - DecisionHub читает оба объекта, но пишет только через StateApplicator
  - LLM получает только VerbalizationContext — не сам NPCState
  
"""

from __future__ import annotations

import math
_math = math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from app.services.npc.behavior_mask import BehaviorMaskState


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class Intent(str, Enum):
    """Возможные намерения NPC. DecisionHub выбирает одно из них."""
    IDLE          = "idle"           # нет активного намерения
    TALK          = "talk"           # вступить в диалог
    WARN          = "warn"           # предупредить
    INTIMIDATE    = "intimidate"     # запугать
    FLEE          = "flee"           # уйти / сбежать
    ATTACK        = "attack"         # атаковать
    HELP          = "help"           # помочь
    REPORT        = "report"         # донести властям
    TRADE         = "trade"          # предложить сделку
    OBSERVE       = "observe"        # наблюдать, не действовать
    EXPLAIN       = "explain"        # ответить "почему" — для диалога

class WillState(str, Enum):
    """Состояние воли NPC. Enum защищает от опечаток в строках."""
    FREE      = "free"
    COERCED   = "coerced"
    BROKEN    = "broken"
    DECEPTIVE = "deceptive"
    LOYAL     = "loyal"

class EmotionTag(str, Enum):
    """Текущая эмоция NPC — передаётся в VerbalizationContext."""
    NEUTRAL   = "neutral"
    ANGRY     = "angry"
    FEARFUL   = "fearful"
    HAPPY     = "happy"
    SUSPICIOUS = "suspicious"
    GRATEFUL  = "grateful"
    DISGUSTED = "disgusted"
    SAD       = "sad"


class NPCTier(str, Enum):
    """
    Статический уровень симуляции NPC.
    Назначается при создании кампании — не меняется в runtime.
    MASS  → только флаги присутствия
    MINOR → расписание + редкие события
    MAJOR → полная симуляция DecisionHub
    """
    MASS  = "mass"
    MINOR = "minor"
    MAJOR = "major"


# ─────────────────────────────────────────────────────────────────────────────
# NarrativeFact — frozen, для объяснений NPC
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class NarrativeFact:
    
    event_type:  str    # значение из IMPORTANCE_RULES — "combat", "theft", "help" и т.д.
                        # TODO R1.6: заменить на EventTypeEnum после унификации типов событий
    """
    R1.6 — Факт из памяти NPC для объяснений ("почему ты злишься?").
    frozen=True: защита от случайной модификации в процессе вербализации.
    Максимум 2 факта передаётся в VerbalizationContext.
    НЕ используется в формуле score() — только для LLM-объяснений.
    """
    target_id:   str    # кто участвовал
    emotion_tag: str    # какая эмоция была применена
    day:         int    # игровой день (для "три дня назад")
    importance:  float  # для выбора top-2
    trust_delta: float = 0.0   # числовой след — было -15
    sequence_id: int   = 0     # порядок для хронологии


# ─────────────────────────────────────────────────────────────────────────────
# EventMemory — L2: смысловая память NPC (из Память.md R5.1)
# Lifecycle: Fresh → Detailed → Compressed → Abstract → Forgotten
# Не участвует в формуле score() — только для вербализации и EXPLAIN.
# ─────────────────────────────────────────────────────────────────────────────

class MemoryStage(str, Enum):
    """Стадия жизненного цикла события в памяти."""
    FRESH      = "fresh"       # только что произошло — детальная
    DETAILED   = "detailed"    # несколько тиков — ещё точная
    COMPRESSED = "compressed"  # сжатая — детали теряются
    ABSTRACT   = "abstract"    # только смысл — уходит в L3 traits
    FORGOTTEN  = "forgotten"   # importance < threshold — удаляется


@dataclass(frozen=True)
class EventMemory:
    """
    R5.1 — L2: смысловая память о событии.
    Хранит clarity (чёткость восприятия) и confidence (уверенность в деталях).
    Decay переводит из Fresh → Forgotten через промежуточные стадии.
    """
    event_type:         str
    target_id:          str
    emotion_tag:        str
    day:                int
    importance:         float       # 0.0–1.0, затухает со временем
    clarity:            float = 1.0 # насколько чётко NPC воспринял событие
    confidence:         float = 1.0 # уверенность в деталях (снижается при drift)
    decay_rate:         float = 0.05  # потеря importance за тик
    stage:              MemoryStage = MemoryStage.FRESH
    sequence_id:        int = 0

    def __post_init__(self) -> None:
        # Защита от невалидных значений при загрузке из JSON
        object.__setattr__(self, "importance",  max(0.0, min(1.0, self.importance)))
        object.__setattr__(self, "clarity",     max(0.0, min(1.0, self.clarity)))
        object.__setattr__(self, "confidence",  max(0.0, min(1.0, self.confidence)))
        object.__setattr__(self, "decay_rate",  max(0.0, min(1.0, self.decay_rate)))

    def decayed(self, ticks: int = 1) -> "EventMemory":
        """
        Возвращает новый EventMemory с применённым decay.
        Используется WorkingMemory.apply_decay() — не мутирует оригинал.
        """
        # Экспоненциальное затухание важности
        new_importance = self.importance * (_math.exp(-self.decay_rate * ticks))
        # Уверенность снижается медленнее — детали теряются постепенно
        new_confidence = self.confidence * (_math.exp(-self.decay_rate * 0.5 * ticks))
        new_stage      = _resolve_stage(new_importance)

        return EventMemory(
            event_type  = self.event_type,
            target_id   = self.target_id,
            emotion_tag = self.emotion_tag,
            day         = self.day,
            importance  = round(new_importance, 4),
            clarity     = self.clarity,       # clarity фиксируется в момент восприятия
            confidence  = round(new_confidence, 4),
            decay_rate  = self.decay_rate,
            stage       = new_stage,
            sequence_id = self.sequence_id,
        )


    def to_identity_weight(self) -> Optional[tuple[str, float]]:
        """
        R5.3/R6 — конвертирует ABSTRACT память в вес для L3 Identity.
        Вызывается WorkingMemory при вытеснении события.
        Возвращает (trait_name, delta) или None если не конвертируется.
        """
        if self.stage != MemoryStage.ABSTRACT:
            return None
        # Негативные эмоции → накопление resentment
        if self.emotion_tag in ("angry", "fearful", "disgusted"):
            return ("resentment", round(self.importance * 0.1, 4))
        # Позитивные → накопление dependency
        if self.emotion_tag in ("grateful", "happy"):
            return ("dependency", round(self.importance * 0.1, 4))
        return None


    @property
    def is_forgotten(self) -> bool:
        """Событие можно удалить из памяти."""
        return self.stage == MemoryStage.FORGOTTEN


def _resolve_stage(importance: float) -> MemoryStage:
    """
    Определяет стадию памяти по текущей важности.
    Пороги откалиброваны под decay_rate=0.05.
    """
    if importance >= 0.80:
        return MemoryStage.FRESH
    if importance >= 0.55:
        return MemoryStage.DETAILED
    if importance >= 0.30:
        return MemoryStage.COMPRESSED
    if importance >= 0.10:
        return MemoryStage.ABSTRACT
    return MemoryStage.FORGOTTEN


# ─────────────────────────────────────────────────────────────────────────────
# NPCPersonality — static, из JSON, не меняется в сессии
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class NPCPersonality:
    """
    Неизменяемая личность NPC. Загружается из major_npcs.json один раз.
    DecisionHub использует как контекст, но не мутирует.
    drives_base — веса для формулы score().
    """
    npc_id:        str
    tier:          NPCTier
    drives_base:   Dict[str, float]   # control, significance, fear, desire
    willpower:     float              # 0–100, сопротивление принуждению
    breakpoint:    float              # порог стресса для слома воли
    loyalty_base:  float              # базовая лояльность (не текущая)
    can_awaken:    bool = False       # может ли Minor стать Major через snapshot

    # Голос персонажа — static из JSON. Не меняется в сессии.
    # Пример: "Говоришь грубо, коротко. Называешь всех 'парень'. Материшься."
    voice_profile: str = ""

    # Биография / backstory — короткие ключевые факты из жизни NPC.
    # Пример: "Жена умерла в войну. Учился у старого кузнеца. Боится собак."
    # Не длинная история, а факты. LLM получает как есть.
    backstory:     str = ""           # ≤ 200 символов

    def __post_init__(self) -> None:
        total = sum(self.drives_base.values())
        if not (0.98 <= total <= 1.02):
            raise ValueError(
                f"NPCPersonality '{self.npc_id}': "
                f"drives_base сумма должна быть 1.0, получено {total:.4f}. "
                f"Проверь JSON конфигурацию NPC."
            )




# ═════════════════════════════════════════════════════════
# L1 — IDENTITY (semi-stable, пишет ТОЛЬКО ResonanceEngine)
# ═════════════════════════════════════════════════════════

@dataclass
class NPCIdentityL1:
    """
    L1: Кристаллизованные черты личности из паттернов памяти.
    Накапливается через ResonanceEngine — не изменяется напрямую.
    Overlay поверх NPCPersonality.drives_base — не замена.
    """
    npc_id: str
    # Накопленные черты: ключ = trait_name, значение = накопленный вес
    # Пример: {"resentment": 0.34, "dependency": 0.12}
    # WRITE: только ResonanceEngine.apply_resonance()
    active_traits: Dict[str, float] = field(default_factory=dict)

    def overlay_drives(self, base: Dict[str, float]) -> Dict[str, float]:
        """
        Возвращает drives с наложенными trait-весами.
        Читается DecisionHub через DecisionView — не напрямую.
        """
        result = dict(base)
        for trait, weight in self.active_traits.items():
            if trait in result:
                result[trait] = max(0.0, min(1.0, result[trait] + weight))
        return result


# ═════════════════════════════════════════════════════════
# L2 — STATE (volatile, пишет ТОЛЬКО StateApplicator)
# ═════════════════════════════════════════════════════════


# ───────────────────────────────────────────────────────
# NPCState — dynamic, единственный изменяемый объект
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NPCState:
    """
    Динамическое состояние NPC. Источник правды для DecisionHub.
    Изменяется только через StateApplicator — не напрямую.
    """
    npc_id: str

    # ── Психика ──────────────────────────────────────────────

    stress: float = 0.0

    # R6.1 — накопленная скрытая агрессия к источнику давления.
    # Используется при выборе FAKE_SUBMISSION и BETRAYAL.
    resentment: float = 0.0

    # R6.1 — психологическая зависимость от источника давления.
    # Растёт при помощи, спасении и формировании привязки.
    dependency: float = 0.0

    # R6.1 — целостность личности (нормализованная шкала 0.0–1.0).
    # Уменьшается ТОЛЬКО через BreakProgressEngine (R6.4).
    identity_integrity: float = 1.0

    # R6.4 — динамическое сопротивление давлению (Anti-abuse).
    pressure_resistance: float = 0.0

    will_state: WillState = WillState.FREE

    # R6.2 — внешний поведенческий паттерн поверх will_state.
    # Читается OpportunityEngine и EmotionalNuanceEngine.
    # NONE = маска отсутствует, поведение соответствует will_state.
    behavior_mask: BehaviorMaskState = field(default_factory=BehaviorMaskState)

    trauma_markers: Set[str] = field(default_factory=set)

    # ── Эмоция (накопительная) ────────────────────────────────────────────────
    emotion:        EmotionTag = EmotionTag.NEUTRAL
    emotion_delta:  float      = 0.0

    # TODO: мост → L1. Будет удалено после подключения ResonanceEngine к StateApplicator.
    # Сейчас пишется StateApplicator, читается verbalization_context и decision_hub.
    # Целевое место: NPCIdentityL1.active_traits (write: ONLY ResonanceEngine)
    active_traits: Dict[str, float] = field(default_factory=dict)

    # ── Intent ────────────────────────────────────────────────────────────────
    intent:              Optional[Intent] = None
    intent_target:       Optional[str]    = None
    intent_formed_at:    int              = 0
    intent_duration:     int              = 0   # тиков держится текущий intent
    intent_progress_ticks: int            = 0   # тиков с реальным прогрессом (значимые дельты)
    last_intent_change:  int              = 0   # тик последней смены intent
    pressure_accumulator: Dict[Tuple[str, str], float] = field(default_factory=dict)  # (from, to) → накопленное давление

    # ── Кэш отношений ────────────────────────────────────────────────────────
    relationship_cache: Dict[str, float] = field(default_factory=dict)
    cache_timestamp:    int              = 0

# ── Narrative facts (max 2 для LLM) ──────────────────────────────────────
    # Union: NarrativeFact (legacy) или EventMemory (R5.1) — оба принимаются.
    # verbalization_context использует getattr для доступа к clarity/confidence.
    narrative_cache: Tuple[Union[NarrativeFact, "EventMemory"], ...] = field(default_factory=tuple)

    # ── Causal Ledger — паспорт изменений состояния (Шаг 3) ──────────────────
    # Хранит последние N записей CausalEntry для отладки и Social Propagation.
    # Не сохраняется в JSON — только runtime.
    causal_ledger: List[Any] = field(default_factory=list)

    # ── Позиция (кэш из SceneState) ───────────────────────────────────────────
    cached_position: Optional[Tuple[float, float]] = None
    position_valid:  bool = False

    def __post_init__(self) -> None:
        """Защита от повреждённых данных на входе."""
        self.stress = max(0.0, min(100.0, self.stress))

        # R6.1/R6.4 — защита диапазонов параметров личности и сопротивления
        self.resentment = max(0.0, min(100.0, self.resentment))
        self.dependency = max(0.0, min(100.0, self.dependency))
        self.identity_integrity = max(0.0, min(1.0, self.identity_integrity))
        self.pressure_resistance = max(0.0, min(100.0, self.pressure_resistance))

        self.emotion_delta = max(-100.0, min(100.0, self.emotion_delta))
        if self.intent is not None and self.intent_target is None:
            if self.intent not in (Intent.IDLE, Intent.OBSERVE, Intent.FLEE,
                                   Intent.EXPLAIN):
                raise ValueError(
                    f"NPCState '{self.npc_id}': intent={self.intent} требует intent_target"
                )

    def _cached_distance_to(self, other_pos: Tuple[float, float]) -> float:
        """
        Евклидово расстояние до позиции из кэша.
        ВНИМАНИЕ: только для визуализации и отладки.
        DecisionHub читает позиции из SceneState напрямую — не отсюда.
        """
        if not self.position_valid or self.cached_position is None:
            return float("inf")
        dx = self.cached_position[0] - other_pos[0]
        dy = self.cached_position[1] - other_pos[1]
        return math.sqrt(dx * dx + dy * dy)

    def get_top_narrative_facts(self, n: int = 2) -> tuple:
        """Top-N фактов по importance. Принимает NarrativeFact и EventMemory."""
        return tuple(sorted(
            self.narrative_cache, key=lambda f: f.importance, reverse=True
        )[:n])

    def snapshot(self) -> Dict[str, Any]:
        """
        Сериализуемый снимок — для логов калибровки R4.2 и сохранений.
        Только данные, без методов.
        """
        return {
            "npc_id":             self.npc_id,
            "stress":             self.stress,

            # R6.1 — состояние накопленного давления личности
            "resentment":         self.resentment,
            "dependency":         self.dependency,
            "identity_integrity": self.identity_integrity,
            "pressure_resistance": self.pressure_resistance,

            "will_state":         self.will_state.value,

            # R6.2 — поведенческая маска
            "behavior_mask":      self.behavior_mask.mask.value,
            "behavior_mask_intensity": self.behavior_mask.intensity,
            "behavior_mask_applied_at_day": self.behavior_mask.applied_at_day,
            
            "emotion":            self.emotion.value,
            "emotion_delta":      self.emotion_delta,
            "active_traits":      {},  # L1: хранится в NPCIdentityL1, не в NPCState
            "trauma_markers":     list(self.trauma_markers),
            "intent":             self.intent.value if self.intent else None,
            "intent_target":      self.intent_target,
            "intent_duration":      self.intent_duration,
            "intent_progress_ticks": self.intent_progress_ticks,
            "last_intent_change":   self.last_intent_change,
            "relationship_cache": dict(self.relationship_cache),
            "position_valid":     self.position_valid,
            "cached_position":    list(self.cached_position) if self.cached_position else None,
        }



    @staticmethod
    def write_to_legacy(state: "NPCState", npc_dict: dict) -> None:
        """
        Записывает NPCState обратно в legacy dict (major_npcs.json).
        Вызывается ПОСЛЕ StateApplicator.apply() — единственная точка записи.
        Мутирует npc_dict (вызывающий должен сохранить через _save_npcs).
        """
        psyche = npc_dict.setdefault("psyche", {})
        ss     = npc_dict.setdefault("social_stats", {})

        # Психика
        psyche["stress"]       = state.stress
        psyche["state"]        = state.will_state.value
        psyche["trauma_flags"] = list(state.trauma_markers)

        # Социальные статы (из relationship_cache)
        rc = state.relationship_cache
        ss["trust"]          = rc.get("trust", 0.0)
        ss["fear_of_player"] = rc.get("fear", 0.0)
        ss["debt"]           = rc.get("debt", 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# NPCStateAdapter — миграция без большого взрыва
# ─────────────────────────────────────────────────────────────────────────────

class NPCStateAdapter:
    """
    R2.1 — Переходный адаптер от legacy npc dict к NPCState.
    Позволяет мигрировать life_engine и npc_cognition инкрементально.
    Удалить после полного перехода на NPCState.
    """

    @staticmethod
    def from_legacy(npc_dict: dict) -> NPCState:
        """Создаёт NPCState из legacy npc dict."""
        psyche = npc_dict.get("psyche", {})
        ss     = npc_dict.get("social_stats", {})
        return NPCState(
            npc_id            = npc_dict.get("id", "unknown"),
            stress            = float(psyche.get("stress", 0)),

            # R6.1/R6.4 — новые параметры личности (если отсутствуют — дефолты)
            resentment        = float(psyche.get("resentment", 0.0)),
            dependency        = float(psyche.get("dependency", 0.0)),
            identity_integrity = float(psyche.get("identity_integrity", 1.0)),
            pressure_resistance = float(psyche.get("pressure_resistance", 0.0)),

            will_state        = psyche.get("state", "free"),
            trauma_markers    = set(psyche.get("trauma_flags", [])),
            relationship_cache = {
                "trust": float(ss.get("trust", 0.0)),
                "fear":  float(ss.get("fear_of_player", 0.0)),
                "debt":  float(ss.get("debt", 0.0)),
            },
        )

# ─────────────────────────────────────────────────────────────────────────────
# NPCPersonality builder — из legacy dict
# ─────────────────────────────────────────────────────────────────────────────

def personality_from_legacy(npc_dict: dict) -> NPCPersonality:
    """Создаёт frozen NPCPersonality из legacy npc dict."""
    psyche = npc_dict.get("psyche", {})
    tier_str = npc_dict.get("tier", "major")
    try:
        tier = NPCTier(tier_str)
    except ValueError:
        tier = NPCTier.MAJOR

    return NPCPersonality(
        npc_id        = npc_dict.get("id", "unknown"),
        tier          = tier,
        drives_base   = dict(npc_dict.get("drives", {
            "control": 0.25, "significance": 0.25,
            "fear": 0.25,    "desire": 0.25,
        })),
        willpower     = float(psyche.get("willpower", 50)),
        breakpoint    = float(psyche.get("breakpoint", 80)),
        loyalty_base  = float(psyche.get("loyalty_true", 50)),
        can_awaken    = bool(npc_dict.get("can_awaken", False)),
        voice_profile = npc_dict.get("voice_profile", ""),
        backstory     = npc_dict.get("backstory", ""),
    )


# ═════════════════════════════════════════════════════════
# DecisionView — read-only контракт для DecisionHub
# Только этот объект передаётся в compute() — не сырые L0/L1/L2
# ═════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DecisionView:
    """
    Контракт чтения для DecisionHub.
    Изолирует ядро решений от прямого доступа к L0/L1/L2.
    Создаётся в game_loop / dm_orchestrator перед вызовом compute().
    """
    profile:  NPCPersonality   # L0 — неизменяемая личность
    identity: NPCIdentityL1    # L1 — накопленные черты
    state:    NPCState         # L2 — текущее состояние


# ═════════════════════════════════════════════════════════
# Алиасы — для будущей миграции к явным именам слоёв
# Нулевой слом тестов: старые имена продолжают работать
# ═════════════════════════════════════════════════════════

NPCProfileL0 = NPCPersonality   # L0
NPCStateL2   = NPCState         # L2
