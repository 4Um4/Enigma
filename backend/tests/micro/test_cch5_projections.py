"""path: backend/tests/micro/test_cch5_projections.py
Назначение: CCH-5 (ADR-O-420) — тесты экспорт-проекций канон-хроник.
            T-CCH-09 (legacy no drift) + T-CCH-01 (round-trip) +
            направление TruthRelation + initial_holders=[] + блокировки.
Зависимости: pytest, app.services.chronicle.*, app.domain.chronicle,
             app.models.truth_state, app.services.truth_state_loader
Основные сущности: TestLegacyNoDrift, TestProjectionRoundTrip,
                   TestTruthRelationDirection, TestEmptyInitialHolders,
                   TestBlockedReferences, TestPublishAtomicity
Запуск: cd backend ; python -m pytest tests/micro/test_cch5_projections.py -v
"""

from __future__ import annotations

import json
import os
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import patch

import pytest

from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    CauseRef,
    CauseKind,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
    KnowledgeChannel,
    KnowledgeLink,
)
from app.services.chronicle import chronicle_projections as proj
from app.services.chronicle.chronicle_seeder import (
    SEED_TRUST_NEGATIVE,
    SEED_TRUST_POSITIVE,
)


# ── Фикстуры ─────────────────────────────────────────────────────────────────


def _make_event(
    entry_id: str,
    npc_id: str,
    summary: str,
    *,
    is_secret: bool = False,
    importance: float = 0.6,
    historical_age: int = 10,
    object_npc_id: str = None,
    causes: Tuple[CauseRef, ...] = (),
) -> ChronicleEntry:
    object_id = None
    if object_npc_id:
        object_id = EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=object_npc_id)
    payload: Dict[str, Any] = {
        "summary": summary,
        "importance": importance,
    }
    if is_secret:
        payload["is_secret"] = True
    return ChronicleEntry(
        entry_id=entry_id,
        kind=EntryKind.EVENT,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=npc_id),
        object_id=object_id,
        historical_age=historical_age,
        payload=payload,
        causes=causes,
        provenance=EntryProvenance.AUTHOR_AUTHORED,
        ordinal=0,
    )


def _make_relationship(
    entry_id: str,
    npc_id: str,
    target_npc_id: str,
    valence: str,
    summary: str = "",
) -> ChronicleEntry:
    return ChronicleEntry(
        entry_id=entry_id,
        kind=EntryKind.RELATIONSHIP,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=npc_id),
        object_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=target_npc_id),
        payload={"valence": valence, "summary": summary},
        provenance=EntryProvenance.AUTHOR_AUTHORED,
        ordinal=0,
    )


def _make_knowledge_link(
    entry_id: str,
    event_ref: str,
    knower_npc_id: str,
    learned_age: int = 12,
) -> ChronicleEntry:
    return ChronicleEntry(
        entry_id=entry_id,
        kind=EntryKind.KNOWLEDGE_LINK,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=knower_npc_id),
        payload={
            "event_ref": event_ref,
            "knower": {
                "ref_kind": EntityRefKind.RESOLVED.value,
                "npc_id": knower_npc_id,
            },
            "learned_age": learned_age,
            "channel": KnowledgeChannel.WITNESSED.value,
            "certainty": 1.0,
        },
        provenance=EntryProvenance.AUTHOR_AUTHORED,
        ordinal=0,
    )


def _make_doc(npc_id: str, entries: Tuple[ChronicleEntry, ...]) -> ChronicleDocument:
    return ChronicleDocument(
        chronicle_id=npc_id,
        npc_ref=npc_id,
        entries=entries,
        canonical=True,
        canonical_version=1,
        game_start_age=18,
    )


@pytest.fixture
def isolated_projections_root(tmp_path, monkeypatch):
    """Изолировать _projections_root в tmp_path (НЕ трогает реальный config/)."""
    monkeypatch.setattr(proj, "BASE_DIR", tmp_path)
    yield tmp_path
    # cleanup — tmp_path удаляется автоматически


# ── T-CCH-09: NPC без хроники → дрифт состояния = 0 ─────────────────────────


