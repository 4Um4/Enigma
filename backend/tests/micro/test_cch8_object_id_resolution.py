"""CCH-8 / COV-10.4: object_id auto-resolution при exact roster match.

Доказанный дефект: при exact match target_hint с roster, normalizer не создаёт
ClarificationQuestion, но decompose_fragment не устанавливал object_id.
Результат: «застрявшая» запись — без object_id, без open_questions.

Фикс: resolve_object_ref_from_roster helper + использование в decompose_fragment.

Тесты:
- 7 unit-тестов на helper resolve_object_ref_from_roster
- 2 integration-теста на decompose_fragment (exact match → object_id; partial → question)
"""
from __future__ import annotations

import asyncio

from app.domain.chronicle import EntityRef, EntityRefKind


_ROSTER = {
    "tavern_keeper_tornin": "Торнин Серебряная Луна",
    "guard_borko": "Стражник Борко",
    "blacksmith_orm": "Кузнец Орм",
    "maid_lusya": "Люся",
    "thief_shadow": "Тень",
}


# ── Unit: resolve_object_ref_from_roster ────────────────────────────────────


def test_exact_full_name_match_resolves():
    """Полное имя из roster → EntityRef(RESOLVED, npc_id)."""
    from app.services.chronicle.decomposition_normalizer import (
        resolve_object_ref_from_roster,
    )

    ref = resolve_object_ref_from_roster("Торнин Серебряная Луна", _ROSTER)
    assert ref is not None
    assert ref.ref_kind is EntityRefKind.RESOLVED
    assert ref.npc_id == "tavern_keeper_tornin"


def test_exact_full_name_case_insensitive():
    """Case-insensitive exact match."""
    from app.services.chronicle.decomposition_normalizer import (
        resolve_object_ref_from_roster,
    )

    ref = resolve_object_ref_from_roster("торнин серебряная луна", _ROSTER)
    assert ref is not None
    assert ref.npc_id == "tavern_keeper_tornin"


def test_exact_npc_id_match_resolves():
    """npc_id из roster → EntityRef(RESOLVED)."""
    from app.services.chronicle.decomposition_normalizer import (
        resolve_object_ref_from_roster,
    )

    ref = resolve_object_ref_from_roster("tavern_keeper_tornin", _ROSTER)
    assert ref is not None
    assert ref.ref_kind is EntityRefKind.RESOLVED
    assert ref.npc_id == "tavern_keeper_tornin"


def test_partial_short_name_no_match():
    """Короткое имя (частичное) НЕ должно auto-resolve'иться.
    «Торнин» ≠ «Торнин Серебряная Луна» → None.
    Автор должен разрешить через ClarificationQuestion."""
    from app.services.chronicle.decomposition_normalizer import (
        resolve_object_ref_from_roster,
    )

    assert resolve_object_ref_from_roster("Торнин", _ROSTER) is None
    assert resolve_object_ref_from_roster("Борко", _ROSTER) is None
    assert resolve_object_ref_from_roster("Орм", _ROSTER) is None


def test_short_name_equal_to_roster_name_resolves():
    """«Тень» — короткое имя, но exact match с roster name='Тень' → resolve.
    Здесь семантика: roster name='Тень' — это полное имя персонажа."""
    from app.services.chronicle.decomposition_normalizer import (
        resolve_object_ref_from_roster,
    )

    ref = resolve_object_ref_from_roster("Тень", _ROSTER)
    assert ref is not None
    assert ref.npc_id == "thief_shadow"


def test_inflected_form_no_match():
    """Падежные формы НЕ должны auto-resolve'иться (exact match only)."""
    from app.services.chronicle.decomposition_normalizer import (
        resolve_object_ref_from_roster,
    )

    assert resolve_object_ref_from_roster("Орму", _ROSTER) is None
    assert resolve_object_ref_from_roster("Торниным", _ROSTER) is None


def test_non_string_and_empty_no_match():
    """Non-string hint → None (type-guarded, не crash). Пустая строка → None."""
    from app.services.chronicle.decomposition_normalizer import (
        resolve_object_ref_from_roster,
    )

    assert resolve_object_ref_from_roster(None, _ROSTER) is None
    assert resolve_object_ref_from_roster(42, _ROSTER) is None
    assert resolve_object_ref_from_roster("", _ROSTER) is None
    assert resolve_object_ref_from_roster("   ", _ROSTER) is None


def test_empty_roster_returns_none():
    """Пустой roster → None для любого hint."""
    from app.services.chronicle.decomposition_normalizer import (
        resolve_object_ref_from_roster,
    )

    assert resolve_object_ref_from_roster("Тень", {}) is None


# ── Integration: decompose_fragment ──────────────────────────────────────────


