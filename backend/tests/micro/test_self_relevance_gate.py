# path: /project/backend/tests/micro/test_self_relevance_gate.py
# Назначение: Замок GC-RELEVANCE-01 (S258) — self-relevance канал эпистемики.
#             Клейм с subject == слушателю обязан: попадать в claims_about_self,
#             НЕ попадать в perceived_threats/violations/trigger_proposition
#             (баг S258-пробы: агент попадал в собственные угрозы и мог навести
#             warn на самого себя), давать talk-модификатор вместо warn/attack.
#             Клейм о третьем лице — прежнее поведение байт-в-байт (легаси S198/S211).
# Зависимости: app.domain.epistemology, belief_revision_engine, epistemic_context_resolver, decision_hub
# Основные сущности: _reliability_stub, _store_spy, GC-RELEVANCE-01 тест-кейсы

"""GC-RELEVANCE-01: self-relevance замок.

Проб сессии S258 (до фикса):
    perceived_threats = ('maid_lusya', 'thief_shadow')  # агент — своя угроза
    violations = 2                                       # обвинение себе = нарушение

После фикса:
    self-клейм → claims_about_self + talk-модификатор;
    third-party-клейм → perceived_threats + warn/attack (легаси нетронут).
"""

import pytest
from app.domain.epistemology import (
    ClaimEvent,
    EpistemicRecord,
    Predicate,
    Proposition,
)
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver

_RELIABILITY = 0.8


class _ReliabilityStub:
    """Фиксированная надёжность: изолирует тест от trust-математики S199."""

    def get_reliability(self, observer: str, source: str, context=None) -> float:
        return _RELIABILITY


class _StoreSpy:
    """Шпион под производственный контракт EpistemicStore.get_all_for_agent."""

    def __init__(self, records):
        self._records = records

    def get_all_for_agent(self, agent_id: str):
        return self._records


def _make_claim(subject_id: str, listener_id: str = "maid_lusya") -> ClaimEvent:
    prop = Proposition(
        subject_id=subject_id, predicate=Predicate.STOLE, object_id="gold"
    )
    return ClaimEvent(
        event_id=f"e-{subject_id}",
        claim_id=f"c-{subject_id}",
        speaker_id="merchant_goran",
        listener_id=listener_id,
        proposition=prop,
        tick=5,
    )


def _resolve_for(records, agent_id="maid_lusya"):
    engine = BeliefRevisionEngine(_ReliabilityStub())
    recs = [engine.revise(agent_id, claim, None) for claim in records]
    return EpistemicContextResolver(_StoreSpy(recs)).resolve(agent_id)


# ── R1: развязка каналов разрешения контекста ──────────────────────────────


def test_self_claim_routed_to_about_self_channel():
    ctx = _resolve_for([_make_claim("maid_lusya")])
    assert len(ctx.claims_about_self) == 1
    assert ctx.claims_about_self[0].subject_id == "maid_lusya"
    # confidence = reliability × _CLAIM_WEIGHT (=1.0, belief_revision_engine);
    # проверено живым пробом S258: 0.8 при reliability 0.8
    assert ctx.max_self_confidence == pytest.approx(_RELIABILITY)


def test_self_claim_excluded_from_own_threats_and_violations():
    ctx = _resolve_for([_make_claim("maid_lusya")])
    assert ctx.perceived_threats.count("maid_lusya") == 0
    assert ctx.perceived_threats == ()
    assert ctx.perceived_violations == 0


def test_self_claim_not_trigger_proposition():
    # Epistemic Targeting (DecisionHub S197) целился бы warn-ом в subject_id:
    # self-клейм не имеет права становиться триггером — самонаведение запрещено.
    ctx = _resolve_for([_make_claim("maid_lusya")])
    assert ctx.trigger_proposition is None


def test_third_party_claim_legacy_behavior_untouched():
    ctx = _resolve_for([_make_claim("thief_shadow")])
    assert ctx.perceived_threats == ("thief_shadow",)
    assert ctx.perceived_violations == 1
    assert ctx.claims_about_self == ()
    assert ctx.max_self_confidence == 0.0
    assert ctx.trigger_proposition is not None
    assert ctx.trigger_proposition.subject_id == "thief_shadow"


def test_mixed_claims_channels_independent():
    ctx = _resolve_for([_make_claim("maid_lusya"), _make_claim("thief_shadow")])
    assert ctx.perceived_threats == ("thief_shadow",)
    assert len(ctx.claims_about_self) == 1
    assert ctx.perceived_violations == 1
    # Легаси-канал триггера держит третье лицо, не агента
    assert ctx.trigger_proposition.subject_id == "thief_shadow"


# ── R2: модификаторная развязка ────────────────────────────────────────────


def test_self_claim_yields_talk_modifier_only():
    ctx = _resolve_for([_make_claim("maid_lusya")])
    mods = EpistemicContextResolver.to_modifiers(ctx)
    assert "talk" in mods
    assert mods["talk"] > 0.0
    # Каналы развязаны: никакой агрессии/предупреждения от клейма о себе
    assert "warn" not in mods
    assert "attack" not in mods


