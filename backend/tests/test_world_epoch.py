"""
path: /project/backend/tests/test_world_epoch.py
Назначение: S266 — замок Temporal Epoch: immutability, read-compat,
    write-запрет, view/overlay разделение.
"""
import pytest
from app.domain.world_epoch import WorldEpoch


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


def test_view_nested_mutation_blocked():
    """S269 (Мастер-гейт перед снятием входного deepcopy): вложенные
    структуры исторически были причиной deepcopy — их защита обязана
    быть доказана рантаймом, а не договорённостью."""
    e = WorldEpoch(1, {"npc_positions": {"borko": {"x": 1.0}}})
    wv = e.view()
    # Вложенная запись через view — громкий запрет
    with pytest.raises(TypeError):
        wv["npc_positions"]["borko"]["x"] = 999
    # Эпоха не изменилась (через легальный read-путь)
    assert wv["npc_positions"]["borko"]["x"] == 1.0
    # S269-РАЗГРАНИЧЕНИЕ ЗОН: прямая запись в сырую ссылку e.state —
    # не view-путь; её сторожит не TypeError, а контракт S266
    # (move-semantics, «пишущий обязан прекратить писать») +
    # INV-TEMPORAL-ISOLATION на границе фаз. View = единственная
    # легальная точка чтения фаз — она запечатана по построению.


def test_epoch_npcs_sealed():
    e = WorldEpoch(1, {}, npcs=[{"npc_id": "borko", "x": 1.0}])
    with pytest.raises(TypeError):
        e.npcs[0]["x"] = 99.0
    with pytest.raises(TypeError):
        e.npcs.append({"npc_id": "intruder"})
    assert e.npcs[0]["x"] == 1.0
    assert len(e.npcs) == 1


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