class TestLegacyNoDrift:
    """T-CCH-09: NPC без хроники → legacy-путь нетронут.
    Два прогона load_l2_state_from_runtime_dict: до и после добавления канона
    другому NPC → дрифт narrative_cache/psyche/relationship_cache = 0.
    """

    def test_npc_without_chronicle_uses_legacy_path(self, isolated_projections_root):
        """NPC без канона → _chronicle_seed_memories_for возвращает None
        → load_l2_state_from_runtime_dict использует _convert_origin_events."""
        from app.services.npc.npc_loader import _chronicle_seed_memories_for

        with patch(
            "app.services.chronicle.chronicle_seeder.canonical_chronicles",
            return_value={},
        ):
            result = _chronicle_seed_memories_for("maid_lusya")
        assert result is None, "NPC без канона должен получить None (→ legacy)"

    def test_npc_with_chronicle_uses_seeder(self, isolated_projections_root):
        """NPC с каноном → seeder возвращает кортеж (даже пустой)."""
        from app.services.npc.npc_loader import _chronicle_seed_memories_for

        doc = _make_doc("test_npc", entries=(_make_event("e1", "test_npc", "test"),))
        with patch(
            "app.services.chronicle.chronicle_seeder.canonical_chronicles",
            return_value={"test_npc": doc},
        ):
            result = _chronicle_seed_memories_for("test_npc")
        assert result is not None, "NPC с каноном должен получить кортеж от seeder'а"


# ── T-CCH-01: round-trip проекций ────────────────────────────────────────────


class TestProjectionRoundTrip:
    """T-CCH-01: семантическая сохранность полей проекций.
    Отсутствие значения НЕ превращается в подтверждённое отсутствие факта/знания.
    """

    def test_origin_events_preserves_summary_importance(self, isolated_projections_root):
        """origin_events-проекция сохраняет summary/importance из канона."""
        doc = _make_doc(
            "test_npc",
            entries=(
                _make_event("e1", "test_npc", "Произошло событие", importance=0.8),
            ),
        )
        oe = proj.build_origin_events_projection("test_npc", doc)
        assert oe["_projection"] == "origin_events"
        assert len(oe["origin_events"]) == 1
        ev = oe["origin_events"][0]
        assert ev["summary"] == "Произошло событие"
        assert ev["importance"] == 0.8

    def test_village_relations_file_scale_01(self, isolated_projections_root):
        """village_relations: шкала ФАЙЛОВАЯ 0..1 (positive → 0.3, negative → -0.4).
        НЕ 30/-40 (это рантайм-шкала после npc_loader ×100)."""
        doc = _make_doc(
            "test_npc",
            entries=(
                _make_relationship("r1", "test_npc", "target_npc", "positive", "доверие"),
                _make_relationship("r2", "test_npc", "target_npc2", "negative", "страх"),
            ),
        )
        vr = proj.build_village_relations_projection({"test_npc": doc})
        rel = vr["relations"]["test_npc"]
        assert rel["target_npc"]["base_trust"] == SEED_TRUST_POSITIVE / 100.0  # 0.3
        assert rel["target_npc2"]["base_trust"] == SEED_TRUST_NEGATIVE / 100.0  # -0.4
        assert rel["target_npc"]["nature"] == "positive"
        assert rel["target_npc"]["chronicle_origin"] == "r1"

    def test_truth_state_explicit_only_secret_events(self, isolated_projections_root):
        """EXPLICIT: только EVENT с payload['is_secret']=True → секрет.
        Не секретные EVENT НЕ попадают в truth_state."""
        doc = _make_doc(
            "test_npc",
            entries=(
                _make_event("e1", "test_npc", "Обычное событие", is_secret=False),
                _make_event("e2", "test_npc", "Секрет", is_secret=True),
            ),
        )
        ts, diag = proj.build_truth_state_projection({"test_npc": doc}, "test_campaign")
        assert ts is not None
        assert len(ts["secrets"]) == 1
        assert ts["secrets"][0]["secret_id"] == "e2"
        assert ts["secrets"][0]["canonical_truth"] == "Секрет"

    def test_no_value_is_not_confirmed_absence(self, isolated_projections_root):
        """Отсутствие KNOWLEDGE_LINK → initial_holders=[], НО это НЕ доказательство,
        что никто не знает. Запрещённые поля (is_known_by_nobody и т.п.) отсутствуют."""
        doc = _make_doc(
            "test_npc",
            entries=(_make_event("e1", "test_npc", "Секрет без knowers", is_secret=True),),
        )
        ts, diag = proj.build_truth_state_projection({"test_npc": doc}, "test_campaign")
        assert ts is not None
        secret = ts["secrets"][0]
        assert secret["initial_holders"] == []
        # Запрещённые поля (подмена отсутствия утверждением):
        assert "is_known_by_nobody" not in secret
        assert "has_no_participants" not in secret
        assert "is_not_secret" not in secret
        # Диагностика фиксирует неопределённость:
        assert "e1" in diag["no_resolved_knowers"]


