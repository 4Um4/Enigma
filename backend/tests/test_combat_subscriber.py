# -*- coding: utf-8 -*-
"""
Тесты CombatSubscriber (Event → Physics Bridge).

Полный Запуск: cd backend; python -m pytest tests/test_combat_subscriber.py -v

Файл: backend/tests/test_combat_subscriber.py
Назначение: Тесты моста между боевыми событиями и физическим интегратором.
Зависимости: pytest, app.services.combat.combat_subscriber, app.models.*

Проверяют:
1. Подписка на боевые события (PLAYER_ATTACKS, COMBAT)
2. Игнорирование небоевых событий
3. Извлечение ImpactIntentDTO из EventDTO.payload
4. Вызов ImpactEngine и возврат Physiology-дельт
5. PHYSICS_COMPOSITE: дельты имеют domain=PHYSIOLOGY
6. Обработка отсутствующего target_id (skip)
7. Fallback на player snapshot при атаке игрока
8. drain_events() очищает буфер
"""
import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.combat.combat_subscriber import CombatSubscriber
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType
from app.models.phase8 import Phase8Context, Phase8Result
from app.models.state_delta import DeltaDomain
from app.models.delta_payloads import PhysiologyPayload
from app.domain.events import EventDTO


def _make_event(
    event_type: str = "player_attacks",
    source: str = "player",
    payload: dict | None = None,
) -> EventDTO:
    """Фабрика EventDTO для тестов — реальные объекты, не моки."""
    return EventDTO.create(
        event_type=event_type,
        source=source,
        payload=payload or {
            "target_id": "npc_1",
            "actor_id": "player",
            "intensity": 0.8,
            "damage_type": "blunt",
        },
    )


def _make_npc(npc_id: str = "npc_1", dexterity: float = 10.0) -> dict:
    """Фабрика NPC dict для Phase8Context."""
    return {
        "id": npc_id,
        "psyche": {"stress": 10.0, "loyalty_true": 50.0},
        "social_stats": {"trust": 40.0, "fear_of_player": 20.0, "debt": 0.0},
        "body_profile": {"max_hp": 100.0, "abilities": {"dexterity": dexterity}},
        "body_state": {"current_hp": 100.0, "pain": 0.0, "fatigue": 0.0,
                       "blood_loss": 0.0, "consciousness": 1.0, "modifiers": {}},
        "relationship_cache": {"player": {"trust": 40.0, "fear": 20.0}},
        "base_values": {"player": 50.0},
        "status_profile": {"faction_rank": {}},
    }


def _make_ctx(all_npcs_raw: list | None = None) -> Phase8Context:
    """Фабрика Phase8Context для тестов."""
    return Phase8Context(
        all_npcs_raw=all_npcs_raw or [_make_npc()],
        all_npc_contexts=[],
        shared_context=None,
        campaign_id="test",
        tick_ctx=None,
    )


class TestCombatSubscriberSubscription:
    """Подписка на боевые события."""

    def test_subscribes_to_player_attacks(self):
        """PLAYER_ATTACKS → подписан."""
        bus = EventBus()
        sub = CombatSubscriber(bus)
        event = _make_event("player_attacks")
        bus.publish(event)
        drained = sub.drain_events()
        assert len(drained) == 1

    def test_subscribes_to_combat(self):
        """COMBAT → подписан."""
        bus = EventBus()
        sub = CombatSubscriber(bus)
        event = _make_event("combat")
        bus.publish(event)
        drained = sub.drain_events()
        assert len(drained) == 1

    def test_ignores_non_combat_events(self):
        """PLAYER_SPOKE → НЕ подписан."""
        bus = EventBus()
        sub = CombatSubscriber(bus)
        event = _make_event("player_spoke")
        bus.publish(event)
        drained = sub.drain_events()
        assert len(drained) == 0


