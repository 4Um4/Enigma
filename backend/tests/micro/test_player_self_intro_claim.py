"""path: /project/backend/tests/micro/test_player_self_intro_claim.py

Назначение: Consumption v0-замок (вердикт Мастера, α, SELF_INTRODUCTION
    only). PLAYER_SPOKE с payload.semantic_acts → Claim в DialogueSession
    адресата; to_prompt_block содержит имя (доехало до cognition NPC).
    Границы: НЕ global player_name, НЕ TruthState — только claim сессии.
    Идемпотентность: дубль event_id → 1 claim.
Зависимости: app.domain.events, app.services.events.player_speech_act_subscriber,
    app.services.memory.dialogue_session.
Запуск: cd backend; python -m pytest tests/micro/test_player_self_intro_claim.py -v; cd ..
"""

from types import SimpleNamespace

from app.domain.events import EventDTO
from app.services.events.event_types import EventType
from app.services.events.player_speech_act_subscriber import (
    PlayerSpeechActSubscriber,
)
from app.services.memory.dialogue_session import DialogueSession


class _SessionMemory:
    """MemoryManager-контракт (прецедент d8p-теста SessionMemory)."""

    def __init__(self) -> None:
        self._sessions: dict = {}

    def get_dialogue_session(
        self, campaign_id: str, npc_id: str, partner_id: str = "player"
    ) -> DialogueSession:
        key = (campaign_id, npc_id, partner_id)
        if key not in self._sessions:
            self._sessions[key] = DialogueSession(npc_id=npc_id, partner_id=partner_id)
        return self._sessions[key]


def _spoke_event(acts, event_id="evt-1", target_id="merchant_goran"):
    return EventDTO.create(
        event_type=EventType.PLAYER_SPOKE.value,
        source="player",
        payload={
            "target_id": target_id,
            "semantic_acts": acts,
        },
        event_id=event_id,
    )


def test_self_intro_creates_claim_and_reaches_prompt_block():
    mem = _SessionMemory()
    sub = PlayerSpeechActSubscriber(memory_manager=mem, campaign_id_provider=lambda: "T")
    sub.on_player_spoke(
        _spoke_event([{"type": "SELF_INTRODUCTION", "params": {"name": "Мю"}}])
    )
    session = mem.get_dialogue_session("T", "merchant_goran", partner_id="player")
    assert len(session.claims) == 1
    claim = session.claims[0]
    assert claim.speaker == "player"
    assert "Мю" in claim.text
    # Граница вердикта: claim ≠ «NPC знает имя» — формулировка «представился как».
    assert "представился" in claim.text
    # Доехало до cognition-канала: prompt-блок содержит имя.
    assert "Мю" in session.to_prompt_block()


def test_no_self_intro_no_claim():
    mem = _SessionMemory()
    sub = PlayerSpeechActSubscriber(memory_manager=mem, campaign_id_provider=lambda: "T")
    sub.on_player_spoke(
        _spoke_event([{"type": "QUESTION", "params": {"topic": "unspecified"}}])
    )
    session = mem.get_dialogue_session("T", "merchant_goran", partner_id="player")
    assert len(session.claims) == 0


def test_duplicate_event_id_single_claim():
    mem = _SessionMemory()
    sub = PlayerSpeechActSubscriber(memory_manager=mem, campaign_id_provider=lambda: "T")
    sub.on_player_spoke(
        _spoke_event([{"type": "SELF_INTRODUCTION", "params": {"name": "Мю"}}])
    )
    sub.on_player_spoke(
        _spoke_event([{"type": "SELF_INTRODUCTION", "params": {"name": "Мю"}}])
    )  # тот же event_id
    session = mem.get_dialogue_session("T", "merchant_goran", partner_id="player")
    assert len(session.claims) == 1


def test_invalid_name_rejected():
    mem = _SessionMemory()
    sub = PlayerSpeechActSubscriber(memory_manager=mem, campaign_id_provider=lambda: "T")
    sub.on_player_spoke(
        _spoke_event([{"type": "SELF_INTRODUCTION", "params": {"name": "   "}}])
    )
    session = mem.get_dialogue_session("T", "merchant_goran", partner_id="player")
    assert len(session.claims) == 0


def test_no_target_no_claim():
    mem = _SessionMemory()
    sub = PlayerSpeechActSubscriber(memory_manager=mem, campaign_id_provider=lambda: "T")
    sub.on_player_spoke(
        _spoke_event([{"type": "SELF_INTRODUCTION", "params": {"name": "Мю"}}], target_id="")
    )
    assert len(mem._sessions) == 0  # сессия не создана без адресата-актора