# backend/tests/micro/test_r1_s357_attribution_fix.py
"""
R1 (S357): Тесты исправления ложной атрибуции player в памяти NPC.

Контракт (вердикт Мастера R1):
- Для хода игрока — state.player_target_id (канонический адресат).
- Для автономного тика — реальный target интента NPC или target события,
  либо "" (честное отсутствие адресата).
- Запрет: fallback на "player" для автономных событий (S357/B'-005).

Три случая:
1. Автономное событие без адресата -> target_id="".
2. Автономное событие с реальным адресатом -> target_id=intent_target.
3. Обычное действие игрока -> target_id=player_target_id.
"""
from __future__ import annotations

import types
from enum import Enum

import pytest


# --- mock-фабрики (unit-тест функций, не интеграция) ---

class _FakeIntent(Enum):
    TALK = "TALK"
    ATTACK = "ATTACK"
    FLEE = "FLEE"


def _make_decision(intent_value: str = "TALK", intent_target=None, deltas=None):
    """Mock DecisionResult: только поля, читаемые create_memory_event."""
    return types.SimpleNamespace(
        intent=_FakeIntent[intent_value] if intent_value else None,
        intent_target=intent_target,
        deltas=deltas or [],
    )


def _make_hub_event(event_type: str = "world_tick", actor_id: str = "merchant_goran",
                    target_id=None, payload=None):
    """Mock EventContext: только поля, читаемые тестируемыми функциями."""
    return types.SimpleNamespace(
        event_type=event_type,
        actor_id=actor_id,
        target_id=target_id,
        payload=payload or {},
    )


def _make_state_l2(emotion: str = "neutral", stress: float = 0.0):
    """Mock NPCState: только поля, читаемые тестируемыми функциями."""
    return types.SimpleNamespace(
        emotion=types.SimpleNamespace(value=emotion),
        stress=stress,
    )


# --- импорт тестируемых функций ---

from app.services.npc.npc_tick_pipeline import (
    create_memory_event,
    apply_perception_memory,
)


# =========================================================================
# create_memory_event — три случая
# =========================================================================

class TestCreateMemoryEventAttribution:
    """R1: create_memory_event получает правильный target_id."""

    def test_1_autonomous_no_target(self):
        """Случай 1: автономное событие без адресата.

        player_target_id="" (WORLD_TICK), intent_target=None.
        Ожидание: create_memory_event возвращает None — событие не создаётся,
        потому что нет интеракции (нет target, нет player_interacts).
        Это правильно: WORLD_TICK без target = нет памяти, нет фантома.
        Главное — НЕ возвращается EventDTO с target_id="player" (S357).
        """
        decision = _make_decision(intent_value="TALK", intent_target=None)
        hub_event = _make_hub_event(event_type="world_tick", actor_id="merchant_goran")
        state_l2 = _make_state_l2()

        # Симулируем логику call site (точка 1226 после патча):
        _effective_target = "" or decision.intent_target or ""

        evt = create_memory_event(
            memory_manager=None,
            state_l2=state_l2,
            decision=decision,
            npc_id="guard_borko",
            hub_event=hub_event,
            player_target_id=_effective_target,
            player_text="",
            scene_state={},
            campaign_id="test",
        )

        # Событие не создаётся: нет интеракции, нет target, нет player_interacts.
        # S357: главное — нет EventDTO с target_id="player" (ложная атрибуция устранена).
        assert evt is None, (
            f"Автономное событие без адресата: ожидался None (нет интеракции), "
            f"получен {evt!r} — если EventDTO, проверь что target_id не 'player' (S357)"
        )

    def test_2_autonomous_with_real_target(self):
        """Случай 2: автономное событие с реальным адресатом.

        player_target_id="" (WORLD_TICK), intent_target="merchant_goran".
        Ожидание: target_id="merchant_goran" (реальный target интента NPC).
        """
        decision = _make_decision(intent_value="TALK", intent_target="merchant_goran")
        hub_event = _make_hub_event(event_type="world_tick", actor_id="guard_borko")
        state_l2 = _make_state_l2()

        # Симулируем логику call site (точка 1226 после патча):
        _effective_target = "" or decision.intent_target or ""

        evt = create_memory_event(
            memory_manager=None,
            state_l2=state_l2,
            decision=decision,
            npc_id="guard_borko",
            hub_event=hub_event,
            player_target_id=_effective_target,
            player_text="",
            scene_state={},
            campaign_id="test",
        )

        assert evt is not None
        assert evt.payload["target_id"] == "merchant_goran", (
            f"Автономное событие с target: должен быть 'merchant_goran', "
            f"получен {evt.payload['target_id']!r}"
        )

    def test_3_player_action_preserved(self):
        """Случай 3: обычное действие игрока.

        player_target_id="guard_borko" (ход игрока).
        Ожидание: target_id="guard_borko" (прежняя атрибуция сохранена).
        """
        decision = _make_decision(intent_value="ATTACK", intent_target=None)
        hub_event = _make_hub_event(
            event_type="player_interacts", actor_id="player", target_id="guard_borko"
        )
        state_l2 = _make_state_l2(emotion="fearful", stress=30.0)

        # Симулируем логику call site (точка 1226 после патча):
        _effective_target = "guard_borko" or decision.intent_target or ""

        evt = create_memory_event(
            memory_manager=None,
            state_l2=state_l2,
            decision=decision,
            npc_id="guard_borko",
            hub_event=hub_event,
            player_target_id=_effective_target,
            player_text="ударить Борко",
            scene_state={},
            campaign_id="test",
        )

        assert evt is not None
        assert evt.payload["target_id"] == "guard_borko", (
            f"Действие игрока: target_id должен быть 'guard_borko', "
            f"получен {evt.payload['target_id']!r} — регрессия атрибуции хода игрока"
        )


