# backend/app/services/npc/npc_state.py
"""
R2.1 — NPCState: единый источник правды о динамическом состоянии NPC.

Принципы:
  - NPCPersonality (frozen) — static, загружается из JSON один раз
  - NPCState (mutable) — dynamic, меняется через StateApplicator
  - DecisionHub читает оба объекта, но пишет только через StateApplicator
  - LLM получает только VerbalizationContext — не сам NPCState
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Set, Tuple


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

    def __post_init__(self) -> None:
        total = sum(self.drives_base.values())
        if not (0.98 <= total <= 1.02):
            raise ValueError(
                f"NPCPersonality '{self.npc_id}': "
                f"drives_base сумма должна быть 1.0, получено {total:.4f}. "
                f"Проверь JSON конфигурацию NPC."
            )

# ─────────────────────────────────────────────────────────────────────────────
# NPCState — dynamic, единственный изменяемый объект
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class NPCState:
    """
    Динамическое состояние NPC. Источник правды для DecisionHub.
    Изменяется только через StateApplicator — не напрямую.
    """
    npc_id: str

    # ── Психика ──────────────────────────────────────────────────────────────
    stress:         float     = 0.0
    will_state:     WillState = WillState.FREE
    trauma_markers: Set[str]  = field(default_factory=set)

    # ── Эмоция (накопительная) ────────────────────────────────────────────────
    emotion:        EmotionTag = EmotionTag.NEUTRAL
    emotion_delta:  float      = 0.0

    # ── Trait Accumulation (overlay на personality_base, не замена) ───────────
    active_traits: Dict[str, float] = field(default_factory=dict)

    # ── Intent ────────────────────────────────────────────────────────────────
    intent:              Optional[Intent] = None
    intent_target:       Optional[str]    = None
    intent_formed_at:    int              = 0
    intent_duration:     int              = 0   # тиков держится текущий intent
    last_intent_change:  int              = 0   # тик последней смены intent

    # ── Кэш отношений ────────────────────────────────────────────────────────
    relationship_cache: Dict[str, float] = field(default_factory=dict)
    cache_timestamp:    int              = 0

    # ── Narrative facts (max 2 для LLM) ──────────────────────────────────────
    narrative_cache: Tuple[NarrativeFact, ...] = field(default_factory=tuple)

    # ── Позиция (кэш из SceneState) ───────────────────────────────────────────
    cached_position: Optional[Tuple[float, float]] = None
    position_valid:  bool = False

    def __post_init__(self) -> None:
        """Защита от повреждённых данных на входе."""
        self.stress = max(0.0, min(100.0, self.stress))
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

    def get_top_narrative_facts(self, n: int = 2) -> Tuple[NarrativeFact, ...]:
        """Top-N фактов по importance. Вызывается при intent=EXPLAIN."""
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
            "will_state":         self.will_state.value,
            "emotion":            self.emotion.value,
            "emotion_delta":      self.emotion_delta,
            "active_traits":      dict(self.active_traits),
            "trauma_markers":     list(self.trauma_markers),
            "intent":             self.intent.value if self.intent else None,
            "intent_target":      self.intent_target,
            "intent_duration":    self.intent_duration,
            "last_intent_change": self.last_intent_change,
            "relationship_cache": dict(self.relationship_cache),
            "position_valid":     self.position_valid,
            "cached_position":    list(self.cached_position) if self.cached_position else None,
        }


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
            will_state        = psyche.get("state", "free"),
            trauma_markers    = set(psyche.get("trauma_flags", [])),
            relationship_cache = {
                "trust": float(ss.get("trust", 0.0)),
                "fear":  float(ss.get("fear_of_player", 0.0)),
                "debt":  float(ss.get("debt", 0.0)),
            },
        )

    @staticmethod
    def to_legacy(state: NPCState, npc_dict: dict) -> None:
        """
        Записывает изменения из NPCState обратно в legacy dict.
        TODO: удалить после полного перехода на StateApplicator.
        будет удалено после: завершения R2 (StateApplicator готов и подключён)
        """
        psyche = npc_dict.setdefault("psyche", {})
        ss     = npc_dict.setdefault("social_stats", {})

        psyche["stress"]       = state.stress
        psyche["state"]        = state.will_state
        psyche["trauma_flags"] = list(state.trauma_markers)

        ss["trust"]          = state.relationship_cache.get("trust", 0.0)
        ss["fear_of_player"] = state.relationship_cache.get("fear", 0.0)
        ss["debt"]           = state.relationship_cache.get("debt", 0.0)


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
        npc_id       = npc_dict.get("id", "unknown"),
        tier         = tier,
        drives_base  = dict(npc_dict.get("drives", {
            "control": 0.25, "significance": 0.25,
            "fear": 0.25,    "desire": 0.25,
        })),
        willpower    = float(psyche.get("willpower", 50)),
        breakpoint   = float(psyche.get("breakpoint", 80)),
        loyalty_base = float(psyche.get("loyalty_true", 50)),
        can_awaken   = bool(npc_dict.get("can_awaken", False)),
    )