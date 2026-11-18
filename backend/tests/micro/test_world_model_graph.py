from __future__ import annotations

# backend/tests/micro/test_world_model_graph.py
"""
Файл: backend/tests/micro/test_world_model_graph.py
Назначение: Спринт 2A-4 (ТЗ Отчёт №6 §3, ADR-O-445): контрактные инварианты
            WorldGraph.find_paths на СИНТЕТИЧЕСКИХ мини-реестрах (без привязки
            к каталогу config/world — вердикт Мастера по 2A) плюс один
            интеграционный тест на живых реестрах, без каталог-деталей.
            Поверяем: достижимость; недостижимость; гипотетические эффекты
            предыдущих шагов (симуляция достижимости); fail-closed
            (отсутствующее значение, числовая дельта без базы, provider-state
            ОТДЕЛЬНО от предусловий процесса); детерминизм; лимиты
            depth/plans и их валидация; немутация исходного снапшота
            (Causal Integrity: план != действие). IA-шум без-предусловных
            процессов — вопрос Спринта 3 (Planner), в контракт не входит.
Зависимости: pytest; app.models.world.*; app.services.world_model.*.
Основные сущности: тесты контракта WorldGraph
Запуск: cd backend; python -m pytest tests/micro/test_world_model_graph.py -v; cd ..
"""

import pytest

from app.models.world.plan import Plan
from app.models.world.process import Process, ProcessSource, WorldStateDelta
from app.models.world.world_predicate import WorldPredicate
from app.services.world_model.process_registry import ProcessRegistry
from app.services.world_model.source_registry import SourceRegistry
from app.services.world_model.world_graph import WorldGraph

FUNCTIONAL = WorldPredicate(domain="item", attribute="state", value="functional")


def _predicate(domain: str, attribute: str, value: object) -> WorldPredicate:
    return WorldPredicate(domain=domain, attribute=attribute, value=value)


def _delta(domain: str, attribute: str, delta: object) -> WorldStateDelta:
    return WorldStateDelta(domain=domain, attribute=attribute, delta=delta, target_ref="hyp")


def _process(
    process_id: str,
    requires: tuple,
    deltas: tuple,
    duration: int = 1,
) -> Process:
    return Process(
        process_id=process_id,
        applies_deltas=tuple(_delta(*d) for d in deltas),
        requires_world_state=tuple(_predicate(*r) for r in requires),
        duration_ticks=duration,
    )


def _source(
    source_id: str,
    kind: str,
    procs: tuple,
    provider: tuple = (),
) -> ProcessSource:
    return ProcessSource(
        source_id=source_id,
        source_kind=kind,
        available_processes=procs,
        requires_provider_state=tuple(_predicate(*r) for r in provider),
    )


def _base_processes() -> dict:
    return {
        "forge_ingot": _process(
            "forge_ingot",
            (("resource", "ore", "present"),),
            (("material", "ingot", "->present"),),
            2,
        ),
        "harvest_coin": _process(
            "harvest_coin",
            (),
            (("resource", "coin", 0.25),),
            1,
        ),
        "repair": _process(
            "repair",
            (("infrastructure", "metalwork", "present"),),
            (("item", "state", "broken->functional"), ("npc", "gold", -5)),
            5,
        ),
        "smith_sword": _process(
            "smith_sword",
            (("material", "ingot", "present"),),
            (("item", "state", "->functional"),),
            3,
        ),
    }


def _base_sources() -> dict:
    return {
        "src_furnace": _source("src_furnace", "location", ("forge_ingot",)),
        "src_harvest_ground": _source("src_harvest_ground", "location", ("harvest_coin",)),
        "src_repair_station": _source("src_repair_station", "item", ("repair",)),
        "src_smith": _source("src_smith", "npc", ("smith_sword",)),
    }


def _graph(sources: dict) -> WorldGraph:
    return WorldGraph(ProcessRegistry(_base_processes()), SourceRegistry(dict(sources)))


class TestReachability:
    def test_direct_process_reaches_target(self) -> None:
        g = _graph(_base_sources())
        snap = {("item", "state"): "broken", ("infrastructure", "metalwork"): "present", ("npc", "gold"): 10}
        plans = g.find_paths(snap, [FUNCTIONAL])
        assert len(plans) == 1, plans
        step = plans[0].steps[0]
        assert step.source.source_id == "src_repair_station"
        assert step.snapshot[("item", "state")] == "functional"
        assert step.snapshot[("npc", "gold")] == 5
        assert plans[0].duration_ticks == 5

    def test_two_step_chain_uses_previous_step_effect(self) -> None:
        g = _graph(_base_sources())
        snap = {("item", "state"): "broken", ("resource", "ore"): "present"}
        plans = g.find_paths(snap, [FUNCTIONAL])
        assert len(plans) == 1, plans
        steps = plans[0].steps
        assert [s.process.process_id for s in steps] == ["forge_ingot", "smith_sword"]
        assert steps[0].snapshot[("material", "ingot")] == "present"
        assert FUNCTIONAL.is_satisfied_by(steps[1].snapshot[("item", "state")])
        assert plans[0].duration_ticks == 5


