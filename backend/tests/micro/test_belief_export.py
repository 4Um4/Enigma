"""path: backend/tests/micro/test_belief_export.py
Назначение: C2 — сборщик: три статуса по правилам; детерминизм порядка;
            оба формата рендерятся.
Зависимости: pytest, belief_export, домен хроники
Основные сущности: collect_belief_seeds"""

from __future__ import annotations

import json

from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
)
from app.services.chronicle import belief_export


def _doc(npc_id: str, canonical: bool, entries) -> ChronicleDocument:
    return ChronicleDocument(
        chronicle_id=npc_id,
        npc_ref=npc_id,
        entries=tuple(entries),
        canonical=canonical,
    )


def _belief(eid: str, statement: str, btype=None, prov=EntryProvenance.AUTHOR_CONFIRMED, confidence=None):
    payload = {"statement": statement}
    if btype is not None:
        payload["belief_type"] = btype
    return ChronicleEntry(
        entry_id=eid,
        kind=EntryKind.BELIEF_SEED,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="x"),
        payload=payload,
        provenance=prov,
        confidence=confidence,
        ordinal=0,
    )


def test_three_statuses_rules():
    docs = {
        "a_canon": _doc(
            "a_canon",
            True,
            [
                _belief("b1", "формулировка", "danger"),      # канон+реестр → runtime
                _belief("b2", "формулировка"),                 # канон без типа → unknown
                _belief("b3", "формулировка", "чужой_тип"),    # канон вне реестра → unknown
            ],
        ),
        "b_draft": _doc(
            "b_draft",
            False,
            [_belief("b1", "формулировка", "danger", prov=EntryProvenance.LLM_DRAFT, confidence=0.5)],
        ),
    }
    recs = belief_export.collect_belief_seeds(docs)
    by = {(r["npc_id"], r["source"].split(":")[1]): r["status"] for r in recs}
    assert by[("a_canon", "b1")] == belief_export.STATUS_RUNTIME
    assert by[("a_canon", "b2")] == belief_export.STATUS_UNKNOWN
    assert by[("a_canon", "b3")] == belief_export.STATUS_UNKNOWN
    assert by[("b_draft", "b1")] == belief_export.STATUS_NEEDS


def test_order_deterministic_and_renders():
    docs = {
        "zz": _doc("zz", True, [_belief("b1", "зета")]),
        "aa": _doc("aa", True, [_belief("b1", "альфа")]),
    }
    recs = belief_export.collect_belief_seeds(docs)
    assert [r["npc_id"] for r in recs] == ["aa", "zz"]  # не порядок вставки
    md = belief_export.render_markdown(recs, "silver_wolf")
    js = belief_export.render_json(recs, "silver_wolf")
    assert "| aa | альфа" in md
    assert json.loads(js)["records"][0]["npc_id"] == "aa"