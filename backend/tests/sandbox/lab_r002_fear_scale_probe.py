"""
path: backend/tests/sandbox/lab_r002_fear_scale_probe.py
Назначение: R002 FEAR-SCALE PROBE (Н-4, M1b.3.6): дифференциальный прогон
    production-контура (ExperimentRunner, тот же что F5-Lab/R001) — одна
    переменная: initial fear(player) ∈ {0, 0.7, 30, 70} при армированных
    условиях FAKE_SUBMISSION (trust=-60, willpower=60). Предсказание при
    прод-каноне V2 (−100..100) и множителе _fear=×100 (phases/decision:207):
    все fear>0.6 дают идентичную маску → mismatch producer(-100..100) vs
    consumer(0..1·100). Трассировка из наблюдаемых: store_read (V2-факт) →
    final_npc_state relationship_cache.player.fear (вход читателя) →
    psyche.behavior_mask (+intensity, will_state, stress — контроль).
    Наблюдение не создаёт каузальность (Закон XI): ноль monkey-patch.
Зависимости: app.services.calibration.experiment_runner, json, pathlib
Основные сущности: PRESETS, main
Запуск: python backend/tests/sandbox/lab_r002_fear_scale_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

_ROOT = _BACKEND.parent
# fear-sweep при армированных условиях FAKE_SUBMISSION: trust=-60 < 0,
# willpower=60 > 40 (порог phases/decision:211-214)
_PRESETS = {
    "R002-F0": "config/calibration/test_presets/golden_fear_f0.yaml",
    "R002-F0.7": "config/calibration/test_presets/golden_fear_f0_7.yaml",
    "R002-F30": "config/calibration/test_presets/golden_fear_f30.yaml",
    "R002-F70": "config/calibration/test_presets/golden_fear_f70.yaml",
}
_TICKS = 30
_CAMPAIGN = "Open_road"
_NPC = "merchant_goran"


def main() -> int:
    import logging

    logging.getLogger().setLevel(logging.ERROR)

    from app.services.calibration.experiment_runner import (
        ExperimentConfig,
        ExperimentRunner,
    )

    results = []
    for run_id, preset in _PRESETS.items():
        runner = ExperimentRunner()
        cfg = ExperimentConfig(
            preset_path=preset,
            duration_ticks=_TICKS,
            campaign_id=_CAMPAIGN,
        )
        experiment_id = runner.start(cfg)
        from app.services.player_session_service import player_session_service

        player_session_service.select_player(cfg.campaign_id, "player")
        runner.step(_TICKS)
        initial = getattr(runner, "_initial_social_applied", {})
        result = runner.stop()

        fin = result.final_npc_state.get(_NPC, {}) or {}
        psyche = fin.get("psyche", {}) or {}
        rc = fin.get("relationship_cache", {}).get("player", {}) or {}
        first = result.npc_captures[0] if result.npc_captures else []
        first_g = next(
            (n for n in first if (n.get("id") or n.get("npc_id")) == _NPC), {}
        )
        rec = {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "initial": initial.get(_NPC, {}),
            # Трассировка V2 → кэш → маска (все — наблюдаемые величины)
            "store_read": initial.get(_NPC, {}).get("store_read", {}),
            "rc_player_fear": rc.get("fear", None),
            "rc_player_trust": rc.get("trust", None),
            "behavior_mask": psyche.get("behavior_mask", None),
            "mask_intensity": psyche.get("behavior_mask_intensity", None),
            "will_state": psyche.get("will_state", None),
            "stress": psyche.get("stress", None),
            # R002-diag (Часть VIII.5): пустые маски → вскрываем РЕАЛЬНЫЕ ключи
            # capture: top-level + psyche (тик 1 vs финал) +全文-scan маски
            "fin_keys": sorted(fin.keys()),
            "psyche_keys": sorted(psyche.keys()),
            "psyche_keys_t1": sorted((first_g.get("psyche") or {}).keys()),
            "mask_in_dump": "behavior_mask" in json.dumps(fin, ensure_ascii=False),
        }
        results.append(rec)
        print(f"[LAB-R002-RUN] {json.dumps(rec, ensure_ascii=False)}")

    out = _ROOT / "reports" / "lab_r002_fear_scale_results.json"
    out.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[LAB-R002] PROTOCOL WRITTEN: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())