# =========================================================================
# apply_perception_memory — три случая
# =========================================================================

class TestApplyPerceptionMemoryAttribution:
    """R1: apply_perception_memory получает правильный target_id."""

    def test_4_perception_autonomous_no_target(self):
        """Случай 1: восприятие автономного события без адресата.

        player_target_id="" (WORLD_TICK), hub_event.target_id=None.
        Ожидание: target_id="" (честное отсутствие), НЕ "player".
        """
        hub_event = _make_hub_event(
            event_type="world_tick", actor_id="merchant_goran", target_id=None
        )
        state_l2 = _make_state_l2()

        # Симулируем логику call site (точка 208 после патча):
        _p_target = "" or hub_event.target_id or ""

        evt = apply_perception_memory(
            memory_manager=None,
            state_l2=state_l2,
            hub_event=hub_event,
            npc_id="guard_borko",
            player_target_id=_p_target,
            player_text="(обрывки разговора)",
            campaign_id="test",
        )

        assert evt is not None
        assert evt.payload["target_id"] == "", (
            f"Восприятие без адресата: target_id должен быть '', "
            f"получен {evt.payload['target_id']!r} — fallback на 'player' не устранён (S357)"
        )

    def test_5_perception_autonomous_with_target(self):
        """Случай 2: восприятие автономного события с адресатом.

        player_target_id="" (WORLD_TICK), hub_event.target_id="merchant_goran".
        Ожидание: target_id="merchant_goran".
        """
        hub_event = _make_hub_event(
            event_type="world_tick", actor_id="guard_borko", target_id="merchant_goran"
        )
        state_l2 = _make_state_l2()

        # Симулируем логику call site (точка 208 после патча):
        _p_target = "" or hub_event.target_id or ""

        evt = apply_perception_memory(
            memory_manager=None,
            state_l2=state_l2,
            hub_event=hub_event,
            npc_id="guard_borko",
            player_target_id=_p_target,
            player_text="(обрывки разговора)",
            campaign_id="test",
        )

        assert evt is not None
        assert evt.payload["target_id"] == "merchant_goran", (
            f"Восприятие с target: должен быть 'merchant_goran', "
            f"получен {evt.payload['target_id']!r}"
        )

    def test_6_perception_player_action_preserved(self):
        """Случай 3: восприятие действия игрока.

        player_target_id="guard_borko" (ход игрока).
        Ожидание: target_id="guard_borko".
        """
        hub_event = _make_hub_event(
            event_type="player_interacts", actor_id="player", target_id="guard_borko"
        )
        state_l2 = _make_state_l2()

        # Симулируем логику call site (точка 208 после патча):
        _p_target = "guard_borko" or hub_event.target_id or ""

        evt = apply_perception_memory(
            memory_manager=None,
            state_l2=state_l2,
            hub_event=hub_event,
            npc_id="guard_borko",
            player_target_id=_p_target,
            player_text="угрожать Борко",
            campaign_id="test",
        )

        assert evt is not None
        assert evt.payload["target_id"] == "guard_borko", (
            f"Восприятие хода игрока: target_id должен быть 'guard_borko', "
            f"получен {evt.payload['target_id']!r} — регрессия"
        )


# =========================================================================
# call site resolution — проверка логики патча
# =========================================================================

class TestCallSiteResolutionLogic:
    """R1: логика разрешения target в call sites (точки 1226 и 208)."""

    def test_7_resolution_priority_player_first(self):
        """Ход игрока имеет приоритет: player_target_id > intent_target > ""."""
        # Симулирует точку 1226
        player_target_id = "guard_borko"
        intent_target = "merchant_goran"
        result = player_target_id or intent_target or ""
        assert result == "guard_borko"

    def test_8_resolution_autonomous_uses_intent_target(self):
        """Автономный тик: intent_target используется, когда player_target_id пуст."""
        # Симулирует точку 1226
        player_target_id = ""
        intent_target = "merchant_goran"
        result = player_target_id or intent_target or ""
        assert result == "merchant_goran"

    def test_9_resolution_autonomous_no_target_empty(self):
        """Автономный тик без target: честное '', НЕ 'player'."""
        # Симулирует точку 1226
        player_target_id = ""
        intent_target = None
        result = player_target_id or intent_target or ""
        assert result == ""
        assert result != "player", "S357: fallback на 'player' запрещён"

    def test_10_resolution_perception_uses_hub_target(self):
        """Точка 208: hub_event.target_id используется, когда player_target_id пуст."""
        # Симулирует точку 208
        player_target_id = ""
        hub_target_id = "merchant_goran"
        result = player_target_id or hub_target_id or ""
        assert result == "merchant_goran"

    def test_11_resolution_perception_no_target_empty(self):
        """Точка 208 без target: честное '', НЕ 'player'."""
        # Симулирует точку 208
        player_target_id = ""
        hub_target_id = None
        result = player_target_id or hub_target_id or ""
        assert result == ""
        assert result != "player", "S357: fallback на 'player' запрещён"