def test_decompose_fragment_sets_object_id_on_exact_match(monkeypatch):
    """Integration: decompose_fragment с exact match target_hint → object_id RESOLVED.

    Мокает decomposer, чтобы вернуть RELATIONSHIP с target_hint='Тень' (exact match).
    После decompose_fragment, draft entry должен иметь object_id=RESOLVED.
    """
    from app.api import routes_chronicle
    from app.api.routes_chronicle import DecomposeRequest
    from app.domain.chronicle import (
        DecompositionItem,
        EntryKind,
    )
    from app.services.chronicle.biography_decomposer import DecomposeResult

    _fake_items = [
        DecompositionItem(
            kind=EntryKind.RELATIONSHIP,
            draft_payload={
                "summary": "test",
                "target_hint": "Тень",
                "nature": "trust",
                "valence": "positive",
            },
            confidence=0.9,
            needs_confirmation=False,
            question=None,
        ),
    ]
    _fake_result = DecomposeResult.success(_fake_items, age_anchors=[])

    class _FakeDecomposer:
        async def decompose(self, chronicle_id, fragment_ord, fragment):
            return _fake_result

    monkeypatch.setattr(routes_chronicle, "_get_decomposer", lambda: _FakeDecomposer())

    _draft_store: dict = {}

    class _FakeStore:
        def load_draft(self, campaign_id, npc_id):
            return _draft_store.get((campaign_id, npc_id))

        def save_draft(self, doc, campaign_id):
            _draft_store[(campaign_id, doc.npc_ref)] = doc
            return "fake_path"

    monkeypatch.setattr(routes_chronicle, "_get_store", lambda: _FakeStore())
    monkeypatch.setattr(
        "app.services.npc.npc_loader.get_display_names",
        lambda: _ROSTER,
    )

    req = DecomposeRequest(
        campaign_id="test_c",
        npc_id="blacksmith_orm",
        fragment_ord=1,
        fragment="some text",
    )
    response = asyncio.run(
        routes_chronicle.decompose_fragment("test_c", "blacksmith_orm", req)
    )

    assert response["status"] == "OK"
    saved_doc = _draft_store[("test_c", "blacksmith_orm")]
    assert len(saved_doc.entries) == 1
    entry = saved_doc.entries[0]
    assert entry.kind is EntryKind.RELATIONSHIP
    assert entry.object_id is not None, (
        "object_id должен быть установлен для exact match (COV-10.4 fix)"
    )
    assert entry.object_id.ref_kind is EntityRefKind.RESOLVED
    assert entry.object_id.npc_id == "thief_shadow"
    assert entry.open_questions == (), "exact match → no open_questions"


def test_decompose_fragment_no_object_id_on_partial_match(monkeypatch):
    """Integration: decompose_fragment с partial name → NEW_NPC placeholder + open_questions.

    target_hint='Торнин' (частичное, не exact match с roster 'Торнин Серебряная Луна').
    Normalizer создаёт ClarificationQuestion; decompose_fragment (COV-12 п.2b)
    создаёт placeholder EntityRef(NEW_NPC, name_hint=target_hint), чтобы /resolve
    нашёл его по _match (name_hint==target_span) и перелинковал на
    WHITE_SPOT/RESOLVED/UNKNOWN. Без placeholder white spot создавался, но
    запись на него не ссылалась (баг №3 вердикта).
    """
    from app.api import routes_chronicle
    from app.api.routes_chronicle import DecomposeRequest
    from app.domain.chronicle import EntryKind
    from app.services.chronicle.biography_decomposer import (
        BiographyDecomposer,
        DecomposeResult,
    )
    from app.services.chronicle.decomposition_normalizer import (
        ChronicleDecompositionNormalizer,
    )

    real_decomposer = BiographyDecomposer()

    async def _fake_decompose(self, chronicle_id, fragment_ord, fragment):
        items = ChronicleDecompositionNormalizer.normalize(
            {
                "items": [
                    {
                        "kind": "RELATIONSHIP",
                        "draft_payload": {
                            "summary": "test",
                            "target_hint": "Торнин",
                            "nature": "trust",
                            "valence": "positive",
                        },
                        "confidence": 0.9,
                    }
                ]
            },
            chronicle_id=chronicle_id,
            fragment_ord=fragment_ord,
            roster=_ROSTER,
        )
        return DecomposeResult.success(items, age_anchors=[])

    monkeypatch.setattr(BiographyDecomposer, "decompose", _fake_decompose)
    monkeypatch.setattr(routes_chronicle, "_get_decomposer", lambda: real_decomposer)

    _draft_store: dict = {}

    class _FakeStore:
        def load_draft(self, campaign_id, npc_id):
            return _draft_store.get((campaign_id, npc_id))

        def save_draft(self, doc, campaign_id):
            _draft_store[(campaign_id, doc.npc_ref)] = doc
            return "fake_path"

    monkeypatch.setattr(routes_chronicle, "_get_store", lambda: _FakeStore())
    monkeypatch.setattr(
        "app.services.npc.npc_loader.get_display_names",
        lambda: _ROSTER,
    )

    req = DecomposeRequest(
        campaign_id="test_c",
        npc_id="blacksmith_orm",
        fragment_ord=1,
        fragment="some text",
    )
    asyncio.run(routes_chronicle.decompose_fragment("test_c", "blacksmith_orm", req))

    saved_doc = _draft_store[("test_c", "blacksmith_orm")]
    assert len(saved_doc.entries) == 1
    entry = saved_doc.entries[0]
    assert entry.kind is EntryKind.RELATIONSHIP
    # COV-12 п.2b: NEW_NPC placeholder, не None. Без placeholder /resolve._match
    # (name_hint==target_span) не находил EntityRef, и white spot терялся.
    assert entry.object_id is not None, (
        "partial match → object_id должен быть NEW_NPC placeholder (не None)"
    )
    assert entry.object_id.ref_kind is EntityRefKind.NEW_NPC
    assert entry.object_id.name_hint == "Торнин"
    assert len(entry.open_questions) > 0, (
        "partial match → должен быть ClarificationQuestion"
    )
    assert entry.open_questions[0].target_span == "Торнин"