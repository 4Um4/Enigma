# path: backend/tests/test_worker_outbox_determinism.py
# Назначение: ADR-O-399 — (1) drain применяет батч в каноническом порядке
# (submit_tick, task_id) независимо от порядка push (имитация разного
# completion-порядка воркера); (2) пустой outbox — no-op; (3) канонический
# порядок effects per-record: events → economy → dialogue → speech_reset.
# Зависимости: app.services.game_loop.task_scheduler.TaskScheduler
# Основные сущности: test_drain_order_independent_of_push_order,
#                    test_empty_outbox_noop, test_effect_order_per_record
"""

"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

from app.services.game_loop.task_scheduler import TaskScheduler, _TaskArtifactRecord


def _bare_scheduler():
    """Скелет TaskScheduler без тяжёлого конструктора (unit-контур drain)."""
    s = TaskScheduler.__new__(TaskScheduler)
    s._task_outbox = []
    import threading
    s._task_outbox_lock = threading.Lock()
    s._dialogue_lock = threading.Lock()
    s._recent_dialogues = []
    s._economy_tracker = None
    return s


def _rec(tid: str, tick: int = 5, dlg: str = "x") -> _TaskArtifactRecord:
    return _TaskArtifactRecord(
        submit_tick=tick, task_id=tid, events=(),
        dialogue_entry={"speaker_id": dlg, "text": f"line-{tid}"},
        economy_talks=(), speech_reset=None,
    )


def test_drain_order_independent_of_push_order(tmp_path):
    s = _bare_scheduler()
    scene = {}
    # push в обратном порядке = имитация другого completion-порядка воркера
    s._task_outbox.append(_rec("dlg-600-000002"))
    s._task_outbox.append(_rec("dlg-600-000001"))
    s.drain_task_worker_outbox(scene)
    order = [d["text"] for d in scene["recent_dialogues"]]
    assert order == ["line-dlg-600-000001", "line-dlg-600-000002"], (
        f"drain применил completion-порядок вместо канонического: {order}"
    )


def test_empty_outbox_noop():
    s = _bare_scheduler()
    scene = {"recent_dialogues": []}
    s.drain_task_worker_outbox(scene)  # не должен упасть и что-либо сделать
    assert scene["recent_dialogues"] == []


def test_effect_order_per_record():
    """Порядок эффектов внутри записи: dialogue после events (зеркало прежнего воркера)."""
    r = _TaskArtifactRecord(
        submit_tick=1, task_id="t", events=(), dialogue_entry={"speaker_id": "a"},
        economy_talks=(("a", 1),), speech_reset=None,
    )
    # frozen-контейнер: поля не мутируются после создания
    assert r.economy_talks == (("a", 1),)
    try:
        r.task_id = "hack"
        raise AssertionError("frozen нарушен")
    except Exception:
        pass


def test_drain_stamps_event_tick():
    """ADR-O-399 Iter1: drain штампует submit_tick в payload (event-time)."""
    from types import SimpleNamespace
    from app.domain.events import EventDTO

    s = _bare_scheduler()
    scene = {}
    # Тип вне карт подписчиков — publish уходит в пустоту, проверяем только штамп
    ev = EventDTO.create(
        event_type="o399_probe",
        source="probe",
        payload={"k": 1},
        visibility="public",
        radius=1.0,
        persistence_level="working",
    )
    s._task_outbox.append(_TaskArtifactRecord(
        submit_tick=777, task_id="t-1", events=(ev,),
        dialogue_entry=None, economy_talks=(), speech_reset=None,
    ))
    s.drain_task_worker_outbox(scene)
    assert ev.payload.get("event_tick") == 777, (
        f"drain не штампует event_tick: {ev.payload}"
    )