# ── Направление TruthRelation ────────────────────────────────────────────────


class TestTruthRelationDirection:
    """E зависит от C → source=E, target=C, DEPENDS_ON.
    Существующая семантика: DEPENDS_ON = 'A зависит от B', source=A, target=B.
    """

    def test_direction_dependent_to_basis(self, isolated_projections_root):
        """Секретный E с cause.origin_ref → C (тоже секретный) →
        TruthRelation(source=E, target=C, DEPENDS_ON)."""
        cause_to_c = CauseRef(cause_kind=CauseKind.EVENT, origin_ref="event_c")
        doc = _make_doc(
            "test_npc",
            entries=(
                _make_event("event_c", "test_npc", "Основание", is_secret=True),
                _make_event(
                    "event_e", "test_npc", "Зависимое", is_secret=True,
                    causes=(cause_to_c,),
                ),
            ),
        )
        ts, diag = proj.build_truth_state_projection({"test_npc": doc}, "test_campaign")
        assert ts is not None
        assert len(ts["relations"]) == 1
        r = ts["relations"][0]
        assert r["source_secret_id"] == "event_e"   # зависящий (E)
        assert r["target_secret_id"] == "event_c"   # основание (C)
        assert r["relation_type"] == "DEPENDS_ON"
        assert r["strength"] == proj.TRUTH_RELATION_STRENGTH

    def test_reversed_direction_is_red(self, isolated_projections_root):
        """Обратное направление (source=C, target=E) — RED.
        Тест падает, если проекция вернёт source=event_c."""
        cause_to_c = CauseRef(cause_kind=CauseKind.EVENT, origin_ref="event_c")
        doc = _make_doc(
            "test_npc",
            entries=(
                _make_event("event_c", "test_npc", "Основание", is_secret=True),
                _make_event(
                    "event_e", "test_npc", "Зависимое", is_secret=True,
                    causes=(cause_to_c,),
                ),
            ),
        )
        ts, _ = proj.build_truth_state_projection({"test_npc": doc}, "test_campaign")
        r = ts["relations"][0]
        # Если проекция перепутала направление — этот assert падает:
        assert r["source_secret_id"] != "event_c", "Обратное направление запрещено"

    def test_relation_to_non_secret_target_skipped(self, isolated_projections_root):
        """cause.origin_ref → не секретный EVENT → связь пропущена с диагностикой."""
        cause_to_nonsecret = CauseRef(cause_kind=CauseKind.EVENT, origin_ref="non_secret_event")
        doc = _make_doc(
            "test_npc",
            entries=(
                _make_event("non_secret_event", "test_npc", "Не секрет"),
                _make_event(
                    "secret_e", "test_npc", "Секрет", is_secret=True,
                    causes=(cause_to_nonsecret,),
                ),
            ),
        )
        ts, diag = proj.build_truth_state_projection({"test_npc": doc}, "test_campaign")
        assert ts is not None
        assert len(ts["relations"]) == 0
        assert diag["skipped_not_secret_target"] == 1

    def test_relation_cause_kind_not_event_skipped(self, isolated_projections_root):
        """cause.cause_kind ≠ EVENT → пропуск с диагностикой
        (непредставимо в TruthRelation без расширения семантики)."""
        cause_trait = CauseRef(cause_kind=CauseKind.TRAIT, origin_ref="some_entry")
        doc = _make_doc(
            "test_npc",
            entries=(
                _make_event("secret_e", "test_npc", "Секрет", is_secret=True,
                            causes=(cause_trait,)),
            ),
        )
        ts, diag = proj.build_truth_state_projection({"test_npc": doc}, "test_campaign")
        assert ts is not None
        assert len(ts["relations"]) == 0
        assert diag["skipped_cause_kind_not_event"] == 1


# ── initial_holders=[] допустим ──────────────────────────────────────────────


