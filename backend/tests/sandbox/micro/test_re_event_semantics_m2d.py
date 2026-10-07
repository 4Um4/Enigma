# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/micro/test_re_event_semantics_m2d.py
Назначение: ADR-O-418 (RE M2/D) — micro-приёмка слоя событийной семантики:
    pure-редукция 4 needs-touching событий §5.5, registry-guard, флаг-полярности,
    UUID-provenance, apply-side round-trip (StateApplicator → Store → read-back).
    Без полного тика (SUPERBOX-приёмка — re_m2d_needs_test.py на GC-00-харнесе).
Зависимости: app.services.events.relationship_event_semantics,
    app.services.npc.state_applicator, app.services.social.relationship_state_store,
    app.domain.events, app.models.state_delta, app.models.delta_payloads.
Основные сущности: 8 тестов.
Запуск: cd backend; python -m pytest tests/sandbox/micro/test_re_event_semantics_m2d.py -v; cd ..
"""
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.events import EventDTO
from app.domain.relationship_contracts import ContractValidationError
from app.models.delta_payloads import NeedDeltaPayload
from app.models.state_delta import DeltaDomain, StateDeltas
from app.services.events.event_types import EventType
from app.services.events.relationship_event_semantics import (
    RELATIONSHIP_EVENT_PROFILES,
    RE_NEEDS_EVENT_MAGNITUDE,
    RelationshipEventSemantics,
    relationship_events_enabled,
)
from app.services.npc.state_applicator import StateApplicator
from app.services.social.relationship_state_store import RelationshipStateStore


def _evt(etype: str, source: str, payload: dict) -> EventDTO:
    """Детерминированная фабрика события (EventDTO.create — §13.4)."""
    return EventDTO.create(etype, source, payload, timestamp=0.0)


def _handler(bus=None) -> RelationshipEventSemantics:
    # bus=None → флаг ON не требует шины (подписка только при ON+bus)
    return RelationshipEventSemantics(bus) if bus is not None else object.__new__(
        RelationshipEventSemantics
    )


class TestPureReduction:
    """Pure-редукция: EventDTO → List[StateDeltas] (bus не нужен)."""

    def test_flirt_accepted_relief(self):
        h = _handler()
        d = h._reduce_event(_evt("flirt_accepted", "borko", {"target_id": "lusya"}))
        assert len(d) == 1
        assert d[0].npc_id == "borko"
        assert d[0].domain == DeltaDomain.RELATIONSHIP
        p = d[0].payload
        assert isinstance(p, NeedDeltaPayload)
        assert p.need_id == "intimacy"
        assert p.pressure_delta == -RE_NEEDS_EVENT_MAGNITUDE
        assert p.satiation_delta == 0.0
        assert p.frustration_delta == 0.0

    def test_flirt_rejected_frustration_path2(self):
        h = _handler()
        d = h._reduce_event(_evt("flirt_rejected", "borko", {"target_id": "lusya"}))
        assert len(d) == 1
        p = d[0].payload
        assert p.need_id == "intimacy"
        assert p.frustration_delta == RE_NEEDS_EVENT_MAGNITUDE  # путь 2, Фр1=C
        assert p.pressure_delta == 0.0  # отказ НЕ снимает давление (№21/22)

    def test_intimate_encounter_both_subjects(self):
        h = _handler()
        d = h._reduce_event(_evt("intimate_encounter", "borko", {"target_id": "lusya"}))
        # Профиль: строка = один эффект = одна дельта (один ненулевой аккумулятор).
        # "both" × 3 эффекта (relief Ф4 + satiation Сат4 + релаксационная волна Фр2,
        # ADR-O-419 — добавлена в профиль после первой редакции этого теста) = 6 дельт;
        # Store агрегирует по полям (clamp per-field, порядок не влияет — DEBT-DET-01).
        assert len(d) == 6
        assert {x.npc_id for x in d} == {"borko", "lusya"}
        press = [x for x in d if x.payload.pressure_delta != 0.0]
        sat = [x for x in d if x.payload.satiation_delta != 0.0]
        relax = [x for x in d if x.payload.frustration_delta != 0.0]
        assert len(press) == 2 and len(sat) == 2 and len(relax) == 2
        assert {x.npc_id for x in press} == {"borko", "lusya"}
        assert {x.npc_id for x in sat} == {"borko", "lusya"}
        assert {x.npc_id for x in relax} == {"borko", "lusya"}
        assert all(x.payload.pressure_delta == -RE_NEEDS_EVENT_MAGNITUDE for x in press)
        assert all(x.payload.satiation_delta == RE_NEEDS_EVENT_MAGNITUDE for x in sat)
        # Фр2: релаксационная волна — ДЕЛЬТА < 0 (не обнуление накопленного)
        assert all(x.payload.frustration_delta == -RE_NEEDS_EVENT_MAGNITUDE for x in relax)
        assert all(x.payload.need_id == "sexual" for x in d)

    def test_intimate_rejection_frustration(self):
        h = _handler()
        d = h._reduce_event(_evt("intimate_rejection", "borko", {"target_id": "lusya"}))
        assert len(d) == 1
        assert d[0].payload.need_id == "sexual"
        assert d[0].payload.frustration_delta == RE_NEEDS_EVENT_MAGNITUDE

    def test_event_outside_registry_ignored(self):
        h = _handler()
        # Событие НЕ из §5.5 — хендлер его не знает (registry-guard)
        d = h._reduce_event(_evt("theft", "borko", {"target_id": "lusya"}))
        assert d == []

    def test_canonical_event_without_needs_profile_ignored(self):
        h = _handler()
        # Каноническое событие §5.5 без needs-профиля (фаза C/E/F/J)
        d = h._reduce_event(_evt("compliment", "borko", {"target_id": "lusya"}))
        assert d == []

    def test_uuid_provenance_required(self):
        h = _handler()
        e = _evt("intimate_rejection", "borko", {"target_id": "lusya"})
        d = h._reduce_event(e)
        # source_event_id = str(EventDTO.id) — валидный UUID (проверяет apply-side)
        from uuid import UUID

        UUID(d[0].payload.source_event_id)  # ValueError если не UUID

    def test_missing_source_fails_loud(self):
        h = _handler()
        with pytest.raises(ContractValidationError):
            h._reduce_event(_evt("intimate_rejection", "", {"target_id": "lusya"}))


class TestApplySide:
    """Apply-side: дельта → apply_relationship_deltas → Store (round-trip)."""

    def test_roundtrip_through_store(self):
        import uuid as uuid_mod

        from app.models.delta_payloads import NeedDeltaPayload as NDP

        h = _handler()
        e = _evt("intimate_rejection", "borko", {"target_id": "lusya"})
        deltas = h._reduce_event(e)
        scene: dict = {}
        sa = StateApplicator.__new__(StateApplicator)
        applied = sa.apply_relationship_deltas(deltas, scene)
        assert applied == 1
        lvl = RelationshipStateStore.get_need_level(scene, "borko", "sexual")
        assert lvl.frustration == pytest.approx(RE_NEEDS_EVENT_MAGNITUDE)
        assert lvl.current_intensity == 0.0  # отказ не трогает давление

    def test_payload_map_validation(self):
        # StateDeltas(domain=RELATIONSHIP, payload=чужой) → TypeError на конструкторе
        from app.models.delta_payloads import SocialPayload

        with pytest.raises(TypeError):
            StateDeltas(
                npc_id="borko",
                domain=DeltaDomain.RELATIONSHIP,
                payload=SocialPayload(trust_delta=1.0),
            )


class TestFlagPolarity:
    def test_default_off(self):
        assert relationship_events_enabled() is False

    def test_profile_registry_consistency(self):
        # Каждый needs-touching тип имеет профиль; каждый профиль — needs-touching
        assert set(RELATIONSHIP_EVENT_PROFILES) == set(
            ["flirt_accepted", "flirt_rejected", "intimate_encounter", "intimate_rejection"]
        )