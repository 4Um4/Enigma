"""DLG-GC-01 — Speaker Symmetry (§9.3i, трек §3.6 DLG-L1).

Одна и та же реплика от PLAYER и NPC → идентичная семантическая разборка
mod provenance. NpcSpeechActSubscriber — симметричный PlayerSpeechActSubscriber
для SELF_INTRODUCTION. Без LLM. Идемпотентность по event_id (Claim Bridge).
"""
from __future__ import annotations

import pytest

from app.domain.events import EventDTO
from app.services.events.event_types import EventType
from app.services.events.npc_speech_act_subscriber import NpcSpeechActSubscriber
from app.services.events.player_speech_act_subscriber import PlayerSpeechActSubscriber
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


def _spoke_event(
    acts: list,
    event_id: str,
    target_id: str | None,
    event_type: str,
    source: str,
) -> EventDTO:
    payload: dict = {"semantic_acts": acts}
    if target_id is not None:
        payload["target_id"] = target_id
    return EventDTO.create(
        event_type=event_type,
        source=source,
        payload=payload,
        event_id=event_id,
    )


# ── DLG-GC-01: 7 + 2 теста ─────────────────────────────────────────────────

def test_case1_npc_self_intro_creates_claim_in_listener_session():
    """NPC SELF_INTRODUCTION → Claim в session(listener, partner=speaker)."""
    mem = _SessionMemory()
    sub = NpcSpeechActSubscriber(memory_manager=mem, campaign_id_provider=lambda: "T",
                                 tick_provider=lambda: 5)
    sub.on_npc_spoke(_spoke_event(
        acts=[{"type": "SELF_INTRODUCTION", "params": {"name": "Горан"}}],
        event_id="evt-dlg1-1",
        target_id="merchant_goran",
        event_type=EventType.NPC_SPOKE.value,
        source="tavern_keeper_tornin",
    ))
    # Сессия listener (Tornin), partner=speaker (Goran)
    session = mem.get_dialogue_session("T", "merchant_goran", partner_id="tavern_keeper_tornin")
    assert len(session.claims) == 1
    assert session.claims[0].speaker == "tavern_keeper_tornin"
    assert "Горан" in session.claims[0].text
    assert session.claims[0].event_id == "evt-dlg1-1"


def test_case2_duplicate_event_id_single_claim():
    """Дубль event_id → 1 claim (идемпотентность)."""
    mem = _SessionMemory()
    sub = NpcSpeechActSubscriber(memory_manager=mem, campaign_id_provider=lambda: "T")
    event = _spoke_event(
        acts=[{"type": "SELF_INTRODUCTION", "params": {"name": "Горан"}}],
        event_id="evt-dlg1-2",
        target_id="merchant_goran",
        event_type=EventType.NPC_SPOKE.value,
        source="tavern_keeper_tornin",
    )
    sub.on_npc_spoke(event)
    sub.on_npc_spoke(event)
    session = mem.get_dialogue_session("T", "merchant_goran", partner_id="tavern_keeper_tornin")
    assert len(session.claims) == 1


def test_case3_no_target_id_skips():
    """listener=None → skip."""
    mem = _SessionMemory()
    sub = NpcSpeechActSubscriber(memory_manager=mem, campaign_id_provider=lambda: "T")
    sub.on_npc_spoke(_spoke_event(
        acts=[{"type": "SELF_INTRODUCTION", "params": {"name": "Горан"}}],
        event_id="evt-dlg1-3",
        target_id=None,
        event_type=EventType.NPC_SPOKE.value,
        source="tavern_keeper_tornin",
    ))
    assert all(len(s.claims) == 0 for s in mem._sessions.values())


def test_case4_self_talk_sentinel_skips():
    """listener=SELF_TALK_SENTINEL → skip (soliloquy)."""
    from app.domain.communication import SELF_TALK_SENTINEL
    mem = _SessionMemory()
    sub = NpcSpeechActSubscriber(memory_manager=mem, campaign_id_provider=lambda: "T")
    sub.on_npc_spoke(_spoke_event(
        acts=[{"type": "SELF_INTRODUCTION", "params": {"name": "Горан"}}],
        event_id="evt-dlg1-4",
        target_id=SELF_TALK_SENTINEL,
        event_type=EventType.NPC_SPOKE.value,
        source="tavern_keeper_tornin",
    ))
    assert all(len(s.claims) == 0 for s in mem._sessions.values())


def test_case5_no_semantic_acts_noop():
    """Без semantic_acts → no-op (не ломает существующий NPC path)."""
    mem = _SessionMemory()
    sub = NpcSpeechActSubscriber(memory_manager=mem, campaign_id_provider=lambda: "T")
    sub.on_npc_spoke(_spoke_event(
        acts=[],
        event_id="evt-dlg1-5",
        target_id="merchant_goran",
        event_type=EventType.NPC_SPOKE.value,
        source="tavern_keeper_tornin",
    ))
    assert all(len(s.claims) == 0 for s in mem._sessions.values())


