# path: /project/backend/tests/gameplay/test_p5_disclosure.py
# Назначение: M1/P5.1 — гейт: KNOWER→RECIPIENT disclosure; универсальность
#   (одна функция — три адресата); A/A; немутация; пороговые переходы;
#   сквозной P1→P4→P5.
# Зависимости: app.domain.disclosure, app.services.npc.disclosure_decision,
#   tests.gameplay.harness
# Основные сущности: test_p5_*, borko_state-fixture
import copy
import dataclasses

import pytest
from app.domain.disclosure import (
    DisclosureContext,
    DisclosureLevel,
    InteractionPressure,
    SocialTarget,
    SocialTargetKind,
)
from app.services.npc.disclosure_decision import decide_disclosure
from app.services.npc.knowledge_retrieval import KnowledgeItem, MatchReason
from app.services.npc.npc_loader import load_l2_state_from_runtime_dict
from tests.gameplay.harness import TavernGameplayHarness

_TARGET_PLAYER = SocialTarget(SocialTargetKind.PERSON, "player")
_TARGET_LUSYA = SocialTarget(SocialTargetKind.PERSON, "maid_lusya")
_TARGET_TORNIN = SocialTarget(SocialTargetKind.PERSON, "tavern_keeper_tornin")


def _item(secret_id: str = "borko_negligence", importance: float = 0.85) -> KnowledgeItem:
    return KnowledgeItem(
        secret_id=secret_id,
        summary="Год назад пропустил через ворота караван без досмотра",
        importance=importance,
        match_reason=MatchReason.EXACT_SECRET,
    )


def _ctx(
    pressure: InteractionPressure = InteractionPressure.QUESTION,
    amount: float = 2.0,
) -> DisclosureContext:
    return DisclosureContext(pressure=pressure, pressure_amount=amount)


@pytest.fixture()
def harness():
    _h = TavernGameplayHarness(seed=42)
    _h.new_game()
    _h.advance_ticks(3)
    yield _h
    _h.dispose()


@pytest.fixture()
def borko_state(harness):
    """Живой Борко-стейт через production-гидратацию (§13.4: from_legacy,
    не конструктор-мечта); stress=0 для чистой пороговой логики."""
    _st = load_l2_state_from_runtime_dict(
        copy.deepcopy(harness.inspect_npc("guard_borko"))
    )
    return dataclasses.replace(_st, stress=0.0)


def test_p5_triple_disclosure(borko_state):
    """T1 (главный): та же функция, три адресата — разные вердикты.
    Борко знает borko_negligence; pressure=QUESTION×2:
    - player (trust=40) → PARTIAL
    - Люся (trust=-20) → DENY
    - Торнин (trust=30) → PARTIAL
    """
    item = _item()
    ctx = _ctx(amount=2.0)

    # player: trust=40 → PARTIAL (≥ T_PARTIAL=20, < T_REVEAL=50)
    o_p = decide_disclosure(
        borko_state, _TARGET_PLAYER, {"trust": 40.0, "fear": 10.0}, item, ctx
    )
    assert o_p.level == DisclosureLevel.PARTIAL

    # Люся: trust=-20 → DENY
    o_l = decide_disclosure(
        borko_state, _TARGET_LUSYA, {"trust": -20.0, "fear": 0.0}, item, ctx
    )
    assert o_l.level == DisclosureLevel.DENY

    # Торнин: trust=30 → PARTIAL
    o_t = decide_disclosure(
        borko_state, _TARGET_TORNIN, {"trust": 30.0, "fear": 50.0}, item, ctx
    )
    assert o_t.level == DisclosureLevel.PARTIAL


def test_p5_aa_identical(borko_state):
    """T2 (A/A): одинаковые входы → одинаковый вердикт."""
    rel = {"trust": 40.0, "fear": 0.0}
    a = decide_disclosure(borko_state, _TARGET_PLAYER, rel, _item(), _ctx())
    b = decide_disclosure(borko_state, _TARGET_PLAYER, rel, _item(), _ctx())
    assert a == b


def test_p5_no_mutation(borko_state):
    """T3 (L-P5-гвард): decide не мутирует source_npc."""
    before = (borko_state.stress, borko_state.npc_id, len(borko_state.narrative_cache))
    decide_disclosure(
        borko_state, _TARGET_PLAYER, {"trust": 60.0, "fear": 0.0},
        _item(), _ctx(),
    )
    after = (borko_state.stress, borko_state.npc_id, len(borko_state.narrative_cache))
    assert before == after


def test_p5_pressure_effect(borko_state):
    """T4: давление 1→5 → вердикт поднимается (trust=15: DENY→HINT)."""
    rel = {"trust": 15.0, "fear": 0.0}
    o1 = decide_disclosure(borko_state, _TARGET_PLAYER, rel, _item(), _ctx(amount=1.0))
    assert o1.level == DisclosureLevel.DENY
    o5 = decide_disclosure(borko_state, _TARGET_PLAYER, rel, _item(), _ctx(amount=5.0))
    assert o5.level == DisclosureLevel.HINT


def test_p5_stress_crack(harness, borko_state):
    """T5: stress=80, trust=0 → HINT (не DENY — трещина от стресса)."""
    stressed = dataclasses.replace(borko_state, stress=80.0)
    o = decide_disclosure(
        stressed, _TARGET_PLAYER, {"trust": 0.0, "fear": 0.0},
        _item(), _ctx(amount=1.0),
    )
    assert o.level == DisclosureLevel.HINT


def test_p5_redirect_from_fear(borko_state):
    """T6: fear=70, trust=0 → REDIRECT (не DENY — уход от темы)."""
    o = decide_disclosure(
        borko_state, _TARGET_PLAYER, {"trust": 0.0, "fear": 70.0},
        _item(), _ctx(amount=1.0),
    )
    assert o.level == DisclosureLevel.REDIRECT


def test_p5_reveal_full(borko_state):
    """T7: trust=60, pressure=3 → REVEAL (fraction=1.0)."""
    o = decide_disclosure(
        borko_state, _TARGET_PLAYER, {"trust": 60.0, "fear": 0.0},
        _item(), _ctx(amount=3.0),
    )
    assert o.level == DisclosureLevel.REVEAL
    assert o.fraction == 1.0


def test_p5_end_to_end_with_p4(harness, borko_state):
    """T8 (сквозной P1→P4→P5): «Спросить Борко про караван» → P4 → item
    → P5(trust=0, P=1) → DENY; P5(trust=60, P=3) → REVEAL."""
    from app.domain.subject_ref import SubjectKind, SubjectRef
    from app.services.input.intent_compressor import IntentCompressor
    from app.services.npc.knowledge_retrieval import retrieve_knowledge

    c = IntentCompressor(llm_client=None)
    f = c._fast_path_parse("Спросить Борко про караван")
    assert f is not None and f.subject_id is not None
    subject = SubjectRef(
        kind=SubjectKind.CANON_TOPIC, subject_id=f.subject_id,
        subject_hint=f.subject_hint,
    )
    items = retrieve_knowledge(borko_state, subject)
    assert len(items) >= 1

    o_low = decide_disclosure(
        borko_state, _TARGET_PLAYER, {"trust": 0.0, "fear": 0.0},
        items[0], _ctx(amount=1.0),
    )
    assert o_low.level == DisclosureLevel.DENY

    o_high = decide_disclosure(
        borko_state, _TARGET_PLAYER, {"trust": 60.0, "fear": 0.0},
        items[0], _ctx(amount=3.0),
    )
    assert o_high.level == DisclosureLevel.REVEAL
