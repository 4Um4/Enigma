# path: /project/backend/tests/gameplay/test_p4_knowledge_retrieval.py
# Назначение: M1/P4 — гейт чистого reader над narrative_cache.
#   Сквозной P1->P2->P3->P4: язык -> QUESTION + SubjectRef -> знание.
#   Ключевой инвариант: TRUTH ≠ KNOWLEDGE (негатив-контроль владения).
#   L-P4: Retrieval Is Observation (немутация + честная пустота).
# Зависимости: tests.gameplay.harness, knowledge_retrieval, intent_compressor
# Основные сущности: test_p4_*
import copy

import pytest
from app.domain.subject_ref import SubjectKind, SubjectRef
from app.services.input.intent_compressor import IntentCompressor
from app.services.npc.knowledge_retrieval import (
    MatchReason,
    retrieve_knowledge,
)
from app.services.npc.npc_loader import load_l2_state_from_runtime_dict
from tests.gameplay.harness import TavernGameplayHarness


@pytest.fixture()
def harness():
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    _h.advance_ticks(3)
    yield _h
    _h.dispose()


def _state(h, npc_id: str):
    return load_l2_state_from_runtime_dict(copy.deepcopy(h.inspect_npc(npc_id)))


def _p3_subject(text: str) -> SubjectRef | None:
    c = IntentCompressor(llm_client=None)
    f = c._fast_path_parse(text)
    if f is None or f.speech_act is None:
        return None
    return SubjectRef(
        kind=SubjectKind(f.subject_kind) if f.subject_kind else SubjectKind.UNKNOWN,
        subject_id=f.subject_id,
        subject_hint=f.subject_hint,
    )


def test_p4_borko_knows_caravan(harness):
    """T1 (сквозной позитив): «про караван» → Борко знает borko_negligence."""
    subject = _p3_subject("Спросить Борко про караван")
    assert subject is not None
    assert subject.subject_id == "borko_negligence"
    items = retrieve_knowledge(_state(harness, "guard_borko"), subject)
    assert len(items) >= 1, "Борко обязан знать borko_negligence"
    top = items[0]
    assert top.secret_id == "borko_negligence"
    assert top.match_reason in (MatchReason.EXACT_SECRET, MatchReason.CANON_TOPIC)
    assert "караван" in top.summary.lower() or "ворота" in top.summary.lower()


def test_p4_goran_does_not_know_caravan(harness):
    """T2 (негатив-контроль владения; Truth ≠ Knowledge): секрет существует
    глобально, но Горан НЕ обладает им → честный пустой кортеж."""
    subject = _p3_subject("Спросить Горана про караван")
    assert subject is not None
    items = retrieve_knowledge(_state(harness, "merchant_goran"), subject)
    assert items == (), (
        f"Горан не обладает borko_negligence; ожидается пустой кортеж; "
        f"получено: {[(i.secret_id, i.match_reason) for i in items]}"
    )


def test_p4_aa_identical(harness):
    """T3 (A/A): same world, same query, same NPC → byte-identical."""
    subject = _p3_subject("Спросить Борко про караван")
    state = _state(harness, "guard_borko")
    a = retrieve_knowledge(state, subject)
    b = retrieve_knowledge(state, subject)
    assert a == b, "A/A: недетерминированный retrieval"


def test_p4_shadow_knows_about_lusya(harness):
    """T4 (PARTICIPANT-матч): «о Люсе» → Тень знает shadow_suspects_lusya."""
    subject = _p3_subject("Что ты знаешь о Люсе?")
    assert subject is not None
    assert subject.kind is SubjectKind.NPC
    assert subject.subject_id == "maid_lusya"
    items = retrieve_knowledge(_state(harness, "thief_shadow"), subject)
    lusya_items = [i for i in items if "lusya" in i.secret_id]
    assert lusya_items, (
        f"Тень должен знать о Люсе (shadow_suspects_lusya; "
        f"participant-матч); получено: {[(i.secret_id, i.match_reason) for i in items]}"
    )


def test_p4_l4_no_mutation(harness):
    """T5 (L-P4-гвард): retrieval не мутирует narrative_cache."""
    state = _state(harness, "guard_borko")
    before = tuple(
        (m.secret_id, m.summary, m.importance, m.stage, m.is_secret)
        for m in state.narrative_cache
    )
    subject = _p3_subject("Спросить Борко про караван")
    retrieve_knowledge(state, subject)
    after = tuple(
        (m.secret_id, m.summary, m.importance, m.stage, m.is_secret)
        for m in state.narrative_cache
    )
    assert before == after, "L-P4: retrieval мутировал narrative_cache"


def test_p4_empty_subject_returns_empty(harness):
    """N2-преемственность: UNKNOWN subject → пустой кортеж (честно)."""
    subject = SubjectRef(kind=SubjectKind.UNKNOWN, subject_id=None, subject_hint="что-то")
    items = retrieve_knowledge(_state(harness, "guard_borko"), subject)
    # UNKNOWN не матчит EXACT/PARTICIPANT/CANON_TOPIC → пусто
    assert items == ()
