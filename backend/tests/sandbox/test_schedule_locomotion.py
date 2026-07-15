# backend/tests/sandbox/test_schedule_locomotion.py
# Назначение: Верификация ADR-051 (LifeEngine De-godification) и Когнитивного Стража
# Зависимости: pytest, app.services.npc.life_engine
# Основные сущности: LifeEngine, MovementIntent

from unittest.mock import MagicMock, patch

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.domain.movement import MovementIntent
from app.services.npc.life_engine import MINOR_TICK_INTERVAL, LifeEngine


@pytest.fixture
def engine():
    le = LifeEngine()
    le._spatial_service = MagicMock()
    return le


# Фикстура: Спокойный NPC со сменой активности
@pytest.fixture
def npc_calm_schedule_change():
    return {
        "id": "guard_1",
        "tier": "minor",
        "perceptual_kernel": {"threat_gradient": 0.1},  # Ниже порога 0.4
        "position": "barracks",
        "location": "tavern_silver_wolf",
        "routine": {
            "current": "sleep",
            "_last_life_tick": 0,
            # Правильный формат расписания: диапазон -> активность
            "schedule": {"06:00-18:00": "patrol", "18:00-06:00": "sleep"},
        },
    }


# Фикстура: Напуганный NPC
@pytest.fixture
def npc_threatened_schedule_change():
    return {
        "id": "guard_1",
        "tier": "minor",
        "perceptual_kernel": {
            "recent_directive": {"source": "player", "salience": 0.9, "interrupts_routine": True}
        },  # ADR-056: Attention Capture
        "position": "barracks",
        "location": "tavern_silver_wolf",
        "routine": {
            "current": "sleep",
            "_last_life_tick": 0,
            "schedule": {"06:00-18:00": "patrol", "18:00-06:00": "sleep"},
        },
    }


def test_schedule_generates_intent_when_calm(engine, npc_calm_schedule_change):
    """ДОКАЗЫВАЕТ: Расписание генерирует MovementIntent при отсутствии давления (LOD1)."""
    # Изолируем создание интента от сложной логики резолва позиций
    with patch.object(engine, "_resolve_position", return_value=("tavern_silver_wolf", "gate", "patrolling")):
        changes, intents = engine._simulate_minor(
            npc_calm_schedule_change, current_time="08:00", tick=MINOR_TICK_INTERVAL + 1
        )

    assert intents is not None and len(intents) > 0, "БАГ: Спокойный NPC не сгенерировал MovementIntent по расписанию!"
    assert isinstance(intents[0], MovementIntent), f"ОШИБКА: Возвращён неверный тип: {type(intents[0])}"


def test_schedule_blocked_by_cognitive_guard(engine, npc_threatened_schedule_change):
    """ДОКАЗЫВАЕТ: Attention Capture (recent_directive.interrupts_routine) отменяет расписание (ADR-056)."""
    with patch.object(engine, "_resolve_position", return_value=("tavern_silver_wolf", "gate", "patrolling")):
        changes, intents = engine._simulate_minor(
            npc_threatened_schedule_change, current_time="08:00", tick=MINOR_TICK_INTERVAL + 1
        )

    assert intents is None or len(intents) == 0, (
        f"БАГ: Напуганный NPC (threat=0.9) всё равно идёт по расписанию! Intents: {intents}"
    )
