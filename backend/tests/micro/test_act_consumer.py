"""path: /project/backend/tests/micro/test_act_consumer.py

Назначение: Шаг 4 (вердикт Мастера) — замки NPC Act Consumer v0:
    A: SELF_INTRO → EpistemicStore с provenance=player
    B: provenance-восстановление из записи (source_id=player)
    C: challenge → ResponsePlan DOUBT_REGISTERED, Store НЕ мутирован
    D: конкурирующие name-записи без overwrite
    E: multi-act (GREETING+SELF_INTRO) сохраняется
    Граница: challenge НЕ меняет confidence (поправка Мастера).
Зависимости: app.services.npc.act_consumer, app.services.npc.epistemic_store,
    app.domain.epistemology, app.services.npc.belief_revision_engine.
Запуск: cd backend; python -m pytest tests/micro/test_act_consumer.py -v; cd ..
"""


from app.domain.epistemology import ClaimEvent, Predicate, Proposition
from app.services.npc.act_consumer import (
    ActAttitude,
    consume_npc_acts,
    plan_to_cognition_line,
)
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.epistemic_store import EpistemicStore


class _FlatReliability:
    """Детерминированный провайдер надёжности (вне соц-зависимостей)."""

    def get_reliability(self, observer: str, source: str, context=None) -> float:
        return 0.5


def _record_self_intro(store: EpistemicStore, name: str) -> None:
    """Детерминированная запись player.name=X через существующий движок."""
    claim = ClaimEvent(
        event_id=f"evt-selfintro-{name}",
        claim_id=f"claim-selfintro-{name}",
        speaker_id="player",
        listener_id="merchant_goran",
        proposition=Proposition(
            subject_id="player", predicate=Predicate.NAME, object_id=name
        ),
        tick=1,
    )
    engine = BeliefRevisionEngine(reliability_provider=_FlatReliability())
    existing = store.get("merchant_goran")
    record = engine.revise("merchant_goran", claim, existing)
    store.upsert(record)


def _acts(*acts):
    return list(acts)


def test_a_self_intro_creates_claim_with_provenance():
    store = EpistemicStore()
    _record_self_intro(store, "Муму")
    rec = store.get("merchant_goran")
    assert rec is not None
    assert rec.proposition.predicate == Predicate.NAME
    assert rec.proposition.object_id == "Муму"
    assert rec.source_id == "player"  # provenance
    plan = consume_npc_acts(
        "merchant_goran",
        [{"type": "SELF_INTRODUCTION", "params": {"name": "Муму"}}],
        store,
    )
    assert plan.attitude == ActAttitude.FRESH
    assert plan.claimed_name == "Муму"


def test_b_provenance_query_restores_source():
    """RC8: provenance — канонический тип ASK_PROVENANCE, не keyword-детектор."""
    store = EpistemicStore()
    _record_self_intro(store, "Муму")
    plan = consume_npc_acts(
        "merchant_goran",
        [{"type": "ASK_PROVENANCE", "params": {"about": "имя игрока"}}],
        store,
    )
    assert plan.attitude == ActAttitude.PROVENANCE_QUERY
    assert plan.provenance_hint == "player"
    line = plan_to_cognition_line(plan)
    assert "сам игрок" in line


def test_b2_ask_provenance_without_record_stays_provenance():
    """Semantic classification ≠ epistemic relevance: отсутствие записи
    НЕ превращает intent обратно в обычный вопрос."""
    store = EpistemicStore()  # пусто
    plan = consume_npc_acts(
        "merchant_goran",
        [{"type": "ASK_PROVENANCE", "params": {"about": "имя игрока"}}],
        store,
    )
    assert plan.attitude == ActAttitude.PROVENANCE_QUERY
    assert plan.provenance_hint == ""  # адресуемое знание разрешится позже


def test_b3_consumer_does_not_read_topic_words():
    """Regression lock: consumer НЕ извлекает provenance из слов topic.
    QUESTION с любым topic при отсутствии ASK_PROVENANCE-акта — neutral
    (даже с записью в Store и «who told» в topic)."""
    store = EpistemicStore()
    _record_self_intro(store, "Муму")
    plan = consume_npc_acts(
        "merchant_goran",
        [{"type": "QUESTION", "params": {"topic": "learn who told you my name"}}],
        store,
    )
    assert plan.attitude == ActAttitude.NEUTRAL


def test_b4_aa_determinism():
    """A/A: одинаковые входы → идентичные планы (decide_disclosure-прецедент)."""
    store = EpistemicStore()
    _record_self_intro(store, "Муму")
    acts = [{"type": "ASK_PROVENANCE", "params": {"about": "имя"}}]
    p1 = consume_npc_acts("merchant_goran", acts, store)
    p2 = consume_npc_acts("merchant_goran", acts, store)
    assert p1 == p2


def test_c_challenge_registered_without_belief_mutation():
    store = EpistemicStore()
    _record_self_intro(store, "Муму")
    _before = store.get("merchant_goran").confidence
    plan = consume_npc_acts(
        "merchant_goran",
        [{"type": "QUESTION", "params": {"topic": "а если я соврал?"}}],
        store,
    )
    assert plan.attitude == ActAttitude.DOUBT_REGISTERED
    assert plan.challenged_claim_object == "Муму"
    # Поправка Мастера: challenge НЕ мутирует belief.
    assert store.get("merchant_goran").confidence == _before


def test_d_competing_names_no_overwrite():
    store = EpistemicStore()
    _record_self_intro(store, "Муму")
    _record_self_intro(store, "Ворг")
    names = [
        r.proposition.object_id
        for r in store.get_all_for_agent("merchant_goran")
        if r.proposition.predicate == Predicate.NAME
    ]
    assert set(names) == {"Муму", "Ворг"}  # обе записи живут, overwrite нет
    plan = consume_npc_acts(
        "merchant_goran",
        [{"type": "SELF_INTRODUCTION", "params": {"name": "Ворг"}}],
        store,
    )
    assert plan.attitude == ActAttitude.CONFLICTING
    assert plan.claimed_name == "Ворг"


def test_e_multi_acts_preserved():
    store = EpistemicStore()
    plan = consume_npc_acts(
        "merchant_goran",
        [
            {"type": "GREETING", "params": {}},
            {"type": "SELF_INTRODUCTION", "params": {"name": "Муму"}},
        ],
        store,
    )
    assert plan.attitude == ActAttitude.FRESH
    assert plan.claimed_name == "Муму"