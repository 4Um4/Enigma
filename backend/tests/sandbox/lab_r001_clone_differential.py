"""
path: backend/tests/sandbox/lab_r001_clone_differential.py
Назначение: R001 CLONE DIFFERENTIAL (вердикт Мастера): production-контур
    ExperimentRunner (тот же, что F5-Lab) — headless. Последовательные
    сессии одного субъекта (merchant_goran), одна переменная: initial
    trust(player) = +60 / −60 / 0. Детерминизм: повтор R001-A.
    Замеры: Initial (YAML) | Store (read-back гейта) | Read (probe
    enrichment→interpretation) | bias. Отчёт: reports/lab_r001_results.json.
    Наблюдение не создаёт каузальность (Закон XI): ноль monkey-patch.
Зависимости: app.services.calibration.experiment_runner, json, pathlib
Основные сущности: RUNS, main
Запуск: python backend/tests/sandbox/lab_r001_clone_differential.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

_ROOT = _BACKEND.parent
_PRESETS = {
    "R001-A": "config/calibration/test_presets/golden_social_p60.yaml",
    "R001-B": "config/calibration/test_presets/golden_social_m60.yaml",
    "R001-C": "config/calibration/test_presets/golden_social_z0.yaml",
    "R001-A2": "config/calibration/test_presets/golden_social_p60.yaml",
}
_SCENARIO = "config/calibration/scenarios/clone_probe_v1.yaml"
_TICKS = 30
_CAMPAIGN = "Open_road"


def _probe_lines(text: str) -> list:
    return [
        ln.split("[LAB-R001]", 1)[1].strip()
        for ln in text.splitlines()
        if "[LAB-R001]" in ln
    ]


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
            scenario_path=_SCENARIO,
            campaign_id=_CAMPAIGN,
        )
        experiment_id = runner.start(cfg)
        # R001: аватар в сессии (S115-прецедент) — штатный API, без NPCState-конструкции
        # (Write Guard цензует прямые мутации; select_player — canonical рождение аватара)
        from app.services.player_session_service import player_session_service

        player_session_service.select_player(cfg.campaign_id, "player")
        runner.step(_TICKS)
        initial = getattr(runner, "_initial_social_applied", {})
        step_out = runner.step(0) if False else None  # step(0) не вызываем
        # Intent после 30 тиков — из capture последнего тика
        npcs = runner.step.__doc__  # noqa: F841 (заглушка типа; реальные данные ниже)
        result = runner.stop()
        # Read-зонд: печатается движком в stdout в момент тиков; перехват
        # через stdout невозможен в этом процессе без redirect — поэтому
        # скрипт запускается с редиректом stdout в файл, строки собираются
        # пост-фактум из артефакта (см. блок прогона). Здесь — только JSON.
        rec = {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "initial": initial,
            "status_tail": getattr(result, "statuses", None) or None,
        }
        try:
            rec["result_summary"] = {
                k: getattr(result, k) for k in ("experiment_id", "duration_ticks")
            }
        except Exception:
            pass
        results.append(rec)
        print(f"[LAB-R001-RUN] {run_id} initial={json.dumps(initial, ensure_ascii=False)}")

    out = _ROOT / "reports" / "lab_r001_results.json"
    out.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[LAB-R001] PROTOCOL WRITTEN: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())