class TestEmptyInitialHolders:
    """K1: initial_holders=[] допустим, НЕ доказательство, что никто не знает.
    TruthStateLoader.validate НЕ требует непустоты.
    """

    def test_empty_initial_holders_allowed(self, isolated_projections_root):
        """Секрет без KNOWLEDGE_LINK → initial_holders=[] допустим."""
        doc = _make_doc(
            "test_npc",
            entries=(_make_event("e1", "test_npc", "Секрет", is_secret=True),),
        )
        ts, diag = proj.build_truth_state_projection({"test_npc": doc}, "test_campaign")
        assert ts is not None
        assert ts["secrets"][0]["initial_holders"] == []
        assert "e1" in diag["no_resolved_knowers"]

    def test_empty_initial_holders_passes_validator(self, isolated_projections_root):
        """TruthStateLoader.validate НЕ падает при initial_holders=[]."""
        from app.services.truth_state_loader import TruthStateLoader
        from app.models.truth_state import Secret, TruthState
        from types import MappingProxyType

        secret = Secret(
            secret_id="e1",
            npc_id="test_npc",
            participants=("test_npc",),
            category="chronicle",
            canonical_truth="Секрет",
            importance=0.6,
            initial_holders=(),  # пусто
            discovery_surface=("dialogue",),
            topics=(),
        )
        state = TruthState(
            secrets=MappingProxyType({"e1": secret}),
            relations=(),
        )
        # Не падает:
        TruthStateLoader.validate(state, known_npcs=None)

    def test_resolved_knower_added_to_initial_holders(self, isolated_projections_root):
        """KNOWLEDGE_LINK с resolved knower → добавляется в initial_holders."""
        doc = _make_doc(
            "test_npc",
            entries=(
                _make_event("e1", "test_npc", "Секрет", is_secret=True),
                _make_knowledge_link("kl1", "e1", "witness_npc", learned_age=12),
            ),
        )
        ts, diag = proj.build_truth_state_projection({"test_npc": doc}, "test_campaign")
        assert ts is not None
        assert "witness_npc" in ts["secrets"][0]["initial_holders"]
        assert "e1" not in diag["no_resolved_knowers"]


# ── Блокировка повреждённых ссылок ───────────────────────────────────────────


class TestBlockedReferences:
    """C2: структурно повреждённые ссылки → блокировка публикации.
    """

    def test_dangling_cause_origin_ref_blocks(self, isolated_projections_root):
        """cause.origin_ref → несуществующий entry_id → BLOCKED."""
        cause_dangling = CauseRef(cause_kind=CauseKind.EVENT, origin_ref="nonexistent")
        doc = _make_doc(
            "test_npc",
            entries=(
                _make_event("secret_e", "test_npc", "Секрет", is_secret=True,
                            causes=(cause_dangling,)),
            ),
        )
        ts, diag = proj.build_truth_state_projection({"test_npc": doc}, "test_campaign")
        assert ts is None  # блокировка
        assert any(
            b["reason"] == "dangling_cause_origin_ref"
            for b in diag["blocked_references"]
        )

    def test_unresolved_subject_blocks(self, isolated_projections_root):
        """subject_id = WHITE_SPOT → не можем создать npc_id → BLOCKED."""
        from app.domain.chronicle import ChronicleEntry

        entry = ChronicleEntry(
            entry_id="e1",
            kind=EntryKind.EVENT,
            subject_id=EntityRef(ref_kind=EntityRefKind.WHITE_SPOT, white_spot_id="ws1"),
            payload={"summary": "Секрет", "is_secret": True},
            provenance=EntryProvenance.AUTHOR_AUTHORED,
            ordinal=0,
        )
        doc = _make_doc("test_npc", entries=(entry,))
        ts, diag = proj.build_truth_state_projection({"test_npc": doc}, "test_campaign")
        assert ts is None
        assert any(
            b["reason"] == "subject_unresolved"
            for b in diag["blocked_references"]
        )

    def test_unknown_participant_blocks(self, isolated_projections_root):
        """participants содержит NPC не из known_npcs → BLOCKED."""
        doc = _make_doc(
            "test_npc",
            entries=(_make_event("e1", "test_npc", "Секрет", is_secret=True),),
        )
        ts, diag = proj.build_truth_state_projection(
            {"test_npc": doc}, "test_campaign",
            known_npcs={"other_npc"},  # test_npc не в списке
        )
        assert ts is None
        assert any(
            b["reason"] == "unknown_participant"
            for b in diag["blocked_references"]
        )


# ── Атомарность публикации (A3) ──────────────────────────────────────────────


