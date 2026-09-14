"""
path: /project/backend/tests/micro/test_intent_liveness_gate.py
[GC-I01-E2] GC-INTERRUPT-01 micro: flee-гейт четырёх точек диспетчеризации.
Юнит-уровень: хелпер (fail-open S198-паритет), outbox 4-кортеж + drain-форвард
(обратная совместимость), process_tasks-гейт (терминал + недиспетчеризация),
death-priority (смерть сильнее), scope (attack вне v1 — по приказу Мастера).
Интеграционный контур третьего голоса — SUPERBOX gc_interrupt_test (следующий шаг).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.services.game_loop.task_scheduler import TaskScheduler


def _row(npc_id="npc_a", intent="talk", life="ALIVE"):
    return {"npc_id": npc_id, "intent": intent, "body_state": {"life_status": life}}


def _task(owner="npc_a"):
    return {
        "kind": "dialogue",
        "owner_id": owner,
        "payload": {"intent_type": "talk", "target_id": "player", "emotional_state": "neutral"},
    }


def _scheduler(provider):
    s = TaskScheduler()
    s._npc_states_provider = provider
    s._executor_pool = MagicMock()
    return s


def _outbox(s):
    with s._commitment_outbox_lock:
        return list(s._commitment_outbox)


# ── хелпер: предикат + fail-open ────────────────────────────────────────────

def test_flee_helper_true_for_flee():
    s = _scheduler(lambda cid: [_row(intent="flee")])
    assert s._owner_intent_flees("t", "npc_a") is True


def test_flee_helper_false_for_talk():
    s = _scheduler(lambda cid: [_row(intent="talk")])
    assert s._owner_intent_flees("t", "npc_a") is False


def test_flee_helper_false_for_attack_scope_v1():
    # Приказ Мастера: attack — отдельный проверяемый вариант, НЕ v1-предикат.
    s = _scheduler(lambda cid: [_row(intent="attack")])
    assert s._owner_intent_flees("t", "npc_a") is False


def test_flee_helper_none_intent_false():
    s = _scheduler(lambda cid: [_row(intent=None)])
    assert s._owner_intent_flees("t", "npc_a") is False


def test_flee_helper_fail_open_no_provider():
    s = TaskScheduler()
    s._executor_pool = MagicMock()
    assert s._owner_intent_flees("t", "npc_a") is False


def test_flee_helper_fail_open_provider_error():
    def _boom(cid):
        raise RuntimeError("provider down")

    s = _scheduler(_boom)
    assert s._owner_intent_flees("t", "npc_a") is False


def test_flee_helper_not_found_false():
    s = _scheduler(lambda cid: [_row(npc_id="other")])
    assert s._owner_intent_flees("t", "npc_a") is False


# ── outbox/drain: interrupt_reason-форвард + backcompat ─────────────────────

def test_drain_forwards_interrupt_reason(monkeypatch):
    from app.services.action import commitment_registry as cr

    calls = []

    def _fake_mirror(ss, nid, tick, outcome, fail_reason=None, interrupt_reason=None):
        calls.append((nid, outcome, fail_reason, interrupt_reason))
        return True

    monkeypatch.setattr(cr.CommitmentRegistry, "mirror_task_terminal", staticmethod(_fake_mirror))
    s = TaskScheduler()
    s._executor_pool = MagicMock()
    s._record_task_outcome("npc_a", "INTERRUPTED", interrupt_reason="TASK_STALE_INTENT")
    s.drain_commitment_outbox({"tick": 5})
    assert calls == [("npc_a", "INTERRUPTED", None, "TASK_STALE_INTENT")]


def test_drain_backward_compat_legacy_three_tuple(monkeypatch):
    from app.services.action import commitment_registry as cr

    calls = []

    def _fake_mirror(ss, nid, tick, outcome, fail_reason=None, interrupt_reason=None):
        calls.append((nid, outcome, fail_reason, interrupt_reason))
        return True

    monkeypatch.setattr(cr.CommitmentRegistry, "mirror_task_terminal", staticmethod(_fake_mirror))
    s = TaskScheduler()
    s._executor_pool = MagicMock()
    with s._commitment_outbox_lock:
        s._commitment_outbox.append(("npc_a", "CANCELLED", None))  # legacy-формат
    s.drain_commitment_outbox({"tick": 5})
    assert calls == [("npc_a", "CANCELLED", None, None)]


# ── process_tasks-гейт: терминал + недиспетчеризация + приоритет смерти ────

def test_process_tasks_flee_owner_interrupted_not_dispatched():
    s = _scheduler(lambda cid: [_row(intent="flee")])
    scene = {"campaign_id": "t", "pending_tasks": [_task()]}
    s.process_tasks(scene)
    args = s._executor_pool.submit.call_args
    assert args is None or not args[0][2]  # пул получил пустой список задач
    assert ("npc_a", "INTERRUPTED", None, "TASK_STALE_INTENT") in _outbox(s)


def test_process_tasks_talk_owner_dispatched():
    s = _scheduler(lambda cid: [_row(intent="talk")])
    scene = {"campaign_id": "t", "pending_tasks": [_task()]}
    s.process_tasks(scene)
    args = s._executor_pool.submit.call_args
    assert args is not None and args[0][2]  # задача доехала до пула
    assert not any(e[1] == "INTERRUPTED" for e in _outbox(s))


def test_process_tasks_dead_beats_flee():
    s = _scheduler(lambda cid: [_row(intent="flee", life="DEAD")])
    scene = {"campaign_id": "t", "pending_tasks": [_task()]}
    s.process_tasks(scene)
    assert ("npc_a", "EXPIRED", None, None) in _outbox(s)
    assert not any(e[1] == "INTERRUPTED" for e in _outbox(s))
