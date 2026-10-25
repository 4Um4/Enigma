"""
R4/GATE-9A D2 — PAT ×8 проверки 4–8 (v2, исправленные).

Исправления vs v1:
  - Имя класса PlayerAction (не ActionRequest).
  - ChatTurnRequest.player_position optional (не передаём).
  - Проверка atomic_commit_all ИЗ unlock_tick (post-acquire), не «вообще не вызывается».
    В idle_tick есть pre-tick save_scene_state @1219 (до lock_all_for_tick) — это
    нормальный pre-tick persist, не входит в D2 контракт. D2 = persist из unlock_tick.

Стратегия spy:
  - in_unlock флаг — True только во время вызова unlock_tick.
  - ac_calls_in_unlock — список atomic_commit_all вызовов, произошедших ИЗ unlock_tick.
  - Контракт D2: при abort → ac_calls_in_unlock пуст; при normal → ac_calls_in_unlock >= 1.
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import patch

from tests.gameplay.harness import TavernGameplayHarness


@pytest.fixture
def harness():
    h = TavernGameplayHarness(seed=42)
    h.new_game()
    yield h
    h.dispose()


def _install_spies(sm):
    """Установить spies на mark_tick_aborted, unlock_tick, atomic_commit_all.

    Возвращает dict со счётчиками:
      - mark_calls: list of campaign_id passed to mark_tick_aborted
      - unlock_calls: list of campaign_id passed to unlock_tick
      - ac_calls_in_unlock: list of kwargs passed to atomic_commit_all FROM unlock_tick
      - ac_calls_total: list of all atomic_commit_all calls (any source)
    """
    state = {
        "mark_calls": [],
        "unlock_calls": [],
        "ac_calls_in_unlock": [],
        "ac_calls_total": [],
        "in_unlock": [False],  # mutable holder for closure
    }

    orig_mark = sm.mark_tick_aborted
    orig_unlock = sm.unlock_tick
    orig_ac = sm._persistence.atomic_commit_all

    def spy_mark(campaign_id):
        state["mark_calls"].append(campaign_id)
        return orig_mark(campaign_id)

    def spy_unlock(campaign_id):
        state["unlock_calls"].append(campaign_id)
        state["in_unlock"][0] = True
        try:
            return orig_unlock(campaign_id)
        finally:
            state["in_unlock"][0] = False

    def spy_ac(**kwargs):
        state["ac_calls_total"].append(kwargs)
        if state["in_unlock"][0]:
            state["ac_calls_in_unlock"].append(kwargs)
        return orig_ac(**kwargs)

    sm.mark_tick_aborted = spy_mark
    sm.unlock_tick = spy_unlock
    sm._persistence.atomic_commit_all = spy_ac

    return state


# ─── Проверка 4: Exception в run_turn → mark_tick_aborted + освобождение ─
def test_check_4_run_turn_exception_marks_aborted_and_unlocks(harness):
    """Exception в _turn_pipeline.execute → mark_tick_aborted вызван,
    atomic_commit_all НЕ вызван ИЗ unlock_tick, _tick_locked освобождён.
    """
    gl = harness.game_loop
    sm = gl.scene_manager
    state = _install_spies(sm)

    from app.models.schemas import ChatTurnRequest, PlayerAction

    req = ChatTurnRequest(
        actions=[PlayerAction(player_name="Tester", action="осмотреться")],
        campaign_id=harness.campaign_id,
        world_id=harness.campaign_id,
        location="tavern",
    )

    def raising_execute(*args, **kwargs):
        raise RuntimeError("PAT-x8 simulated execute failure")

    with patch.object(gl._turn_pipeline, "execute", side_effect=raising_execute):
        with pytest.raises(RuntimeError, match="PAT-x8 simulated execute failure"):
            asyncio.run(gl.run_turn(req))

    assert len(state["mark_calls"]) == 1, f"mark_tick_aborted should be called once, got {state['mark_calls']}"
    assert state["mark_calls"][0] == harness.campaign_id

    assert len(state["unlock_calls"]) == 1, f"unlock_tick should be called once, got {state['unlock_calls']}"
    assert state["unlock_calls"][0] == harness.campaign_id

    # D2 contract: atomic_commit_all НЕ вызывается ИЗ unlock_tick при abort
    assert len(state["ac_calls_in_unlock"]) == 0, (
        f"atomic_commit_all should NOT be called from unlock_tick on abort, "
        f"got {len(state['ac_calls_in_unlock'])} calls"
    )

    assert sm._tick_locked is False
    assert sm._tick_aborted is False


# ─── Проверка 5: Exception в idle_tick → mark_tick_aborted + освобождение ─
def test_check_5_idle_tick_exception_marks_aborted_and_unlocks(harness):
    """Exception в _tick_orch.execute → mark_tick_aborted вызван,
    atomic_commit_all НЕ вызван ИЗ unlock_tick, _tick_locked освобождён.
    """
    gl = harness.game_loop
    sm = gl.scene_manager
    state = _install_spies(sm)

    def raising_execute(*args, **kwargs):
        raise RuntimeError("PAT-x8 simulated tick_orch failure")

    with patch.object(gl._tick_orch, "execute", side_effect=raising_execute):
        with pytest.raises(RuntimeError, match="PAT-x8 simulated tick_orch failure"):
            gl.idle_tick(harness.campaign_id)

    assert len(state["mark_calls"]) == 1, f"mark_tick_aborted should be called once, got {state['mark_calls']}"
    assert state["mark_calls"][0] == harness.campaign_id

    assert len(state["unlock_calls"]) == 1
    assert state["unlock_calls"][0] == harness.campaign_id

    assert len(state["ac_calls_in_unlock"]) == 0, (
        f"atomic_commit_all should NOT be called from unlock_tick on abort, "
        f"got {len(state['ac_calls_in_unlock'])} calls"
    )

    assert sm._tick_locked is False
    assert sm._tick_aborted is False


# ─── Проверка 6: Exception в skip_time → mark_tick_aborted + освобождение ─
def test_check_6_skip_time_exception_marks_aborted_and_unlocks(harness):
    """Exception в _time_skip.skip → mark_tick_aborted вызван,
    atomic_commit_all НЕ вызван ИЗ unlock_tick, _tick_locked освобождён.
    """
    gl = harness.game_loop
    sm = gl.scene_manager
    state = _install_spies(sm)

    def raising_skip(*args, **kwargs):
        raise RuntimeError("PAT-x8 simulated time_skip failure")

    with patch.object(gl._time_skip, "skip", side_effect=raising_skip):
        with pytest.raises(RuntimeError, match="PAT-x8 simulated time_skip failure"):
            gl.skip_time(harness.campaign_id, ticks=5)

    assert len(state["mark_calls"]) == 1, f"mark_tick_aborted should be called once"
    assert state["mark_calls"][0] == harness.campaign_id
    assert len(state["unlock_calls"]) == 1
    assert state["unlock_calls"][0] == harness.campaign_id
    assert len(state["ac_calls_in_unlock"]) == 0, (
        f"atomic_commit_all should NOT be called from unlock_tick on abort"
    )
    assert sm._tick_locked is False
    assert sm._tick_aborted is False


# ─── Проверка 7a: Штатный путь — atomic_commit_all ИЗ unlock_tick вызывается ─
def test_check_7a_normal_path_persists(harness):
    """Штатный idle_tick → atomic_commit_all вызывается ИЗ unlock_tick (нормальный persist).
    """
    gl = harness.game_loop
    sm = gl.scene_manager
    state = _install_spies(sm)

    gl.idle_tick(harness.campaign_id)

    assert len(state["ac_calls_in_unlock"]) >= 1, (
        f"atomic_commit_all should be called from unlock_tick on normal path, "
        f"got {len(state['ac_calls_in_unlock'])} calls"
    )
    assert state["ac_calls_in_unlock"][0]["campaign_id"] == harness.campaign_id
    assert sm._tick_locked is False
    assert sm._tick_aborted is False


# ─── Проверка 7b: Аварийный путь — atomic_commit_all ИЗ unlock_tick НЕ вызывается ─
def test_check_7b_abort_path_skips_persist(harness):
    """Аварийный idle_tick (exception) → atomic_commit_all НЕ вызывается ИЗ unlock_tick.
    """
    gl = harness.game_loop
    sm = gl.scene_manager
    state = _install_spies(sm)

    def raising_execute(*args, **kwargs):
        raise RuntimeError("PAT-x8 7b simulated failure")

    with patch.object(gl._tick_orch, "execute", side_effect=raising_execute):
        with pytest.raises(RuntimeError):
            gl.idle_tick(harness.campaign_id)

    assert len(state["ac_calls_in_unlock"]) == 0, (
        f"atomic_commit_all should NOT be called from unlock_tick on abort, "
        f"got {len(state['ac_calls_in_unlock'])} calls"
    )


# ─── Проверка 8: Чужой campaign_id не снимает блокировку ─────────────────
def test_check_8_foreign_campaign_id_noop(harness):
    """Чужой campaign_id в mark_tick_aborted/unlock_tick → silent no-op,
    блокировка другого тика НЕ снимается, состояние НЕ сбрасывается.
    """
    gl = harness.game_loop
    sm = gl.scene_manager

    scene_a = {"location_id": "tavern", "npc_positions": {}}
    sm.adopt_scene_for_tick("camp-A", "tavern", scene_a)
    assert sm._tick_locked is True
    assert sm._tick_campaign_id == "camp-A"

    sm.mark_tick_aborted("camp-OTHER")
    assert sm._tick_aborted is False, "Foreign mark_tick_aborted should be silent no-op"

    sm.unlock_tick("camp-OTHER")
    assert sm._tick_locked is True, "Foreign unlock_tick should NOT release the lock"
    assert sm._tick_campaign_id == "camp-A"
    assert "tavern" in sm._tick_scenes

    sm.unlock_tick("camp-A")
    assert sm._tick_locked is False
