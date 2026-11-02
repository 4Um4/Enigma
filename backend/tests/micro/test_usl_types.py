"""
Контрактные тесты USL Core (USL-1.1, ADR-O-437).

Проверяют:
    - типы создаются с валидными полями;
    - frozen dataclasses не мутируются;
    - make_unit_id детерминирован (USL-6);
    - enum значения существуют;
    - USLModal None defaults не трактуются как False;
    - USLUnit собирается из всех компонент.

Не проверяют адаптеры (BiographyAdapter/InteractiveLanguageAdapter) —
это следующие шаги USL-1.2 / USL-1.3.
"""
import dataclasses
import pytest

from app.domain.usl import (
    USLAnchorKind,
    USLCausalLink,
    USLCausalRelation,
    USLContext,
    USLEntityRef,
    USLEpistemics,
    USLEvent,
    USLModality,
    USLModal,
    USLPredicate,
    USLRelation,
    USLSourceKind,
    USLSourceRef,
    USLTimeExpression,
    USLTimeKind,
    USLUnit,
    make_unit_id,
)


# ── 1. Type creation ──────────────────────────────────────────────────────────

def test_usl_source_kind_has_9_values():
    """USL-2: 9 видов источников (AUTHOR_CANON..HYPOTHESIS)."""
    assert len(USLSourceKind) == 9
    assert USLSourceKind.AUTHOR_CANON.value == "author_canon"
    assert USLSourceKind.PLAYER_ASSERTION.value == "player_assertion"
    assert USLSourceKind.HYPOTHESIS.value == "hypothesis"


def test_usl_time_kind_has_6_forms():
    """Вердикт Мастера Q2: 6 форм времени."""
    assert len(USLTimeKind) == 6
    assert USLTimeKind.POINT.value == "point"
    assert USLTimeKind.DURATION.value == "duration"
    assert USLTimeKind.INTERVAL.value == "interval"
    assert USLTimeKind.ORDER.value == "order"
    assert USLTimeKind.RELATIVE.value == "relative"
    assert USLTimeKind.UNKNOWN.value == "unknown"


def test_usl_anchor_kind_has_7_values():
    assert len(USLAnchorKind) == 7
    assert USLAnchorKind.AGE_N.value == "age_n"
    assert USLAnchorKind.SPEECH_TIME.value == "speech_time"
    assert USLAnchorKind.UNKNOWN.value == "unknown"


def test_usl_predicate_has_15_values():
    """6 общих (совпадают с Predicate.value) + 9 биографических."""
    assert len(USLPredicate) == 15
    # Общие 6 — значения совпадают с epistemology.Predicate
    assert USLPredicate.STOLE.value == "stole"
    assert USLPredicate.ATTACKED.value == "attacked"
    assert USLPredicate.HELPED.value == "helped"
    assert USLPredicate.ASSERTS.value == "asserts"
    assert USLPredicate.EXITS_TO.value == "exits_to"
    assert USLPredicate.NAME.value == "name"
    # Биографические 9
    assert USLPredicate.WORK_FOR.value == "work_for"
    assert USLPredicate.KNOWS.value == "knows"
    assert USLPredicate.BORN.value == "born"
    assert USLPredicate.DIED.value == "died"
    assert USLPredicate.LIVES_AT.value == "lives_at"
    assert USLPredicate.HAS_TRAIT.value == "has_trait"
    assert USLPredicate.HAS_EFFECT.value == "has_effect"
    assert USLPredicate.BELIEVES.value == "believes"
    assert USLPredicate.DESIRES.value == "desires"


def test_usl_predicate_maps_to_epistemology_predicate():
    """Общие 6 значений USLPredicate совпадают с Predicate.value — trivial mapping."""
    from app.domain.epistemology import Predicate
    for usl_pred in (USLPredicate.STOLE, USLPredicate.ATTACKED, USLPredicate.HELPED,
                     USLPredicate.ASSERTS, USLPredicate.EXITS_TO, USLPredicate.NAME):
        # Predicate(uslpred.value) должен работать
        ep_pred = Predicate(usl_pred.value)
        assert ep_pred.value == usl_pred.value


def test_usl_modality_has_4_values():
    assert len(USLModality) == 4
    assert USLModality.REALIS.value == "REALIS"
    assert USLModality.HYPOTHETICAL.value == "HYPOTHETICAL"
    assert USLModality.CONDITIONAL.value == "CONDITIONAL"
    assert USLModality.DESIRED.value == "DESIRED"


