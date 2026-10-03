"""
path: backend/tests/sandbox/lab_r003_diff_analysis.py
Назначение: post-hoc дифф протокола R003 (reports/lab_r003_gc11_results.json):
    где именно миры A/B расходятся на тике 5; полный dict-дифф merchant_goran
    по всем 30 тикам. Только чтение артефакта, ноль прогонов (Закон XI).
Основные сущности: main
Запуск: python backend/tests/sandbox/lab_r003_diff_analysis.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_PROTO = _ROOT / "reports" / "lab_r003_gc11_results.json"
_NPC = "merchant_goran"


def _find(npcs: list, nid: str) -> dict | None:
    for n in npcs:
        if isinstance(n, dict) and (n.get("id") or n.get("npc_id")) == nid:
            return n
    return None


def _diff(a: object, b: object, path: str = "") -> list[str]:
    if type(a) is not type(b):
        return [f"{path}: type {type(a).__name__} vs {type(b).__name__}"]
    if isinstance(a, dict):
        out: list[str] = []
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}.{k}: only-B={b[k]!r}")
            elif k not in b:
                out.append(f"{path}.{k}: only-A={a[k]!r}")
            else:
                out.extend(_diff(a[k], b[k], f"{path}.{k}"))
        return out
    if isinstance(a, list):
        out = [] if len(a) == len(b) else [f"{path}: len {len(a)} vs {len(b)}"]
        for i, (x, y) in enumerate(zip(a, b)):
            out.extend(_diff(x, y, f"{path}[{i}]"))
        return out
    return [] if a == b else [f"{path}: A={a!r} B={b!r}"]


def main() -> int:
    data = json.loads(_PROTO.read_text(encoding="utf-8"))
    runs = {r["run_id"]: r for r in data["runs"]}
    a, b = runs["GC11-A"], runs["GC11-B"]

    print("=== WORLD DIFF A vs B (первый разошедшийся тик) ===")
    for i, (wa, wb) in enumerate(zip(a["world_timeline"], b["world_timeline"])):
        if wa == wb:
            continue
        print(f"tick={i + 1}")
        shown = 0
        for na in wa:
            nid = na.get("id") or na.get("npc_id") if isinstance(na, dict) else None
            nb = _find(wb, nid) if nid else None
            d = _diff(na, nb) if nb is not None else ["MISSING in B"]
            if d and shown < 12:
                for line in d[:4]:
                    print(f"  npc={nid} {line}")
                if len(d) > 4:
                    print(f"  npc={nid} ... ещё {len(d) - 4}")
                shown += 1
        break

    print("=== GORAN: полный dict-дифф A vs B (все тики) ===")
    any_diff = False
    for i, (wa, wb) in enumerate(zip(a["world_timeline"], b["world_timeline"])):
        ga, gb = _find(wa, _NPC), _find(wb, _NPC)
        if ga is None or gb is None:
            print(f"tick={i + 1}: goran отсутствует")
            any_diff = True
            continue
        d = _diff(ga, gb)
        if d:
            any_diff = True
            print(f"tick={i + 1}: {len(d)} расхождений")
            for line in d[:6]:
                print(f"  {line}")
    if not any_diff:
        print("goran: полный dict идентичен A vs B на всех 30 тиках")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())