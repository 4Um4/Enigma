"""
path: /backend/tests/services/execution/test_dialogue_materializer_p5b.py
Назначение: P5-B3 — интеграционный контракт DialogueMaterializer × PropositionVerifier.

Покрывает Master условия A/B/C/D на уровне материализатора.
"""
from __future__ import annotations

from app.domain.execution import Artifact
from app.services.events.event_types import EventType
from app.services.execution.dialogue_materializer import DialogueMaterializer
from app.services.cognition.proposition_verifier import (
    PassthroughVerifier,
    PropositionVerifier,
)


class _RecordingVerifier:
    def __init__(self, verdict: bool):
        self._verdict = verdict
        self.calls: list[tuple[dict, str]] = []

    def verify(self, proposition: dict, text: str) -> bool:
        self.calls.append((proposition, text))
        return self._verdict


class _RaisingVerifier:
    def __init__(self, exc):
        self._exc = exc
        self.calls: list[tuple[dict, str]] = []

    def verify(self, proposition: dict, text: str) -> bool:
        self.calls.append((proposition, text))
        raise self._exc


class _NeverLLM:
    def complete(self, prompt: str, *, max_tokens: int = 16, timeout: float | None = None) -> str:
        raise AssertionError("LLM не должен вызываться на пустом тексте")


def _make_dialogue_artifact(
    *,
    text: str = "Open_road оскорбил вас, Торнин.",
    proposition=None,
    speaker_id: str = "maid_lusya",
    target_id: str = "tornin",
    exposure: str = "normal",
):
    return Artifact(
        task_id="t-1",
        success=True,
        result_type="dialogue_line",
        data={
            "speaker_id": speaker_id,
            "target_id": target_id,
            "text": text,
            "exposure": exposure,
            "proposition": proposition,
            "topic": "rumor",
            "emotional_state": "concerned",
            "intent_type": "spread_rumor",
        },
    )


PROP = {
    "subject": "Open_road",
    "predicate": "INSULTED",
    "object": "tornin",
    "polarity": True,
}

PROP_NEGATIVE = {
    "subject": "Open_road",
    "predicate": "INSULTED",
    "object": "tornin",
    "polarity": False,
}


def test_confirmed_proposition_emits_both_npc_spoke_and_claim():
    verifier = _RecordingVerifier(verdict=True)
    mat = DialogueMaterializer(proposition_verifier=verifier)

    events = list(mat.materialize(_make_dialogue_artifact(proposition=PROP)))

    event_types = [e.type for e in events]
    assert EventType.NPC_SPOKE.value in event_types
    assert EventType.COMMUNICATION_CLAIM.value in event_types
    assert len(verifier.calls) == 1
    called_prop, called_text = verifier.calls[0]
    assert called_prop == PROP
    assert "Open_road" in called_text


def test_rejected_proposition_emits_only_npc_spoke():
    verifier = _RecordingVerifier(verdict=False)
    mat = DialogueMaterializer(proposition_verifier=verifier)

    events = list(mat.materialize(_make_dialogue_artifact(proposition=PROP)))

    event_types = [e.type for e in events]
    assert EventType.NPC_SPOKE.value in event_types
    assert EventType.COMMUNICATION_CLAIM.value not in event_types
    assert len(verifier.calls) == 1


def test_no_proposition_emits_only_npc_spoke_no_verifier_call():
    verifier = _RecordingVerifier(verdict=True)
    mat = DialogueMaterializer(proposition_verifier=verifier)

    events = list(mat.materialize(_make_dialogue_artifact(proposition=None)))

    event_types = [e.type for e in events]
    assert event_types == [EventType.NPC_SPOKE.value]
    assert verifier.calls == []


def test_empty_text_with_proposition_suppresses_claim():
    verifier = PropositionVerifier(_NeverLLM())
    mat = DialogueMaterializer(proposition_verifier=verifier)

    artifact = _make_dialogue_artifact(text="", proposition=PROP)
    events = list(mat.materialize(artifact))

    event_types = [e.type for e in events]
    assert EventType.NPC_SPOKE.value in event_types
    assert EventType.COMMUNICATION_CLAIM.value not in event_types


def test_no_verifier_production_misconfig_suppresses_claim():
    mat = DialogueMaterializer()

    events = list(mat.materialize(_make_dialogue_artifact(proposition=PROP)))

    event_types = [e.type for e in events]
    assert EventType.NPC_SPOKE.value in event_types
    assert EventType.COMMUNICATION_CLAIM.value not in event_types


def test_no_verifier_with_no_proposition_still_emits_npc_spoke():
    mat = DialogueMaterializer()

    events = list(mat.materialize(_make_dialogue_artifact(proposition=None)))

    event_types = [e.type for e in events]
    assert event_types == [EventType.NPC_SPOKE.value]


