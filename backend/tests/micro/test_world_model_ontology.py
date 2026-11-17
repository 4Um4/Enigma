from __future__ import annotations

# backend/tests/micro/test_world_model_ontology.py
"""
Файл: backend/tests/micro/test_world_model_ontology.py
Назначение: Спринт 1 (ТЗ Отчёт №6, ADR-O-445): каждый Process каталога имеет
            валидные requires/applies; реестры читают YAML в frozen-модели;
            AffordancePredicate.matches и value_matches (диапазоны, fail-closed).
Зависимости: pytest; app.domain.motion_core; app.models.world.*; app.services.world_model.*.
Основные сущности: тесты реестров и предикатов слоя Process
Запуск: cd backend; python -m pytest tests/micro/test_world_model_ontology.py -v; cd ..
"""

import pytest

from app.domain.motion_core import AffordanceVector
from app.models.world.affordance import (
    ALCOHOL_AVAILABLE,
    CONCEALMENT,
    AffordancePredicate,
    vector_to_predicates,
)
from app.models.world.plan import Plan, PlanStep
from app.models.world.process import Process, ProcessSource, WorldStateDelta
from app.models.world.world_predicate import WorldPredicate, value_matches
from app.services.world_model.ontology_registry import OntologyRegistry
from app.services.world_model.process_registry import ProcessRegistry


@pytest.fixture(scope="module")
def ontology() -> OntologyRegistry:
    return OntologyRegistry.load()


@pytest.fixture(scope="module")
def processes() -> ProcessRegistry:
    return ProcessRegistry.load()


class TestOntologyCatalog:
    def test_catalog_is_documentation_not_enum(self, ontology: OntologyRegistry) -> None:
        assert len(ontology.domains) == 11
        assert ontology.is_documented("resource")
        assert not ontology.is_documented("item")

    def test_domains_outside_catalog_are_allowed(self, ontology: OntologyRegistry) -> None:
        assert ontology.attributes_of("item") == ()


class TestProcessCatalog:
    def test_all_processes_have_valid_deltas(self, processes: ProcessRegistry) -> None:
        for process in processes.all():
            assert process.applies_deltas, process.process_id
            for delta in process.applies_deltas:
                assert isinstance(delta, WorldStateDelta)
                assert delta.domain and delta.attribute and delta.target_ref

    def test_all_processes_have_valid_requirements(self, processes: ProcessRegistry) -> None:
        for process in processes.all():
            for predicate in process.requires_world_state:
                assert isinstance(predicate, WorldPredicate)
                assert predicate.domain and predicate.attribute

    def test_duration_ticks_positive(self, processes: ProcessRegistry) -> None:
        assert all(p.duration_ticks >= 1 for p in processes.all())

    def test_canonical_processes_present(self, processes: ProcessRegistry) -> None:
        for pid in ("item_repair_via_blacksmith", "alcohol_serving", "rain_fills_river"):
            assert pid in processes

    def test_unknown_process(self, processes: ProcessRegistry) -> None:
        assert processes.get("no_such_process") is None
        assert "no_such_process" not in processes


class TestValueMatches:
    def test_range_constraint(self) -> None:
        assert value_matches(10, ">5")
        assert not value_matches(3, ">5")
        assert value_matches(5, ">=5")
        assert value_matches(2, "<3")
        assert value_matches(4, "<=4")

    def test_fail_closed_on_incomparable(self) -> None:
        assert not value_matches("warm", ">5")
        assert not value_matches(None, ">5")

    def test_bool_int_mismatch(self) -> None:
        assert not value_matches(1, True)

    def test_equality(self) -> None:
        assert value_matches("present", "present")
        assert not value_matches("absent", "present")


class TestAffordancePredicate:
    def test_domain_attribute_gating(self) -> None:
        left = AffordancePredicate("cover", "visual", "available")
        assert left.matches(AffordancePredicate("cover", "visual", "available"))
        assert not left.matches(AffordancePredicate("social", "visual", "available"))
        assert not left.matches(AffordancePredicate("cover", "acoustic", "available"))

    def test_named_predicates_match_by_value(self) -> None:
        assert ALCOHOL_AVAILABLE.matches(AffordancePredicate("resource", "alcohol", "present"))
        assert CONCEALMENT.matches(AffordancePredicate("cover", "visual", "available"))

    def test_vector_bridge_read_only(self) -> None:
        vec = AffordanceVector(can_conceal=0.9, light_level=0.1)
        preds = vector_to_predicates(vec)
        assert len(preds) == 2
        assert vec.can_conceal == 0.9


class TestPlan:
    def test_empty_plan(self) -> None:
        assert Plan().steps == ()
        assert Plan().duration_ticks == 0

    def test_plan_duration_sums_steps(self) -> None:
        process = Process(
            process_id="p",
            applies_deltas=(WorldStateDelta("item", "state", "x", "item:s"),),
            requires_world_state=(),
            duration_ticks=3,
        )
        source = ProcessSource("src", "npc", ("p",))
        step = PlanStep(process, source, {("item", "state"): "x"})
        assert Plan(steps=(step, step)).duration_ticks == 6
