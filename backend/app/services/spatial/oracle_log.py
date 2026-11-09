# path: backend/app/services/spatial/oracle_log.py
# Назначение: P2-02 (ADR-O-439 D.2) — структурный лог решения оракула локации.
#     Единая точка логирования для 3 оракулов (HTTP/idle/bridge): world_xy,
#     candidates, winner, prev→new, правило. Без поведенческих изменений —
#     только диагностика рассинхрона «логика/визуал» (C-P1, ROADMAP §P2-02).
# Зависимости: logging (stdlib), typing.
# Основные сущности:
#     - log_oracle_decision — структурный лог одной строкой
"""
P2-02 (ADR-O-439 D.2): наблюдаемость оракула локации.

Контракт ROADMAP §P2-02:
- Структурный лог (одна строка): world_xy, кандидаты, выбранная локация, правило.
- При смене локации относительно metadata — INFO-лог.
- Без PII в логах.

Реализован как единый helper для 3 оракулов:
- routes.py (HTTP path) — tag="HTTP"
- game_loop.py (idle oracle) — tag="IDLE"
- game_loop_bridge.py (frontend oracle) — tag="BRIDGE"

Multi-chunk warning остаётся в SpatialRegistry.resolve_primary (P2-01) —
не дублируется здесь. Этот helper логирует КОНТЕКСТ вызова оракула (когда,
зачем, что выбрано), а resolve_primary — ГЕОМЕТРИЧЕСКОЕ правило выбора
(кандидаты, площадь, lex tiebreaker).
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def log_oracle_decision(
    *,
    tag: str,
    world_x: float,
    world_y: float,
    candidates_count: int,
    winner_id: Optional[str],
    prev_location: Optional[str],
    new_location: Optional[str],
    source: str = "",
) -> None:
    """Структурный лог решения оракула локации (P2-02, D.2).

    Одна строка, maшиночитаемая для grep/фильтрации:
    [SPATIAL_ORACLE] tag=HTTP world=(33.0, 12.0) candidates=1 winner=tavern prev=city_gate → new=tavern rule=D.2

    Уровни:
    - INFO  — смена локации (prev != new, winner_id is not None)
    - DEBUG — отсутствие смены (prev == new, winner_id is not None)
    - WARNING — winner_id is None (точка вне footprint'ов)

    Multi-chunk warning (candidates > 1) логируется отдельно в
    SpatialRegistry.resolve_primary (P2-01) — здесь не дублируется.

    Args:
        tag: источник вызова ("HTTP" / "IDLE" / "BRIDGE")
        world_x, world_y: мировые координаты игрока
        candidates_count: количество чанков, содержащих точку (из find_chunks)
        winner_id: location_id победителя (из resolve_primary); None если точка вне
        prev_location: локация ДО оракула (из metadata/active_loc)
        new_location: локация ПОСЛЕ оракула (= winner_id или prev если winner None)
        source: файл:строка для диагностики (опционально)
    """
    src = f" src={source}" if source else ""
    base = (
        f"[SPATIAL_ORACLE] tag={tag} world=({world_x:.1f}, {world_y:.1f}) "
        f"candidates={candidates_count} winner={winner_id} "
        f"prev={prev_location} → new={new_location} rule=D.2{src}"
    )

    if winner_id is None:
        # Точка вне footprint'ов — fallback к saved location
        logger.warning(f"{base} | OUTSIDE_ALL_CHUNKS")
    elif prev_location is not None and prev_location != new_location:
        # Смена локации — INFO (видимое событие)
        logger.info(f"{base} | LOCATION_CHANGED")
    else:
        # Нет смены (или prev неизвестен) — DEBUG (шум подавить)
        logger.debug(f"{base} | no_change")