class TestPublishAtomicity:
    """A3: при ошибке старый current.json действующий.
    """

    def test_successful_publish_creates_generation(self, isolated_projections_root):
        """Успешная публикация → current.json указывает на новое поколение."""
        doc = _make_doc(
            "test_npc",
            entries=(_make_event("e1", "test_npc", "Событие"),),
        )
        result = proj.publish_generation(
            {"test_npc": doc}, "test_campaign", known_npcs={"test_npc"}
        )
        assert result["status"] == proj.STATUS_OK
        assert result["generation_id"] is not None
        current = proj.read_current_pointer()
        assert current is not None
        assert current["generation"] == result["generation_id"]

    def test_empty_publish_no_generation(self, isolated_projections_root):
        """Нет канонов → EMPTY, поколение не создаётся.
        Патчим canonical_chronicles на {} — иначе читаются реальные каноны
        (blacksmith_orm/guard_borko) с машины Master."""
        with patch(
            "app.services.chronicle.chronicle_seeder.canonical_chronicles",
            return_value={},
        ):
            result = proj.export_all_projections("test_campaign")
        assert result["status"] == proj.STATUS_EMPTY
        assert result["generation_id"] is None

    def test_blocked_publish_keeps_old_current(self, isolated_projections_root):
        """При BLOCKED старый current.json действующий, новый не создаётся."""
        # Сначала успешная публикация
        doc_ok = _make_doc(
            "test_npc",
            entries=(_make_event("e1", "test_npc", "Событие"),),
        )
        result1 = proj.publish_generation(
            {"test_npc": doc_ok}, "test_campaign", known_npcs={"test_npc"}
        )
        assert result1["status"] == proj.STATUS_OK
        old_generation = result1["generation_id"]

        # Теперь публикация с повреждённой ссылкой → BLOCKED
        cause_dangling = CauseRef(cause_kind=CauseKind.EVENT, origin_ref="nonexistent")
        doc_bad = _make_doc(
            "test_npc",
            entries=(
                _make_event("secret_e", "test_npc", "Секрет", is_secret=True,
                            causes=(cause_dangling,)),
            ),
        )
        result2 = proj.publish_generation(
            {"test_npc": doc_bad}, "test_campaign", known_npcs={"test_npc"}
        )
        assert result2["status"] == proj.STATUS_BLOCKED

        # current.json всё ещё указывает на старое поколение
        current = proj.read_current_pointer()
        assert current is not None
        assert current["generation"] == old_generation

    def test_truth_state_empty_when_no_secrets(self, isolated_projections_root):
        """Нет секретных EVENT → truth_state_status=EMPTY, файл не создаётся."""
        doc = _make_doc(
            "test_npc",
            entries=(_make_event("e1", "test_npc", "Обычное событие", is_secret=False),),
        )
        result = proj.publish_generation(
            {"test_npc": doc}, "test_campaign", known_npcs={"test_npc"}
        )
        assert result["status"] == proj.STATUS_OK
        assert result["truth_state_status"] == proj.STATUS_EMPTY
        assert result["files"]["truth_state"] is None

    def test_manifest_lists_actual_files(self, isolated_projections_root):
        """manifest.json перечисляет фактически созданные файлы."""
        doc = _make_doc(
            "test_npc",
            entries=(
                _make_event("e1", "test_npc", "Событие"),
                _make_event("e2", "test_npc", "Секрет", is_secret=True),
            ),
        )
        result = proj.publish_generation(
            {"test_npc": doc}, "test_campaign", known_npcs={"test_npc"}
        )
        gen_path = proj._generations_dir() / result["generation_id"]
        manifest = json.loads((gen_path / "manifest.json").read_text(encoding="utf-8"))
        # Файлы перечислены:
        assert "origin_events/test_npc.origin_events.json" in manifest["files"]["origin_events"]
        assert manifest["files"]["village_relations"] == "village_relations.json"
        assert manifest["files"]["truth_state"] == "truth_state_test_campaign.json"
        # truth_state-файл действительно существует:
        assert (gen_path / "truth_state_test_campaign.json").exists()

    def test_manifest_truth_state_null_when_empty(self, isolated_projections_root):
        """При EMPTY truth_state → manifest.files.truth_state=null,
        файл не существует (НЕ фиктивный)."""
        doc = _make_doc(
            "test_npc",
            entries=(_make_event("e1", "test_npc", "Обычное"),),
        )
        result = proj.publish_generation(
            {"test_npc": doc}, "test_campaign", known_npcs={"test_npc"}
        )
        gen_path = proj._generations_dir() / result["generation_id"]
        manifest = json.loads((gen_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["files"]["truth_state"] is None
        # Файл НЕ существует:
        assert not (gen_path / "truth_state_test_campaign.json").exists()