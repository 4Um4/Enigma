# path: C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\character\front_applicator.py
"""
Применение FrontEngine к профилю персонажа.

Фаза 5.1: давление мира на персонажа — решение о маске/фасаде.
Вынесено из game_loop — координация между FrontEngine и CharacterService.

Назначение: Применение FrontEngine к профилю персонажа
Зависимости: logging, app.services.character.front_engine (lazy import)
Основные сущности: apply_front_engine
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def apply_front_engine(
    character_service: Any,
    reputation_engine: Optional[Any],
    campaign_id: str,
    player_name: str,
    shared_context: Any,
) -> None:
    """Давление мира на персонажа — решение о маске/фасаде.

    Мутирует: player_profile (front, erosion), shared_context (front_description, front_type, world_pressure).
    Записывает изменения через character_service.upsert_profile.
    """
    try:
        from app.services.character.front_engine import FrontEngine

        _front_eng = FrontEngine()
        _player_profile = character_service.get_or_create_profile(
            campaign_id, player_name
        )
        # Собираем сигналы давления из систем
        _player_rep = 0.0
        if reputation_engine:
            _rep_states = reputation_engine.get_all_faction_states()
            if _rep_states:
                _player_rep = sum(s["reputation"] for s in _rep_states.values()) / len(
                    _rep_states
                )
        _world_pressure = _front_eng.compute_pressure(
            profile=_player_profile,
            player_reputation=_player_rep,
        )
        _front_decision = _front_eng.decide(
            profile=_player_profile,
            pressure=_world_pressure,
            current_tick=shared_context.current_tick or 0,
        )
        # Применяем решение к профилю
        if _front_decision.action == "adopt":
            if _player_profile.front is None:
                from app.models.front import FrontState

                _player_profile.front = FrontState()
            _player_profile.front.adopt(
                _front_decision.front_type,
                tick=shared_context.current_tick or 0,
                intensity=_world_pressure.total_pressure,
            )
        elif _front_decision.action == "intensify" and _player_profile.front:
            _player_profile.front.intensity = min(
                1.0, _player_profile.front.intensity + 0.1
            )
        elif _front_decision.action in ("drop", "break") and _player_profile.front:
            if _front_decision.action == "break":
                _player_profile.front.breaks.append(
                    f"tick={shared_context.current_tick or 0}: {_front_decision.front_description}"
                )
            _player_profile.front.drop()
        # Стоимость поддержания маски — эрозия целостности
        if _front_decision.integrity_cost > 0:
            _player_profile.apply_erosion(
                _front_decision.integrity_cost,
                f"front_{_front_decision.front_type.value}",
            )
        character_service.upsert_profile(campaign_id, _player_profile)
        # Передаём DM описание маски
        if _front_decision.front_description:
            shared_context.front_description = _front_decision.front_description
            shared_context.front_type = _front_decision.front_type.value
        if _world_pressure.total_pressure > 0.1:
            shared_context.world_pressure = round(_world_pressure.total_pressure, 3)
        logger.debug(
            f"[FRONT] action={_front_decision.action}, "
            f"pressure={_world_pressure.total_pressure:.2f}, "
            f"cost={_front_decision.integrity_cost:.4f}"
        )
    except Exception as _fe_err:
        logger.warning(f"[FRONT] Error: {_fe_err}")
