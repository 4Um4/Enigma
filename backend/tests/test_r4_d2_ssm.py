"""
R4 / GATE-9A D2 — тесты SSM-контракта abort/persist.

7 сценариев:
  1. test_normal_path_persists                  — unlock без abort -> atomic_commit_all вызывается
  2. test_abort_skips_persist                   — mark_tick_aborted -> atomic_commit_all НЕ вызывается
  3. test_foreign_unlock_silent_noop           — чужой campaign_id -> silent no-op
  4. test_foreign_mark_aborted_noop            — чужой campaign_id в mark_tick_aborted -> маркер НЕ устанавливается
  5. test_marker_reset_after_normal_unlock     — нормальный путь сбрасывает маркер
  6. test_marker_reset_at_fresh_acquire        — fresh lock_for_tick сбрасывает маркер
  7. test_marker_reset_on_atomic_commit_exception — БЛОКЕР Мастера: atomic_commit_all исключение -> маркер всё равно сбрасывается
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.scene_state_manager import SceneStateManager


@pytest.fixture
def ssm_with_mock_persistence(tmp_path: Path):
    mock_port = MagicMock()
    mock_port.atomic_commit_all.return_value = True
    mock_port.load_scene.return_value = None
    mock_port.load_scene_at.return_value = None
    mgr = SceneStateManager(
        data_dir=tmp_path,
        persistence=mock_port,
        saves_dir=tmp_path,
        life_engine=None,
    )
    return mgr, mock_port


def test_normal_path_persists(ssm_with_mock_persistence):
    mgr, mock_port = ssm_with_mock_persistence
    scene_state = {"location_id": "tavern", "npc_positions": {}}
    mgr.adopt_scene_for_tick("camp-1", "tavern", scene_state)
    assert mgr._tick_locked is True
    assert mgr._tick_campaign_id == "camp-1"

    mgr.unlock_tick("camp-1")

    assert mock_port.atomic_commit_all.called, "atomic_commit_all должен вызываться на нормальном пути"
    call_kwargs = mock_port.atomic_commit_all.call_args
    assert call_kwargs.kwargs.get("campaign_id") == "camp-1"
    all_scenes = call_kwargs.kwargs.get("all_scenes")
    assert "tavern" in all_scenes
    assert all_scenes["tavern"] is scene_state
    assert mgr._tick_locked is False


def test_abort_skips_persist(ssm_with_mock_persistence):
    mgr, mock_port = ssm_with_mock_persistence
    scene_state = {"location_id": "tavern", "npc_positions": {}}
    mgr.adopt_scene_for_tick("camp-1", "tavern", scene_state)

    mgr.mark_tick_aborted("camp-1")
    mgr.unlock_tick("camp-1")

    assert not mock_port.atomic_commit_all.called, "atomic_commit_all НЕ должен вызываться при abort"
    assert mgr._tick_locked is False
    assert "tavern" in mgr._tick_scenes
    assert mgr._tick_scenes["tavern"] is scene_state


def test_foreign_unlock_silent_noop(ssm_with_mock_persistence):
    mgr, mock_port = ssm_with_mock_persistence
    scene_state = {"location_id": "tavern"}
    mgr.adopt_scene_for_tick("camp-1", "tavern", scene_state)

    mgr.unlock_tick("camp-OTHER")

    assert mgr._tick_locked is True
    assert mgr._tick_campaign_id == "camp-1"
    assert not mock_port.atomic_commit_all.called


def test_foreign_mark_aborted_noop(ssm_with_mock_persistence):
    mgr, mock_port = ssm_with_mock_persistence
    scene_state = {"location_id": "tavern"}
    mgr.adopt_scene_for_tick("camp-1", "tavern", scene_state)

    mgr.mark_tick_aborted("camp-OTHER")

    assert mgr._tick_aborted is False, "Чужой mark_tick_aborted не должен устанавливать маркер"

    mgr.unlock_tick("camp-1")
    assert mock_port.atomic_commit_all.called, "Нормальный unlock должен persist, если маркер не установлен"


def test_marker_reset_after_normal_unlock(ssm_with_mock_persistence):
    mgr, _ = ssm_with_mock_persistence
    scene_state = {"location_id": "tavern"}
    mgr.adopt_scene_for_tick("camp-1", "tavern", scene_state)
    mgr._tick_aborted = True
    mgr.unlock_tick("camp-1")
    assert mgr._tick_aborted is False, "Маркер должен сбрасываться после нормального unlock"


def test_marker_reset_at_fresh_acquire(ssm_with_mock_persistence):
    mgr, mock_port = ssm_with_mock_persistence
    mgr._tick_aborted = True
    fresh_scene = {"location_id": "tavern", "npc_positions": {}}
    mock_port.load_scene_at.return_value = fresh_scene

    result = mgr.lock_for_tick("camp-1", "tavern")

    assert result is fresh_scene
    assert mgr._tick_aborted is False, "Fresh acquire должен сбрасывать маркер"


def test_marker_reset_on_atomic_commit_exception(ssm_with_mock_persistence):
    import sqlite3
    mgr, mock_port = ssm_with_mock_persistence
    mock_port.atomic_commit_all.side_effect = sqlite3.Error("simulated failure")

    scene_state = {"location_id": "tavern"}
    mgr.adopt_scene_for_tick("camp-1", "tavern", scene_state)
    assert mgr._tick_aborted is False

    with pytest.raises(Exception):
        mgr.unlock_tick("camp-1")

    assert mgr._tick_aborted is False, (
        "Маркер должен сбрасываться даже при исключении в atomic_commit_all — "
        "требуется finally в guard тела unlock_tick"
    )
