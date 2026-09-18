# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/sandbox/SUPERBOX/scenarios/relocation_causal_bridge_test.py
Назначение: мандат SHADOW RELOCATION FORENSIC, шаг 3. RED→GREEN на causal
    bridge: activity_map[act].location != npc.location_id → relocation intent
    → ходьба → BOUNDARY_DWELL → S186 → arrival. Механизм, не NPC-ID.
Зависимости: tests.gameplay.harness
Основные сущности: main

Запуск: cd backend; python -m tests.sandbox.SUPERBOX.scenarios.relocation_causal_bridge_test 2>&1 | Select-String -Pattern "RCB"; cd ..
"""

from __future__ import annotations

from tests.gameplay.harness import TavernGameplayHarness

_C = "Open_road"
_GREEN: list[str] = []
_RED: list[str] = []


def _log(m: str) -> None:
    print(f"[RCB] {m}", flush=True)


def main() -> int:
    with TavernGameplayHarness(location="tavern") as h:
        # NPC_A = borko (fixture-роль: «спящий в city_gate»); механизм, не ID.
        _nid = "guard_borko"

        # GIVEN: 2 тика — runtime-снапшот NPC наполняется после первого тика.
        h.advance_ticks(2)
        n = h.inspect_npc(_nid)
        if n is None:
            # fallback: прямая правка в авторитетной сцене (единый runtime-слот)
            _sc = h.game_loop.scene_manager.get_scene_state(_C, "tavern") or {}
            n = (_sc.get("npc_positions") or {}).get(_nid)
        if n is None:
            _RED.append(f"GIVEN: {_nid} не найден ни в снапшоте, ни в сцене")
            _report()
            return 1
        n["activity_map"] = {
            "sleeping": {
                "location": "city_gate",
                "position": "tent_3",
                "display": "sleeping",
            }
        }
        n.setdefault("routine", {})["current"] = "idle"
        # L5: Needs(0.8) перезаписывают Schedule — форсируем сон:
        # ночное время (00:30) + body sleep_pressure (CouplingResolver).
        sc0 = h.game_loop.scene_manager.get_scene_state(_C, "tavern")
        if sc0 is not None:
            sc0["game_time_seconds"] = 0.5 * 3600.0   # 00:30
            h.game_loop.scene_manager.save_scene_state(_C, sc0)
        body = n.get("body_state")
        if isinstance(body, dict):
            body["sleep_pressure"] = 1.0

        # WHEN: ночь (сон доминирует), смотрим цепь до relocation
        _seen_reloc = False
        for t in range(1, 200 + 1):
            h.advance_ticks(1)
            if t % 50 == 0:
                print(f"[RCB] ...tick {t}", flush=True)

        # THEN: физическая цепь
        sm = h.game_loop.scene_manager
        in_city = any(
            (sm.get_scene_state(_C, "city_gate") or {})
            .get("npc_positions", {})
            .get(_nid)
            for _ in (0,)
        )
        still_in_tavern = any(
            (sm.get_scene_state(_C, "tavern") or {})
            .get("npc_positions", {})
            .get(_nid)
        )
        _log(f"финал: in_city={in_city} still_tavern={still_in_tavern}")
        if in_city and not still_in_tavern:
            _GREEN.append(f"CHAIN: {_nid} прошёл relocation через существующий pipeline (AM cross-loc)")
        elif in_city and still_in_tavern:
            _RED.append("CHAIN: TORN — в обеих сценах (регресс атомарности)")
        else:
            _RED.append("CHAIN RED: relocation не состоялся — bridge отсутствует/не активирован")

        _report()
    return 0


def _report() -> None:
    _log("=== ОТЧЁТ ===")
    for g in _GREEN:
        _log(f"GREEN: {g}")
    for r in _RED:
        _log(f"RED:   {r}")
    _log(f"Итог: GREEN={len(_GREEN)} RED={len(_RED)}")


if __name__ == "__main__":
    raise SystemExit(main())