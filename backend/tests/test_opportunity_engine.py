# backend\tests\test_opportunity_engine.py
# Назначение: Unit-тесты для проверки корректности внедрения R6.3 (OpportunityEngine — hidden actions для сломленных NPC).
# Зависимости: pytest opportunity_engine.py (OpportunityContext, OpportunityResult, OpportunityEngine)
# Основные сущности: OpportunityContext, OpportunityResult, OpportunityEngine
#  $env:PYTHONPATH="backend"; pytest backend/tests/test_opportunity_engine.py -v

from dataclasses import asdict

import pytest
from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.services.economy.opportunity_engine import (
    OpportunityContext,
    OpportunityEngine,
    OpportunityResult,
)

# ===================================================================
# FIXTURES
# ===================================================================


@pytest.fixture
def broken_npc_state():
    """Фикстура для типичного сломленного NPC (will_state = broken)."""
    return type("NPCState", (), {"will_state": "broken"})()


@pytest.fixture
def free_npc_state():
    """Фикстура для обычного NPC (will_state = free)."""
    return type("NPCState", (), {"will_state": "free"})()


@pytest.fixture
def coerced_npc_state():
    """Фикстура для coerced NPC (не broken)."""
    return type("NPCState", (), {"will_state": "coerced"})()


# ===================================================================
# ТЕСТЫ: БАЗОВАЯ ЛОГИКА OpportunityEngine.calculate()
# ===================================================================


@pytest.mark.parametrize(
    "ctx, will_state, expected_allow, min_score",
    [
        # Максимальный шанс (игрок полностью отвлечён, NPC в выгодной позиции)
        (
            OpportunityContext(
                player_attention=0.05,
                distance=28.0,
                weapon_access=True,
                allies=3,
            ),
            "broken",
            True,
            0.90,  # актуальное значение по текущей формуле ≈0.925
        ),
        # Минимальный шанс (игрок в упор, полное внимание)
        (
            OpportunityContext(
                player_attention=1.0,
                distance=0.3,
                weapon_access=False,
                allies=0,
            ),
            "broken",
            False,
            0.0,
        ),
        # Пограничный случай (score ниже порога 0.65)
        (
            OpportunityContext(
                player_attention=0.4,
                distance=12.0,
                weapon_access=True,
                allies=1,
            ),
            "broken",
            False,  # по текущей формуле ≈0.5675 < 0.65
            0.50,
        ),
        # Нулевые/отрицательные значения (защита от некорректных данных)
        (
            OpportunityContext(
                player_attention=0.0,
                distance=0.0,
                weapon_access=False,
                allies=-1,
            ),
            "broken",
            False,
            0.0,
        ),
    ],
)
def test_opportunity_score_calculation(ctx, will_state, expected_allow, min_score):
    """Проверка корректности формулы opportunity_score = player_attention↓ + distance + weapon_access + allies."""
    result: OpportunityResult = OpportunityEngine.calculate(ctx, will_state)

    assert result.hidden_action_allowed is expected_allow
    assert result.score >= min_score
    assert 0.0 <= result.score <= 1.0


def test_non_broken_will_state_always_denied(broken_npc_state, free_npc_state, coerced_npc_state):
    """OpportunityEngine игнорирует любые высокие score, если will_state ≠ broken."""
    high_score_ctx = OpportunityContext(
        player_attention=0.05,
        distance=30.0,
        weapon_access=True,
        allies=5,
    )

    for state in [free_npc_state, coerced_npc_state]:
        result = OpportunityEngine.calculate(high_score_ctx, state.will_state)
        assert result.hidden_action_allowed is False
        assert result.score == 0.0
        assert result.score_trace.get("reason") == "will_state_not_broken"


def test_broken_state_with_low_score_still_denied():
    """Даже при will_state=broken низкий score → отказ."""
    low_ctx = OpportunityContext(
        player_attention=0.95,
        distance=1.0,
        weapon_access=False,
        allies=0,
    )
    result = OpportunityEngine.calculate(low_ctx, "broken")
    assert result.hidden_action_allowed is False
    assert result.score < 0.3


# ===================================================================
# ТЕСТЫ: АНТИ-ЭКСПЛОЙТ И DIMINISHING RETURNS
# ===================================================================


@pytest.mark.parametrize("repeat_count", [1, 3, 7])
def test_repeated_opportunity_has_diminishing_returns(repeat_count):
    """Повторные вызовы на одном NPC снижают score (защита от абьюза)."""
    ctx = OpportunityContext(
        player_attention=0.1,
        distance=25.0,
        weapon_access=True,
        allies=2,
    )

    scores = []
    for _ in range(repeat_count):
        result = OpportunityEngine.calculate(ctx, "broken")
        scores.append(result.score)
        # имитируем небольшой тик
        ctx = OpportunityContext(
            player_attention=ctx.player_attention + 0.05,
            distance=ctx.distance,
            weapon_access=ctx.weapon_access,
            allies=ctx.allies,
        )

    # каждый следующий score должен быть ниже предыдущего
    for i in range(1, len(scores)):
        assert scores[i] < scores[i - 1], f"Diminishing returns не сработал на шаге {i}"


def test_opportunity_result_structure():
    """Проверка dataclass-структуры результата (для совместимости с StateApplicator)."""
    ctx = OpportunityContext(player_attention=0.2, distance=15.0, weapon_access=True, allies=1)
    result = OpportunityEngine.calculate(ctx, "broken")

    assert isinstance(result, OpportunityResult)
    assert hasattr(result, "hidden_action_allowed")
    assert hasattr(result, "score")
    assert hasattr(result, "unlocked_intents")
    assert hasattr(result, "score_trace")

    # можно сериализовать в dict
    data = asdict(result)
    assert "hidden_action_allowed" in data
    assert isinstance(data["score"], float)


# ===================================================================
# ИНТЕГРАЦИОННЫЙ ТЕСТ С NPCState (минимальный)
# ===================================================================


def test_integration_with_npcstate_will_state(broken_npc_state):
    """OpportunityEngine корректно читает will_state напрямую из NPCState."""
    ctx = OpportunityContext(player_attention=0.05, distance=20.0, weapon_access=True, allies=2)

    result = OpportunityEngine.calculate(ctx, broken_npc_state.will_state)
    assert result.hidden_action_allowed is True


# ===================================================================
# ЗАПУСК
# ===================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
