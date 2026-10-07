"""CCH-2.5 приёмочные тесты ConsistencyService (ADR-O-422)."""
from __future__ import annotations

from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
)
from app.services.chronicle.chronicle_store import (
    document_from_dict,
    document_to_dict,
)
from app.services.chronicle.consistency_service import (
    CanonicalRegistry,
    ConsistencyService,
)


def _entry(npc, **kw):
    base = dict(
        entry_id=kw.pop("eid"),
        kind=EntryKind.EVENT,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=npc),
        provenance=EntryProvenance.AUTHOR_AUTHORED,
    )
    base.update(kw)
    return ChronicleEntry(**base)


def _doc(npc, age_start, entries):
    return ChronicleDocument(
        chronicle_id=f"c_{npc}", npc_ref=npc, entries=tuple(entries), game_start_age=age_start
    )


REG = CanonicalRegistry(
    alias_to_npc={"стражник": "guard_borko", "кузнец": "blacksmith_orm"},
    archetype_of={"guard_borko": "guard", "blacksmith_orm": "blacksmith", "maid_lusya": "maid"},
)


def test_wara_old_document_without_new_fields():
    d = document_to_dict(_doc("a", 20, []))
    d.pop("game_start_age", None)
    d.pop("event_groups", None)
    back = document_from_dict(d)
    assert back.game_start_age is None and back.event_groups == ()
    assert document_to_dict(back) == document_to_dict(document_from_dict(document_to_dict(back)))


def test_intra_gap_window_between_anchors():
    # ordinal различны — иначе сортировка dated схлопывает порядок (дефолт 0)
    doc = _doc(
        "a",
        None,
        [
            _entry("a", eid="e1", historical_age=10, ordinal=0),
            _entry("a", eid="e2", ordinal=1),  # без даты → окно [10..14]
            _entry("a", eid="e3", historical_age=14, ordinal=2),
        ],
    )
    rep = ConsistencyService().check([doc], REG)
    gaps = rep.by_kind("GAP")
    assert len(gaps) == 1 and gaps[0].payload["window"] == [10, 14]


def test_cross_age_math_merge_candidate():
    # start: Люся 14 / Торнин 45 → delta = -31; её 9 ↔ его 40 (9-40=-31 ✓)
    lusya = _doc("maid_lusya", 14, [_entry("maid_lusya", eid="l1", historical_age=9)])
    tornin = _doc("tavern_keeper_tornin", 45, [_entry("tavern_keeper_tornin", eid="t1", historical_age=40)])
    rep = ConsistencyService().check([lusya, tornin], REG)
    merges = rep.by_kind("MERGE_CANDIDATE")
    # Роли не пересекаются (maid vs tavern_keeper) — кандидат даёт общая роль только при совпадении;
    # здесь проверяем, что временная совместимость не роняет алгоритм и что роль-фильтр сработал
    assert all("maid" not in f.payload.get("shared_roles", []) for f in merges)


def test_cross_shared_role_guard_known_vs_unknown():
    # «стражник»-неизвестный у Люси ↔ guard_borko-именованный у Борко: роли совместимы
    lusya = _doc(
        "maid_lusya",
        14,
        [_entry("maid_lusya", eid="l1", historical_age=12,
                object_id=EntityRef(ref_kind=EntityRefKind.UNKNOWN_PERSON, name_hint="стражник"))],
    )
    borko = _doc(
        "guard_borko",
        26,
        [_entry("guard_borko", eid="b1", historical_age=24)],  # 12+14=26-24 → (12)-(24)=delta(14-26)=-12 ✓
    )
    rep = ConsistencyService().check([lusya, borko], REG)
    merges = [f for f in rep.by_kind("MERGE_CANDIDATE") if f.level == "cross"]
    assert len(merges) == 1 and "guard" in merges[0].payload["shared_roles"]


def test_cross_time_incompatible_no_candidate():
    lusya = _doc("maid_lusya", 14, [_entry("maid_lusya", eid="l1", historical_age=9,
                object_id=EntityRef(ref_kind=EntityRefKind.UNKNOWN_PERSON, name_hint="стражник"))])
    borko = _doc("guard_borko", 26, [_entry("guard_borko", eid="b1", historical_age=18)])
    rep = ConsistencyService().check([lusya, borko], REG)
    assert rep.by_kind("MERGE_CANDIDATE") == ()


def test_canon_alias_resolution_and_unknown_npc_contradiction():
    doc = _doc(
        "maid_lusya",
        None,
        [
            _entry("maid_lusya", eid="e1",
                   object_id=EntityRef(ref_kind=EntityRefKind.UNKNOWN_PERSON, name_hint="Стражник")),
            _entry("maid_lusya", eid="e2",
                   object_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="ghost_none")),
        ],
    )
    rep = ConsistencyService().check([doc], REG)
    assert any(f.kind == "INFO" and "guard_borko" in f.payload.get("npc_id", "") for f in rep.findings)
    assert any(f.kind == "CONTRADICTION" and "ghost_none" in f.message for f in rep.findings)


def test_canon_secret_known_by_mismatch():
    reg = CanonicalRegistry(
        alias_to_npc={}, archetype_of={"maid_lusya": "maid"},
        secret_known_by={"lusya_orm_borko": frozenset({"maid_lusya", "blacksmith_orm", "guard_borko"})},
    )
    doc = _doc(
        "maid_lusya",
        None,
        [_entry("maid_lusya", eid="s1", payload={"is_secret": True, "secret_id": "lusya_orm_borko",
                                                 "known_by": ["maid_lusya"]})],
    )
    rep = ConsistencyService().check([doc], reg)
    sync = rep.by_kind("CANON_SYNC")
    assert len(sync) == 1 and sync[0].payload["secret_id"] == "lusya_orm_borko"


def test_tail_window_uses_game_start_age():
    """Недатированное событие ПОСЛЕ последнего якоря: правая граница = game_start_age."""
    doc = _doc(
        "a",
        30,
        [_entry("a", eid="e1", historical_age=10, ordinal=0), _entry("a", eid="e2", ordinal=1)],
    )
    rep = ConsistencyService().check([doc], REG)
    gaps = rep.by_kind("GAP")
    assert len(gaps) == 1 and gaps[0].payload["window"] == [10, 30]


def test_canon_unknown_name_question():
    """Имя вне канона и вне словаря ролей («Лом») → QUESTION-карточка автору."""
    doc = _doc(
        "maid_lusya",
        None,
        [_entry("maid_lusya", eid="e1",
                object_id=EntityRef(ref_kind=EntityRefKind.UNKNOWN_PERSON, name_hint="Лом"))],
    )
    rep = ConsistencyService().check([doc], REG)
    assert any(f.kind == "QUESTION" and "Лом" in f.message for f in rep.findings)