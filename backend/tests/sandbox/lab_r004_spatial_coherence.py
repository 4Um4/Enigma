"""
path: backend/tests/sandbox/lab_r004_spatial_coherence.py
Назначение: R004 INV-SC-1-8 targeted probe (precedent lab_r003).
Проверяет SpatialCoherenceProbe на blacksmith_orm в стандартном пресете.
"""
from __future__ import annotations
import sys
import json
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

from app.services.calibration.experiment_runner import ExperimentRunner, ExperimentConfig
from app.services.probes.probe_alerts import probe_alerts
from app.services.player_session_service import player_session_service

_ROOT = _BACKEND.parent
_PRESET = str(_ROOT / "config" / "calibration" / "test_presets" / "golden_social_z0.yaml")
_CAMPAIGN = "Open_road"
_TICKS = 30

def main() -> int:
    # Reset probe_alerts singleton
    probe_alerts._history.clear()
    probe_alerts._violations.clear()

    runner = ExperimentRunner()
    cfg = ExperimentConfig(preset_path=_PRESET, duration_ticks=_TICKS, campaign_id=_CAMPAIGN)
    runner.start(cfg)
    player_session_service.select_player(cfg.campaign_id, "player")
    
    # lab_r003 precedent: _initial_social_applied устанавливается внутри runner.start()
    _ = getattr(runner, "_initial_social_applied", {})

    for _ in range(_TICKS):
        runner.step(1)

    runner.stop()

    history = list(probe_alerts._history)
    sc_failures = []
    for tick_summary in history:
        if tick_summary["failed"] > 0:
            for err in tick_summary["errors"]:
                if "SC-" in err or "SPATIAL" in err:
                    sc_failures.append({"tick": tick_summary["tick_id"], "error": err})

    result = {
        "probe_name": "INV-SC-1-8-SPATIAL-COHERENCE",
        "preset": _PRESET,
        "ticks_run": len(history),
        "total_sc_failures": len(sc_failures),
        "failures": sc_failures,
        "dashboard": probe_alerts.get_dashboard()
    }
    
    out_path = _BACKEND.parent / "reports" / "lab_r004_spatial_coherence.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"Итог: GREEN={'YES' if not sc_failures else 'NO'} FAILURES={len(sc_failures)}")
    if sc_failures:
        print(json.dumps(sc_failures, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())