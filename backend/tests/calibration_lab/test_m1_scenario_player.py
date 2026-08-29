"""
Файл: backend/tests/calibration_lab/test_m1_scenario_player.py
Назначение: M1/Задача 2 (S221) — ScenarioPlayer: строгая валидация YAML,
    тиковая семантика poll (1-based, однократность), запрет «второго
    оркестратора» (правило M1, S220), replay-идентичность протокола,
    сквозная дельта trust через scripted-сценарий (суперсессия
    test_m1_trust_intervention.py).
Зависимости: app.services.calibration.scenario_player, experiment_runner.
Основные сущности: load_scenario, ScenarioPlayer, Scenario, ScenarioEvent.
"""
from pathlib import Path

import pytest

from app.core.config import BASE_DIR
from app.services.calibration.scenario_player import (
    Scenario,
    ScenarioError,
    ScenarioEvent,
    ScenarioPlayer,
    load_scenario,
)

_PRESETS_DIR = Path(BASE_DIR) / "config" / "calibration" / "test_presets"
_SCENARIO = (
    Path(BASE_DIR) / "config" / "calibration" / "scenarios" / "trust_probe_v1.yaml"
)
_TRUST_KEY = "maid_lusya→player"


def _write_yaml(tmp_path: Path, content: str) -> Path:
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text(content, encoding="utf-8")
    return scenario


def _run_session(steps: int):
    """Полная сессия на дефолтном сценарии; возвращает (state, result)."""
    from app.services.calibration.experiment_runner import (
        ExperimentConfig,
        ExperimentRunner,
    )

    runner = ExperimentRunner()
    config = ExperimentConfig(
        preset_path=str(_PRESETS_DIR / "enigma_golden.yaml"),
        duration_ticks=300,
        scenario_path=str(_SCENARIO),
    )
    runner.start(config)
    try:
        state = {}
        for _ in range(steps):
            state = runner.step(1)
    finally:
        result = runner.stop()
    return state, result


# ── Валидация (house-style preset_io: громкие отказы) ───────────────────


def test_default_scenario_loads():
    scenario = load_scenario(_SCENARIO)
    assert scenario.scenario_id == "trust_probe_v1"
    assert len(scenario.events) == 1
    event = scenario.events[0]
    assert (event.tick, event.action, event.target, event.secret_id) == (
        11,
        "HELP",
        "maid_lusya",
        None,
    )


def test_unknown_action_rejected(tmp_path):
    path = _write_yaml(
        tmp_path,
        "scenario_id: x\nevents:\n  - tick: 1\n    action: DANCE\n    target: a\n",
    )
    with pytest.raises(ScenarioError) as excinfo:
        load_scenario(path)
    assert "DANCE" in str(excinfo.value)


def test_blackmail_requires_secret(tmp_path):
    path = _write_yaml(
        tmp_path,
        "scenario_id: x\nevents:\n  - tick: 1\n    action: BLACKMAIL\n    target: a\n",
    )
    with pytest.raises(ScenarioError) as excinfo:
        load_scenario(path)
    assert "secret_id" in str(excinfo.value)


def test_bad_tick_rejected(tmp_path):
    path = _write_yaml(
        tmp_path,
        "scenario_id: x\nevents:\n  - tick: 0\n    action: HELP\n    target: a\n",
    )
    with pytest.raises(ScenarioError) as excinfo:
        load_scenario(path)
    assert "tick" in str(excinfo.value)


def test_unknown_root_key_rejected(tmp_path):
    path = _write_yaml(
        tmp_path,
        "scenario_id: x\nfoo: 1\nevents:\n  - tick: 1\n    action: HELP\n    target: a\n",
    )
    with pytest.raises(ScenarioError) as excinfo:
        load_scenario(path)
    assert "foo" in str(excinfo.value)


def test_missing_events_rejected(tmp_path):
    path = _write_yaml(tmp_path, "scenario_id: x\n")
    with pytest.raises(ScenarioError) as excinfo:
        load_scenario(path)
    assert "events" in str(excinfo.value)


