# path: C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\character\character_filter_applicator.py
"""
Применение CharacterFilter к действию игрока.

Фаза 2.0.4: фильтрует действие через психологию персонажа.
Вынесено из game_loop — координация между CharacterFilter и CharacterService.

Назначение: Применение CharacterFilter к профилю персонажа
Зависимости: logging, app.services.character.character_filter (lazy import)
Основные сущности: apply_character_filter
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def apply_character_filter(
    character_service: Any,
    campaign_id: str,
    player_name: str,
    hub_event: Any,
    shared_context: Any,
) -> Optional[dict]:
    """Фильтрует действие через психологию персонажа (один раз на ход).

    Возвращает filter_result.to_dict() если RESIST/REFUSE, иначе None.
    Если профиль пустой (аватар без ценностей) — пропускает фильтр.
    Мутирует: profile (erosion), shared_context.character_filter.
    """
    _filter_result = None
    try:
        from app.services.character.character_filter import (
            CharacterFilter as CharFilter,
        )

        _profile = character_service.get_or_create_profile(campaign_id, player_name)
        # Если профиль пустой (аватар без ценностей) — пропускаем фильтр
        if _profile.values.weights:
            _cf = CharFilter()
            _filter_result = _cf.compute_resistance(
                profile=_profile,
                event_type=hub_event.event_type,
                intensity=getattr(hub_event, "intensity", 0.5) or 0.5,
            )
            # Применяем эрозию если была
            if _filter_result.erosion_applied > 0:
                _profile.apply_erosion(
                    _filter_result.erosion_applied,
                    f"{hub_event.event_type}: {_filter_result.outcome.value}",
                )
                character_service.upsert_profile(campaign_id, _profile)

            logger.debug(
                f"[CHAR_FILTER] {player_name}: {_filter_result.outcome.value} "
                f"(res={_filter_result.resistance:.2f}, mod={_filter_result.action_modifier:.2f})"
            )

            # RESIST/REFUSE — передаём контекст DM, пропускаем NPC решения
            if _filter_result.outcome.value in ("resist", "refuse"):
                _result_dict = _filter_result.to_dict()
                shared_context.character_filter = _result_dict
                # DM увидит описание в prompt, NPC решения не нужны
                return _result_dict
    except Exception as _cfe:
        logger.warning(f"[CHAR_FILTER] Error (non-blocking): {_cfe}")
    return None
