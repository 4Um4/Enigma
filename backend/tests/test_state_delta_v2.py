# -*- coding: utf-8 -*-
"""
path: backend/tests/test_state_delta_v2.py
Назначение: Тесты контракта StateDeltas v2 (Domain-Tagged Typed Payloads).
Зависимости: pytest, app.models.state_delta, app.models.delta_payloads
Основные сущности: TestDeltaDomainValidation, TestDeltaPayloadExtraction

Запускать: pytest backend/tests/test_state_delta_v2.py
"""

import pytest
from app.models.delta_payloads import (
    EmotionPayload,
    IdentityPayload,
    ReputationPayload,
    SocialPayload,
)
from app.models.state_delta import DeltaDomain, StateDeltas


class TestDeltaDomainValidation:
    """Проверяет __post_init__ валидацию: payload соответствует domain."""

    def test_social_payload_with_social_domain_valid(self):
        delta = StateDeltas(
            npc_id="1", domain=DeltaDomain.SOCIAL, target="player", payload=SocialPayload(trust_delta=10.0)
        )
        assert delta.domain == DeltaDomain.SOCIAL
        assert delta.payload.trust_delta == 10.0

    def test_emotion_payload_with_emotion_domain_valid(self):
        delta = StateDeltas(npc_id="1", domain=DeltaDomain.EMOTION, payload=EmotionPayload(stress_delta=-5.0))
        assert delta.domain == DeltaDomain.EMOTION
        assert delta.payload.stress_delta == -5.0

    def test_reputation_payload_with_reputation_domain_valid(self):
        delta = StateDeltas(
            npc_id="1",
            domain=DeltaDomain.REPUTATION,
            target="faction_1",
            payload=ReputationPayload(reputation_delta=0.05),
        )
        assert delta.domain == DeltaDomain.REPUTATION
        assert delta.payload.reputation_delta == 0.05

    def test_identity_payload_with_identity_domain_valid(self):
        delta = StateDeltas(
            npc_id="1", domain=DeltaDomain.IDENTITY, payload=IdentityPayload(identity_integrity_delta=-0.1)
        )
        assert delta.domain == DeltaDomain.IDENTITY
        assert delta.payload.identity_integrity_delta == -0.1

    def test_payload_mismatch_raises_type_error(self):
        """EMOTION domain + Social payload → TypeError."""
        with pytest.raises(TypeError, match="domain emotion требует EmotionPayload"):
            StateDeltas(npc_id="1", domain=DeltaDomain.EMOTION, payload=SocialPayload(trust_delta=10.0))

    def test_social_payload_with_emotion_domain_raises_type_error(self):
        """SOCIAL domain + Emotion payload → TypeError."""
        with pytest.raises(TypeError, match="domain social требует SocialPayload"):
            StateDeltas(
                npc_id="1", domain=DeltaDomain.SOCIAL, target="player", payload=EmotionPayload(stress_delta=5.0)
            )


class TestDeltaV1V2Coexistence:
    """Проверяет, что v1 и v2 поля могут сосуществовать для обратной совместимости."""

    def test_v1_fields_populated_alongside_v2(self):
        """Producer заполняет обе версии для безопасной миграции Consumer."""
        delta = StateDeltas(
            npc_id="1",
            # v1
            trust_delta=10.0,
            social_target="player",
            # v2
            domain=DeltaDomain.SOCIAL,
            target="player",
            payload=SocialPayload(trust_delta=10.0),
        )
        # StateApplicator может читать из v1 или v2
        assert delta.trust_delta == 10.0
        assert delta.payload.trust_delta == 10.0

    def test_v1_fallback_when_domain_is_none(self):
        """Если domain не указан (легаси Producer), работает v1 логика."""
        delta = StateDeltas(npc_id="1", stress_delta=15.0, source="decision_hub")
        assert delta.domain is None
        assert delta.payload is None
        assert delta.stress_delta == 15.0


class TestDeltaPayloadFrozen:
    """Проверяет, что payload'ы неизменяемы (frozen dataclasses)."""

    def test_social_payload_frozen(self):
        payload = SocialPayload(trust_delta=10.0)
        with pytest.raises(AttributeError):
            payload.trust_delta = 20.0

    def test_emotion_payload_frozen(self):
        payload = EmotionPayload(stress_delta=5.0)
        with pytest.raises(AttributeError):
            payload.stress_delta = 10.0
