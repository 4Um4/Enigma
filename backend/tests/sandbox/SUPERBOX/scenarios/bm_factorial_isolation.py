# path: backend/tests/sandbox/SUPERBOX/scenarios/bm_factorial_isolation.py
# Назначение: E-BM1 §4-инцидент — изоляция клетки от префикса: ОДНА клетка,
#   свежий процесс, ноль предшествующих ног. Дискриминация H-D2 vs H-D3.
#   Вызов: python bm_factorial_isolation.py <CELL-ключ>. x1 повтор (кросс-
#   процессная детерминированность контура доказана E7).
# Зависимости: bm_factorial_test (реюз _CELLS/_cell_metrics/_run_leg/_sha256/
#   _git_head; его импорт применяет патч _SCORE_LEGS донора — run_id клетки
#   обязан быть ровно ключом клетки, иначе etap не повесится).
# Основные сущности: метрики y1_window/y1_masked/y2/mask_ticks; артефакт
#   reports/bm_factorial_iso_<key>.json со штампом HEAD+SHA-256 (урок щита).
from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parents[3]  # scenarios -> SUPERBOX -> sandbox -> tests -> backend
for _p in (str(_HERE), str(_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bm_factorial_test as _f  # noqa: E402  (импорт безопасен: __main__-гварды)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in _f._CELLS:
        print("usage: bm_factorial_isolation.py <" + "|".join(_f._CELLS) + ">")
        return 2
    key = sys.argv[1]
    # run_id = ровно ключ клетки: членство в _SCORE_LEGS (патч факториала)
    # вешает execute-tap -> scores_per_tick. Суффикс _ISO сломал бы членство.
    rec, _fin = _f._donor._run_leg(key, _f._CELLS[key], True)
    m = _f._cell_metrics(rec)
    report = {
        "cell": key,
        "rep": 1,
        "artifacts": {
            "head": _f._git_head(),
            "sha256": {
                "isolation": _f._sha256(str(Path(__file__).resolve())),
                "factorial": _f._sha256(str(Path(_f.__file__).resolve())),
                "preset": _f._sha256(_f._CELLS[key]),
            },
        },
        "metrics": {k: v for k, v in m.items() if k != "scores_raw"},
    }
    out = Path("reports") / ("bm_factorial_iso_" + key + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[BM-ISO] " + key + " alone: y1=" + str(m["y1_window"])
          + " y1_masked=" + str(m["y1_masked"])
          + " y2=" + str(m["y2_share"])
          + " mask_ticks=" + str(m["mask_ticks"]) + " -> " + str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())