def test_third_party_claim_yields_no_talk_modifier():
    ctx = _resolve_for([_make_claim("thief_shadow")])
    mods = EpistemicContextResolver.to_modifiers(ctx)
    assert "talk" not in mods
    assert "warn" in mods and "attack" in mods  # легаси S198 жив


def test_empty_context_neutral():
    ctx = _resolve_for([])
    mods = EpistemicContextResolver.to_modifiers(ctx)
    assert mods == {}


def test_self_modifier_survives_apply_modifiers():
    # Ключ обязан совпадать со словарём scores (Intent.TALK.value = "talk"):
    # apply_modifiers молча бросает чужой ключ (decision_hub:401) — канал
    # не имеет права родиться мёртвым.
    from app.services.npc.decision_hub import DecisionHub

    ctx = _resolve_for([_make_claim("maid_lusya")])
    mods = EpistemicContextResolver.to_modifiers(ctx)
    base_scores = {"talk": 1.0, "observe": 0.5}
    merged = DecisionHub.apply_modifiers(base_scores, epistemic_modifiers=mods)
    assert merged["talk"] == pytest.approx(1.0 + mods["talk"])
    # Чистота Modifier Contract: вход не мутирован
    assert base_scores == {"talk": 1.0, "observe": 0.5}


# ── GATE-TRIGGER-01: predicate-фильтр trigger_proposition (баг №2) ─────────
# Гео-запись (EXITS_TO, subject = узел графа) хранится в store легитимно,
# но не имеет права становиться WARN-целью S197-таргетинга: can_address
# не различает NPC и узел графа — резать обязано на уровне резолвера.
# Записи создаются напрямую (образец EpistemicStore.from_dict) — это
# payload-форма реального runtime-канала exploration (tick_orchestrator:874).


def _geo_record(agent_id: str = "maid_lusya") -> EpistemicRecord:
    # Легитимная гео-запись эксплорации: «tavern:exit_east ведёт в city_gate»
    return EpistemicRecord(
        agent_id=agent_id,
        proposition=Proposition(
            subject_id="tavern:exit_east",
            predicate=Predicate.EXITS_TO,
            object_id="city_gate",
        ),
        confidence=0.9,
        source_id="exploration_target_resolver",
        source_claim_id="geo-1",
        first_observed_tick=10,
        last_updated_tick=10,
    )


def test_geo_exits_to_never_trigger_proposition():
    # Ядро фикса: дверь — не угроза, не цель WARN (шторм ~60/мин пресечён
    # на источнике, раунды 2-4 приёмки).
    ctx = EpistemicContextResolver(_StoreSpy([_geo_record()])).resolve("maid_lusya")
    assert ctx.trigger_proposition is None
    # Гео-запись не попадает и в угрози (страховочный ассерт того же контракта)
    assert ctx.perceived_threats == ()


def test_helped_higher_conf_does_not_steal_threat_trigger():
    # Развязка трекеров: HELPED conf=0.9 шёл раньше STOLE conf=0.7 —
    # старый код (условие на max_conf) терял триггер угрозы вовсе.
    helped = EpistemicRecord(
        agent_id="maid_lusya",
        proposition=Proposition(
            subject_id="merchant_goran",
            predicate=Predicate.HELPED,
            object_id="gold",
        ),
        confidence=0.9,
        source_id="tavern_keeper_tornin",
        source_claim_id="c-helped",
        first_observed_tick=10,
        last_updated_tick=10,
    )
    stole = EpistemicRecord(
        agent_id="maid_lusya",
        proposition=Proposition(
            subject_id="thief_shadow",
            predicate=Predicate.STOLE,
            object_id="gold",
        ),
        confidence=0.7,
        source_id="merchant_goran",
        source_claim_id="c-stole",
        first_observed_tick=11,
        last_updated_tick=11,
    )
    ctx = EpistemicContextResolver(_StoreSpy([helped, stole])).resolve("maid_lusya")
    # Триггер — угроза, не союзник
    assert ctx.trigger_proposition is not None
    assert ctx.trigger_proposition.subject_id == "thief_shadow"
    assert ctx.trigger_proposition.predicate == Predicate.STOLE
    # max_confidence НЕ тронут фильтром (питает to_modifiers): 0.9 от HELPED
    assert ctx.max_confidence == pytest.approx(0.9)


def test_threat_predicates_legacy_trigger_untouched():
    # STOLE и ATTACKED — прежнее поведение (условие Мастера).
    att = EpistemicRecord(
        agent_id="maid_lusya",
        proposition=Proposition(
            subject_id="guard_borko",
            predicate=Predicate.ATTACKED,
            object_id="maid_lusya",
        ),
        confidence=0.8,
        source_id="blacksmith_orm",
        source_claim_id="c-att",
        first_observed_tick=12,
        last_updated_tick=12,
    )
    ctx = EpistemicContextResolver(_StoreSpy([att])).resolve("maid_lusya")
    assert ctx.trigger_proposition is not None
    assert ctx.trigger_proposition.subject_id == "guard_borko"
    assert ctx.trigger_proposition.predicate == Predicate.ATTACKED