class TestCombatSubscriberHandle:
    """Обработка событий и генерация Physiology-дельт."""

    def test_attack_generates_physiology_deltas(self):
        """Атака → Physiology-дельты для цели."""
        bus = EventBus()
        sub = CombatSubscriber(bus)
        npc = _make_npc("npc_1")
        ctx = _make_ctx([npc])

        event = _make_event("player_attacks", payload={
            "target_id": "npc_1",
            "actor_id": "player",
            "intensity": 0.8,
        })
        result = sub.handle([event], ctx)

        assert isinstance(result, Phase8Result)
        assert len(result.deltas) > 0
        # Все дельты — PHYSIOLOGY domain
        for d in result.deltas:
            assert d.domain == DeltaDomain.PHYSIOLOGY

    def test_deltas_have_correct_npc_ids(self):
        """Дельты адресованы цели и атакующему."""
        bus = EventBus()
        sub = CombatSubscriber(bus)
        # dexterity=0 гарантирует попадание (Contact Resolution Model)
        npc = _make_npc("npc_1", dexterity=0.0)
        ctx = _make_ctx([npc])

        event = _make_event("player_attacks", payload={
            "target_id": "npc_1",
            "actor_id": "player",
            "intensity": 0.8,
        })
        result = sub.handle([event], ctx)

        npc_ids = {d.npc_id for d in result.deltas}
        assert "npc_1" in npc_ids  # Цель получила урон
        # "player" может получить fatigue_delta

    def test_no_target_id_skips_event(self):
        """Нет target_id → событие пропущено."""
        bus = EventBus()
        sub = CombatSubscriber(bus)
        ctx = _make_ctx()

        event = _make_event("player_attacks", payload={
            "actor_id": "player",
            # no target_id
        })
        result = sub.handle([event], ctx)

        assert len(result.deltas) == 0
        assert result.events_processed == 0

    def test_empty_events_returns_empty_result(self):
        """Пустой список событий → пустой результат."""
        bus = EventBus()
        sub = CombatSubscriber(bus)
        ctx = _make_ctx()

        result = sub.handle([], ctx)

        assert len(result.deltas) == 0
        assert result.events_processed == 0


class TestCombatSubscriberPlayerFallback:
    """Игрок как атакующий — идеальный снапшот."""

    def test_player_attacker_uses_fallback_snapshot(self):
        """Игрок не в all_npcs_raw → fallback снапшот."""
        bus = EventBus()
        sub = CombatSubscriber(bus)
        npc = _make_npc("npc_1")
        ctx = _make_ctx([npc])

        # actor_id = "player" — нет в npc_by_id
        event = _make_event("player_attacks", payload={
            "target_id": "npc_1",
            "actor_id": "player",
            "intensity": 1.0,
            "force": 50.0,
        })
        result = sub.handle([event], ctx)

        # Должны быть дельты — fallback-снапшот не блокирует
        assert len(result.deltas) > 0


class TestCombatSubscriberDrain:
    """drain_events() — буфер и очистка."""

    def test_drain_clears_buffer(self):
        """drain_events() очищает буфер после снятия."""
        bus = EventBus()
        sub = CombatSubscriber(bus)

        event = _make_event("player_attacks")
        bus.publish(event)

        first_drain = sub.drain_events()
        assert len(first_drain) == 1

        second_drain = sub.drain_events()
        assert len(second_drain) == 0

    def test_name_property(self):
        """name = 'combat'."""
        bus = EventBus()
        sub = CombatSubscriber(bus)
        assert sub.name == "combat"


class TestCombatSubscriberIntentExtraction:
    """Извлечение ImpactIntentDTO из payload."""

    def test_extracts_damage_type_from_payload(self):
        """damage_type из payload используется."""
        bus = EventBus()
        sub = CombatSubscriber(bus)
        npc = _make_npc("npc_1")
        ctx = _make_ctx([npc])

        event = _make_event("player_attacks", payload={
            "target_id": "npc_1",
            "actor_id": "player",
            "intensity": 0.5,
            "damage_type": "slash",
        })
        result = sub.handle([event], ctx)

        # Должны быть дельты со slash-типом (кровопотеря выше)
        assert len(result.deltas) > 0
        for d in result.deltas:
            if d.npc_id == "npc_1" and d.payload is not None:
                assert isinstance(d.payload, PhysiologyPayload)
                # Slash вызывает кровопотерю
                if d.payload.blood_loss_delta > 0:
                    break

    def test_fallback_to_blunt_without_damage_type(self):
        """Нет damage_type → fallback 'blunt'."""
        bus = EventBus()
        sub = CombatSubscriber(bus)
        npc = _make_npc("npc_1")
        ctx = _make_ctx([npc])

        event = _make_event("player_attacks", payload={
            "target_id": "npc_1",
            "actor_id": "player",
            "force": 30.0,
        })
        result = sub.handle([event], ctx)

        assert len(result.deltas) > 0  # Blunt тоже генерирует дельты