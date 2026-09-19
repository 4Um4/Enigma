"""
path: backend/tests/sandbox/micro/test_epoch_view.py
Назначение: PR-5 (S268) — WorldView read-only + epoch_id носитель в TickState.
Зависимости: app.domain.world_epoch, app.domain.tick
Основные сущности: test_worldview_read, test_worldview_write_guard, test_tick_state_carrier

Запуск: cd backend; python tests/sandbox/micro/test_epoch_view.py 2>&1 | Select-Object -Last 5; cd ..
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.domain.tick import create_tick_state
from app.domain.world_epoch import WorldEpoch


def test_worldview_read():
    ep = WorldEpoch(7, {"location_id": "tavern", "tick": 7}, [{"npc_id": "a"}])
    wv = ep.view()
    assert wv.epoch_id == 7
    assert wv["location_id"] == "tavern"
    assert wv.get("missing", "d") == "d"
    assert "location_id" in wv
    assert wv.npcs[0]["npc_id"] == "a"


def test_worldview_write_guard():
    """Мутация committed-мира через WorldView невозможна ПО ПОСТРОЕНИЮ."""
    ep = WorldEpoch(1, {"x": 1})
    wv = ep.view()
    for op in (
        lambda: wv.__setitem__("x", 2),
        lambda: wv.__delitem__("x"),
        lambda: wv.update({"x": 2}),
        lambda: wv.setdefault("x", 2),
        lambda: wv.pop("x"),
        lambda: wv.clear(),
    ):
        try:
            op()
            raise AssertionError("write op прошёл молча — EPOCH-VIOLATION")
        except AttributeError:
            pass
    assert ep.state["x"] == 1  # мир не тронут


def test_tick_state_carrier():
    """TickState несёт epoch_id + world_view; дефолты нейтральны."""
    ts = create_tick_state(
        tick_id=42,
        campaign_id="c",
        scene_state={"location_id": "tavern"},
        all_npcs_raw=[],
        effective_drives_map={},
        interventions=[],
    )
    assert ts.epoch_id == -1 and ts.world_view is None  # дефолт = no-op для старых вызовов
    ep = WorldEpoch(42, {"location_id": "tavern"})
    ts2 = create_tick_state(
        tick_id=42,
        campaign_id="c",
        scene_state={"location_id": "tavern"},
        all_npcs_raw=[],
        effective_drives_map={},
        interventions=[],
        epoch_id=42,
        world_view=ep.view(),
    )
    assert ts2.epoch_id == 42 and ts2.world_view.epoch_id == 42


def test_tick_overlay_pr6():
    """PR-6a: overlay изолирован от epoch, shadow-read, журнал, commit."""
    from app.domain.world_epoch import TickOverlay

    ep = WorldEpoch(5, {"a": 1, "b": {"deep": True}})
    ov = TickOverlay(ep)

    # shadow-read: неперекрытый ключ читается из epoch, перекрытый — из overlay
    assert ov["a"] == 1 and ov.get("missing", "d") == "d" and "b" in ov
    ov["a"] = 2
    assert ov["a"] == 2 and ep.state["a"] == 1  # epoch не тронут
    assert ov.epoch_id == 5
    assert len(ov.mutation_log) == 1 and ov.mutation_log[0]["key"] == "a"

    # setdefault: создаёт только при отсутствии в overlay И в epoch
    sd = ov.setdefault("c", [])
    assert sd == [] and "c" in ov and ep.state.get("c") is None
    assert ov.setdefault("a", 99) == 2  # существующий не затёрт

    # commit: сборка следующего состояния, epoch остаётся иммутабельным
    nxt = ov.commit()
    assert nxt["a"] == 2 and nxt["c"] == [] and nxt["b"] == {"deep": True}
    assert ep.state["a"] == 1  # committed epoch N не мутировал (главный закон)
    # S268-урок: type-совместимость — часть контракта scene_state
    assert isinstance(ov, dict)  # isinstance-гварды сцены обязаны пропускать


def test_deepcopy_contracts():
    """S268: immutable → self; overlay → материализованный dict."""
    import copy
    ep = WorldEpoch(3, {"a": 1})
    assert copy.deepcopy(ep) is ep
    assert copy.deepcopy(ep.view()) is ep.view()
    ov = TickOverlay(ep)
    ov["b"] = 2
    snap = copy.deepcopy(ov)
    assert isinstance(snap, dict) and snap == {"a": 1, "b": 2}
    ov["a"] = 9
    assert snap["a"] == 1  # снимок оторван от overlay


def test_nested_mutation_DOCUMENTED_LIMITATION():
    """S268 (требование Мастера): ФИКСАЦИЯ известной границы.

    Гвард WorldView покрывает только ВЕРХНИЙ уровень: вложенные
    структуры Epoch (state["npc_positions"]["borko"]["x"]) мутабельны
    и обходят write-guard. Это историческая причина существования
    deepcopy (input_snapshot — 7b-вердикт: изоляция несущая) —
    снимается ТОЛЬКО Epoch-финалом (единая committed/live модель,
    параллельная сессия). Тест ФИКСИРУЕТ текущее поведение как
    известную границу: при Epoch-финале он ОБЯЗАН стать красным —
    это маркер завершения миграции, не одобренная семантика."""
    ep = WorldEpoch(1, {"npc_positions": {"borko": {"x": 1}}})
    wv = ep.view()
    # текущее поведение: вложенная мутация проходит МИМО гварда
    wv["npc_positions"]["borko"]["x"] = 999
    assert ep.state["npc_positions"]["borko"]["x"] == 999  # утечка задокументирована
    # и через прямое свойство:
    ep.state["npc_positions"]["borko"]["x"] = 1000
    assert ep.state["npc_positions"]["borko"]["x"] == 1000