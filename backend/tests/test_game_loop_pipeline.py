# -*- coding: utf-8 -*-
"""
test_game_loop_pipeline.py — базовая фиксация работоспособности _run_pipeline.
Запуск: python -m pytest backend/tests/test_game_loop_pipeline.py -v --tb=short
Цель: убедиться, что _run_pipeline отрабатывает без падений
и возвращает _PipelineState с корректным shared_context.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.game_loop import GameLoop, _PipelineState


@pytest.fixture
def mock_deps(tmp_path):
    """Моки для всех зависимостей GameLoop."""
    return {
        "data_dir": tmp_path / "data",
        "memory_manager": MagicMock(
            run_decay_if_needed=MagicMock(return_value=None),
            detect_resonance=MagicMock(return_value=None),
            apply_identity_weights=MagicMock(),
            read_campaign_history=MagicMock(return_value=[]),
        ),
        "dm_orchestrator": AsyncMock(),
        "scene_manager": MagicMock(load_scene=MagicMock(return_value={"location_id": "test"})),
        "world_scheduler": MagicMock(),
        "character_service": MagicMock(),
        "avatar_service": MagicMock(),
        "dm_agent": AsyncMock(),
        "rules_agent": AsyncMock(),
        "load_npcs_func": MagicMock(return_value=[]),
        "adventure_loader": MagicMock(),
        "system_requirements": MagicMock(),
        "saves_dir": tmp_path / "saves",
    }


@pytest.fixture
def game_loop(mock_deps):
    """Создает GameLoop с замоканными зависимостями."""
    (mock_deps["data_dir"]).mkdir(parents=True, exist_ok=True)
    (mock_deps["saves_dir"]).mkdir(parents=True, exist_ok=True)

    return GameLoop(**mock_deps)


@pytest.mark.anyio
async def test_run_pipeline_returns_pipeline_state(game_loop):
    """Базовый тест: _run_pipeline должен завершиться и вернуть _PipelineState."""

    # Патчим settings, чтобы не падать на конфиге world_tick_minutes
    with patch("app.services.game_loop.settings") as mock_settings:
        mock_settings.world_tick_minutes = 10

        _mock_action = MagicMock(player_name="TestPlayer", raw_text="осмотреться")
        result = await game_loop._run_pipeline(
            actions=[_mock_action],
            campaign_id="test_campaign",
            world_id="test_world",
            location="tavern",
            campaign_state={},
            is_session_start=False,
        )

    # Проверки
    assert isinstance(result, _PipelineState), "Должен возвращать _PipelineState"

    # ФИКСАЦИЯ: shared_context теперь строго типизированный dataclass
    from app.models.pipeline_context import PipelineContext

    assert isinstance(result.shared_context, PipelineContext), "Должен быть PipelineContext"

    # Доступ через атрибуты, а не через ключи
    assert result.shared_context.campaign_id == "test_campaign"
    assert result.shared_context.scene_state is not None
