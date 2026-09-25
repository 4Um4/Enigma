"""
path: /project/backend/tests/micro/test_semantic_span_chain.py
Назначение: Вертикальный срез Фазы 3 — шина (финальный event.id) →
    journal → ground_speaker_mention → project_journal. Доказательство:
    span.source_event_id == event.id шины; span_id детерминирован; границы
    grounding (имя не в тексте → []; без identity → []).
Зависимости: event_bus, event_identity, journal_presentation, semantic_span
Основные сущности: тесты chain Фазы 3
"""

from app.domain.events import EventDTO
from app.domain.semantic_span import make_span_id
from app.services.events.event_bus import EventBus
from app.services.events.event_identity import next_event_identity
from app.services.integration.journal_presentation import project_journal


def _publish_spoke(scene: dict, text: str, source: str = "lusya") -> EventBus:
    bus = EventBus()
    bus.set_identity_provider(lambda t, s: next_event_identity(scene, t, s))
    bus.publish(
        EventDTO.create(
            event_type="npc_spoke",
            source=source,
            payload={"text": text, "event_tick": scene["tick"]},
        )
    )
    return bus


def test_chain_span_source_event_id_is_bus_event_id():
    """ГЛАВНАЯ проверка Фазы 3: спан указывает на ТОТ ЖЕ event.id, что
    породил journal-запись (сквозная идентичность до диапазона текста)."""
    scene = {"tick": 300}
    bus = _publish_spoke(scene, "Лусия поставила кружку на стол.")
    final_id = str(bus._event_log[-1].id)
    journal_entry = {
        "speaker": "Лусия",
        "text": "Лусия поставила кружку на стол.",
        "channel": "direct",
        "event_id": final_id,
        "tick": 300,
    }
    projected = project_journal([journal_entry])
    span = projected[0]["spans"][0]
    assert span["source_event_id"] == final_id
    assert span["semantic_id"] == "Лусия"
    assert (span["start"], span["end"]) == (0, 5)
    assert span["confidence"] == 1.0
    assert span["creator"] == "grounding"
    assert span["status"] == "accepted"


def test_span_id_deterministic_and_child_of_event():
    """span_id = md5(source_event_id + range + type): детерминирован;
    разные события → разные span_id для одинакового текста (не слиты)."""
    s1 = make_span_id("event-A", 0, 5, "speaker_mention")
    s2 = make_span_id("event-A", 0, 5, "speaker_mention")
    s3 = make_span_id("event-B", 0, 5, "speaker_mention")
    assert s1 == s2          # same event + same range → same span_id
    assert s1 != s3          # разные события → разные span_id


def test_grounding_boundary_speaker_not_in_text():
    """Граница Мастера: speaker ≠ substring текста. Имя отсутствует →
    spans=[] (никаких искусственных спанов из метаданных)."""
    from app.services.integration.span_grounding import ground_speaker_mention
    assert ground_speaker_mention("E1", "Горан", "Он вошёл в таверну.") == []
    assert ground_speaker_mention("E1", "", "Лусия здесь.") == []
    assert ground_speaker_mention("", "Лусия", "Лусия здесь.") == []


def test_full_projection_matrix_spans():
    """Матрица проекции: identity+имя → span; identity без имени → [];
    без identity → [] + provenance_complete=False."""
    projected = project_journal(
        [
            {"speaker": "Лусия", "text": "Лусия кивнула.", "channel": "direct",
             "event_id": "E9", "tick": 1},
            {"speaker": "Лусия", "text": "Кивнула.", "channel": "direct",
             "event_id": "E10", "tick": 2},
            {"speaker": "Лусия", "text": "Лусия кивнула.", "channel": "narrative"},
        ]
    )
    assert len(projected[0]["spans"]) == 1
    assert projected[1]["spans"] == []
    assert projected[2]["spans"] == [] and projected[2]["provenance_complete"] is False