class TestFailClosed:
    def test_process_precondition_not_met(self) -> None:
        g = _graph(_base_sources())
        snap = {("item", "state"): "broken", ("infrastructure", "metalwork"): "absent", ("npc", "gold"): 10}
        assert g.find_paths(snap, [FUNCTIONAL]) == []

    def test_missing_value_is_not_satisfied(self) -> None:
        g = _graph(_base_sources())
        assert g.find_paths({}, [FUNCTIONAL]) == []

    def test_provider_state_missing_blocks_edge(self) -> None:
        needy = _source("src_blacksmith", "npc", ("repair",), (("npc", "health", ">0"),))
        g = WorldGraph(ProcessRegistry(_base_processes()), SourceRegistry({"src_blacksmith": needy}))
        snap = {("item", "state"): "broken", ("infrastructure", "metalwork"): "present"}
        assert g.find_paths(snap, [FUNCTIONAL]) == []
        snap_with_health = dict(snap)
        snap_with_health[("npc", "health")] = 8
        plans = g.find_paths(snap_with_health, [FUNCTIONAL])
        assert len(plans) == 1 and plans[0].steps[0].source.source_id == "src_blacksmith"

    def test_provider_state_independent_from_process_preconditions(self) -> None:
        needy = _source("src_blacksmith", "npc", ("repair",), (("npc", "health", ">0"),))
        sources = _base_sources()
        sources["src_blacksmith"] = needy
        g = _graph(sources)
        base = {("item", "state"): "broken", ("infrastructure", "metalwork"): "present"}
        snap = dict(base)
        snap[("npc", "health")] = 8
        used_with = [p.steps[0].source.source_id for p in g.find_paths(snap, [FUNCTIONAL])]
        assert used_with == ["src_blacksmith", "src_repair_station"], used_with
        used_without = [p.steps[0].source.source_id for p in g.find_paths(base, [FUNCTIONAL])]
        assert used_without == ["src_repair_station"], used_without

    def test_numeric_delta_requires_numeric_base(self) -> None:
        g = _graph(_base_sources())
        snap = {("resource", "coin"): 10}
        plans = g.find_paths(snap, [_predicate("resource", "coin", ">=10.1")])
        assert len(plans) == 1 and plans[0].steps[0].snapshot[("resource", "coin")] == 10.25
        assert g.find_paths({}, [_predicate("resource", "coin", ">=10.1")]) == []

    def test_conditional_transition_requires_exact_match(self) -> None:
        g = _graph(_base_sources())
        snap = {("item", "state"): "cracked", ("infrastructure", "metalwork"): "present"}
        assert g.find_paths(snap, [FUNCTIONAL]) == []


class TestDeterminism:
    def test_output_is_deterministic(self) -> None:
        g = _graph(_base_sources())
        snap = {("item", "state"): "broken", ("infrastructure", "metalwork"): "present", ("npc", "health"): 8}
        first = g.find_paths(snap, [FUNCTIONAL])
        for _ in range(5):
            assert g.find_paths(snap, [FUNCTIONAL]) == first


class TestLimits:
    def test_max_depth_enforced(self) -> None:
        g = _graph(_base_sources())
        snap = {("item", "state"): "broken", ("resource", "ore"): "present"}
        assert g.find_paths(snap, [FUNCTIONAL], max_depth=1) == []
        assert len(g.find_paths(snap, [FUNCTIONAL], max_depth=2)) == 1

    def test_max_plans_truncates_deterministically(self) -> None:
        sources = _base_sources()
        for sid in ("src_repair_a", "src_repair_b"):
            sources[sid] = _source(sid, "npc", ("repair",))
        g = _graph(sources)
        snap = {("item", "state"): "broken", ("infrastructure", "metalwork"): "present"}
        full = g.find_paths(snap, [FUNCTIONAL])
        used = [p.steps[0].source.source_id for p in full]
        assert used == ["src_repair_a", "src_repair_b", "src_repair_station"], used
        assert g.find_paths(snap, [FUNCTIONAL], max_plans=2) == full[:2]

    @pytest.mark.parametrize("bad", [0, -1, True, 2.5])
    def test_invalid_limits_rejected(self, bad: object) -> None:
        g = _graph(_base_sources())
        snap = {("item", "state"): "broken", ("infrastructure", "metalwork"): "present"}
        for kw in ("max_depth", "max_plans"):
            with pytest.raises(ValueError):
                g.find_paths(snap, [FUNCTIONAL], **{kw: bad})


class TestPurity:
    def test_input_snapshot_not_mutated(self) -> None:
        g = _graph(_base_sources())
        snap = {("item", "state"): "broken", ("infrastructure", "metalwork"): "present", ("npc", "gold"): 10}
        before = dict(snap)
        assert g.find_paths(snap, [FUNCTIONAL])
        assert snap == before

    def test_early_goal_returns_empty_plan(self) -> None:
        g = _graph(_base_sources())
        already = g.find_paths({("item", "state"): "functional"}, [FUNCTIONAL])
        assert len(already) == 1 and isinstance(already[0], Plan)
        assert already[0].steps == ()


class TestLiveCatalogs:
    def test_integration_no_catalog_details(self) -> None:
        g = WorldGraph(ProcessRegistry.load(), SourceRegistry.load())
        snap = {("item", "state"): "broken", ("infrastructure", "metalwork"): "present", ("npc", "health"): 8}
        plans = g.find_paths(snap, [FUNCTIONAL])
        assert plans, "живой каталог потерял достижимость ремонта"
        for plan in plans:
            assert plan.steps
            assert FUNCTIONAL.is_satisfied_by(plan.steps[-1].snapshot[("item", "state")])
