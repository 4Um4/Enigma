"""
path: /project/backend/tests/test_world_epoch.py
Назначение: S266 — замок Temporal Epoch: immutability, read-compat,
    write-запрет, view/overlay разделение.
"""
import pytest

from app.domain.world_epoch import WorldEpoch, WorldView


def _mk_state():
    return {
        "tick": 100,
        "location_id": "tavern",
        "npc_positions": {"goran": {"x": 1.0, "y": 2.0}},
        "recent_dialogues": [],
    }


def test_epoch_immutable():
    e = WorldEpoch(100, _mk_state())
    with pytest.raises(AttributeError):
        e.epoch_id = 999


def test_view_read_compat():
    e = WorldEpoch(100, _mk_state())
    v = e.view()
    assert v["tick"] == 100
    assert v.get("location_id") == "tavern"
    assert "npc_positions" in v
    assert set(v.keys()) >= {"tick", "location_id"}
    assert len(v) == 4
    assert v.epoch_id == 100


def test_view_write_forbidden():
    e = WorldEpoch(100, _mk_state())
    v = e.view()
    with pytest.raises(AttributeError):
        v["tick"] = 200
    with pytest.raises(AttributeError):
        v.new_field = "x"


def test_epoch_state_not_isolated_dict():
    """КОНТРАКТ: Epoch владеет переданным dict (move-semantics).
    Вызывающий, мутирующий после создания, нарушает контракт —
    это ловится INV-TEMPORAL-ISOLATION на границе фаз."""
    s = _mk_state()
    e = WorldEpoch(100, s)
    # Мутация исходной ссылки ВИДНА в epoch — это ожидаемо:
    # move-semantics, а не copy. Пишущий обязан прекратить писать.
    s["tick"] = 999
    assert e.state["tick"] == 999
    # Доказательство: НЕТ скрытой копии. Честность вместо иллюзии.


def test_view_no_copy():
    """Чтение view = ноль копий (ссылка на epoch-state)."""
    e = WorldEpoch(100, _mk_state())
    v = e.view()
    assert v._epoch.state is e.state  # та же самая ссылка