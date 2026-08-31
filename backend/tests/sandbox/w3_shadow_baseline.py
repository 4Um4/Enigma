"""
path: backend/tests/sandbox/w3_shadow_baseline.py
Назначение: GORAN beta G1 (ADR-O-373) — proof-of-innocence discovery-тени.
    A/B: W3_SHADOW_ENABLED=1 vs OFF, 200 idle-тиков, контур DriftLaboratory
    (прецедент commitment_baseline S215 — production-стек, изолированный
    temp-dir, БЕЗ прямого GameLoop-конструирования). Гипотеза: тень =
    орган восприятия возможностей, НЕ двигатель поведения — behavioral
    diff = 0. Допустимое исключение (S215): жизненный цикл llama-server.
    Оси сравнения: финальные позиции NPC / moved-множество / тики с
    traversals / терминальные commitment-статусы / real_errors / crash.
    Валидность: crash любого прогона = INVALID RUN (exit 2), не GREEN.
Зависимости: sys.path-bootstrap, collections.Counter, os,
    tests.sandbox.SUPERBOX.drift_laboratory (DriftConfig, DriftLaboratory)
Основные сущности: run_profile, compare_profiles, main

Запуск: cd backend; python -m tests.sandbox.w3_shadow_baseline; cd ..
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_ROOT / "backend"))

TICKS = 200
SHADOW_ENV = "W3_SHADOW_ENABLED"


def _snapshot_positions(scene: dict) -> dict:
    """S215-паттерн: nid -> (x, y) из npc_positions.local_position."""
    _out: dict = {}
    for _nid, _p in (scene.get("npc_positions") or {}).items():
        _lp = _p.get("local_position") or {}
        try:
            _out[_nid] = (
                round(float(_lp.get("x", 0.0)), 2),
                round(float(_lp.get("y", 0.0)), 2),
            )
        except (TypeError, ValueError):
            _out[_nid] = None
    return _out


def run_profile(label: str, shadow_on: bool) -> dict:
    """Один прогон: 200 idle-тиков в DriftLab-контуре (S215)."""
    if shadow_on:
        os.environ[SHADOW_ENV] = "1"
    else:
        os.environ.pop(SHADOW_ENV, None)

    from tests.sandbox.SUPERBOX.drift_laboratory import (
        DriftConfig,
        DriftLaboratory,
    )

    profile: dict = {"label": label, "crash": None, "real_errors": 0,
                     "first_error": None}
    lab = DriftLaboratory(DriftConfig())
    try:
        lab._setup()
    except Exception as _e:
        profile["crash"] = f"setup: {_e!r}"
        os.environ.pop(SHADOW_ENV, None)
        return profile
    try:
        scene = (
            lab._scene_manager.get_scene_state(
                lab.config.campaign_id, lab.config.location_id)
            or {}
        )
        before = _snapshot_positions(scene)

        ticks_with_traversals = 0
        max_trav = 0
        for _tick in range(1, TICKS + 1):
            try:
                lab._run_idle_tick_direct()
            except Exception as _e:
                # real crash — наблюдаемость, не глоток (S215-паттерн)
                profile["real_errors"] += 1
                if profile["first_error"] is None:
                    profile["first_error"] = f"{type(_e).__name__}: {_e}"
            scene = (
                lab._scene_manager.get_scene_state(
                    lab.config.campaign_id, lab.config.location_id)
                or {}
            )
            _travs = scene.get("active_traversals") or {}
            if _travs:
                ticks_with_traversals += 1
                max_trav = max(max_trav, len(_travs))

        after = _snapshot_positions(scene)
        terminals = [
            _t for _bucket in (scene.get("commitment_history") or {}).values()
            for _t in _bucket
        ]
        profile.update({
            "positions_after": after,
            "moved": sorted(_n for _n in before if before[_n] != after.get(_n)),
            "ticks_with_traversals": ticks_with_traversals,
            "max_trav": max_trav,
            "terminals_total": len(terminals),
            "status_counts": dict(
                Counter(_t.get("status") for _t in terminals)),
            "actives": len(scene.get("active_commitments") or {}),
        })
    except Exception as _e:
        profile["crash"] = f"run: {_e!r}"
    finally:
        try:
            lab._teardown()
        except Exception as _e:
            print(f"[W3_SHADOW_BASELINE] teardown warning ({label}): {_e}")
        os.environ.pop(SHADOW_ENV, None)
    return profile


def compare_profiles(a: dict, b: dict) -> list:
    """Diff по осям GORAN beta G1 (пусто = поведение идентично)."""
    _diffs: list = []
    for _key in ("crash", "real_errors", "ticks_with_traversals",
                 "max_trav", "terminals_total", "actives"):
        if a.get(_key) != b.get(_key):
            _diffs.append(f"{_key}: {a.get(_key)!r} vs {b.get(_key)!r}")
    if a.get("moved") != b.get("moved"):
        _diffs.append(f"moved: {a.get('moved')} vs {b.get('moved')}")
    if a.get("status_counts") != b.get("status_counts"):
        _diffs.append(
            f"status_counts: {a.get('status_counts')} "
            f"vs {b.get('status_counts')}")
    _pa = a.get("positions_after") or {}
    _pb = b.get("positions_after") or {}
    if set(_pa) != set(_pb):
        _diffs.append(f"NPC_SET: {sorted(set(_pa) ^ set(_pb))}")
    else:
        for _nid in sorted(_pa):
            if _pa[_nid] != _pb[_nid]:
                _diffs.append(
                    f"POSITION[{_nid}]: {_pa[_nid]} vs {_pb[_nid]}")
    return _diffs


def main() -> int:
    print(f"[W3_SHADOW_BASELINE] GORAN beta G1 v3 (контроль OFF-vs-OFF): "
          f"{TICKS} ticks x3")
    _a = run_profile("A/OFF", shadow_on=False)
    _b = run_profile("B/ON", shadow_on=True)
    _c = run_profile("C/OFF-control", shadow_on=False)  # дискриминатор фона
    for _p in (_a, _b, _c):
        print(f"[W3_SHADOW_BASELINE] {_p['label']}: crash={_p['crash']} "
              f"real_errors={_p['real_errors']} "
              f"npcs={len(_p.get('positions_after') or {})}")

    _invalid = [f"{_p['label']} crash={_p['crash']}"
                for _p in (_a, _b, _c) if _p["crash"] is not None]
    if _invalid:
        print(f"[W3_SHADOW_BASELINE] VERDICT: INVALID RUN — {_invalid}")
        return 2

    _diffs_ab = compare_profiles(_a, _b)   # кандидат теневого эффекта
    _diffs_ac = compare_profiles(_a, _c)   # фоновой недетерминизм
    print(f"[W3_SHADOW_BASELINE] DIFF(A|B)={len(_diffs_ab)} "
          f"DIFF(A|C)={len(_diffs_ac)}")
    for _d in _diffs_ab:
        print(f"  AB - {_d}")
    for _d in _diffs_ac:
        print(f"  AC - {_d}")

    if not _diffs_ab:
        print("[W3_SHADOW_BASELINE] VERDICT: GREEN — тень невидима "
              f"(фон: {'стабилен' if not _diffs_ac else 'нестабилен, но A==B'})")
        return 0
    if not _diffs_ac:
        print("[W3_SHADOW_BASELINE] VERDICT: RED — дрейф коррелирует "
              "с тенью при стабильном фоне; стоп, археология до ADR")
        return 1
    print("[W3_SHADOW_BASELINE] VERDICT: INCONCLUSIVE-AMBIENT — A≠C "
          "при обоих OFF: фоновой дрейф подтверждён, теневой вклад не "
          "выделяется; диапазонный критерий S216 / ретрансляция Мастеру")
    return 3


if __name__ == "__main__":
    sys.exit(main())