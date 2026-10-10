"""path: backend/tests/micro/test_trait_gap_detector.py
Назначение: детектор: слова из Портретов/Черт/Мечт собираются; статус из
            словаря vs НЕТ В ИГРЕ; соседи; md/json рендерятся.
Зависимости: pytest, trait_gap_detector, домен хроники
Основные сущности: build_report"""

from __future__ import annotations

from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
)
from app.services.chronicle import trait_gap_detector


def _doc(npc: str, entries) -> ChronicleDocument:
    return ChronicleDocument(
        chronicle_id=npc, npc_ref=npc, entries=tuple(entries), canonical=False
    )


def _portret(eid: str, statement: str, traits) -> ChronicleEntry:
    return ChronicleEntry(
        entry_id=eid,
        kind=EntryKind.PORTRET,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="x"),
        payload={"statement": statement, "traits": traits},
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
        ordinal=0,
    )


def _trait(eid: str, name: str) -> ChronicleEntry:
    return ChronicleEntry(
        entry_id=eid,
        kind=EntryKind.TRAIT_SEED,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="x"),
        payload={"trait": name, "evidence": "x"},
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
        ordinal=1,
    )


def test_collect_and_status():
    docs = {
        "maid_lusya": _doc(
            "maid_lusya",
            [
                _portret("p1", "Люся злится, глотает злость", ["подавленная злость", "расчёт"]),
                _trait("t1", "наблюдение"),
            ],
        )
    }
    rep = trait_gap_detector.build_report(docs, "silver_wolf")
    by = {r["word"]: r for r in rep["records"]}
    assert "подавленная злость" in by
    assert by["наблюдение"]["count"] == 1
    # каждый рекорд имеет статус и md/json рендерятся
    assert all(r["status"] for r in rep["records"])
    md = trait_gap_detector.render_markdown(rep)
    js = trait_gap_detector.render_json(rep)
    assert "Карта разрывов" in md
    assert '"records"' in js


def test_neighbors_cooccurrence():
    docs = {
        "a": _doc("a", [_portret("p1", "x", ["страсть", "вожделение"])]),
    }
    rep = trait_gap_detector.build_report(docs, "c")
    by = {r["word"]: r for r in rep["records"]}
    assert "вожделение" in by["страсть"]["neighbors"]  # соседи = основа гипотезы