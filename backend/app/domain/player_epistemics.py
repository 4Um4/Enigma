# path: /project/backend/app/domain/player_epistemics.py
"""
Файл: backend/app/domain/player_epistemics.py
Назначение: P6 — доменные DTO эпистемического слоя ИГРОКА.
    Третий онтологический слой (TruthState -> NPC narrative_cache -> игрок).
    Законы (S255, утверждены Мастером):
      - PlayerEpistemicState != Truth (игрок-ось Truth!=Knowledge; зеркало
        "ClaimEvent никогда не является World Truth")
      - PROVENANCE, NOT STRINGS: уровень определяется структурным
        происхождением события, не текстом реплики
      - DISCOVERY IS DELIVERY: знание игрока порождается только
        SurfaceEvent'ом через DiscoveryBridge (монополия)
Зависимости: app.domain.disclosure (DisclosureLevel — опубликованный
    контракт P5; импорт без изменений)
Основные сущности: UNKNOWN/CLUE/IDENTIFIED, SurfaceKind, SurfaceEvent,
    PlayerObservation, LevelChangeEvent, EpistemicUpdate
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.domain.disclosure import DisclosureLevel

# ── Уровни знания игрока (ТЗ-P6: 0/1/2) ─────────────────────────────────
UNKNOWN = 0       # сигнала нет
CLUE = 1          # улика/подозрение (вкладка "Гипотезы", P8)
IDENTIFIED = 2    # секрет идентифицирован ("раскрыт" для compat-поверхности)


class SurfaceKind(str, Enum):
    """Классы поверхностей — единственные источники знания игрока."""

    DIALOGUE_OUTCOME = "dialogue_outcome"  # уровень P5-решения (не текст!)
    EAVESDROP = "eavesdrop"                # подслушанная реплика NPC->NPC
    DM_NARRATIVE = "dm_narrative"          # мир/мастер подтвердил
    VISUAL_CUE = "visual_cue"              # ТЗ-мандат; эмиссии в P6 нет


# ── content_class-словарь (структурные метки; НЕ строки реплик) ─────────
CONTENT_EAVESDROP_FULL = "eavesdrop_full"              # полная реплика -> 2
CONTENT_ACTION_SECRET_LANDED = "action_secret_landed"  # действие подтвердило -> 2


@dataclass(frozen=True)
class PlayerObservation:
    """Автотекст-наблюдение игрока (ТЗ-P6 п.6: уровень != текст).

    НЕ app.models.observation.Observation (evidence-конвейер NPC-петли):
    нейминг-развод D9 — разные онтологии.
    """

    tick: int
    secret_id: Optional[str]      # None -> предметное наблюдение без секрета
    surface_kind: SurfaceKind
    source_id: str                # кто породил поверхность
    text: str                     # автотекст из шаблонов (kind, level)


@dataclass(frozen=True)
class SurfaceEvent:
    """Вход DiscoveryBridge. Прямой вызов — НЕ шинное событие (D17:
    на EventBus выходит только LevelChangeEvent; закон 2.1.1 EventDTO-only).
    """

    kind: SurfaceKind
    tick: int
    source_id: str
    secret_id: Optional[str] = None          # структурный провенанс
    disclosure_level: Optional[DisclosureLevel] = None  # DIALOGUE_OUTCOME
    content_class: Optional[str] = None      # EAVESDROP / DM_NARRATIVE
    subject_hint: Optional[str] = None       # тема/предмет (для шаблонов)


@dataclass(frozen=True)
class LevelChangeEvent:
    """Трасса перехода уровня. observation-only (Закон XI, прецедент
    CONCLUSION_FORMED): пассивные данные, НЕ команда. Подписчики —
    журнал/toast (P8), телеметрия. persistence=session (campaign — P11).
    """

    secret_id: str
    from_level: int
    to_level: int
    tick: int
    surface_kind: SurfaceKind


@dataclass(frozen=True)
class EpistemicUpdate:
    """Выход DiscoveryBridge.process: журнал одного применения
    (телеметрия/снапшот; observation-only)."""

    secret_id: Optional[str]
    surface_kind: SurfaceKind
    from_level: int
    to_level: int
    level_changed: bool
    marked_discovered: bool       # вызван ли truth.mark_discovered (только ->2)
    level_change: Optional[LevelChangeEvent]
    observation: Optional[PlayerObservation]
