# path: backend/tests/sandbox/SUPERBOX/scenarios/bm_aprime_offline.py
# Назначение: A' — офлайн-анализ СОХРАНЁННЫХ данных факториала (вердикт П4а):
#   новый рантайм не запускается, отсутствующие компоненты не фабрикуются.
#   Отчёт заканчивается на последнем проверяемом звене цепи.
# Зависимости: ebm1_passport (только sha256_file), reports/bm_factorial_ebm1.json
#   и iso-артефакты, закоммиченные в 318b33e6. Запуск из корня репо (урок №4).
# Основные сущности: аудит 13 звеньев; inversion_ticks; per_intent_means;
#   B-A дельты (наблюдательные); verdict о вычислимости контрфактов.
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ebm1_passport import sha256_file

_SRC = Path("reports/bm_factorial_ebm1.json")
_ISO = [
    Path("reports/bm_factorial_iso_CELL-" + c + ".json")
    for c in ("A_f0_tm60", "B_f70_tm60", "C_f0_tp50", "D_f70_tp50")
]
_INCONSISTENT = ("attack", "intimidate", "warn")
_CONSISTENT = ("observe", "talk", "idle")
_OUT = Path("reports/bm_aprime_offline.json")

_CHAIN_AUDIT = [
    {"stage": 1, "name": "base components", "status": "NOT_CAPTURED",
     "note": "per-tick base не сохранён (DIAG покрывает только attack/flee)"},
    {"stage": 2, "name": "mask multiplier", "status": "STATIC_KNOWN",
     "note": "0.155/1.21 при intensity=0.7; CONSUME-unit; вклад не сохранён"},
    {"stage": 3, "name": "noise draw", "status": "NOT_CAPTURED",
     "note": "амплитуда ±0.10 статична; реализация не сохранена"},
    {"stage": 4, "name": "inertia/exhaustion", "status": "NOT_CAPTURED", "note": ""},
    {"stage": 5, "name": "clamp [-2,3]", "status": "STATIC_KNOWN",
     "note": "decision_hub:1134"},
    {"stage": 6, "name": "PHYSICS_OF_POWER", "status": "NOT_CAPTURED", "note": ""},
    {"stage": 7, "name": "apply_modifiers (9)", "status": "NOT_CAPTURED", "note": ""},
    {"stage": 8, "name": "reflex constraints", "status": "NOT_CAPTURED", "note": ""},
    {"stage": 9, "name": "feasibility (O-R2)", "status": "NOT_CAPTURED", "note": ""},
    {"stage": 10, "name": "commitment bonus/cost", "status": "NOT_CAPTURED", "note": ""},
    {"stage": 11, "name": "argmax winner", "status": "CAPTURED",
     "note": "intent_seq в iso-артефактах (30 тиков)"},
    {"stage": 12, "name": "hysteresis gate", "status": "NOT_CAPTURED",
     "note": "исход наблюдаем через intent_seq"},
    {"stage": 13, "name": "final scores", "status": "CAPTURED",
     "note": "scores_raw; fear-70 клетки до тика 15 (empty_ticks)"},
]


def _mean(vals: List[float]) -> Optional[float]:
    return sum(vals) / len(vals) if vals else None


def _inversion_ticks(scores_raw: List[Dict[str, Any]], window: List[int]) -> List[int]:
    out: List[int] = []
    for t in window:
        s = scores_raw[t - 1]
        if not s:
            continue
        inc = [s[k] for k in _INCONSISTENT if k in s]
        con = [s[k] for k in _CONSISTENT if k in s]
        if inc and con and _mean(inc) > _mean(con):
            out.append(t)
    return out


def _per_intent(scores_raw: List[Dict[str, Any]], window: List[int]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for intent in _INCONSISTENT + _CONSISTENT:
        vals = [
            s[intent]
            for t in window
            if (s := scores_raw[t - 1]) and intent in s
        ]
        out[intent] = {
            "mean": round(_mean(vals), 6) if vals else None,
            "present_ticks": len(vals),
        }
    return out


def main() -> int:
    data = json.loads(_SRC.read_text(encoding="utf-8"))
    window = data["common_window"]
    analysis: Dict[str, Any] = {}
    for cell, m in data["cells"].items():
        raw = m["scores_raw"]
        analysis[cell] = {
            "y1_common": data["y1_common"][cell],
            "inversion_ticks": _inversion_ticks(raw, window),
            "per_intent_common": _per_intent(raw, window),
            "empty_ticks": m["empty_ticks"],
        }

    deltas: Dict[str, Optional[float]] = {}
    for intent in _INCONSISTENT + _CONSISTENT:
        a = analysis["CELL-A_f0_tm60"]["per_intent_common"][intent]["mean"]
        b = analysis["CELL-B_f70_tm60"]["per_intent_common"][intent]["mean"]
        deltas[intent] = round(b - a, 6) if (a is not None and b is not None) else None

    report = {
        "spec": "E-BM1 A' offline (вердикт П4а): без нового рантайма и фабрикации",
        "source_artifacts": {
            "factorial": {"path": str(_SRC), "sha256": sha256_file(str(_SRC))},
            "iso": [
                {"path": str(p), "sha256": sha256_file(str(p))}
                for p in _ISO if p.exists()
            ],
        },
        "common_window": window,
        "chain_audit": _CHAIN_AUDIT,
        "cells": analysis,
        "b_minus_a_per_intent_common": deltas,
        "b_minus_a_caveat": (
            "наблюдательный контраст: конфаунд страха не устранён "
            "(B отличается от A и маской, и fear)"
        ),
        "computability_verdict": {
            "per_tick_counterfactual": (
                "НЕ вычислим офлайн: требует per-tick base и вклад маски "
                "(components_trace не захвачен этапом B1)"
            ),
            "established_offline": [
                "финальный уровень: классовая инверсия в B (inversion_ticks) "
                "при её отсутствии в A/C/D",
                "пер-интентная структура лифта B-vs-A (наблюдательно)",
            ],
            "h1_requirement": (
                "захват components_trace (per intent per tick, целевой NPC) "
                "расширением execute-тапа в H1-харнессе — координационное окно"
            ),
        },
        "applicability": {
            "E4": "числа собраны в registry-blind/R-эра условиях; кросс-эра "
                  "сравнения условны",
            "tier_rule": "скоровые наблюдения не равны поведенческим выводам; "
                         "intent-ярус = intent_seq (iso-артефакты)",
        },
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for cell, a in analysis.items():
        print("[A'-OFF] " + cell + ": y1_common=" + str(a["y1_common"])
              + " inversion_ticks=" + str(a["inversion_ticks"]))
    print("[A'-OFF] B-A per-intent: " + json.dumps(deltas, ensure_ascii=False))
    print("[A'-OFF] report=" + str(_OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())