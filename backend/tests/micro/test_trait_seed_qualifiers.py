"""CCH-12 Point 2: qualifiers в TRAIT_SEED payload.

4 группы тестов:
1. Раздельная декомпозиция X и Y — структура payload принимает qualifiers.
2. «Только» сохраняется в qualifiers обоих элементов перечисления.
3. Старые TRAIT_SEED без qualifiers продолжают работать (backward-compat).
4. Неподдержанные qualifiers («особенно», «всегда») не принимаются автоматически —
   только «только» / «исключительно» контрактуемы.

Также: qualifiers не распространяются на соседние несвязанные TRAIT_SEED.

Не тестирует: LLM-вывод (недетерминированный), материализацию TRAIT_SEED в
NPCState (системный долг, отдельная задача).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.chronicle import (
    ChronicleDocument,
    ChronicleEntry,
    EntityRef,
    EntityRefKind,
    EntryKind,
    EntryProvenance,
    make_entry_id,
)
from app.services.chronicle.chronicle_store import (
    ChronicleStore,
    document_from_dict,
    document_to_dict,
)

_NPC = "npc_test_qualifiers"


# ── Хелперы ──────────────────────────────────────────────────────────────


def _make_trait_entry(
    ordinal: int,
    trait: str,
    evidence: str,
    qualifiers=None,
    provenance_extra=None,
) -> ChronicleEntry:
    payload = {"trait": trait, "evidence": evidence}
    if qualifiers is not None:
        payload["qualifiers"] = qualifiers
    if provenance_extra:
        payload["_provenance"] = provenance_extra
    return ChronicleEntry(
        entry_id=make_entry_id(_NPC, ordinal // 100, ordinal % 100),
        kind=EntryKind.TRAIT_SEED,
        subject_id=EntityRef(ref_kind=EntityRefKind.RESOLVED, npc_id=_NPC),
        object_id=None,
        historical_age=None,
        payload=payload,
        provenance=EntryProvenance.AUTHOR_CONFIRMED,
        confidence=None,
        ordinal=ordinal,
    )


def _roundtrip(doc: ChronicleDocument, tmp_path: Path) -> ChronicleDocument:
    """Сериализация → десериализация через chronicle_store."""
    store = ChronicleStore(tmp_path / "canon", tmp_path / "drafts")
    (tmp_path / "canon").mkdir(parents=True, exist_ok=True)
    (tmp_path / "drafts").mkdir(parents=True, exist_ok=True)
    store.save_canonical(doc)
    loaded = store.load_canonical(_NPC)
    assert loaded is not None
    return loaded


# ── Группа 1: Раздельная декомпозиция X и Y ─────────────────────────────


def test_separate_traits_for_enumeration(tmp_path):
    """«Увлечён работой и выпивкой» → 2 отдельных TRAIT_SEED, не 1 слитый."""
    doc = ChronicleDocument(
        chronicle_id=_NPC,
        npc_ref=_NPC,
        entries=(
            _make_trait_entry(200, "увлечён работой", "Увлечён по-настоящему только своей работой"),
            _make_trait_entry(201, "увлечён выпивкой", "и выпивкой"),
        ),
        canonical=True,
        canonical_version=1,
    )
    loaded = _roundtrip(doc, tmp_path)
    traits = [e for e in loaded.entries if e.kind is EntryKind.TRAIT_SEED]
    assert len(traits) == 2, "перечисление X и Y должно дать 2 отдельных TRAIT_SEED"
    trait_values = [e.payload.get("trait") for e in traits]
    assert "увлечён работой" in trait_values
    assert "увлечён выпивкой" in trait_values


# ── Группа 2: «Только» сохраняется в qualifiers обоих ──────────────────


def test_qualifiers_only_preserved_in_both_traits(tmp_path):
    """«Только» применяется ко всем элементам перечисления — оба traits
    получают qualifiers: ["только"]."""
    doc = ChronicleDocument(
        chronicle_id=_NPC,
        npc_ref=_NPC,
        entries=(
            _make_trait_entry(
                200, "увлечён работой",
                "Увлечён по-настоящему только своей работой",
                qualifiers=["только"],
            ),
            _make_trait_entry(
                201, "увлечён выпивкой",
                "и выпивкой",
                qualifiers=["только"],
                provenance_extra={
                    "qualifier_basis": "Увлечён по-настоящему только своей работой и выпивкой"
                },
            ),
        ),
        canonical=True,
        canonical_version=1,
    )
    loaded = _roundtrip(doc, tmp_path)
    traits = sorted(
        [e for e in loaded.entries if e.kind is EntryKind.TRAIT_SEED],
        key=lambda e: e.ordinal,
    )
    assert len(traits) == 2

    # Оба имеют qualifiers: ["только"]
    for t in traits:
        assert t.payload.get("qualifiers") == ["только"], (
            f"trait {t.payload.get('trait')}: qualifiers должен быть ['только']"
        )

    # Второй имеет _provenance.qualifier_basis (основание qualifier'а)
    second = traits[1]
    prov = second.payload.get("_provenance", {})
    assert "qualifier_basis" in prov, (
        "второй элемент перечисления должен иметь _provenance.qualifier_basis"
    )
    assert "только" in prov["qualifier_basis"]


def test_qualifier_exclusively_supported(tmp_path):
    """«Исключительно» — поддерживаемый qualifier (семантический эквивалент «только»)."""
    doc = ChronicleDocument(
        chronicle_id=_NPC,
        npc_ref=_NPC,
        entries=(
            _make_trait_entry(
                200, "сосредоточен на работе",
                "Исключительно на работе",
                qualifiers=["исключительно"],
            ),
        ),
        canonical=True,
        canonical_version=1,
    )
    loaded = _roundtrip(doc, tmp_path)
    traits = [e for e in loaded.entries if e.kind is EntryKind.TRAIT_SEED]
    assert len(traits) == 1
    assert traits[0].payload.get("qualifiers") == ["исключительно"]


# ── Группа 3: Backward-compat — старые TRAIT_SEED без qualifiers ────────


def test_trait_seed_without_qualifiers_backward_compat(tmp_path):
    """Старые TRAIT_SEED без qualifiers продолжают работать после roundtrip."""
    doc = ChronicleDocument(
        chronicle_id=_NPC,
        npc_ref=_NPC,
        entries=(
            _make_trait_entry(200, "занятость работой", "Увлечён работой"),
            _make_trait_entry(201, "пьянство", "и выпивкой"),
        ),
        canonical=True,
        canonical_version=1,
    )
    loaded = _roundtrip(doc, tmp_path)
    traits = sorted(
        [e for e in loaded.entries if e.kind is EntryKind.TRAIT_SEED],
        key=lambda e: e.ordinal,
    )
    assert len(traits) == 2
    for t in traits:
        # qualifiers отсутствует — backward-compat
        assert "qualifiers" not in t.payload, (
            f"trait {t.payload.get('trait')}: qualifiers не должен быть добавлен автоматически"
        )
        assert t.payload.get("trait") in ("занятость работой", "пьянство")


def test_mixed_qualifiers_and_no_qualifiers_in_same_doc(tmp_path):
    """Документ с частью TRAIT_SEED имеющих qualifiers и частью без —
    оба типа сосуществуют, нет регрессии."""
    doc = ChronicleDocument(
        chronicle_id=_NPC,
        npc_ref=_NPC,
        entries=(
            _make_trait_entry(
                200, "увлечён работой", "только работой",
                qualifiers=["только"],
            ),
            _make_trait_entry(201, "упрямый", "Орм упрям"),  # без qualifiers
            _make_trait_entry(
                202, "увлечён выпивкой", "и выпивкой",
                qualifiers=["только"],
            ),
        ),
        canonical=True,
        canonical_version=1,
    )
    loaded = _roundtrip(doc, tmp_path)
    traits = sorted(
        [e for e in loaded.entries if e.kind is EntryKind.TRAIT_SEED],
        key=lambda e: e.ordinal,
    )
    assert len(traits) == 3
    # ord=200: qualifiers есть
    assert traits[0].payload.get("qualifiers") == ["только"]
    # ord=201: qualifiers отсутствует
    assert "qualifiers" not in traits[1].payload
    # ord=202: qualifiers есть
    assert traits[2].payload.get("qualifiers") == ["только"]


# ── Группа 4: Неподдержанные qualifiers не принимаются автоматически ────


def test_unsupported_qualifiers_preserved_but_not_contractual(tmp_path):
    """«Особенно», «всегда» — пока не контрактуемы. Промпт их не добавляет,
    но если LLM их проставит — payload сохранит (Dict[str, Any] не валидирует
    содержимое qualifiers). Тест фиксирует: нормализатор/сериализация НЕ
    rejected, но контракт поддерживает только «только»/«исключительно».
    
    Это не запрет на другие значения — это явное указание, что семантика
    других qualifiers не определена контрактом Point 2.
    """
    doc = ChronicleDocument(
        chronicle_id=_NPC,
        npc_ref=_NPC,
        entries=(
            _make_trait_entry(
                200, "старательный", "особенно старательный",
                qualifiers=["особенно"],
            ),
        ),
        canonical=True,
        canonical_version=1,
    )
    loaded = _roundtrip(doc, tmp_path)
    traits = [e for e in loaded.entries if e.kind is EntryKind.TRAIT_SEED]
    assert len(traits) == 1
    # Поле сохраняется (Dict[str, Any] не валидирует содержимое)
    assert traits[0].payload.get("qualifiers") == ["особенно"]
    # Но семантика «особенно» НЕ определена контрактом Point 2 —
    # только «только»/«исключительно» поддерживаются промптом.


# ── Группа 5: qualifiers не распространяются на несвязанные traits ──────


def test_qualifiers_do_not_leak_to_unrelated_traits(tmp_path):
    """Qualifiers из перечисления «работой и выпивкой» НЕ распространяются
    на соседние несвязанные TRAIT_SEED из другого пункта."""
    doc = ChronicleDocument(
        chronicle_id=_NPC,
        npc_ref=_NPC,
        entries=(
            # Пункт 2: перечисление с «только»
            _make_trait_entry(
                200, "увлечён работой", "только работой",
                qualifiers=["только"],
            ),
            _make_trait_entry(
                201, "увлечён выпивкой", "и выпивкой",
                qualifiers=["только"],
            ),
            # Пункт 3: несвязанный trait из другого пункта — БЕЗ qualifiers
            _make_trait_entry(300, "хороший друг", "Хороший его друг Торнин"),
        ),
        canonical=True,
        canonical_version=1,
    )
    loaded = _roundtrip(doc, tmp_path)
    traits = sorted(
        [e for e in loaded.entries if e.kind is EntryKind.TRAIT_SEED],
        key=lambda e: e.ordinal,
    )
    assert len(traits) == 3
    # ord=200, 201: qualifiers есть (из перечисления)
    assert traits[0].payload.get("qualifiers") == ["только"]
    assert traits[1].payload.get("qualifiers") == ["только"]
    # ord=300: qualifiers ОТСУТСТВУЕТ (несвязанный trait)
    assert "qualifiers" not in traits[2].payload, (
        "qualifiers из перечисления не должен утекать в несвязанные traits"
    )