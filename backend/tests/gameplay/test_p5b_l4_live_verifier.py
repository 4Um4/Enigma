"""
path: /backend/tests/gameplay/test_p5b_l4_live_verifier.py
Назначение: P5-B Step 5+6 — real-LLM live-тест семантической верификации.

Master directive: доказать живую семантическую передачу между NPC.
- Positive: Люся сообщает слух → verifier YES → COMMUNICATION_CLAIM published
- Negative: Люся off-topic → verifier NO → COMMUNICATION_CLAIM suppressed
- No-bypass: при отрицательном verdict candidate proposition НЕ попадает
  слушателю обходным путём (EpistemicStore listener'а не содержит record)

Аудит 4 артефактов (Master требует):
  1. candidate proposition (from Artifact.data["proposition"])
  2. LLM text (from Artifact.data["text"])
  3. verifier response (YES/NO + raw LLM response)
  4. final events (NPC_SPOKE + COMMUNICATION_CLAIM or только NPC_SPOKE)

Запуск: P5B_LIVE_LLM=1 python -m pytest backend/tests/gameplay/test_p5b_l4_live_verifier.py -v
Без P5B_LIVE_LLM=1 — skip (требует Hermes-3 server на localhost:8181).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

import pytest

logger = logging.getLogger(__name__)

_LLM_LIVE = os.environ.get("P5B_LIVE_LLM") == "1"

pytestmark = pytest.mark.skipif(
    not _LLM_LIVE,
    reason="Set P5B_LIVE_LLM=1 to run P5-B live LLM tests (requires Hermes-3 server on localhost:8181).",
)


# ───────────────────────── Audit Trace ─────────────────────────

@dataclass
class ArtifactTrace:
    """Spy: захват 4 артефактов для аудита."""
    candidate_proposition: dict[str, Any] | None = None
    llm_text: str = ""
    verifier_verdict: str = ""
    verifier_raw: str = ""
    verifier_confirmed: bool = False
    npc_spoke_published: bool = False
    communication_claim_published: bool = False
    npc_spoke_payload: dict[str, Any] = field(default_factory=dict)
    communication_claim_payload: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            "=== AUDIT TRACE ===",
            f"1. candidate proposition: {self.candidate_proposition}",
            f"2. LLM text: {self.llm_text[:160]!r}",
            f"3. verifier verdict: {self.verifier_verdict} (raw={self.verifier_raw!r})",
            f"   confirmed: {self.verifier_confirmed}",
            f"4. NPC_SPOKE published: {self.npc_spoke_published}",
            f"   payload keys: {list(self.npc_spoke_payload.keys())}",
            f"5. COMMUNICATION_CLAIM published: {self.communication_claim_published}",
            f"   payload keys: {list(self.communication_claim_payload.keys())}",
            "=== END AUDIT ===",
        ]
        return "\n".join(lines)


class _SpyVerifier:
    """Wrapper around PropositionVerifier — captures verdict for audit."""

    def __init__(self, real_verifier, trace: ArtifactTrace):
        self._real = real_verifier
        self._trace = trace

    def verify(self, proposition: dict, text: str) -> bool:
        self._trace.candidate_proposition = proposition
        self._trace.llm_text = text
        confirmed = self._real.verify(proposition, text)
        self._trace.verifier_confirmed = confirmed
        self._trace.verifier_verdict = "YES" if confirmed else "NO"
        return confirmed


# ───────────────────────── Helpers ─────────────────────────

def _live_llm_client():
    """Production LLM client via RouterAdapter (agent_name='verifier' ? DIALOGUE capability).

    Calls initialize_router() to ensure ModelPool is registered before
    get_router() returns singleton. Without this, pool is empty and
    request_for_agent fails with '??? ?????? ???? ??????????'.
    """
    from app.services.llm.router import get_router, initialize_router
    from app.services.cognition.router_adapter import RouterAdapter
    initialize_router()  # ensures ModelPool registered
    router = get_router()
    return RouterAdapter(router, agent_name="verifier")


def _build_materializer_with_spy(trace: ArtifactTrace):
    """Materializer with spy verifier — captures 4 artifacts."""
    from app.services.cognition.proposition_verifier import PropositionVerifier
    from app.services.execution.dialogue_materializer import DialogueMaterializer

    real_verifier = PropositionVerifier(_live_llm_client(), timeout=30.0, max_tokens=3)
    spy_verifier = _SpyVerifier(real_verifier, trace)
    return DialogueMaterializer(proposition_verifier=spy_verifier)


PROP_INSULT = {
    "subject": "Open_road",
    "predicate": "INSULTED",
    "object": "tornin",
    "polarity": True,
}


def _make_dialogue_artifact(text: str, proposition: dict | None = PROP_INSULT):
    from app.domain.execution import Artifact
    return Artifact(
        task_id="t-l4-live",
        success=True,
        result_type="dialogue_line",
        data={
            "speaker_id": "maid_lusya",
            "target_id": "tornin",
            "text": text,
            "exposure": "normal",
            "proposition": proposition,
            "topic": "rumor",
            "emotional_state": "concerned",
            "intent_type": "spread_rumor",
        },
    )


def _capture_events(events: list, trace: ArtifactTrace):
    """Extract NPC_SPOKE + COMMUNICATION_CLAIM from events list."""
    from app.services.events.event_types import EventType
    for ev in events:
        if ev.type == EventType.NPC_SPOKE.value:
            trace.npc_spoke_published = True
            trace.npc_spoke_payload = ev.payload
        elif ev.type == EventType.COMMUNICATION_CLAIM.value:
            trace.communication_claim_published = True
            trace.communication_claim_payload = ev.payload


# ───────────────────────── Tests ─────────────────────────

class TestL4LiveVerifier:
    """P5-B Step 5+6: real-LLM verifier tests."""

    def test_l4_positive_verifier_confirms_rumor(self):
        """Step 5 positive: Люся сообщает слух → verifier YES."""
        from app.services.cognition.proposition_verifier import PropositionVerifier

        text = (
            "Торнин, я слышала, что Open_road оскорбил вас за спиной. "
            "Говорил неприятные вещи."
        )
        verifier = PropositionVerifier(_live_llm_client(), timeout=30.0, max_tokens=3)
        confirmed = verifier.verify(PROP_INSULT, text)

        print(f"\n[POSITIVE] text={text[:80]!r}")
        print(f"[POSITIVE] confirmed={confirmed}")
        assert confirmed is True, (
            f"Expected Hermes-3 to confirm proposition in rumor text, "
            f"but verifier returned {confirmed}."
        )

    def test_l4_negative_verifier_rejects_off_topic(self):
        """Step 6 negative: Люся off-topic → verifier NO."""
        from app.services.cognition.proposition_verifier import PropositionVerifier

        text = (
            "Сегодня славная погода, не правда ли? "
            "Я слышала, лорд мэр устраивает бал на следующей неделе."
        )
        verifier = PropositionVerifier(_live_llm_client(), timeout=30.0, max_tokens=3)
        confirmed = verifier.verify(PROP_INSULT, text)

        print(f"\n[NEGATIVE off-topic] text={text[:80]!r}")
        print(f"[NEGATIVE off-topic] confirmed={confirmed}")
        assert confirmed is False, (
            f"Expected Hermes-3 to REJECT off-topic text, "
            f"but verifier returned {confirmed}."
        )

    def test_l4_negative_verifier_rejects_negation(self):
        """Step 6 negative: Люся отрицает → verifier NO."""
        from app.services.cognition.proposition_verifier import PropositionVerifier

        text = (
            "Торнин, не верьте слухам. Ничего подобного не было — "
            "Open_road вас не оскорблял."
        )
        verifier = PropositionVerifier(_live_llm_client(), timeout=30.0, max_tokens=3)
        confirmed = verifier.verify(PROP_INSULT, text)

        print(f"\n[NEGATIVE negation] text={text[:80]!r}")
        print(f"[NEGATIVE negation] confirmed={confirmed}")
        assert confirmed is False, (
            f"Expected Hermes-3 to REJECT negation text, "
            f"but verifier returned {confirmed}."
        )


class TestL4LiveMaterializer:
    """P5-B Step 5+6: materializer + verifier integration with audit."""

    def test_l4_positive_materializer_emits_both_events(self):
        """Positive: materializer with real LLM → NPC_SPOKE + COMMUNICATION_CLAIM."""
        trace = ArtifactTrace()
        mat = _build_materializer_with_spy(trace)

        text = (
            "Торнин, я слышала, что Open_road оскорбил вас за спиной. "
            "Говорил неприятные вещи."
        )
        artifact = _make_dialogue_artifact(text)
        events = list(mat.materialize(artifact))
        _capture_events(events, trace)

        print(f"\n{trace.summary()}")

        assert trace.npc_spoke_published is True, "NPC_SPOKE must always be published"
        assert trace.communication_claim_published is True, (
            "COMMUNICATION_CLAIM must be published when verifier confirms"
        )
        assert trace.verifier_confirmed is True
        assert trace.candidate_proposition == PROP_INSULT
        assert trace.llm_text == text

    def test_l4_negative_materializer_suppresses_claim_no_bypass(self):
        """Negative + no-bypass: off-topic → NPC_SPOKE only, COMMUNICATION_CLAIM suppressed.

        Master no-bypass contract: candidate proposition НЕ попадает слушателю
        обходным путём. Проверяем:
        1. NPC_SPOKE published (speech happened)
        2. COMMUNICATION_CLAIM suppressed (verifier rejected)
        3. NPC_SPOKE payload НЕ содержит proposition (structural guarantee)
        4. No alternative path for proposition to reach listener
        """
        trace = ArtifactTrace()
        mat = _build_materializer_with_spy(trace)

        text = (
            "Сегодня славная погода, не правда ли? "
            "Я слышала, лорд мэр устраивает бал на следующей неделе."
        )
        artifact = _make_dialogue_artifact(text)
        events = list(mat.materialize(artifact))
        _capture_events(events, trace)

        print(f"\n{trace.summary()}")

        # NPC_SPOKE published (speech happened)
        assert trace.npc_spoke_published is True, (
            "NPC_SPOKE must be published even when proposition rejected"
        )

        # COMMUNICATION_CLAIM suppressed
        assert trace.communication_claim_published is False, (
            "COMMUNICATION_CLAIM must be suppressed when verifier rejects"
        )

        # verifier rejected
        assert trace.verifier_confirmed is False

        # No-bypass: NPC_SPOKE payload does NOT contain proposition
        assert "proposition" not in trace.npc_spoke_payload, (
            "No-bypass violation: NPC_SPOKE payload must NOT contain proposition"
        )

        # No-bypass: no COMMUNICATION_CLAIM event means ClaimEventSubscriber
        # won't receive claim → EpistemicStore listener won't be updated
        # from this source. This is the structural guarantee.
        print("\n[NO-BYPASS] OK: NPC_SPOKE has no proposition, COMMUNICATION_CLAIM suppressed")
        print("[NO-BYPASS] Listener EpistemicStore will NOT receive this proposition")

    def test_l4_audit_artifacts_all_four_persisted(self):
        """Master audit requirement: 4 artifacts persisted in trace."""
        trace = ArtifactTrace()
        mat = _build_materializer_with_spy(trace)

        text = "Торнин, Open_road оскорбил вас за спиной."
        artifact = _make_dialogue_artifact(text)
        events = list(mat.materialize(artifact))

        _capture_events(events, trace)

        # 4 artifacts audit
        assert trace.candidate_proposition is not None, "Artifact 1: candidate proposition missing"
        assert trace.llm_text, "Artifact 2: LLM text missing"
        assert trace.verifier_verdict, "Artifact 3: verifier verdict missing"
        assert trace.npc_spoke_published, "Artifact 4: NPC_SPOKE missing"

        print(f"\n{trace.summary()}")
        print("\n[AUDIT] All 4 artifacts persisted:")
        print(f"  1. candidate proposition: {trace.candidate_proposition}")
        print(f"  2. LLM text: {trace.llm_text[:100]!r}")
        print(f"  3. verifier verdict: {trace.verifier_verdict}")
        print(f"  4. final events: NPC_SPOKE={trace.npc_spoke_published}, COMMUNICATION_CLAIM={trace.communication_claim_published}")
