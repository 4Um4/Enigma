"""
Назначение: замок fast-path omit-дефекта (S271): execute_pending → fast-path warn → outbox.submit_tick == тик сцены (не 0) → drain → event_tick штампован честным тиком.
Зависимости: app.services.game_loop.task_scheduler, app.services.events.event_bus
Основные сущности: test_fastpath_submit_tick_is_scene_tick, test_fastpath_event_tick_stamped_on_drain
Запуск: cd backend; python -m pytest tests/micro/test_fastpath_submit_tick_stamp.py -v --tb=short 2>&1 | Select-Object -Last 10; cd ..
"""

from app.services.events.event_bus import get_event_bus
from app.services.game_loop.task_scheduler import TaskScheduler


def _task_dict(tick: int) -> dict:
    # Форма — сериализация Фазы 6 (прецедент test_dialogue_liveness_gate._task_dict);
    # warn = fast-path: LLM не требуется (S216), исполняется синхронно.
    return {
        "task_id": f"task-fastpath-tick-{tick}",
        "tick": tick,
        "counter": 0,
        "kind": "dialogue",
        "priority": 1,
        "state": "PENDING",
        "creator_system": "DecisionHub",
        "owner_id": "thief_shadow",
        "target_ids": ["guard_borko"],
        "payload": {
            "topic": "radius",
            "target_id": "guard_borko",
            "exposure_semantic": "normal",
            "intent_type": "warn",
            "emotional_state": "NEUTRAL",
            "npc_npc_context": "",
            "thread_id": "thread-fastpath",
            "prepared_prompt": "",
            "proposition": None,
        },
        "created_tick": tick,
    }


def _scene(tick: int) -> dict:
    return {
        "campaign_id": "test_campaign",
        "tick": tick,
        "game_time_seconds": 1000.0,
        "pending_tasks": [_task_dict(tick)],
    }


def test_fastpath_submit_tick_is_scene_tick():
    # Дефект S271: fast-path вызывал _process_tasks_async без submit_tick →
    # дефолт 0 → _TaskArtifactRecord.submit_tick=0 → event_tick=0 в drain.
    sched = TaskScheduler()
    sched.execute_pending(_scene(42), "test_campaign")
    assert len(sched._task_outbox) == 1, f"ожидался 1 артефакт в outbox: {sched._task_outbox}"
    assert sched._task_outbox[0].submit_tick == 42, (
        f"fast-path submit_tick == 0 (дефект S271 воспроизведён): {sched._task_outbox[0].submit_tick}"
    )


def test_fastpath_event_tick_stamped_on_drain():
    # Сквозная цепь: outbox.submit_tick(42) → drain setdefault("event_tick", 42) → publish.
    sched = TaskScheduler()
    scene = _scene(42)
    sched.execute_pending(scene, "test_campaign")

    bus = get_event_bus()
    captured: list = []
    _orig_publish = bus.publish

    def _capture(ev):
        captured.append(ev)
        return _orig_publish(ev)

    bus.publish = _capture  # probe-only перехват: не зависит отEventType материала
    try:
        sched.drain_task_worker_outbox(scene)
    finally:
        bus.publish = _orig_publish

    assert captured, "drain не опубликовал ни одного события fast-path задачи"
    for ev in captured:
        _payload = getattr(ev, "payload", None)
        assert isinstance(_payload, dict), f"событие без dict-payload: {type(_payload)}"
        assert _payload.get("event_tick") == 42, (
            f"event_tick != 42 после фикса S271: {_payload.get('event_tick')}"
        )