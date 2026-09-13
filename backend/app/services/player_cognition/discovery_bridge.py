# path: /project/backend/app/services/player_cognition/discovery_bridge.py
"""
Файл: backend/app/services/player_cognition/discovery_bridge.py
Назначение: P6 — DiscoveryBridge: ЕДИНСТВЕННАЯ точка превращения игровых
    событий в знание игрока (ТЗ-P6). map_surface — чистая функция (решение
    только из структурных полей surface; TruthState не читается; текст
    реплик не анализируется — анти-лотерея). Writer применяет решение:
    raise_level -> при ->2 truth.mark_discovered (Р1: единственный вызов
    во всём коде) -> наблюдение.
    S255-фикс приёмки: Р1-гейт (mark ТОЛЬКО при фактическом переходе
    -> IDENTIFIED) + сортировка импортов (I001).
Зависимости: app.domain.player_epistemics, app.domain.disclosure,
    app.models.player_epistemic_state (TruthState — TYPE_CHECKING;
    модель НЕ меняется)
Основные сущности: SurfaceDecision, map_surface, DiscoveryBridge
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from app.domain.disclosure import DisclosureLevel
from app.domain.player_epistemics import (
    CLUE,
    CONTENT_ACTION_SECRET_LANDED,
    CONTENT_EAVESDROP_FULL,
    IDENTIFIED,
    UNKNOWN,
    EpistemicUpdate,
    LevelChangeEvent,
    PlayerObservation,
    SurfaceEvent,
    SurfaceKind,
)
from app.models.player_epistemic_state import PlayerEpistemicState

if TYPE_CHECKING:
    from app.models.truth_state import TruthState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SurfaceDecision:
    """Решение чистого маппера: целевой уровень + флаг наблюдения."""

    secret_id: Optional[str]
    target_level: Optional[int]   # None -> уровень не меняется (obs only)
    observation: bool


def map_surface(surface: SurfaceEvent) -> SurfaceDecision:
    """ЧИСТАЯ функция (T9-инвариант: немутация входа, детерминизм).

    Mapping (ТЗ-P6 + Р3/Q7, утверждено S255):
        DIALOGUE_OUTCOME:
            REVEAL           -> IDENTIFIED
            PARTIAL          -> CLUE (enriched — в observation-тексте)
            HINT             -> CLUE ("если ещё 0" — гвард монотонности)
            DENY/REDIRECT/-  -> observation only
        EAVESDROP:
            без секрет-метки (весь P6, до P7) -> observation only
            с меткой: CONTENT_EAVESDROP_FULL -> IDENTIFIED; иначе CLUE
        DM_NARRATIVE:
            CONTENT_ACTION_SECRET_LANDED -> IDENTIFIED (Р3)
            прочий -> observation only
        VISUAL_CUE: ТЗ-мандат enum; эмиссии в P6 нет -> консервативно
            observation only
    """
    if surface.kind == SurfaceKind.DIALOGUE_OUTCOME:
        level = surface.disclosure_level
        if level == DisclosureLevel.REVEAL:
            return SurfaceDecision(surface.secret_id, IDENTIFIED, True)
        if level == DisclosureLevel.PARTIAL:
            return SurfaceDecision(surface.secret_id, CLUE, True)
        if level == DisclosureLevel.HINT:
            return SurfaceDecision(surface.secret_id, CLUE, True)
        return SurfaceDecision(surface.secret_id, None, True)

    if surface.kind == SurfaceKind.EAVESDROP:
        if surface.secret_id is None:
            return SurfaceDecision(None, None, True)
        if surface.content_class == CONTENT_EAVESDROP_FULL:
            return SurfaceDecision(surface.secret_id, IDENTIFIED, True)
        return SurfaceDecision(surface.secret_id, CLUE, True)

    if surface.kind == SurfaceKind.DM_NARRATIVE:
        if surface.content_class == CONTENT_ACTION_SECRET_LANDED:
            return SurfaceDecision(surface.secret_id, IDENTIFIED, True)
        return SurfaceDecision(surface.secret_id, None, True)

    return SurfaceDecision(surface.secret_id, None, True)


def _observation_text(surface: SurfaceEvent, secret_id: Optional[str]) -> str:
    """Автотекст из шаблонов по (kind, level) — ТЗ-P6 п.6.
    НЕ LLM-фантазия; НЕ анализ текста реплики."""
    subject = surface.subject_hint or secret_id or "?"
    if surface.kind == SurfaceKind.DIALOGUE_OUTCOME:
        level = surface.disclosure_level
        if level == DisclosureLevel.REVEAL:
            return f"{surface.source_id} рассказал про {subject}"
        if level == DisclosureLevel.PARTIAL:
            return f"{surface.source_id} частично подтвердил: {subject}"
        if level == DisclosureLevel.HINT:
            return f"{surface.source_id} намекнул про {subject}"
        return f"{surface.source_id} уклонился от ответа про {subject}"
    if surface.kind == SurfaceKind.EAVESDROP:
        if secret_id is None:
            return f"подслушано ({surface.source_id}): {subject}"
        return f"подслушано у {surface.source_id} про {subject}"
    if surface.kind == SurfaceKind.DM_NARRATIVE:
        return f"мир подтвердил: {subject}"
    return f"наблюдение: {subject}"


class DiscoveryBridge:
    """Единственный writer discovery игрока (Р1; монополия-гейт T5 —
    scripts/check_discovery_monopoly.py, Шаг 2)."""

    def __init__(
        self,
        state: PlayerEpistemicState,
        truth_state: Optional["TruthState"] = None,
    ) -> None:
        self._state = state
        self._truth = truth_state

    def process(self, surface: SurfaceEvent) -> List[EpistemicUpdate]:
        """Применить SurfaceEvent: наблюдение -> (валидация) -> подъём
        уровня -> при переходе к IDENTIFIED truth.mark_discovered (Р1).
        Возвращает журнал применения (observation-only)."""
        decision = map_surface(surface)

        observation: Optional[PlayerObservation] = None
        if decision.observation:
            observation = PlayerObservation(
                tick=surface.tick,
                secret_id=decision.secret_id,
                surface_kind=surface.kind,
                source_id=surface.source_id,
                text=_observation_text(surface, decision.secret_id),
            )
            self._state.add_observation(observation)

        from_level = (
            self._state.level(decision.secret_id) if decision.secret_id else UNKNOWN
        )
        to_level = from_level
        change: Optional[LevelChangeEvent] = None
        marked = False

        if decision.secret_id and decision.target_level is not None:
            if self._truth is not None and decision.secret_id not in self._truth.secrets:
                # Гвард D4: неизвестный id -> телеметрия, не молча;
                # уровень не поднимаем (невалидный провенанс surface)
                logger.warning(
                    f"[DISCOVERY_BRIDGE] unknown secret_id={decision.secret_id!r}: "
                    "уровень не поднят (телеметрия)"
                )
            else:
                change = self._state.raise_level(
                    decision.secret_id, decision.target_level, surface
                )
                if change is not None:
                    from_level = change.from_level
                    to_level = change.to_level
                    # Р1 (S255, вердикт приёмки): mark_discovered ⇔
                    # фактический переход → IDENTIFIED. UNKNOWN→CLUE и
                    # CLUE→CLUE права на mark НЕ имеют.
                    if change.to_level == IDENTIFIED:
                        marked = self._mark_discovered(decision.secret_id)

        return [
            EpistemicUpdate(
                secret_id=decision.secret_id,
                surface_kind=surface.kind,
                from_level=from_level,
                to_level=to_level,
                level_changed=change is not None,
                marked_discovered=marked,
                level_change=change,
                observation=observation,
            )
        ]

    def _mark_discovered(self, secret_id: str) -> bool:
        """Р1 (S255): truth.mark_discovered вызывается ТОЛЬКО отсюда и
        ТОЛЬКО при переходе -> IDENTIFIED. Вызов существующего метода;
        модель TruthState не меняется (запрет Шага 1)."""
        if self._truth is None:
            return False
        self._truth.mark_discovered(secret_id)
        return True
