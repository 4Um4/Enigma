"""
path: backend/tests/test_affordance_facts.py
Назначение: Тесты ADR-O-377 (G2 v1, канал b1′ producer-facts) —
    AffordanceSet -> производный факт weapon_access -> OpportunityContext.
    Гварды: (1) truth table D6 (holder ∨ FREE∧adjacent≤1.5м) на РЕАЛЬНЫХ
    структурах (WorldObjectStore.spawn + BODY_STATE_HEALTHY, §12.4 —
    ноль объектов мечты); (2) OFF = no-op / ON honest-empty (D3);
    (3) отказ продюсера = пустая карта (D5, §11); (4) чистота: снапшот
    и all_npcs_raw не мутируются, детерминизм; (5) каузальный proof-гейт
    Мастера (Г2): 0.50 -> 0.70, порог 0.65, Δ=W_WEAPON, will-гейт;
    (6) негативные контроли: реестр закрыт (19), TickState default =
    честный False, policy-таблица без npc_id-хардкодов.
Зависимости: pytest, app.domain (tick, semantic_action), app.models.npc_state,
    app.services.economy.opportunity_engine, app.services.world.*
Основные сущности: compute_weapon_access_facts, run_affordance_facts_guarded,
    WEAPON_ARCHETYPES
"""
import copy
from types import SimpleNamespace

from typing import Any, Optional

import pytest
from app.domain.semantic_action import WorldActionType
from app.domain.tick import create_tick_state
from app.models.npc_state import BODY_STATE_HEALTHY
from app.services.economy.opportunity_engine import (
    OpportunityContext,
    OpportunityEngine,
)
from app.services.world.affordance_facts import (
    WEAPON_ARCHETYPES,
    compute_weapon_access_facts,
    run_affordance_facts_guarded,
)
from app.services.world.world_object_store import WorldObjectStore

_LOC = "tavern"


def _scene_with_weapon(
    position: tuple[float, float] = (1.0, 1.0),
    holder: Optional[str] = None,
    location: str = _LOC,
    archetype: str = "weapon",
) -> dict:
    """Реальная сцена через WorldObjectStore.spawn (§13.4: фабрика).

    holder — тестовая установка HELD_BY (прецедент прямой работы с
    subtree в test_world_object_topology:189 — тест, не runtime-код).
    """
    scene = {"world_objects": {}}
    WorldObjectStore.spawn(
        scene, "wo_test_weapon", archetype, location, position)
    if holder is not None:
        scene["world_objects"]["wo_test_weapon"]["holder"] = holder
    return scene


def _snapshot(
    scene: dict, npc_xy: tuple[float, float] = (1.0, 1.0), npc_id: str = "npc_a"
) -> SimpleNamespace:
    return SimpleNamespace(
        world_objects=scene["world_objects"],
        npc_positions={
            npc_id: {
                "local_position": {"x": npc_xy[0], "y": npc_xy[1]}
            }
        },
    )


def _npcs(with_body: bool = True, npc_id: str = "npc_a") -> list[dict]:
    return [
        {
            "npc_id": npc_id,
            "body_state": dict(BODY_STATE_HEALTHY) if with_body else None,
        }
    ]


# ── Truth table D6: holder ∨ (FREE ∧ adjacent ≤ 1.5м) ───────────────


@pytest.mark.parametrize(
    "npc_xy,holder,expected",
    [
        ((1.0, 1.0), None, True),        # FREE, d=0.0
        ((2.0, 1.0), None, True),        # FREE, d=1.0 <= 1.5
        ((2.4, 1.0), None, True),        # FREE, d=1.4 <= 1.5
        ((2.6, 1.0), None, False),       # FREE, d=1.6 > 1.5
        ((3.0, 1.0), None, False),       # FREE, d=2.0 > 1.5
        ((50.0, 50.0), "npc_a", True),   # HELD_BY самим NPC — позиция неважна
        ((1.0, 1.0), "npc_b", False),    # HELD_BY чужим -> не FREE -> False
    ],
)
def test_truth_table(npc_xy: tuple[float, float], holder: Optional[str], expected: bool) -> None:
    scene = _scene_with_weapon(holder=holder)
    facts = compute_weapon_access_facts(
        _snapshot(scene, npc_xy), _npcs(), _LOC)
    assert facts == {"npc_a": expected}


def test_empty_world_honest_empty() -> None:
    assert compute_weapon_access_facts(
        SimpleNamespace(world_objects={}, npc_positions={}), _npcs(), _LOC
    ) == {}
    assert compute_weapon_access_facts(None, _npcs(), _LOC) == {}


# ── Гварды канала (D3/D5) ───────────────────────────────────────────


def test_off_flag_is_noop(monkeypatch) -> None:
    monkeypatch.delenv("W3_G2_ENABLED", raising=False)
    scene = _scene_with_weapon()
    assert run_affordance_facts_guarded(
        1, _snapshot(scene), _npcs(), _LOC) == {}


def test_on_flag_delivers_facts(monkeypatch) -> None:
    monkeypatch.setenv("W3_G2_ENABLED", "1")
    scene = _scene_with_weapon()
    assert run_affordance_facts_guarded(
        1, _snapshot(scene), _npcs(), _LOC) == {"npc_a": True}


def test_on_empty_world_honest_empty(monkeypatch) -> None:
    monkeypatch.setenv("W3_G2_ENABLED", "1")
    assert run_affordance_facts_guarded(
        1, SimpleNamespace(world_objects={}, npc_positions={}),
        _npcs(), _LOC) == {}


