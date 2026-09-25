"""
path: backend/tests/sandbox/micro/test_claim_guard.py
Назначение: Proposition-guard — мусорные пропозиции (пустой object_id, polarity=None) не доезжают до веры
Зависимости: app.services.events.claim_event_subscriber
Основные сущности: ClaimEventSubscriber

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_claim_guard.py -v --tb=short; cd ..
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.events.claim_event_subscriber import ClaimEventSubscriber


def _make_subscriber():
    # MagicMock-движок: guard проверяем тем, что revise/upsert НЕ вызываются.
    # spatial_query_provider=None → легитимный путь уходит в target_id-fallback.
    return ClaimEventSubscriber(engine=MagicMock(), store=MagicMock(), spatial_query_provider=None)


def _event(prop_data):
    return SimpleNamespace(
        id="evt-1",
        source="player",
        type="social_action",
        payload={"proposition": prop_data, "target_id": "maid_lusya"},
    )


def test_reject_none_object_and_polarity():
    # Точный кейс из живого корпуса: 'stole' + object_id=None + polarity=None
    sub = _make_subscriber()
    sub.on_claim_event(_event({"subject_id": "player", "predicate": "stole", "object_id": None, "polarity": None}))
    sub._engine.revise.assert_not_called()
    sub._store.upsert.assert_not_called()


def test_reject_empty_object_id():
    sub = _make_subscriber()
    sub.on_claim_event(_event({"subject_id": "player", "predicate": "attacked", "object_id": "", "polarity": True}))
    sub._engine.revise.assert_not_called()


def test_valid_proposition_passes():
    sub = _make_subscriber()
    sub.on_claim_event(_event({"subject_id": "player", "predicate": "attacked", "object_id": "maid_lusya", "polarity": True}))
    sub._engine.revise.assert_called_once()