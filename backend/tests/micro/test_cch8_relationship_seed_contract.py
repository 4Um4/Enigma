"""CCH-8 / COV-10.3: контракт seeder'а для RELATIONSHIP.

Фиксация существующего контракта: какие object_id проходят в relationship_cache,
какие skip'аются. Тесты не предписывают конкретных отношений — они проверяют
контракт обработки EntityRef.

6 кейсов:
1. RESOLVED с npc_id → материализуется (positive → SEED_TRUST_POSITIVE)
2. UNKNOWN_PERSON → skip (не становится известным)
3. WHITE_SPOT → skip (не становится известным)
4. RESOLVED с target==npc_id → skip (self-link)
5. RESOLVED с valence=neutral → skip (invalid valence)
6. object_id=None → skip (неразрешённая сущность)
"""
from __future__ import annotations

from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
)
from app.services.chronicle.chronicle_seeder import (
    SEED_TRUST_POSITIVE,
    build_seed_relationships,
)


def _make_doc(npc_id: str, entries: tuple) -> ChronicleDocument:
    return ChronicleDocument(
        chronicle_id=npc_id,
        npc_ref=npc_id,
        entries=entries,
        canonical=True,
        canonical_version=1,
    )


def _make_rel(
    entry_id: str,
    subject_npc: str,
    object_ref,
    valence: str,
    target_hint: str = "",
    ordinal: int = 100,
) -> ChronicleEntry:
    return ChronicleEntry(
        entry_id=entry_id,
        kind=EntryKind.RELATIONSHIP,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=subject_npc),
        object_id=object_ref,
        payload={"summary": "", "target_hint": target_hint, "nature": "", "valence": valence},
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
        ordinal=ordinal,
    )


def test_resolved_relationship_seeded():
    """RESOLVED с npc_id → материализуется в relationship_cache (positive)."""
    doc = _make_doc("npc_a", (
        _make_rel(
            "rel_001",
            "npc_a",
            EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="npc_b"),
            "positive",
            target_hint="NPC B",
        ),
    ))
    result = build_seed_relationships("npc_a", doc)
    assert "npc_b" in result
    assert result["npc_b"]["trust"] == SEED_TRUST_POSITIVE
    assert result["npc_b"]["chronicle_origin"] == "rel_001"


def test_unknown_person_not_seeded():
    """UNKNOWN_PERSON → skip. Не становится известной сущностью."""
    doc = _make_doc("npc_a", (
        _make_rel(
            "rel_002",
            "npc_a",
            EntityRef(ref_kind=EntityRefKind.UNKNOWN_PERSON, name_hint="stranger"),
            "positive",
            target_hint="stranger",
        ),
    ))
    result = build_seed_relationships("npc_a", doc)
    assert result == {}, "UNKNOWN_PERSON не должна материализоваться"


def test_white_spot_not_seeded():
    """WHITE_SPOT → skip. Намеренно неопределённая сущность не становится известной."""
    doc = _make_doc("npc_a", (
        _make_rel(
            "rel_003",
            "npc_a",
            EntityRef(ref_kind=EntityRefKind.WHITE_SPOT, white_spot_id="ws_001"),
            "positive",
            target_hint="mystery",
        ),
    ))
    result = build_seed_relationships("npc_a", doc)
    assert result == {}, "WHITE_SPOT не должна материализоваться"


def test_self_link_not_seeded():
    """RESOLVED с target==subject → skip. Self-link не сеется."""
    doc = _make_doc("npc_a", (
        _make_rel(
            "rel_004",
            "npc_a",
            EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="npc_a"),
            "positive",
            target_hint="self",
        ),
    ))
    result = build_seed_relationships("npc_a", doc)
    assert result == {}, "Self-link не должен материализоваться"


def test_neutral_valence_not_seeded():
    """RESOLVED с valence=neutral → skip. Только positive/negative допустимы."""
    doc = _make_doc("npc_a", (
        _make_rel(
            "rel_005",
            "npc_a",
            EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id="npc_b"),
            "neutral",
            target_hint="NPC B",
        ),
    ))
    result = build_seed_relationships("npc_a", doc)
    assert result == {}, "neutral valence не должен материализоваться"


def test_null_object_id_not_seeded():
    """object_id=None → skip. Неразрешённая сущность не материализуется."""
    doc = _make_doc("npc_a", (
        _make_rel(
            "rel_006",
            "npc_a",
            None,
            "positive",
            target_hint="someone",
        ),
    ))
    result = build_seed_relationships("npc_a", doc)
    assert result == {}, "object_id=None не должен материализоваться"

# ── COV-10.4: гарантии на границе normalizer (roster matching) ──────────────
# Эти тесты проверяют, что target_hint НЕ превращается в object_id автоматически
# через roster matching. Exact match — единственный путь к авто-признанию сущности
# известной; partial / fuzzy / падежные формы → False → ClarificationQuestion.

from app.services.chronicle.decomposition_normalizer import _matches_roster_exact


def test_roster_exact_match_full_name():
    """Полное имя из roster → exact match True (сущность известна)."""
    roster = {
        "tavern_keeper_tornin": "Торнин Серебряная Луна",
        "guard_borko": "Стражник Борко",
    }
    # Полное имя — exact match
    assert _matches_roster_exact("Торнин Серебряная Луна", roster) is True
    assert _matches_roster_exact("торнин серебряная луна", roster) is True  # case-insensitive


def test_roster_partial_name_no_match():
    """Частичное имя (короткая форма) НЕ совпадает с roster exact match.
    «Торнин» ≠ «Торнин Серебряная Луна» → False → будет создан ClarificationQuestion.
    Это доказывает: target_hint из авторского текста не превращается в RESOLVED
    без явного выбора автора."""
    roster = {
        "tavern_keeper_tornin": "Торнин Серебряная Луна",
        "guard_borko": "Стражник Борко",
        "blacksmith_orm": "Кузнец Орм",
    }
    # Короткие имена — НЕ exact match
    assert _matches_roster_exact("Торнин", roster) is False
    assert _matches_roster_exact("Борко", roster) is False
    assert _matches_roster_exact("Орм", roster) is False
    # Падежные формы — НЕ exact match
    assert _matches_roster_exact("Орму", roster) is False
    assert _matches_roster_exact("Торниным", roster) is False


def test_roster_npc_id_match():
    """npc_id из roster → exact match True (можно ссылаться по id)."""
    roster = {"tavern_keeper_tornin": "Торнин Серебряная Луна"}
    assert _matches_roster_exact("tavern_keeper_tornin", roster) is True


def test_roster_non_string_hint_no_match():
    """Non-string hint → False (type-guarded, не crash)."""
    roster = {"npc_a": "Name A"}
    assert _matches_roster_exact(None, roster) is False
    assert _matches_roster_exact(42, roster) is False
    assert _matches_roster_exact("", roster) is False

