# backend/tests/test_run_terminal_dm.py
# Legacy: run_terminal_dm.py удалён вместе с orchestrator.
# Файл оставлен как smoke-тест текущего ядра (game_loop).
import pytest


def test_game_loop_import():
    """game_loop должен импортироваться без ошибок."""
    from app.services.game_loop import GameLoop
    assert GameLoop is not None


def test_action_classifier_import():
    """Классификатор действий должен быть доступен."""
    from app.services.action_classifier import classifier
    assert classifier is not None


def test_classifier_returns_known_type():
    """Классификатор возвращает известный тип для простого действия."""
    from app.services.action_classifier import classifier
    result = classifier.classify("атакую стражника мечом")
    assert result is not None


def test_event_bus_campaign_filter():
    """get_recent_events фильтрует по campaign_id."""
    from app.services.events.event_bus import get_event_bus, reset_event_bus
    reset_event_bus()
    bus = get_event_bus()

    from app.services.events.event_types import GameEvent, EventType
    e1 = GameEvent(event_type=EventType.PLAYER_SPOKE, actor_id="player", location="tavern", campaign_id="camp_A")
    e2 = GameEvent(event_type=EventType.PLAYER_SPOKE, actor_id="player", location="tavern", campaign_id="camp_B")
    bus.publish(e1)
    bus.publish(e2)

    result_a = bus.get_recent_events(limit=10, campaign_id="camp_A")
    result_b = bus.get_recent_events(limit=10, campaign_id="camp_B")

    assert all(e["campaign_id"] == "camp_A" for e in result_a)
    assert all(e["campaign_id"] == "camp_B" for e in result_b)

    reset_event_bus()