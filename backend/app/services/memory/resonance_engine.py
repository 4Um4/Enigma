# backend/app/services/memory/resonance_engine.py
"""
R5.4 — ResonanceEngine: детекция паттернов поверх EventMemory.
R5.5 — Personality Modulation: один паттерн → разный trait по drives_base.

Реализует §6 и §10 из Память.md:
  §6:  importance += reinforcement_from_related_events (те же actor/type/theme)
  §10: if Σ related_events > threshold → create_trait()

Принципы:
  - Только READ: не мутирует EventMemory, не пишет в NPCState
  - Возвращает ResonancePattern → вызывающий код применяет через active_traits
  - Без LLM, без IO
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from app.models.npc_state import EventMemory, MemoryStage, NPCPersonality


# ─────────────────────────────────────────────────────────────────────────────
# Константы паттернов
# ─────────────────────────────────────────────────────────────────────────────

# Минимальное количество событий для детекции паттерна
_MIN_EVENTS_FOR_PATTERN: int = 3

# Порог importance суммы событий для формирования trait (§10 Память.md)
_TRAIT_FORMATION_THRESHOLD: float = 0.60

# Максимальный вес одного паттерна в active_traits
_MAX_PATTERN_DELTA: float = 0.30


# Группировка типов событий по теме (§6 Память.md — "та же тема")
_THEME_BETRAYAL: frozenset = frozenset({
    "theft", "vandalism", "intimidation", "deception", "betrayal",
})
_THEME_HELP: frozenset = frozenset({
    "help", "quest", "rescue", "gift", "dialogue_key",
})
_THEME_AGGRESSION: frozenset = frozenset({
    "combat", "intimidation", "threat", "capture",
})


# ─────────────────────────────────────────────────────────────────────────────
# ResonancePattern — результат детекции
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ResonancePattern:
    """
    Детектированный паттерн поведения игрока относительно NPC.
    frozen=True: не мутируется после создания — только читается.
    """
    pattern_name: str    # "betrayal_chain" | "chronic_help" | "gaslighting"
    strength:     float  # 0.0–1.0, сила паттерна (сумма importance совпавших событий)
    trait_name:   str    # имя L3 trait который усиливается
    trait_delta:  float  # вес для добавления в active_traits


# ─────────────────────────────────────────────────────────────────────────────
# ResonanceEngine
# ─────────────────────────────────────────────────────────────────────────────

class ResonanceEngine:
    """
    Читает список EventMemory, детектирует паттерны, возвращает trait deltas.

    Вызывается из MemoryManager после decay — не напрямую из python_engines.
    Не мутирует входные данные.
    """

    def detect(
        self,
        events: Sequence[EventMemory],
        actor_id: str = "player",
        personality: Optional[NPCPersonality] = None,
    ) -> List[ResonancePattern]:
        """
        Основной метод. Принимает снимок WorkingMemory, возвращает паттерны.

        actor_id — чьи действия анализируем (обычно "player").
        personality — если передана, trait_name модулируется по drives_base.
        Игнорирует FORGOTTEN события — они уже вышли из памяти.
        """
        # Фильтруем: только релевантные события от нужного actor
        relevant = [
            e for e in events
            if isinstance(e, EventMemory)
            and e.stage != MemoryStage.FORGOTTEN
            and e.target_id == actor_id
        ]

        if len(relevant) < _MIN_EVENTS_FOR_PATTERN:
            return []

        patterns: List[ResonancePattern] = []

        p = self._detect_betrayal_chain(relevant, personality)
        if p:
            patterns.append(p)

        p = self._detect_chronic_help(relevant, personality)
        if p:
            patterns.append(p)

        p = self._detect_gaslighting(relevant, personality)
        if p:
            patterns.append(p)

        return patterns

    # ─────────────────────────────────────────────────────────────────────────
    # Детекторы паттернов
    # ─────────────────────────────────────────────────────────────────────────

    def _detect_betrayal_chain(
        self,
        events: List[EventMemory],
        personality: Optional[NPCPersonality] = None,
    ) -> Optional[ResonancePattern]:
        """
        §10 Память.md: частый обман → distrust_player (или paranoid/vindictive).
        Условие: 3+ событий из темы BETRAYAL от одного actor.
        Trait модулируется по drives_base если передана personality.
        """
        betrayal_events = [
            e for e in events
            if any(theme in e.event_type for theme in _THEME_BETRAYAL)
        ]

        if len(betrayal_events) < _MIN_EVENTS_FOR_PATTERN:
            return None

        raw = sum(e.importance for e in betrayal_events)
        if raw < _TRAIT_FORMATION_THRESHOLD:
            return None

        density = self._temporal_density(betrayal_events)
        strength = raw * density

        delta = min(_MAX_PATTERN_DELTA, round(strength * 0.15, 4))
        return ResonancePattern(
            pattern_name="betrayal_chain",
            strength=round(min(strength, 1.0), 4),
            trait_name=self._resolve_trait("betrayal_chain", personality),
            trait_delta=delta,
        )

    def _detect_chronic_help(
        self,
        events: List[EventMemory],
        personality: Optional[NPCPersonality] = None,
    ) -> Optional[ResonancePattern]:
        """
        §10 Память.md: частая помощь → trust_bias (или dependent/obligated).
        Условие: 3+ событий из темы HELP.
        Trait модулируется по drives_base если передана personality.
        """
        help_events = [
            e for e in events
            if any(theme in e.event_type for theme in _THEME_HELP)
        ]

        if len(help_events) < _MIN_EVENTS_FOR_PATTERN:
            return None

        raw = sum(e.importance for e in help_events)
        if raw < _TRAIT_FORMATION_THRESHOLD:
            return None

        density = self._temporal_density(help_events)
        strength = raw * density

        delta = min(_MAX_PATTERN_DELTA, round(strength * 0.12, 4))
        return ResonancePattern(
            pattern_name="chronic_help",
            strength=round(min(strength, 1.0), 4),
            trait_name=self._resolve_trait("chronic_help", personality),
            trait_delta=delta,
        )

    def _detect_gaslighting(
        self,
        events: List[EventMemory],
        personality: Optional[NPCPersonality] = None,
    ) -> Optional[ResonancePattern]:
        """
        Чередование агрессии и помощи → suspicious (или hypervigilant).
        Условие: в последних N событиях есть и AGGRESSION и HELP,
        причём они чередуются (не просто смешаны).
        Trait модулируется по drives_base если передана personality.
        """
        if len(events) < _MIN_EVENTS_FOR_PATTERN:
            return None

        # Классифицируем последние события по теме
        classified = []
        for e in events[-6:]:
            if any(t in e.event_type for t in _THEME_AGGRESSION):
                classified.append("A")
            elif any(t in e.event_type for t in _THEME_HELP):
                classified.append("H")
            else:
                classified.append("_")

        # Ищем чередование A-H или H-A (минимум 2 перехода)
        transitions = sum(
            1 for i in range(1, len(classified))
            if classified[i] != classified[i - 1]
            and classified[i] in ("A", "H")
            and classified[i - 1] in ("A", "H")
        )

        if transitions < 2:
            return None

        strength = sum(e.importance for e in events[-6:]) / 6.0
        if strength < 0.25:
            return None

        delta = min(_MAX_PATTERN_DELTA, round(strength * 0.18, 4))
        return ResonancePattern(
            pattern_name="gaslighting",
            strength=round(strength, 4),
            trait_name=self._resolve_trait("gaslighting", personality),
            trait_delta=delta,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Вспомогательные методы
    # ─────────────────────────────────────────────────────────────────────────

    def _resolve_trait(
        self,
        pattern_name: str,
        personality: Optional[NPCPersonality],
    ) -> str:
        """
        Один паттерн → разный trait в зависимости от личности NPC.
        Без personality → стандартный trait (обратная совместимость R5.4).
        Логика: §Personality Modulation из Баги.md.
        """
        if personality is None:
            # Стандартные traits — поведение идентично R5.4
            return {
                "betrayal_chain": "distrust_player",
                "chronic_help":   "trust_bias",
                "gaslighting":    "suspicious",
            }.get(pattern_name, pattern_name)

        drives = personality.drives_base

        if pattern_name == "betrayal_chain":
            if drives.get("fear", 0.0) > 0.4:
                return "paranoid"       # боязливый NPC → страх повторения
            if drives.get("control", 0.0) > 0.4:
                return "vindictive"     # контролирующий NPC → желание отомстить
            return "distrust_player"    # стандарт

        if pattern_name == "chronic_help":
            if drives.get("desire", 0.0) > 0.4:
                return "dependent"      # NPC с высоким desire → зависимость
            if drives.get("significance", 0.0) > 0.4:
                return "obligated"      # NPC важна значимость → чувство долга
            return "trust_bias"         # стандарт

        if pattern_name == "gaslighting":
            if drives.get("fear", 0.0) > 0.4:
                return "hypervigilant"  # боязливый NPC → постоянная настороженность
            return "suspicious"         # стандарт

        return pattern_name

    def _temporal_density(self, events: List[EventMemory]) -> float:
        """
        Чем ближе события по времени — тем сильнее паттерн.
        Формула: n / (span_days + 1), где span = max(day) - min(day).
        Одиночные или одновременные события дают множитель = n.
        Редкие события с большим разрывом — ослабляют strength.
        """
        if len(events) < 2:
            return float(len(events))

        days = [e.day for e in events]
        span = max(days) - min(days)
        return len(events) / (span + 1)