def test_case6_speaker_does_not_get_self_knowledge():
    """Speaker не получает Claim о себе — cognition listener, не speaker."""
    mem = _SessionMemory()
    sub = NpcSpeechActSubscriber(memory_manager=mem, campaign_id_provider=lambda: "T")
    sub.on_npc_spoke(_spoke_event(
        acts=[{"type": "SELF_INTRODUCTION", "params": {"name": "Горан"}}],
        event_id="evt-dlg1-6",
        target_id="merchant_goran",
        event_type=EventType.NPC_SPOKE.value,
        source="tavern_keeper_tornin",
    ))
    # Speaker (tavern_keeper_tornin) НЕ должен иметь Claim о себе
    speaker_session = mem.get_dialogue_session("T", "tavern_keeper_tornin",
                                                partner_id="merchant_goran")
    assert len(speaker_session.claims) == 0
    # Listener (merchant_goran) — должен
    listener_session = mem.get_dialogue_session("T", "merchant_goran",
                                                  partner_id="tavern_keeper_tornin")
    assert len(listener_session.claims) == 1


def test_case7_broadcast_target_all_skips():
    """listener="all" → skip (broadcast — не конкретный cognition)."""
    mem = _SessionMemory()
    sub = NpcSpeechActSubscriber(memory_manager=mem, campaign_id_provider=lambda: "T")
    sub.on_npc_spoke(_spoke_event(
        acts=[{"type": "SELF_INTRODUCTION", "params": {"name": "Горан"}}],
        event_id="evt-dlg1-7",
        target_id="all",
        event_type=EventType.NPC_SPOKE.value,
        source="tavern_keeper_tornin",
    ))
    assert all(len(s.claims) == 0 for s in mem._sessions.values())


def test_case8_player_path_symmetry_same_act_format():
    """DLG-GC-01: тот же semantic_act format работает для PLAYER и NPC
    (симметрия — один контракт semantic_acts для обоих классов спикеров)."""
    # PLAYER path
    mem_p = _SessionMemory()
    sub_p = PlayerSpeechActSubscriber(memory_manager=mem_p, campaign_id_provider=lambda: "T")
    sub_p.on_player_spoke(_spoke_event(
        acts=[{"type": "SELF_INTRODUCTION", "params": {"name": "Мю"}}],
        event_id="evt-sym-1",
        target_id="merchant_goran",
        event_type=EventType.PLAYER_SPOKE.value,
        source="player",
    ))
    p_session = mem_p.get_dialogue_session("T", "merchant_goran", partner_id="player")
    assert len(p_session.claims) == 1
    assert "Мю" in p_session.claims[0].text
    assert p_session.claims[0].speaker == "player"

    # NPC path — same act, different speaker
    mem_n = _SessionMemory()
    sub_n = NpcSpeechActSubscriber(memory_manager=mem_n, campaign_id_provider=lambda: "T")
    sub_n.on_npc_spoke(_spoke_event(
        acts=[{"type": "SELF_INTRODUCTION", "params": {"name": "Горан"}}],
        event_id="evt-sym-2",
        target_id="merchant_goran",
        event_type=EventType.NPC_SPOKE.value,
        source="tavern_keeper_tornin",
    ))
    n_session = mem_n.get_dialogue_session("T", "merchant_goran",
                                            partner_id="tavern_keeper_tornin")
    assert len(n_session.claims) == 1
    assert "Горан" in n_session.claims[0].text
    assert n_session.claims[0].speaker == "tavern_keeper_tornin"

    # Структура Claim симметрична: same confidence, text-template "представился как"
    assert p_session.claims[0].confidence == n_session.claims[0].confidence
    assert "представился" in p_session.claims[0].text
    assert "представился" in n_session.claims[0].text


def test_case9_double_processing_no_duplicate():
    """Если NpcDialogueSubscriber._process_canonical уже написал Claim
    с тем же event_id в той же сессии — дубль не пройдёт (Claim Bridge).

    Симулируем: два subscriber'а обрабатывают один event, оба зовут add_claim
    с одним event_id → в session.claims только один Claim.
    """
    mem = _SessionMemory()
    sub = NpcSpeechActSubscriber(memory_manager=mem, campaign_id_provider=lambda: "T")
    event = _spoke_event(
        acts=[{"type": "SELF_INTRODUCTION", "params": {"name": "Горан"}}],
        event_id="evt-dlg1-9",
        target_id="merchant_goran",
        event_type=EventType.NPC_SPOKE.value,
        source="tavern_keeper_tornin",
    )
    # Simulate: NpcDialogueSubscriber already wrote Claim with same event_id
    session = mem.get_dialogue_session("T", "merchant_goran",
                                        partner_id="tavern_keeper_tornin")
    session.add_claim(
        text="extractor wrote this claim",
        speaker="tavern_keeper_tornin",
        confidence=0.7,
        tick=5,
        event_id="evt-dlg1-9",  # SAME event_id
    )
    assert len(session.claims) == 1
    # Now NpcSpeechActSubscriber processes the same event
    sub.on_npc_spoke(event)
    # Дедупликация должна сработать — остаётся 1 Claim
    session = mem.get_dialogue_session("T", "merchant_goran",
                                        partner_id="tavern_keeper_tornin")
    assert len(session.claims) == 1, "double processing must not duplicate Claim (event_id dedup)"