# ── 2. Frozen dataclasses ─────────────────────────────────────────────────────

def test_usl_unit_is_frozen():
    """USLUnit frozen — попытка мутации raises FrozenInstanceError (прецедент IntentSemanticField)."""
    unit = USLUnit(
        unit_id="test_id",
        source_ref=USLSourceRef(source_kind=USLSourceKind.AUTHOR_CANON),
        text_span="тест",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        unit.text_span = "mutated"  # type: ignore


def test_usl_event_is_frozen():
    event = USLEvent(predicate=USLPredicate.WORK_FOR)
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.predicate = USLPredicate.HELPED  # type: ignore


def test_usl_time_expression_is_frozen():
    expr = USLTimeExpression(kind=USLTimeKind.DURATION, value=5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        expr.value = 10  # type: ignore


def test_usl_modal_is_frozen():
    modal = USLModal(negated=True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        modal.negated = False  # type: ignore


# ── 3. make_unit_id детерминизм (USL-6) ───────────────────────────────────────

def test_make_unit_id_deterministic():
    """USL-6: одинаковый source_ref + text_span → одинаковый id."""
    src = USLSourceRef(
        source_kind=USLSourceKind.AUTHOR_CANON,
        document_ref="orm",
        span="пять лет работал на Орма",
    )
    id1 = make_unit_id(src, "пять лет работал на Орма")
    id2 = make_unit_id(src, "пять лет работал на Орма")
    assert id1 == id2
    assert len(id1) == 32  # md5 hex


def test_make_unit_id_differs_on_different_source():
    """Разный source_kind → разный id."""
    src1 = USLSourceRef(source_kind=USLSourceKind.AUTHOR_CANON, document_ref="orm")
    src2 = USLSourceRef(source_kind=USLSourceKind.PLAYER_ASSERTION, document_ref="orm")
    id1 = make_unit_id(src1, "пять лет работал")
    id2 = make_unit_id(src2, "пять лет работал")
    assert id1 != id2


def test_make_unit_id_differs_on_different_span():
    """Разный span → разный id."""
    src = USLSourceRef(source_kind=USLSourceKind.AUTHOR_CANON, document_ref="orm")
    id1 = make_unit_id(src, "пять лет работал")
    id2 = make_unit_id(src, "десять лет работал")
    assert id1 != id2


# ── 4. USLModal None defaults (правило Блока 1) ──────────────────────────────

def test_usl_modal_none_defaults():
    """None = недостаточная информация, НЕ False (правило Блока 1, intent_profile.py:53-55)."""
    modal = USLModal()
    assert modal.negated is None
    assert modal.modality is None
    assert modal.condition is None
    assert modal.quoted is None
    assert modal.quoted_speaker is None


def test_usl_modal_explicit_realis():
    modal = USLModal(modality=USLModality.REALIS)
    assert modal.modality is USLModality.REALIS


# ── 5. USLUnit construction (полная сборка) ──────────────────────────────────

def test_usl_unit_minimal_construction():
    """Минимальный USLUnit — только обязательные поля."""
    src = USLSourceRef(source_kind=USLSourceKind.AUTHOR_CANON, span="фрагмент")
    unit = USLUnit(
        unit_id=make_unit_id(src, "фрагмент"),
        source_ref=src,
        text_span="фрагмент",
    )
    assert unit.unit_id
    assert unit.source_ref.source_kind is USLSourceKind.AUTHOR_CANON
    assert unit.entities == ()
    assert unit.events == ()
    assert unit.temporal == ()
    assert unit.causal == ()
    assert unit.relations == ()


def test_usl_unit_full_construction():
    """Полная сборка USLUnit со всеми компонентами (сквозной пример §6.5)."""
    src = USLSourceRef(
        source_kind=USLSourceKind.AUTHOR_CANON,
        document_ref="orm",
        span="Он пять лет работал на Орма",
    )
    span = "Он пять лет работал на Орма"
    unit = USLUnit(
        unit_id=make_unit_id(src, span),
        source_ref=src,
        text_span=span,
        entities=(
            USLEntityRef(kind="resolved", ref_id="orm", source_span="Орма"),
            USLEntityRef(kind="resolved", ref_id="npc_he", source_span="Он"),
        ),
        events=(
            USLEvent(
                predicate=USLPredicate.WORK_FOR,
                subject="npc_he",
                object="orm",
                completed=True,
                source_span="работал на Орма",
            ),
        ),
        temporal=(
            USLTimeExpression(
                kind=USLTimeKind.DURATION,
                anchor=USLAnchorKind.AGE_N,
                value=5,
                relative_to="event_work_for",
                source_span="пять лет",
            ),
        ),
        relations=(
            USLRelation(
                relation_type="work_relation",
                subject="npc_he",
                object="orm",
                valence="neutral",
                source_span="работал на",
            ),
        ),
        modality=USLModal(),
        epistemics=USLEpistemics(source_kind=USLSourceKind.AUTHOR_CANON),
        context=USLContext(),
        origin_kind="chronicle_entry",
        origin_id="entry_orm_work",
    )
    assert unit.events[0].predicate is USLPredicate.WORK_FOR
    assert unit.events[0].completed is True
    assert unit.temporal[0].kind is USLTimeKind.DURATION
    assert unit.temporal[0].value == 5
    assert unit.epistemics.source_kind is USLSourceKind.AUTHOR_CANON
    assert unit.origin_kind == "chronicle_entry"


# ── 6. USLEntityRef kinds ─────────────────────────────────────────────────────

def test_usl_entity_ref_kinds():
    """USLEntityRef поддерживает kind из обоих контуров."""
    # Из биографии
    ref1 = USLEntityRef(kind="resolved", ref_id="orm", source_span="Орма")
    assert ref1.kind == "resolved"
    # Из ввода (subject=self)
    ref2 = USLEntityRef(kind="self", ref_id="player", source_span="Я")
    assert ref2.kind == "self"
    # Из ввода (addressee)
    ref3 = USLEntityRef(kind="addressee", ref_id="npc_orm", source_span="тебя")
    assert ref3.kind == "addressee"
    # Unresolved
    ref4 = USLEntityRef(kind="unknown", name_hint="стражник", source_span="стражник")
    assert ref4.kind == "unknown"


# ── 7. USLSourceKind PLAYER_ASSERTION ≠ AUTHOR_CANON (инвариант USL-2) ────────

def test_player_assertion_not_author_canon():
    """USL-2: PLAYER_ASSERTION и AUTHOR_CANON — разные source_kind.
    Утверждение игрока не становится каноном (инвариант USL-2).
    Этот тест — фундамент для будущего тест-запрета PLAYER_ASSERTION → CANON.
    """
    assert USLSourceKind.PLAYER_ASSERTION is not USLSourceKind.AUTHOR_CANON
    assert USLSourceKind.PLAYER_ASSERTION.value != USLSourceKind.AUTHOR_CANON.value


# ── 8. USLTimeExpression: DURATION vs RELATIVE (поправка Мастера Q2) ─────────

def test_duration_vs_relative_distinction():
    """«Пять лет работал» — DURATION; «пять лет назад работал» — RELATIVE.
    Это разные семантические конструкции (поправка Мастера к Q2).
    """
    duration_expr = USLTimeExpression(
        kind=USLTimeKind.DURATION,
        value=5,
        source_span="пять лет",
    )
    relative_expr = USLTimeExpression(
        kind=USLTimeKind.RELATIVE,
        anchor=USLAnchorKind.YEARS_AGO,
        value=5,
        source_span="пять лет назад",
    )
    assert duration_expr.kind is USLTimeKind.DURATION
    assert relative_expr.kind is USLTimeKind.RELATIVE
    assert duration_expr.kind != relative_expr.kind


# ── 9. USLCausalLink: ORDER ≠ CAUSES (запрет хронология→причина) ─────────────

def test_order_not_causes():
    """USLTimeExpression(ORDER) никогда не конвертируется в USLCausalLink автоматически.
    Хронология ≠ причина (USL §6.4, запрет).
    """
    order_expr = USLTimeExpression(
        kind=USLTimeKind.ORDER,
        relative_to="event_death",
        source_span="после смерти отца",
    )
    causal_link = USLCausalLink(
        relation=USLCausalRelation.CAUSES,
        cause_ref="event_death",
        effect_ref="event_inherit",
        source_span="после смерти отца он унаследовал",
    )
    # Это РАЗНЫЕ типы — ORDER не становится CAUSES автоматически
    assert order_expr.kind is USLTimeKind.ORDER
    assert causal_link.relation is USLCausalRelation.CAUSES
    # Связь существует только если asserted_by_text=True
    assert causal_link.asserted_by_text is True