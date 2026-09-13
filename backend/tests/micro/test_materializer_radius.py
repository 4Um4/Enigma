"""
path: /project/backend/tests/micro/test_materializer_radius.py
Назначение: D0 (GC-DIALOGUE-01) — замок SSOT-радиуса материализатора: EventDTO
    NPC_SPOKE / COMMUNICATION_CLAIM обязаны нести radius = exposure_radius
    (SpeechExposure Contract, Р-В), не хардкод 10.0 (ADR-148). Закрывает дыру,
    из-за которой production-речь жила на loud-радиусе при зелёной батарее Р-В.
Зависимости: app.domain.execution, app.domain.events, app.services.events.event_types,
    app.services.execution.dialogue_materializer, app.domain.communication
Основные сущности: _artifact (фабрика production-формы), DialogueMaterializer

Запуск: cd backend; python -m pytest tests/micro/test_materializer_radius.py -v; cd ..
"""

from app.domain.communication import SELF_TALK_SENTINEL, exposure_radius
from app.domain.execution import Artifact
from app.services.events.event_types import EventType
from app.services.execution.dialogue_materializer import DialogueMaterializer


def _artifact(exposure: str, target_id: str = "guard_borko", proposition: dict = None) -> Artifact:
    # Форма повторяет успешный yield DialogueExecutor.execute (№66) —
    # production-контракт data-ключей, не объект мечты (§13.4).
    return Artifact(
        task_id="task-d0-test",
        success=True,
        result_type="dialogue_line",
        data={
            "speaker_id": "thief_shadow",
            "target_id": target_id,
            "text": "Проверка радиуса.",
            "exposure": exposure,
            "topic": "radius",
            "emotional_state": "NEUTRAL",
            "proposition": proposition,
            "intent_type": "talk",
        },
    )


def _speech_event(events):
    return next(e for e in events if e.type == EventType.NPC_SPOKE.value)


def test_materializer_normal_radius_from_ssot():
    events = DialogueMaterializer().materialize(_artifact("normal"))
    _ev = _speech_event(events)
    assert _ev.radius == exposure_radius("normal") == 6.0, (
        "D0: normal-речь несёт SSOT-радиус 6.0, не хардкод 10.0"
    )


def test_materializer_whisper_radius_from_ssot():
    events = DialogueMaterializer().materialize(_artifact("whisper"))
    _ev = _speech_event(events)
    assert _ev.radius == exposure_radius("whisper") == 3.0
    assert _ev.visibility == "whisper"


def test_materializer_soliloquy_sentinel_whisper_class():
    # D4: сентинел → whisper-класс независимо от входного semantic
    events = DialogueMaterializer().materialize(
        _artifact("normal", target_id=SELF_TALK_SENTINEL)
    )
    _ev = _speech_event(events)
    assert _ev.radius == exposure_radius("whisper")
    assert _ev.visibility == "whisper"


def test_materializer_claim_radius_follows_speech():
    _prop = {
        "subject_id": "thief_shadow",
        "predicate": "STOLE",
        "object_id": "merchant_goran",
        "polarity": True,
    }
    events = DialogueMaterializer().materialize(_artifact("secret", proposition=_prop))
    _claim = next(e for e in events if e.type == EventType.COMMUNICATION_CLAIM.value)
    # S197: клейм едет с той же мембраной, что и речь (secret → 1.5)
    assert _claim.radius == exposure_radius("secret") == 1.5