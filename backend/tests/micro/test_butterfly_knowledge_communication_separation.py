"""
B4-R14: Knowledge / Communication Separation test.

Проверяет, что Proposition из EpistemicContext переносится в CommunicationIntent
ТОЛЬКО для claim-producing интентов (spread_rumor, warn, intimidate, report,
threaten). Non-claim интенты (talk, trade, offer_job, request_service,
call_for_help) не получают Proposition автоматически.

Запуск: cd backend; python -m pytest tests/micro/test_butterfly_knowledge_communication_separation.py -v
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock

import pytest

from app.domain.epistemology import EpistemicContext, Predicate, Proposition
from app.domain.intent_profiles import produces_claim
from app.services.npc.decision_hub import DecisionHub


def _make_proposition(predicate: Predicate = Predicate.ATTACKED,
                       subject_id: str = "player",
                       object_id: str = "merchant_goran") -> Proposition:
    return Proposition(
        subject_id=subject_id,
        predicate=predicate,
        object_id=object_id,
        polarity=True,
    )


def _make_epistemic_context(
    trigger_prop: Optional[Proposition] = None,
    report_prop: Optional[Proposition] = None,
    claims_about_self: tuple = (),
) -> EpistemicContext:
    return EpistemicContext(
        agent_id="guard_borko",
        perceived_threats=("player",) if trigger_prop else (),
        perceived_allies=(),
        perceived_violations=1 if trigger_prop else 0,
        max_confidence=0.8 if trigger_prop else 0.0,
        trigger_proposition=trigger_prop,
        claims_about_self=claims_about_self,
        max_self_confidence=0.0,
        report_proposition=report_prop,
    )


def _make_decision_hub() -> DecisionHub:
    """Создаёт DecisionHub с mock RNG."""
    from app.services.npc.kernel_rng import KernelRNG
    rng = KernelRNG(tick=1, npc_id="test", salt="test")
    return DecisionHub(rng=rng)


class TestKnowledgeCommunicationSeparation:
    """B4-R14: Развязка Knowledge и Communication."""

    def setup_method(self):
        self.hub = _make_decision_hub()
        self.trigger_prop = _make_proposition(
            predicate=Predicate.ATTACKED,
            subject_id="player",
            object_id="guard_borko",
        )
        self.report_prop = _make_proposition(
            predicate=Predicate.INSULTED,
            subject_id="player",
            object_id="tavern_keeper_tornin",
        )
        self.self_claim_prop = _make_proposition(
            predicate=Predicate.INSULTED,
            subject_id="player",
            object_id="guard_borko",
        )
        self.epistemic_ctx = _make_epistemic_context(
            trigger_prop=self.trigger_prop,
            report_prop=self.report_prop,
            claims_about_self=(self.self_claim_prop,),
        )

    def test_talk_no_proposition(self):
        """1. talk + trigger_proposition -> proposition отсутствует."""
        intent = self.hub._build_communication(
            npc_id="guard_borko",
            intent_value="talk",
            intent_target="merchant_goran",
            topic="торговля",
            emotion_value="нейтрально",
            epistemic_context=self.epistemic_ctx,
        )
        assert intent is not None, "CommunicationIntent должен быть создан"
        assert intent.proposition is None, (
            f"talk intent не должен нести Proposition, но получил: {intent.proposition}"
        )

    def test_trade_no_proposition(self):
        """2. trade + trigger_proposition -> proposition отсутствует."""
        intent = self.hub._build_communication(
            npc_id="guard_borko",
            intent_value="trade",
            intent_target="merchant_goran",
            topic="торговля",
            emotion_value="нейтрально",
            epistemic_context=self.epistemic_ctx,
        )
        assert intent is not None
        assert intent.proposition is None, (
            f"trade intent не должен нести Proposition, но получил: {intent.proposition}"
        )

    def test_spread_rumor_keeps_trigger_proposition(self):
        """3. spread_rumor + trigger_proposition -> proposition сохранён."""
        intent = self.hub._build_communication(
            npc_id="guard_borko",
            intent_value="spread_rumor",
            intent_target="merchant_goran",
            topic="слухи",
            emotion_value="беспокойство",
            epistemic_context=self.epistemic_ctx,
        )
        assert intent is not None
        assert intent.proposition is not None, (
            "spread_rumor должен нести Proposition (produces_claim=True)"
        )
        assert intent.proposition == self.trigger_prop, (
            f"Ожидался trigger_proposition, получен: {intent.proposition}"
        )

    def test_spread_rumor_stage_b_fallback_preserved(self):
        """4. spread_rumor + claims_about_self/INSULTED -> Stage B fallback сохранён."""
        ctx_self_only = _make_epistemic_context(
            trigger_prop=None,
            report_prop=None,
            claims_about_self=(self.self_claim_prop,),
        )
        intent = self.hub._build_communication(
            npc_id="guard_borko",
            intent_value="spread_rumor",
            intent_target="merchant_goran",
            topic="слухи",
            emotion_value="беспокойство",
            epistemic_context=ctx_self_only,
        )
        assert intent is not None
        assert intent.proposition is not None, (
            "spread_rumor + Stage B fallback должен найти proposition из claims_about_self"
        )
        assert intent.proposition.predicate == Predicate.INSULTED, (
            f"Stage B fallback должен выбрать INSULTED, получен: {intent.proposition.predicate}"
        )

    def test_warn_keeps_proposition(self):
        """5. warn + trigger_proposition -> Proposition сохранён."""
        intent = self.hub._build_communication(
            npc_id="guard_borko",
            intent_value="warn",
            intent_target="player",
            topic="угроза",
            emotion_value="гнев",
            epistemic_context=self.epistemic_ctx,
        )
        assert intent is not None
        assert intent.proposition is not None, (
            "warn должен нести Proposition (produces_claim=True)"
        )

    def test_unknown_intent_no_proposition(self):
        """6. неизвестный intent -> Proposition отсутствует."""
        intent = self.hub._build_communication(
            npc_id="guard_borko",
            intent_value="unknown_intent",
            intent_target="merchant_goran",
            topic="?",
            emotion_value="?",
            epistemic_context=self.epistemic_ctx,
        )
        assert intent is None, (
            "Неизвестный intent не должен создавать CommunicationIntent"
        )

    def test_epistemic_context_not_mutated(self):
        """7. Отсутствие Proposition в CommunicationIntent не удаляет
        и не изменяет исходное убеждение в EpistemicContext."""
        ctx_before = _make_epistemic_context(
            trigger_prop=self.trigger_prop,
            report_prop=self.report_prop,
            claims_about_self=(self.self_claim_prop,),
        )
        self.hub._build_communication(
            npc_id="guard_borko",
            intent_value="talk",
            intent_target="merchant_goran",
            topic="торговля",
            emotion_value="нейтрально",
            epistemic_context=ctx_before,
        )
        assert ctx_before.trigger_proposition == self.trigger_prop, (
            "trigger_proposition не должен быть изменён"
        )
        assert ctx_before.report_proposition == self.report_prop, (
            "report_proposition не должен быть изменён"
        )
        assert len(ctx_before.claims_about_self) == 1, (
            "claims_about_self не должен быть изменён"
        )
        assert ctx_before.claims_about_self[0] == self.self_claim_prop, (
            "claims_about_self[0] не должен быть изменён"
        )
