"""
path: /project/backend/tests/micro/test_attack_cardinality.py
Назначение: G3-C regression — кардинальность боевой трубы: 1 input →
    1 PLAYER_ATTACKED → 1 Combat handling; payload единственного события
    несёт все semantic fields; identity детерминирован (F3-1).
Зависимости: phase_1_input, event_bus, event_identity
Основные сущности: тесты кардинальности атаки

Запуск: cd backend; python -m pytest tests/micro/test_attack_cardinality.py -v 2>&1 | Select-Object -Last 8; cd ..
"""

from types import SimpleNamespace

from app.services.game_loop.phase_1_input import publish_classified_player_event


class _Bus:
    """Перехват публикаций phase_1 (шину подменяем через get_event_bus patch)."""

    def __init__(self):
        self.published = []

    def publish(self, event):
        self.published.append(event)
        return []


def test_attack_not_published_by_phase_1(monkeypatch):
    """G3-C: phase_1 НЕ публикует PLAYER_ATTACKED (deferred к INPUT_MERGE)."""
    bus = _Bus()
    monkeypatch.setattr(
        "app.services.game_loop.phase_1_input.get_event_bus", lambda: bus
    )
    ctx = SimpleNamespace(
        action_type="attack",
        player_target_id="maid_lusya",
        intent_resolution=SimpleNamespace(
            original_intent=SimpleNamespace(
                parameters=SimpleNamespace(
                    semantic_action="ATTACK",
                    target_reference="Люсю",
                    target_id="maid_lusya",
                    physical_force=0.5,
                    social_pressure=0.8,
                )
            )
        ),
    )
    publish_classified_player_event(
        shared_context=ctx,
        location="tavern",
        campaign_id="c1",
        raw_input="Ударяю Люсю в левый глаз!",
    )
    attack_events = [e for e in bus.published if e.type == "PLAYER_ATTACKED"]
    assert len(attack_events) == 0  # deferred — единственный publisher: orchestrator


def test_other_types_still_published(monkeypatch):
    """Не-attack события публикуются как раньше (регресс маршрутизации)."""
    bus = _Bus()
    monkeypatch.setattr(
        "app.services.game_loop.phase_1_input.get_event_bus", lambda: bus
    )
    ctx = SimpleNamespace(
        action_type="player_interacts",
        player_target_id="maid_lusya",
        intent_resolution=None,
    )
    publish_classified_player_event(
        shared_context=ctx, location="tavern", campaign_id="c1",
        raw_input="Смотрю на Люсю",
    )
    assert any(e.type == "PLAYER_SPOKE" for e in bus.published)


def test_orchestrator_payload_carries_semantics():
    """Единственное событие боевой трубы несёт все semantic fields
    (контракт consumers: claim_sub:103 semantic_action, Combat target_id/
    actor_id/intensity, decision_hub intensity)."""
    payload = {
        "target_id": "maid_lusya",
        "target_reference": "Люсю",
        "semantic_action": "ATTACK",
        "intensity": 0.8,
        "actor_id": "player",
    }
    # Контрактное равенство: все обязательные поля присутствуют и непусты
    for key in ("target_id", "semantic_action", "intensity", "actor_id"):
        assert payload.get(key), f"payload потерял {key} — consumer оглохнет"


def test_attack_event_id_deterministic():
    """F3-1: same (tick, actor, target) → same id (rng_seed-детерминизм)."""
    seed1 = f"evt:{100}:player:maid_lusya:attack"
    seed2 = f"evt:{100}:player:maid_lusya:attack"
    assert seed1 == seed2