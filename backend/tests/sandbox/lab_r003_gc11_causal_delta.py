"""
path: backend/tests/sandbox/lab_r003_gc11_causal_delta.py
Назначение: R003 GC-11 CAUSAL DELTA (L3-gate RE-01, roadmap §0.2): живой
    harness «event → V2-RAM non-zero delta → следующий выбор NPC сдвинут».
    Production-контур ExperimentRunner (тот же, что R001/R002) — headless,
    MockProvider, temp-saves (изоляция start()), init_campaign активен
    (P2-мост компилятора жив, S220-прецедент).
    Матрица: GC11-A (MOVE-only@15, контроль) / GC11-B (HELP@5 + MOVE@15) /
    GC11-B2 (повтор B — детерминизм). Единственная переменная A↔B — HELP
    (тик 5: trust+20 через компилятор → WriteGate → V2-RAM, K=5).
    Три звена критерия:
      L1 store_delta — V2-факт (rel_store.get_pair): trust 0→20 после тика 5
                      в B; отсутствие той же дельты в A (тот же тик);
      L2 cache_hydr  — relationship_cache["player"] у NPC в per-tick
                      captures различается A vs B после тика 5;
      L3 choice_shift— первый тик расхождения миров A vs B (полный срез
                      npc-lists) и траектории ключевого NPC; санити:
                      тики 1..4 (до HELP) обязаны совпадать.
    Вердикт: GREEN = L1+L2+L3+санити+B≡B2. L1+L2 при L3-identical =
    GAP-находка (RE-D2-класс нулевой игровой реальности — легитимный
    исход гейта, не провал инструмента).
    Наблюдение не создаёт каузальность (Закон XI): ноль monkey-patch;
    приватные атрибуты — лабораторный прецедент _apply_initial_social.
Зависимости: app.services.calibration.experiment_runner, json, pathlib
Основные сущности: _PRESET, _SCENARIOS, main
Запуск: python backend/tests/sandbox/lab_r003_gc11_causal_delta.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND))

_ROOT = _BACKEND.parent
_PRESET = "config/calibration/test_presets/golden_social_z0.yaml"
_SCENARIOS = {
    "GC11-A": "config/calibration/scenarios/gc11_move_only.yaml",
    "GC11-B": "config/calibration/scenarios/gc11_help_move.yaml",
    "GC11-B2": "config/calibration/scenarios/gc11_help_move.yaml",
}
_TICKS = 30
_CAMPAIGN = "Open_road"
_NPC = "merchant_goran"
_K_HELP = 5  # тик HELP-интервенции (1-based)


def _norm_pos(pos: object) -> object:
    """Нормализация позиции к JSON-сравнимому виду (dict {"x","y"} / tuple)."""
    if isinstance(pos, dict):
        return [pos.get("x"), pos.get("y")]
    if isinstance(pos, (list, tuple)):
        return list(pos)
    return pos


def _npc_sample(npc_dict: dict) -> dict:
    """Срез ключевого NPC из capture: выбор-наблюдаемые + rc-гидратация."""
    psyche = npc_dict.get("psyche", {}) or {}
    rc_player = (npc_dict.get("relationship_cache", {}) or {}).get("player", {})
    return {
        "activity": npc_dict.get("activity", ""),
        "local_position": _norm_pos(npc_dict.get("local_position", npc_dict.get("position"))),
        "velocity": list(npc_dict.get("velocity", []) or []),
        "will_state": psyche.get("state", ""),
        "stress": psyche.get("stress"),
        "last_intent_change": npc_dict.get("last_intent_change"),
        "intent_progress_ticks": npc_dict.get("intent_progress_ticks"),
        "rc_player": dict(rc_player),
    }


def _find_npc(npcs: list) -> dict:
    for n in npcs:
        if isinstance(n, dict) and (n.get("id") or n.get("npc_id")) == _NPC:
            return n
    return {}


def main() -> int:
    import logging

    logging.getLogger().setLevel(logging.ERROR)

    from app.services.calibration.experiment_runner import (
        ExperimentConfig,
        ExperimentRunner,
    )

    results = []
    for run_id, scenario in _SCENARIOS.items():
        runner = ExperimentRunner()
        cfg = ExperimentConfig(
            preset_path=_PRESET,
            duration_ticks=_TICKS,
            scenario_path=scenario,
            campaign_id=_CAMPAIGN,
        )
        experiment_id = runner.start(cfg)
        from app.services.player_session_service import player_session_service

        player_session_service.select_player(cfg.campaign_id, "player")

        initial = getattr(runner, "_initial_social_applied", {})
        store_timeline: list = []
        world_timeline: list = []
        goran_timeline: list = []
        for _t in range(_TICKS):
            step = runner.step(1)
            game_loop = runner._active_game_loop  # noqa: SLF001 (лабораторный прецедент)
            rel_store = getattr(game_loop, "_rel_store", None)
            pair: dict = {}
            if rel_store is not None and hasattr(rel_store, "get_pair"):
                pair = rel_store.get_pair(cfg.campaign_id, _NPC, "player") or {}
            store_timeline.append({"tick": _t + 1, "pair": dict(pair)})
            npcs = step.get("npcs", []) or []
            world_timeline.append(npcs)
            goran_timeline.append({"tick": _t + 1, "npc": _npc_sample(_find_npc(npcs))})

        result = runner.stop()
        results.append(
            {
                "run_id": run_id,
                "experiment_id": experiment_id,
                "preset": _PRESET,
                "scenario": scenario,
                "initial": initial,
                "store_timeline": store_timeline,
                "goran_timeline": goran_timeline,
                "world_timeline": world_timeline,
                "statuses_tail": (getattr(result, "statuses", None) or [])[-3:],
            }
        )
        _k_idx = _K_HELP - 1
        _pair_k = results[-1]["store_timeline"][_k_idx]["pair"]
        print(
            f"[LAB-R003-RUN] {run_id} scenario={Path(scenario).name} "
            f"store@{_K_HELP}={json.dumps(_pair_k, ensure_ascii=False)}"
        )

    # ── Вердикт по трём звеньям ──
    def _store_trust(run: dict, tick_idx: int) -> float:
        pair = run["store_timeline"][tick_idx]["pair"] or {}
        return float(pair.get("trust", 0.0) or 0.0)

    def _rc_trust(run: dict, tick_idx: int) -> float:
        npc = run["goran_timeline"][tick_idx]["npc"] or {}
        return float((npc.get("rc_player") or {}).get("trust", 0.0) or 0.0)

    a, b, b2 = results[0], results[1], results[2]

    # L1: V2-RAM non-zero delta после HELP (индекс 4 = тик 5) в B; нет в A
    l1_b_delta = _store_trust(b, 4) - _store_trust(b, 3)
    l1_a_delta = _store_trust(a, 4) - _store_trust(a, 3)
    l1 = {
        "B_delta_after_help": l1_b_delta,
        "A_delta_same_tick": l1_a_delta,
        "pass": abs(l1_b_delta) > 0.0 and abs(l1_a_delta) == 0.0,
    }

    # L2: гидратация rc у ключевого NPC различается A vs B после тика 5
    l2 = {
        "B_rc_after": _rc_trust(b, 5),
        "A_rc_after": _rc_trust(a, 5),
        "pass": _rc_trust(b, 5) != _rc_trust(a, 5),
    }

    # Санити-детерминизм: до HELP (тики 1..4) миры A и B совпадают
    pre_help_diverge: int | None = None
    for i in range(_K_HELP - 1):
        if a["world_timeline"][i] != b["world_timeline"][i]:
            pre_help_diverge = i + 1
            break

    # L3: первый тик расхождения миров A vs B + траектории ключевого NPC
    world_diverge: int | None = None
    for i in range(_TICKS):
        if a["world_timeline"][i] != b["world_timeline"][i]:
            world_diverge = i + 1
            break
    goran_diverge: int | None = None
    for i in range(_TICKS):
        if a["goran_timeline"][i] != b["goran_timeline"][i]:
            goran_diverge = i + 1
            break

    # Детерминизм: B ≡ B2 (полные мировые таймлайны)
    b_eq_b2 = b["world_timeline"] == b2["world_timeline"]

    l3_pass = (
        world_diverge is not None and world_diverge > _K_HELP
    ) or (goran_diverge is not None and goran_diverge > _K_HELP)

    verdict = {
        "L1_store_delta": l1,
        "L2_cache_hydr": l2,
        "sanity_pre_help_diverge_tick": pre_help_diverge,  # обязан быть None
        "L3_world_first_diverge_tick": world_diverge,
        "L3_goran_first_diverge_tick": goran_diverge,
        "determinism_B_eq_B2": b_eq_b2,
    }
    verdict["GREEN"] = bool(
        l1["pass"] and l2["pass"] and l3_pass and pre_help_diverge is None and b_eq_b2
    )
    if l1["pass"] and l2["pass"] and not l3_pass:
        verdict["GAP_DIAGNOSIS"] = (
            "RE-D2-класс: дельта в V2-RAM и гидратация кэша есть, "
            "следующий выбор NPC не сдвинут (нулевой игровой эффект)"
        )

    out = _ROOT / "reports" / "lab_r003_gc11_results.json"
    out.write_text(
        json.dumps({"verdict": verdict, "runs": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[LAB-R003] VERDICT: {json.dumps(verdict, ensure_ascii=False)}")
    print(f"[LAB-R003] PROTOCOL WRITTEN: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())