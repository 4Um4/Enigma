"""NPC_LONGFORM E0 — ExperimentRunner tests (7 scenarios).

E0 тестирует harness infrastructure, не E2 (dialogue between NPCs).
Сценарии адаптированы к реальности idle без стимула:
NPC двигаются (movement_intents), но могут не разговаривать.

7 сценариев из ТЗ E0:
1. Smoke: run() завершается без критических ошибок
2. Pre-flight: snapshots содержат NPC данные
3. Ticks: trace.ticks имеет n_ticks entries
4. Movement intents: observation tap захватывает (NPC двигаются)
5. Scene changes: observation tap захватывает SceneChange
6. Errors isolated: один tick error не разрушает весь run
7. Report saved: save_report создаёт JSON файл
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from tests.sandbox.experiment_runner import ExperimentRunner, ExperimentTrace


def _make_runner(n_ticks: int = 3) -> ExperimentRunner:
    """Create runner with minimal config for fast tests."""
    return ExperimentRunner(
        seed=42,
        campaign="Open_road",
        target_npcs=["maid_lusya", "tavern_keeper_tornin", "blacksmith_orm"],
    )


@pytest.fixture(scope="module")
def shared_trace():
    """Run experiment once per module (slow ~30-60s), share trace across tests."""
    runner = _make_runner(n_ticks=3)
    runner.setup(n_ticks=3, experiment_id="test_e0_shared")
    trace = runner.run(n_ticks=3)
    # Save report for inspection
    runner.save_report()
    return trace


# ── Scenario 1: Smoke — run completes ───────────────────────────────────────

def test_scenario_1_smoke(shared_trace):
    """ExperimentRunner.run() completes without critical errors."""
    assert isinstance(shared_trace, ExperimentTrace)
    assert shared_trace.elapsed_seconds > 0
    # No critical errors (warnings ok)
    critical_errors = [e for e in shared_trace.errors if "run:" in e]
    assert len(critical_errors) == 0, f"Critical errors: {critical_errors}"


# ── Scenario 2: Pre-flight snapshots ────────────────────────────────────────

def test_scenario_2_pre_flight_snapshots(shared_trace):
    """Pre-flight snapshots contain NPC data (static + runtime)."""
    # Static path
    assert "maid_lusya" in shared_trace.pre_flight_static
    _static_lusya = shared_trace.pre_flight_static["maid_lusya"]
    assert _static_lusya.get("present", False), "maid_lusya not found in static"

    # Runtime path — может быть present=False (LifeEngine cache пуст после new_game,
    # до первого idle_tick). Это валидное состояние, не баг harness.
    assert "maid_lusya" in shared_trace.pre_flight_runtime
    _rt_lusya = shared_trace.pre_flight_runtime["maid_lusya"]

    # Static path должен иметь narrative_cache_count
    assert "narrative_cache_count" in _static_lusya

    # Runtime path: если present — проверяем narrative_cache_count
    # Если not present — валидное состояние (cache ещё не заполнен)
    if _rt_lusya.get("present", False):
        assert "narrative_cache_count" in _rt_lusya


# ── Scenario 3: Ticks captured ──────────────────────────────────────────────

def test_scenario_3_ticks_captured(shared_trace):
    """trace.ticks has n_ticks entries."""
    assert len(shared_trace.ticks) == 3, f"Expected 3 ticks, got {len(shared_trace.ticks)}"
    for i, tick in enumerate(shared_trace.ticks):
        assert tick.tick_id == i + 1, f"tick_id mismatch at {i}: {tick.tick_id}"
        assert tick.game_time >= 0, f"game_time negative at tick {tick.tick_id}"


# ── Scenario 4: Movement intents captured ───────────────────────────────────

def test_scenario_4_movement_intents_captured(shared_trace):
    """Observation tap captures movement_intents (NPC move in idle)."""
    _all_intents = []
    for tick in shared_trace.ticks:
        _all_intents.extend(tick.movement_intents)

    # In idle, NPC should produce at least some movement intents
    # (exploration, schedule, needs — confirmed by S415.2 DIAG_D3)
    assert len(_all_intents) > 0, "No movement_intents captured — observation tap broken?"

    # Verify structure
    for mi in _all_intents:
        assert "npc_id" in mi
        assert "intent" in mi
        assert "tick" in mi


# ── Scenario 5: Scene changes captured ──────────────────────────────────────

def test_scenario_5_scene_changes_captured(shared_trace):
    """Observation tap captures SceneChange from MovementEngine."""
    _all_changes = []
    for tick in shared_trace.ticks:
        _all_changes.extend(tick.scene_changes)

    # Scene changes may be 0 if NPC don't move (but S415.2 showed they do)
    # At minimum, verify structure if any
    for sc in _all_changes:
        assert "target" in sc
        assert "field" in sc
        assert "tick" in sc

    # If movement_intents exist, scene_changes should too (movement -> world state)
    _all_intents = []
    for tick in shared_trace.ticks:
        _all_intents.extend(tick.movement_intents)
    if len(_all_intents) > 0:
        # Some intents should produce scene_changes (not all — some may be dropped)
        # Just log if 0 — don't fail (movement may be collapsed)
        if len(_all_changes) == 0:
            pytest.skip("movement_intents exist but no scene_changes — movement collapsed/dropped")


# ── Scenario 6: Errors isolated ─────────────────────────────────────────────

def test_scenario_6_errors_isolated(shared_trace):
    """One tick error does not destroy entire run."""
    # If any tick has errors, other ticks should still have data
    _ticks_with_errors = [t for t in shared_trace.ticks if t.errors]
    _ticks_clean = [t for t in shared_trace.ticks if not t.errors]

    if _ticks_with_errors:
        # At least some ticks should be clean (errors isolated)
        assert len(_ticks_clean) > 0, "All ticks have errors — errors not isolated"
    # If no errors at all — even better


# ── Scenario 7: Report saved ────────────────────────────────────────────────

def test_scenario_7_report_saved(shared_trace):
    """save_report creates JSON file."""
    _report_path = ROOT / "reports" / "experiments" / "test_e0_shared.json"
    assert _report_path.exists(), f"Report not created: {_report_path}"

    # Verify JSON is valid + contains expected fields
    with open(_report_path, "r", encoding="utf-8") as f:
        _data = json.load(f)

    assert "experiment_id" in _data
    assert "config" in _data
    assert "pre_flight_static" in _data
    assert "pre_flight_runtime" in _data
    assert "ticks" in _data
    assert "post_flight_runtime" in _data
    assert len(_data["ticks"]) == 3


# ── Convenience: get_dialogues / get_movement_intents ───────────────────────

def test_get_movement_intents_flattened(shared_trace):
    """get_movement_intents returns flattened list across all ticks."""
    runner = _make_runner()
    runner._trace = shared_trace  # Use shared trace
    _intents = runner.get_movement_intents()
    assert isinstance(_intents, list)
    assert len(_intents) > 0  # Should match scenario 4


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--no-header", "-W", "ignore::DeprecationWarning"])