def test_producer_fault_degrades_to_empty_map(monkeypatch) -> None:
    """D5/§11: отказ продюсера = пустая карта (деградация канала, не тика)."""
    monkeypatch.setenv("W3_G2_ENABLED", "1")

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("producer fault simulation")

    monkeypatch.setattr(
        "app.services.world.affordance_facts.project_world_objects", _boom)
    scene = _scene_with_weapon()
    assert run_affordance_facts_guarded(
        1, _snapshot(scene), _npcs(), _LOC) == {}


# ── Фильтры и пропуски (честность, не тишина) ───────────────────────


def test_wrong_location_filtered() -> None:
    scene = _scene_with_weapon(location="cellar")
    assert compute_weapon_access_facts(
        _snapshot(scene), _npcs(), _LOC) == {}


def test_non_weapon_archetype_ignored() -> None:
    scene = _scene_with_weapon(archetype="chair")
    assert compute_weapon_access_facts(
        _snapshot(scene), _npcs(), _LOC) == {}


def test_falsy_body_state_npc_skipped() -> None:
    """L2.2/§ENIGMA-003: falsy body -> ValueError фабрики -> NPC без
    факта (NPC не «оживляется» на дефолтах — урок S237 №7)."""
    scene = _scene_with_weapon()
    facts = compute_weapon_access_facts(
        _snapshot(scene), _npcs(with_body=False), _LOC)
    assert facts == {}


def test_npc_without_position_skipped() -> None:
    scene = _scene_with_weapon()
    snap = SimpleNamespace(
        world_objects=scene["world_objects"], npc_positions={})
    assert compute_weapon_access_facts(snap, _npcs(), _LOC) == {}


# ── Чистота и детерминизм ───────────────────────────────────────────


def test_producer_does_not_mutate_inputs() -> None:
    scene = _scene_with_weapon()
    snap = _snapshot(scene, npc_xy=(2.0, 1.0))
    npcs = _npcs()
    _objs_before = copy.deepcopy(scene["world_objects"])
    _pos_before = copy.deepcopy(snap.npc_positions)
    _npcs_before = copy.deepcopy(npcs)
    compute_weapon_access_facts(snap, npcs, _LOC)
    assert scene["world_objects"] == _objs_before
    assert snap.npc_positions == _pos_before
    assert npcs == _npcs_before


def test_producer_deterministic() -> None:
    scene = _scene_with_weapon()
    snap = _snapshot(scene, npc_xy=(2.0, 1.0))
    r1 = compute_weapon_access_facts(snap, _npcs(), _LOC)
    r2 = compute_weapon_access_facts(snap, _npcs(), _LOC)
    assert r1 == r2 == {"npc_a": True}


def test_weapon_policy_table_shape() -> None:
    """Policy-таблица — калибровка, не онтология (класс S211):
    archetype-строки; npc_id-хардкоды запрещены (S209-инцидент)."""
    assert isinstance(WEAPON_ARCHETYPES, tuple)
    assert "weapon" in WEAPON_ARCHETYPES
    for _arch in WEAPON_ARCHETYPES:
        assert isinstance(_arch, str) and _arch
        assert not _arch.startswith("npc")


# ── Каузальный proof-гейт Мастера (Г2, уровень Engine) ──────────────


def test_engine_causal_flip_preregistered() -> None:
    """Предрегистрация: weapon absent -> 0.50/False; weapon reachable ->
    0.70/True; Δ = ровно W_WEAPON=0.20; порог 0.65; unlock содержит
    steal. Прочие равные; will-гейт: скрытость — привилегия
    broken/deceptive воли (R6.3)."""
    base = OpportunityContext(
        player_attention=0.0, distance=15.0, weapon_access=False, allies=0
    )
    with_weapon = OpportunityContext(
        player_attention=0.0, distance=15.0, weapon_access=True, allies=0
    )
    r0 = OpportunityEngine.calculate(base, "deceptive")
    r1 = OpportunityEngine.calculate(with_weapon, "deceptive")
    assert r0.score == pytest.approx(0.50)
    assert r1.score == pytest.approx(0.70)
    assert abs((r1.score - r0.score) - 0.20) < 1e-9
    assert not r0.hidden_action_allowed
    assert r1.hidden_action_allowed
    assert "steal" in r1.unlocked_intents
    r_free = OpportunityEngine.calculate(with_weapon, "free")
    assert r_free.score == 0.0
    assert not r_free.hidden_action_allowed


# ── Негативные контроли (границы контракта) ─────────────────────────


def test_action_registry_closed_19() -> None:
    assert len(WorldActionType) == 19
    assert "EQUIP" not in WorldActionType.__members__


def test_tickstate_default_honest_false() -> None:
    """P3-семантика: пустая карта -> .get(npc, False) = легаси-литерал."""
    ts = create_tick_state(
        tick_id=1, campaign_id="c", scene_state={}, all_npcs_raw=[],
        effective_drives_map={}, interventions=[])
    assert ts.affordance_facts_map.get("npc_a", False) is False


def test_tickstate_carries_fact() -> None:
    ts = create_tick_state(
        tick_id=1, campaign_id="c", scene_state={}, all_npcs_raw=[],
        effective_drives_map={}, interventions=[],
        affordance_facts_map={"npc_a": True})
    assert ts.affordance_facts_map.get("npc_a") is True