def test_verifier_raises_runtime_error_suppresses_claim():
    verifier = _RaisingVerifier(RuntimeError("test-induced failure"))
    mat = DialogueMaterializer(proposition_verifier=verifier)

    events = list(mat.materialize(_make_dialogue_artifact(proposition=PROP)))

    event_types = [e.type for e in events]
    assert EventType.NPC_SPOKE.value in event_types
    assert EventType.COMMUNICATION_CLAIM.value not in event_types
    assert len(verifier.calls) == 1


def test_verifier_raises_timeout_suppresses_claim():
    verifier = _RaisingVerifier(TimeoutError("LLM timed out"))
    mat = DialogueMaterializer(proposition_verifier=verifier)

    events = list(mat.materialize(_make_dialogue_artifact(proposition=PROP)))

    event_types = [e.type for e in events]
    assert EventType.NPC_SPOKE.value in event_types
    assert EventType.COMMUNICATION_CLAIM.value not in event_types


def test_speaker_id_preserved_in_both_events():
    verifier = _RecordingVerifier(verdict=True)
    mat = DialogueMaterializer(proposition_verifier=verifier)

    events = list(mat.materialize(_make_dialogue_artifact(
        proposition=PROP,
        speaker_id="maid_lusya",
        target_id="tornin",
    )))

    npc_spoke = next(e for e in events if e.type == EventType.NPC_SPOKE.value)
    claim = next(e for e in events if e.type == EventType.COMMUNICATION_CLAIM.value)

    assert npc_spoke.source == "maid_lusya"
    assert claim.source == "maid_lusya"
    assert claim.payload["proposition"]["subject"] == "Open_road"


def test_target_id_preserved_in_both_events():
    verifier = _RecordingVerifier(verdict=True)
    mat = DialogueMaterializer(proposition_verifier=verifier)

    events = list(mat.materialize(_make_dialogue_artifact(
        proposition=PROP,
        speaker_id="maid_lusya",
        target_id="tornin",
    )))

    npc_spoke = next(e for e in events if e.type == EventType.NPC_SPOKE.value)
    claim = next(e for e in events if e.type == EventType.COMMUNICATION_CLAIM.value)

    assert npc_spoke.payload["target_id"] == "tornin"
    assert claim.payload["target_id"] == "tornin"


def test_proposition_payload_not_mutated():
    verifier = _RecordingVerifier(verdict=True)
    mat = DialogueMaterializer(proposition_verifier=verifier)

    events = list(mat.materialize(_make_dialogue_artifact(proposition=PROP)))
    claim = next(e for e in events if e.type == EventType.COMMUNICATION_CLAIM.value)
    assert claim.payload["proposition"] == PROP
    assert claim.payload["proposition"]["polarity"] is True

    events = list(mat.materialize(_make_dialogue_artifact(proposition=PROP_NEGATIVE)))
    claim = next(e for e in events if e.type == EventType.COMMUNICATION_CLAIM.value)
    assert claim.payload["proposition"]["polarity"] is False
    assert claim.payload["proposition"]["subject"] == "Open_road"


def test_claim_inherits_visibility_and_radius_from_speech():
    verifier = _RecordingVerifier(verdict=True)
    mat = DialogueMaterializer(proposition_verifier=verifier)

    artifact = Artifact(
        task_id="t-1",
        success=True,
        result_type="dialogue_line",
        data={
            "speaker_id": "maid_lusya",
            "target_id": "tornin",
            "text": "Open_road оскорбил вас, Торнин.",
            "exposure": "whisper",
            "proposition": PROP,
            "topic": "rumor",
            "emotional_state": "concerned",
            "intent_type": "spread_rumor",
        },
    )
    events = list(mat.materialize(artifact))

    claim = next(e for e in events if e.type == EventType.COMMUNICATION_CLAIM.value)
    npc_spoke = next(e for e in events if e.type == EventType.NPC_SPOKE.value)
    assert claim.visibility == npc_spoke.visibility
    assert claim.radius == npc_spoke.radius
    assert claim.visibility == "whisper"


def test_explicit_passthrough_verifier_emits_claim():
    mat = DialogueMaterializer(proposition_verifier=PassthroughVerifier())

    events = list(mat.materialize(_make_dialogue_artifact(proposition=PROP)))

    event_types = [e.type for e in events]
    assert EventType.NPC_SPOKE.value in event_types
    assert EventType.COMMUNICATION_CLAIM.value in event_types


def test_npc_spoke_payload_does_not_contain_proposition():
    verifier = _RecordingVerifier(verdict=True)
    mat = DialogueMaterializer(proposition_verifier=verifier)

    events = list(mat.materialize(_make_dialogue_artifact(proposition=PROP)))

    npc_spoke = next(e for e in events if e.type == EventType.NPC_SPOKE.value)
    assert "proposition" not in npc_spoke.payload
    assert "text" in npc_spoke.payload
    assert npc_spoke.payload["text"] == "Open_road оскорбил вас, Торнин."
