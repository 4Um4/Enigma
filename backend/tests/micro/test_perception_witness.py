"""path: /project/backend/tests/micro/test_perception_witness.py
Назначение: G3-A — witness-контракт восприятия: observable event →
    filter_perceiving_npcs (LOS+radius мембрана) → perceiving_npc_ids.
    Детерминизм: same event + same world state → same witness set.
Запуск: cd backend; python -m pytest tests/micro/test_perception_witness.py -v 2>&1 | Select-Object -Last 8; cd ..
Зависимости: reaction_subscriber, perception_filter, event_bus, event_identity
Основные сущности: тесты witness-детерминизма
"""

from types import SimpleNamespace

from app.domain.events import EventDTO
from app.services.npc.perception_filter import filter_perceiving_npcs


class _FakeSpatial:
    """Детерминированный spatial: player в (0,0), NPC на заданных дистанциях."""

    def __init__(self, positions):
        # positions: {npc_id: (x, y)}
        self._pos = dict(positions)
        self._pos["player"] = (0.0, 0.0)

    def _p(self, npc_id):
        return self._pos.get(npc_id, (999.0, 999.0))

    # Контракты, используемые _can_hear/_can_see внутри filter:
    def player_distances(self, ids):
        import math
        px, py = self._pos["player"]
        return {
            i: round(math.hypot(self._p(i)[0] - px, self._p(i)[1] - py), 2)
            for i in ids
        }

    def distance(self, a, b):
        import math
        ax, ay = self._p(a)
        bx, by = self._p(b)
        return math.hypot(ax - bx, ay - by)


def _attack_event(radius=15.0):
    return EventDTO.create(
        event_type="PLAYER_ATTACKED",
        source="player",
        payload={"target_id": "maid_lusya", "semantic_action": "ATTACK"},
        radius=radius,
    )


def test_witness_in_range():
    """ATTACK в 4м → maid_lusya ∈ witnesses (контракт Мастера)."""
    sp = _FakeSpatial({"maid_lusya": (4.0, 0.0)})
    out = filter_perceiving_npcs(
        npc_ids=["maid_lusya"], event=_attack_event(),
        scene_state={}, spatial_query=sp,
    )
    assert "maid_lusya" in out


def test_witness_out_of_range():
    """NPC за радиусом → ∉ witnesses."""
    sp = _FakeSpatial({"far_npc": (40.0, 0.0)})
    out = filter_perceiving_npcs(
        npc_ids=["far_npc"], event=_attack_event(radius=15.0),
        scene_state={}, spatial_query=sp,
    )
    assert "far_npc" not in out


def test_witness_set_deterministic():
    """same event + same world state → same witness set (двойной вызов)."""
    sp1 = _FakeSpatial({"a": (5.0, 1.0), "b": (12.0, 0.0)})
    sp2 = _FakeSpatial({"a": (5.0, 1.0), "b": (12.0, 0.0)})
    ids = ["a", "b"]
    r1 = filter_perceiving_npcs(npc_ids=ids, event=_attack_event(),
                                scene_state={}, spatial_query=sp1)
    r2 = filter_perceiving_npcs(npc_ids=ids, event=_attack_event(),
                                scene_state={}, spatial_query=sp2)
    assert r1 == r2


def test_reaction_handle_returns_perceiving():
    """Интеграция: handle() возвращает Phase8Result с непустым
    perceiving_npc_ids (reduction-контракт замкнут)."""
    from app.services.events.reaction_subscriber import ReactionSubscriber
    from app.models.phase8 import Phase8Context

    sp = _FakeSpatial({"maid_lusya": (4.0, 0.0), "far_npc": (40.0, 0.0)})
    shared = SimpleNamespace(spatial_query=sp, scene_state={})
    ctx = Phase8Context(
        all_npcs_raw=[
            {"npc_id": "maid_lusya", "name": "Люся"},
            {"npc_id": "far_npc", "name": "Далёкий"},
        ],
        all_npc_contexts=[],
        shared_context=shared,
        campaign_id="c1",
        tick_ctx=None,
    )
    sub = ReactionSubscriber.__new__(ReactionSubscriber)  # handle не использует __init__-состояние
    result = sub.handle([_attack_event()], ctx)
    assert result.perceiving_npc_ids is not None
    assert "maid_lusya" in result.perceiving_npc_ids
    assert "far_npc" not in result.perceiving_npc_ids