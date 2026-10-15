# path: backend/tests/sandbox/SUPERBOX/scenarios/bm_factorial_test.py
# Назначение: E-BM1 v1.0 §2 — факториал 2×2 (fear × trust), симметричный
#   interaction-контраст, детерминизм-гейт §4 (2 повтора), артефакты §4
#   (HEAD, SHA-256 пресетов/сценария, env-снимок). Production не трогается.
# Зависимости: behavior_mask_closure_test (реюз _run_leg/тапов, read-only),
#   ExperimentRunner (прод-путь, без правок).
# Основные сущности: 4 клетки × 2 повтора; Y1 (D-гэп, окно 2..30 — поправка
#   SPEC §2.3), Y2 (доля победителей несовместимого класса), маск-активность;
#   Δ_int = [Y(70,-60) - Y(70,+50)] - [Y(0,-60) - Y(0,+50)].
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parents[3]  # scenarios -> SUPERBOX -> sandbox -> tests -> backend
for _p in (str(_HERE), str(_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import behavior_mask_closure_test as _donor  # noqa: E402

# Клетки факториала: A=(0,-60) B=(70,-60) C=(0,+50) D=(70,+50).
# A/B — перепрогон существующих пресетов на текущем HEAD (уточнение A:
# «прочее фиксируется» = один HEAD на все клетки; блоб-клетки 6cfee64f
# не смешиваются). C/D — новые пресеты (коммит b186c389).
_CELLS: Dict[str, str] = {
    "CELL-A_f0_tm60": "config/calibration/test_presets/golden_fear_f0.yaml",
    "CELL-B_f70_tm60": "config/calibration/test_presets/golden_fear_f70.yaml",
    "CELL-C_f0_tp50": "config/calibration/test_presets/golden_fear_f0_trustp50.yaml",
    "CELL-D_f70_tp50": "config/calibration/test_presets/golden_fear_f70_trustp50.yaml",
}
# Единственное вмешательство в донора: расширить набор score-ног, чтобы все
# 4 клетки получили execute-tap (scores_per_tick). Файл донора не изменяется.
_donor._SCORE_LEGS = set(_donor._SCORE_LEGS) | set(_CELLS)

_INCONSISTENT = ("attack", "intimidate", "warn")
_CONSISTENT = ("observe", "talk", "idle")
_WINDOW_FROM = 2  # тик 1 = до _apply_initial_social: общий базлайн всех клеток
# v1.0.1: параметры клеток — в отчёте (условие вердикта: клетка/окно/пропуски
# сохранены в артефакте; сырые пер-тиковые данные — scores_raw).
_CELLS_CONFIG: Dict[str, Dict[str, Any]] = {
    "CELL-A_f0_tm60": {"preset": _CELLS["CELL-A_f0_tm60"], "fear": 0.0, "trust": -60.0},
    "CELL-B_f70_tm60": {"preset": _CELLS["CELL-B_f70_tm60"], "fear": 70.0, "trust": -60.0},
    "CELL-C_f0_tp50": {"preset": _CELLS["CELL-C_f0_tp50"], "fear": 0.0, "trust": 50.0},
    "CELL-D_f70_tp50": {"preset": _CELLS["CELL-D_f70_tp50"], "fear": 70.0, "trust": 50.0},
}
_REPS = 2
_REPORT = Path("reports") / "bm_factorial_ebm1.json"


def _d_gap(scores: Dict[str, Any]) -> Optional[float]:
    inc = [scores[k] for k in _INCONSISTENT if k in scores]
    con = [scores[k] for k in _CONSISTENT if k in scores]
    if not inc or not con:
        return None
    return (sum(inc) / len(inc)) - (sum(con) / len(con))


def _cell_metrics(rec: Dict[str, Any]) -> Dict[str, Any]:
    spt = rec.get("scores_per_tick") or []
    fp = rec.get("fingerprint") or []
    mpt = rec.get("mask_per_tick") or []
    y1_vals: List[float] = []
    y1_masked: List[float] = []
    y2_hit = 0
    y2_total = 0
    mask_ticks = 0
    for idx in range(len(spt)):
        if idx + 1 < _WINDOW_FROM:
            continue
        masked = (mpt[idx] if idx < len(mpt) else None) not in (None, "none")
        if masked:
            mask_ticks += 1
        g = _d_gap(spt[idx] or {})
        if g is not None:
            y1_vals.append(g)
            if masked:
                y1_masked.append(g)
        intent = fp[idx].get("intent") if idx < len(fp) else None
        if intent is not None:
            y2_total += 1
            if intent in _INCONSISTENT:
                y2_hit += 1
    # v1.0.1: пропуски и пер-тиковые гэпы — явные поля (пустой скор != нулевой
    # скор; empty_ticks принципиальны по вердикту).
    empty_ticks = [i + 1 for i, s in enumerate(spt) if not s]
    gaps_per_tick = [
        {"tick": i + 1, "gap": round(g, 6)}
        for i, g in ((i, _d_gap(spt[i] or {})) for i in range(len(spt)))
        if i + 1 >= _WINDOW_FROM and g is not None
    ]
    return {
        "y1_window": round(sum(y1_vals) / len(y1_vals), 6) if y1_vals else None,
        "y1_masked": round(sum(y1_masked) / len(y1_masked), 6) if y1_masked else None,
        "y2_share": round(y2_hit / y2_total, 6) if y2_total else None,
        "mask_ticks": mask_ticks,
        "ticks_scored": len(y1_vals),
        "empty_ticks": empty_ticks,
        "gaps_per_tick": gaps_per_tick,
        "intent_seq": [f.get("intent") for f in fp],
        "mask_seq": list(mpt),
        "scores_raw": spt,
    }


def _interaction(cells: Dict[str, Dict[str, Any]], key: str) -> Optional[float]:
    a = cells["CELL-A_f0_tm60"].get(key)
    b = cells["CELL-B_f70_tm60"].get(key)
    c = cells["CELL-C_f0_tp50"].get(key)
    d = cells["CELL-D_f70_tp50"].get(key)
    if None in (a, b, c, d):
        return None
    return round((b - d) - (a - c), 6)


def _interaction_vals(vals: Dict[str, Optional[float]]) -> Optional[float]:
    """v1.0.1: симметричный контраст по готовым пер-клеточным значениям."""
    a = vals.get("CELL-A_f0_tm60")
    b = vals.get("CELL-B_f70_tm60")
    c = vals.get("CELL-C_f0_tp50")
    d = vals.get("CELL-D_f70_tp50")
    if None in (a, b, c, d):
        return None
    return round((b - d) - (a - c), 6)


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001 — артефакт-метаданные, не симуляция
        return "unavailable"


def main() -> int:
    artifacts = {
        "head": _git_head(),
        "python": sys.version.split()[0],
        "env": {k: os.environ.get(k) for k in ("COGNITION_DIAG", "R2_DIAG", "N18_EXP")},
        "sha256": {
            "scenario": _sha256(str(Path(__file__).resolve())),
            **{cell: _sha256(p) for cell, p in _CELLS.items()},
        },
        "donor_sha256": _sha256(str(Path(_donor.__file__).resolve())),
    }

    reps: Dict[str, List[Dict[str, Any]]] = {c: [] for c in _CELLS}
    for cell_id, preset in _CELLS.items():
        for rep in range(_REPS):
            rec, _fin = _donor._run_leg(cell_id, preset, True)
            m = _cell_metrics(rec)
            reps[cell_id].append(m)
            print(
                f"[BM-FACTORIAL] {cell_id} rep{rep + 1}: "
                f"y1={m['y1_window']} y1_masked={m['y1_masked']} "
                f"y2={m['y2_share']} mask_ticks={m['mask_ticks']}"
            )

    determinism = {
        c: bool(
            ms[0]["y1_window"] == ms[1]["y1_window"]
            and ms[0]["y2_share"] == ms[1]["y2_share"]
            and ms[0]["mask_ticks"] == ms[1]["mask_ticks"]
            and ms[0]["intent_seq"] == ms[1]["intent_seq"]
            and ms[0]["mask_seq"] == ms[1]["mask_seq"]
        )
        for c, ms in reps.items()
    }
    cells = {
        c: {k: v for k, v in ms[0].items() if k not in ("intent_seq", "mask_seq")}
        for c, ms in reps.items()
    }
    # v1.0.1: канонический контраст — ОБЩЕЕ покрытое окно всех клеток
    # (средние на разных окнах несравнимы без оговорки — вердикт В2).
    def _covered(scores_raw: List[Dict[str, Any]]) -> set:
        return {
            i + 1
            for i, s in enumerate(scores_raw)
            if i + 1 >= _WINDOW_FROM and s and _d_gap(s) is not None
        }

    common_window = (
        sorted(set.intersection(*(_covered(ms[0]["scores_raw"]) for ms in reps.values())))
        if reps
        else []
    )
    y1_common: Dict[str, Optional[float]] = {}
    y2_common: Dict[str, Optional[float]] = {}
    for c, ms in reps.items():
        spt = ms[0]["scores_raw"]
        intents = ms[0]["intent_seq"]
        vals = [g for g in (_d_gap(spt[t - 1]) for t in common_window) if g is not None]
        y1_common[c] = round(sum(vals) / len(vals), 6) if vals else None
        hits = sum(
            1
            for t in common_window
            if t - 1 < len(intents) and intents[t - 1] in _INCONSISTENT
        )
        y2_common[c] = round(hits / len(common_window), 6) if common_window else None

    interaction = {
        "y1_window": _interaction(cells, "y1_window"),
        "y2_share": _interaction(cells, "y2_share"),
        "y1_common": _interaction_vals(y1_common),
        "y2_common": _interaction_vals(y2_common),
    }
    # Семантика клеток: маска ожидается ТОЛЬКО в B (70,-60) — тройная
    # проверка контракта условий (код decision.py:214-227) на живом прогоне.
    mask_semantics = {
        "A_f0_tm60_no_mask": cells["CELL-A_f0_tm60"]["mask_ticks"] == 0,
        "B_f70_tm60_masked": cells["CELL-B_f70_tm60"]["mask_ticks"] > 0,
        "C_f0_tp50_no_mask": cells["CELL-C_f0_tp50"]["mask_ticks"] == 0,
        "D_f70_tp50_no_mask": cells["CELL-D_f70_tp50"]["mask_ticks"] == 0,
    }
    status = "OK" if all(determinism.values()) else "INVALID_DETERMINISM"

    report = {
        "spec": (
            "E-BM1 v1.0.1: канонический контраст — общее покрытое окно клеток "
            "(common_window); v1.0-метрики окна 2..30 сохранены как диагностические"
        ),
        "status": status,
        "artifacts": artifacts,
        "cells": cells,
        "determinism": determinism,
        "mask_semantics": mask_semantics,
        "interaction": interaction,
        "common_window": common_window,
        "y1_common": y1_common,
        "y2_common": y2_common,
        "cells_config": _CELLS_CONFIG,
        "interpretation": {
            "delta_int_status": (
                "наблюдаемый факториальный контраст скоров при выбранной метрике "
                "и окне; НЕ доказанный размер эффекта маски (страх/доверие "
                "действуют в немасочных каналах, их взаимодействие может быть "
                "нелинейным)"
            ),
            "score_coverage": (
                "empty_ticks = ограничение покрытия измерения, НЕ остановка "
                "поведения: intent-последовательности полные (30 тиков), "
                "скоровое окно короче; причина отсутствия скоров не "
                "идентифицирована (кандидат: релокация/транзит носителя)"
            ),
            "bd_caveat": (
                "B==D — совпадение трасс в двух РАЗНЫХ конфигурациях (маска "
                "при trust=-60 vs без маски при trust=+50): наблюдение "
                "неразличимости, НЕ причинное доказательство no-op; причинный "
                "контраст = парный прогон одной клетки маска on/off (B'-протокол)"
            ),
            "contrast": "D_int = [Y(70,-60) - Y(70,+50)] - [Y(0,-60) - Y(0,+50)]",
            "meaning": (
                "взаимодействие при заданных условиях; НЕ чистый причинный "
                "эффект маски (SPEC §8: немасочные fear-каналы логируются, "
                "но не устраняются)"
            ),
            "tiers": (
                "Y1 — диагностическая (скоры); Y2 — поведенческая (победитель); "
                "смешение ярусов запрещено (SPEC §3)"
            ),
        },
    }
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[BM-FACTORIAL] D_int(Y1)={interaction['y1_window']} "
          f"D_int(Y2)={interaction['y2_share']}")
    print(f"[BM-FACTORIAL] common_window={common_window} "
          f"D_int_common(Y1)={interaction['y1_common']} "
          f"D_int_common(Y2)={interaction['y2_common']}")
    print(f"[BM-FACTORIAL] determinism={determinism} mask_semantics={mask_semantics}")
    print(f"[BM-FACTORIAL] status={status} report={_REPORT}")
    # exit 1 только при INVALID детерминизма (дрейф окружения — не данные).
    return 0 if status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())