# ── Тиковая семантика poll ──────────────────────────────────────────────


def test_poll_fires_exactly_on_scheduled_tick():
    scenario = Scenario(
        scenario_id="t",
        events=(
            ScenarioEvent(tick=2, action="HELP", target="npc_a"),
            ScenarioEvent(tick=2, action="GIVE", target="npc_b"),
        ),
    )
    player = ScenarioPlayer(scenario)
    assert player.poll(1) == []
    fired = player.poll(2)
    assert len(fired) == 2
    assert fired[0].payload["semantic_action"] == "HELP"
    assert fired[0].payload["target_id"] == "npc_a"
    assert fired[0].payload["target_reference"] == "npc_a"
    assert fired[0].tick == 2
    assert player.poll(2) == []  # однократность
    assert player.poll(3) == []
    assert player.pending_count == 0
    assert len(player.journal) == 2


def test_blackmail_secret_in_payload():
    scenario = Scenario(
        scenario_id="t",
        events=(
            ScenarioEvent(
                tick=1, action="BLACKMAIL", target="npc_a", secret_id="sec_1"
            ),
        ),
    )
    fired = ScenarioPlayer(scenario).poll(1)
    assert fired[0].payload["secret_id"] == "sec_1"


# ── Граница: не второй оркестратор (правило M1) ────────────────────────


def test_scenario_player_is_not_second_orchestrator():
    """Прямые касания доменов состояния/решений ядра = красный тест."""
    import app.services.calibration.scenario_player as scenario_player_module

    source = Path(scenario_player_module.__file__).read_text(encoding="utf-8")
    for token in (
        "RelationshipStore",
        "relationship_store",
        "DecisionHub",
        "decision_hub",
        "StateApplicator",
        "state_applicator",
        "process_action",
        "delta_buffer",
    ):
        assert token not in source, (
            f"ScenarioPlayer касается '{token}' — второй оркестратор (правило M1)"
        )


# ── Сквозная интеграция (суперсессия test_m1_trust_intervention.py) ────


def test_scenario_help_raises_trust_and_clean_statuses():
    """trust_probe_v1: HELP на тике 11 поднимает trust в SSOT; тики без
    error; журнал эмуляций полный (replay-идентичность входа)."""
    from app.services.calibration.experiment_runner import (
        ExperimentConfig,
        ExperimentRunner,
    )

    runner = ExperimentRunner()
    config = ExperimentConfig(
        preset_path=str(_PRESETS_DIR / "enigma_golden.yaml"),
        duration_ticks=300,
        scenario_path=str(_SCENARIO),
    )
    runner.start(config)
    try:
        for _ in range(10):
            state = runner.step(1)
        before = float(
            state.get("relationships", {}).get(_TRUST_KEY, {}).get("trust", 0.0)
        )
        state = runner.step(1)  # тик 11: scripted HELP
        after = float(
            state.get("relationships", {}).get(_TRUST_KEY, {}).get("trust", 0.0)
        )
        assert after > before, f"сценарий не изменил SSOT: {before} -> {after}"
    finally:
        result = runner.stop()

    assert "error" not in result.statuses, result.statuses
    assert result.scenario_id == "trust_probe_v1"
    assert result.scenario_events == [
        {
            "tick": 11,
            "action": "HELP",
            "target": "maid_lusya",
            "secret_id": None,
            "emitted": True,
        }
    ]


def test_scenario_replay_identity():
    """Мастер-требование S220: один сценарий → идентичный журнал эмуляций
    и финальное состояние ядра (скоуп AC-004; rel-слой — DEBT-QUIESCE,
    в вердикт не входит)."""
    _, result_1 = _run_session(14)
    _, result_2 = _run_session(14)
    assert result_1.scenario_events == result_2.scenario_events
    assert result_1.final_npc_state == result_2.final_npc_state