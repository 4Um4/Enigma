"""
path: backend/tests/micro/test_d1_dialogue_cache_npc_spoke.py
Назначение: D1 regression (NPC_SPEECH_SILENCE_ROOT_CAUSE §6.5).
    Проверяет, что _dlg_entry строится из NPC_SPOKE event, не из последнего
    event в списке materializer'а. Прежний код читал ev.payload.text из
    loop variable, которая после `for ev in events:` указывала на
    COMMUNICATION_CLAIM (если он есть) — у него нет text, пузырь терялся.
Зависимости: pytest, app.services.execution.dialogue_materializer
Основные сущности: test_d1_*
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from app.domain.execution import Artifact
from app.services.execution.dialogue_materializer import DialogueMaterializer
from app.services.events.event_types import EventType


def _make_artifact(data: dict[str, Any], *, success: bool = True) -> Artifact:
    """Создаёт production Artifact, а не структурный test double."""
    return Artifact(task_id="test-dialogue", success=success, result_type="dialogue_line", data=data)


def _make_dialogue_data(
    *,
    speaker_id: str = "maid_lusya",
    target_id: str = "player",
    text: str = "Здравствуйте, господин.",
    proposition: dict[str, Any] | None = None,
    exposure: str = "normal",
) -> dict[str, Any]:
    return {
        "speaker_id": speaker_id,
        "target_id": target_id,
        "text": text,
        "proposition": proposition,
        "exposure": exposure,
        "emotional_state": "calm",
        "topic": "greeting",
        "intent_type": "talk",
    }


def _collect_speech_text_from_events(events: list[Any]) -> str | None:
    """Имитация D1-fixed логики task_scheduler: select NPC_SPOKE explicitly."""
    speech_event = next(
        (e for e in events if e.type == EventType.NPC_SPOKE.value),
        None,
    )
    if speech_event is None:
        return None
    return cast(str, speech_event.payload.get("text", ""))


# ─── Case 1: NPC_SPOKE only — cache contains speech text ───────────────────


def test_d1_case1_npc_spoke_only_has_text() -> None:
    """Materializer returns NPC_SPOKE only: text добрался до cache entry."""
    data = _make_dialogue_data(text="Привет!")
    artifact = _make_artifact(data)
    mat = DialogueMaterializer()
    events = list(mat.materialize(artifact))

    types = [e.type for e in events]
    assert EventType.NPC_SPOKE.value in types
    assert EventType.COMMUNICATION_CLAIM.value not in types

    text = _collect_speech_text_from_events(events)
    assert text == "Привет!", f"Expected 'Привет!', got {text!r}"


# ─── Case 2: NPC_SPOKE + COMMUNICATION_CLAIM — text сохранён ────────────────


def test_d1_case2_npc_spoke_then_claim_keeps_text() -> None:
    """Главный D1-кейс: materializer возвращает [NPC_SPOKE, COMMUNICATION_CLAIM].
    Прежний код брал ev.payload.text из ПОСЛЕДНЕГО event (COMMUNICATION_CLAIM),
    у которого нет text — пузырь терялся. D1 fix: select NPC_SPOKE explicitly.
    """
    proposition = {
        "predicate": "knows",
        "subject_id": "maid_lusya",
        "object_id": "player",
        "confidence": 0.9,
    }
    data = _make_dialogue_data(
        text="Я знаю, что ты шпион.",
        proposition=proposition,
    )
    artifact = _make_artifact(data)

    # Stub verifier — proposition всегда подтверждён.
    # Контракт: verify(proposition, text) — без data (см. _VerifierProtocol в
    # app/services/cognition/proposition_verifier.py, прецедент test_dialogue_materializer_p5b.py:24).
    class _AlwaysConfirm:
        def verify(self, proposition: dict, text: str) -> bool:  # noqa: ARG002
            return True

    mat = DialogueMaterializer(proposition_verifier=_AlwaysConfirm())
    events = list(mat.materialize(artifact))

    types = [e.type for e in events]
    assert types == [EventType.NPC_SPOKE.value, EventType.COMMUNICATION_CLAIM.value], (
        f"Expected [NPC_SPOKE, COMMUNICATION_CLAIM], got {types}"
    )

    # D1 BUG (преждний код): ev = events[-1] = COMMUNICATION_CLAIM → text = ""
    # D1 FIX (select NPC_SPOKE): text = "Я знаю, что ты шпион."
    text = _collect_speech_text_from_events(events)
    assert text == "Я знаю, что ты шпион.", (
        f"D1 REGRESSION: text должен быть 'Я знаю, что ты шпион.', got {text!r}. "
        "Если '' — D1 вернулся (берётся payload COMMUNICATION_CLAIM, у которого нет text)."
    )


# ─── Case 3: proposition rejected — NPC_SPOKE всё ещё в cache ───────────────


def test_d1_case3_proposition_rejected_keeps_speech() -> None:
    """Proposition не верифицирован → COMMUNICATION_CLAIM не публикуется,
    но NPC_SPOKE публикуется ВСЕГДА (Master условие D в materializer:56).
    """
    proposition = {
        "predicate": "knows",
        "subject_id": "maid_lusya",
        "object_id": "player",
        "confidence": 0.9,
    }
    data = _make_dialogue_data(
        text="Я думаю, ты шпион.",
        proposition=proposition,
    )
    artifact = _make_artifact(data)

    class _AlwaysReject:
        def verify(self, proposition: dict, text: str) -> bool:  # noqa: ARG002
            return False

    mat = DialogueMaterializer(proposition_verifier=_AlwaysReject())
    events = list(mat.materialize(artifact))

    types = [e.type for e in events]
    assert types == [EventType.NPC_SPOKE.value], f"Expected only [NPC_SPOKE], got {types}"
    assert EventType.COMMUNICATION_CLAIM.value not in types

    text = _collect_speech_text_from_events(events)
    assert text == "Я думаю, ты шпион.", f"NPC_SPOKE text lost: {text!r}"


# ─── Case 4: no NPC_SPOKE event — no cache entry ────────────────────────────


def test_d1_case4_no_npc_spoke_no_entry() -> None:
    """Если materializer вернул пустой список (artifact не success),
    _collect_speech_text_from_events возвращает None — cache entry не создаётся.
    """
    data = _make_dialogue_data(text="Привет!")
    artifact = _make_artifact(data, success=False)
    mat = DialogueMaterializer()
    events = list(mat.materialize(artifact))

    assert events == [], f"Expected empty events for failed artifact, got {events}"

    text = _collect_speech_text_from_events(events)
    assert text is None, f"Expected None for no NPC_SPOKE, got {text!r}"


# ─── Case 5: drain copy — text в _recent_dialogues и scene_state ─────────────


def test_d1_case5_drain_preserves_text() -> None:
    """Симуляция drain-копирования: dialogue_entries → _recent_dialogues +
    scene_state["recent_dialogues"]. Text должен сохраниться не пустым.
    """
    data = _make_dialogue_data(text="С возвращением, господин.")
    artifact = _make_artifact(data)
    mat = DialogueMaterializer()
    events = list(mat.materialize(artifact))

    # Imitate task_scheduler.build dialogue_entries
    _game_time = 12345.0
    import time

    _speech_event = next(
        (e for e in events if e.type == EventType.NPC_SPOKE.value),
        None,
    )
    assert _speech_event is not None, "NPC_SPOKE event missing"
    _dlg_entry = {
        "speaker_id": _speech_event.source,
        "target_id": _speech_event.payload.get("target_id", ""),
        "text": _speech_event.payload.get("text", ""),
        "exposure": _speech_event.payload.get("exposure", "normal"),
        "timestamp": _game_time,
        "real_ts": time.time(),
        "game_time": _game_time,
    }
    dialogue_entries = [_dlg_entry]

    # Imitate drain: _recent_dialogues + scene_state mirror
    _recent_dialogues: list[dict[str, Any]] = []
    scene_state: dict[str, Any] = {}
    for entry in dialogue_entries:
        _recent_dialogues.append(entry)
        scene_state.setdefault("recent_dialogues", []).append(entry)

    # Assert non-empty text in BOTH channels
    assert _recent_dialogues[0]["text"] == "С возвращением, господин.", (
        f"text lost in _recent_dialogues: {_recent_dialogues[0]!r}"
    )
    assert scene_state["recent_dialogues"][0]["text"] == "С возвращением, господин.", (
        f"text lost in scene_state: {scene_state['recent_dialogues'][0]!r}"
    )


# ─── Case 6: visible_text non-empty для frontend projection ──────────────────


def test_d1_case6_visible_text_non_empty_for_frontend() -> None:
    """Frontend читает visible_text из perceived_narratives. Backend-side
    проверка: dialogue_entries содержат non-empty text, который попадёт в
    perceived_narratives через NarrativeProjector.
    """
    data = _make_dialogue_data(text="Чем могу помочь?")
    artifact = _make_artifact(data)
    mat = DialogueMaterializer()
    events = list(mat.materialize(artifact))

    _speech_event = next(
        (e for e in events if e.type == EventType.NPC_SPOKE.value),
        None,
    )
    assert _speech_event is not None
    visible_text = _speech_event.payload.get("text", "")
    speaker_id = _speech_event.source

    # Frontend injection condition: `if _spk_id and _dlg_text:`
    assert speaker_id, "speaker_id empty — frontend skip bubble"
    assert visible_text, (
        "visible_text empty — frontend skip bubble. D1 REGRESSION if empty: text берётся из COMMUNICATION_CLAIM."
    )
    assert visible_text == "Чем могу помочь?"
