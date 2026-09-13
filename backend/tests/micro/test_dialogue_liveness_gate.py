"""
Назначение: B (пункт 10 GC-DIALOGUE-01) — замок liveness-гейта диалоговых задач:
owner DEAD → EXPIRED (ADR-O-365 terminal-mapping), посмертная реплика не
исполняется. Контроль: живой владелец исполняется; fail-open (нет
провайдера / не найден / ошибка провайдера) → исполнение как раньше.
Зависимости: app.services.game_loop.task_scheduler, app.domain.execution
Основные сущности: _task_dict (production-сериализация Фазы 6), TaskScheduler

Запуск: cd backend; python -m pytest tests/micro/test_dialogue_liveness_gate.py -v; cd ..
"""

from app.domain.execution import TaskKind, TaskPriority, TaskState
from app.services.game_loop.task_scheduler import TaskScheduler


def _task_dict(owner: str) -> dict:
    # Форма — сериализация Фазы 6 (post_decision), production-контракт;
    # enum-значения через .value — не угаданные строки.
    return {
        "task_id": f"task-liveness-{owner}",
        "tick": 1,
        "counter": 0,
        "kind": TaskKind.DIALOGUE.value,
        "priority": TaskPriority.NORMAL.value,
        "state": TaskState.PENDING.value,
        "creator_system": "DecisionHub",
        "owner_id": owner,
        "target_ids": ["guard_borko"],
        "payload": {
            "topic": "radius",
            "target_id": "guard_borko",
            "exposure_semantic": "normal",
            "intent_type": "warn",  # fast-path: LLM не требуется (S216)
            "emotional_state": "NEUTRAL",
            "npc_npc_context": "",
            "thread_id": "thread-liveness",
            "prepared_prompt": "",
            "proposition": None,
        },
        "created_tick": 1,
    }


def _scene(task: dict) -> dict:
    # game_time_seconds > NPC-cooldown: при 0.0 dequeue_next держит ВСЕХ на
    # cooldown (last_speak=0 → now-0 < COOLDOWN) — очередь-путь теста голодал
    # (№156). 1000.0 — реалистичное игровое время (прод-инвариант не задет).
    return {"campaign_id": "test_campaign", "game_time_seconds": 1000.0, "pending_tasks": [task]}


def _states(life_status: str) -> list:
    return [{
        "npc_id": "thief_shadow",
        "body_state": {"life_status": life_status, "current_hp": 1},
    }]


def _expired_entries(scheduler) -> list:
    # Форма outbox не предполагается — ищем терминал строковым сканом.
    return [e for e in scheduler._commitment_outbox if "EXPIRED" in str(e)]


def test_liveness_gate_dead_owner_expires_before_execution():
    sched = TaskScheduler(npc_states_provider=lambda cid: _states("DEAD"))
    sched.execute_pending(_scene(_task_dict("thief_shadow")), "test_campaign")
    assert sched.total_processed_tasks == 0, "B: мёртвый владелец — задача не исполняется"
    assert _expired_entries(sched), "B: DEAD → EXPIRED (ADR-O-365 mapping)"


def test_liveness_gate_alive_owner_executes():
    sched = TaskScheduler(npc_states_provider=lambda cid: _states("ALIVE"))
    sched.execute_pending(_scene(_task_dict("thief_shadow")), "test_campaign")
    assert sched.total_processed_tasks == 1, "B: живой владелец — исполнение не тронуто"
    assert not _expired_entries(sched), "B: живой владелец не получает EXPIRED"


def test_liveness_gate_fail_open_without_provider():
    sched = TaskScheduler()  # провайдер не задан — гейт выключен
    sched.execute_pending(_scene(_task_dict("thief_shadow")), "test_campaign")
    assert sched.total_processed_tasks == 1, "B: fail-open — без провайдера исполняется"


def test_liveness_gate_process_tasks_dispatch():
    # B (№149): process_tasks — параллельный dispatcher мимо DialogueQueue;
    # гейт обязан стоять и здесь (посмертные реплики шли именно этим путём).
    sched = TaskScheduler(npc_states_provider=lambda cid: _states("DEAD"))
    sched.process_tasks(_scene(_task_dict("thief_shadow")))
    assert _expired_entries(sched), "B: process_tasks-путь гейтится (точка №3)"
    import time as _t
    _t.sleep(0.3)
    assert sched.total_processed_tasks == 0, "B: мёртвый не исполняется (process_tasks)"


def test_liveness_gate_worker_in_flight():
    # B8: задача сабмичена ДО смерти (dispatch-гейты прошли честно), воркер
    # видит DEAD → EXPIRED, реплика не материализуется (истинный mid-generation).
    sched = TaskScheduler(npc_states_provider=lambda cid: _states("DEAD"))
    # Фикксура №156: tasks — аргумент воркера (не pending сцены); пустой список
    # означал «гейт не запускался вовсе».
    sched._process_tasks_async(
        _scene(_task_dict("thief_shadow")), [_task_dict("thief_shadow")],
        "test_campaign", "canonical", 0.0,
    )
    assert _expired_entries(sched), "B8: worker-гейт даёт EXPIRED in-flight задаче"
    assert sched.total_processed_tasks == 0, "B8: in-flight мёртвый не исполняется"


def test_liveness_gate_queue_path_not_fast_path():
    # Дыра замка №149: фиксура была warn → всегда fast-path. Talk идёт через
    # очередь → dequeue-гейт (B5): покрывает основной production-путь задач.
    _td = _task_dict("thief_shadow")
    _td["payload"]["intent_type"] = "talk"  # requires_llm → очередь
    sched = TaskScheduler(npc_states_provider=lambda cid: _states("DEAD"))
    sched.execute_pending(_scene(_td), "test_campaign")
    assert _expired_entries(sched), "B5/B8: очередь-путь гейтится (talk)"


def test_owner_is_dead_unit_semantics():
    sched = TaskScheduler(npc_states_provider=lambda cid: _states("DEAD"))
    assert sched._owner_is_dead("c", "thief_shadow") is True
    assert sched._owner_is_dead("c", "unknown_npc") is False  # не найден → fail-open
    sched2 = TaskScheduler(npc_states_provider=lambda cid: (_ for _ in ()).throw(RuntimeError("x")))
    assert sched2._owner_is_dead("c", "thief_shadow") is False  # ошибка → fail-open
    sched3 = TaskScheduler(npc_states_provider=lambda cid: [])
    assert sched3._owner_is_dead("c", "thief_shadow") is False  # пустой мир → fail-open