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
    import logging as _logging

    class _Col(_logging.Handler):
        def __init__(self) -> None:
            super().__init__(level=_logging.DEBUG)
            self.lines: list[str] = []

        def emit(self, record: _logging.LogRecord) -> None:
            try:
                m = record.getMessage()
                if any(
                    k in m
                    for k in ("LIFE_ENGINE", "SCHED_TRACE", "RELOCATE", "BOUNDARY_DWELL",
                              "INTENT_DEGRADE", "DIAG_GAP9", "DIAG_S140", "NEED_TRACE",
                              "cross-loc relocation", "ARBITER_REJECT")
                ) and ("borko" in m or "NEED_TRACE" in m):
                    self.lines.append(f"{record.levelname}|{m[:240]}")
            except Exception:  # noqa: S110
                pass

    _col = _Col()
    # Target: app.services (root не ловит app-логгеры — rcb2/rcb4 пустые
    # при живых RELOCATE в трассе; прецедент — shadow_relocation_forensic).
    _svc = _logging.getLogger("app.services")
    _svc.setLevel(_logging.DEBUG)
    _svc.addHandler(_col)
    # Полный лог в файл: DEBUG-строки (MOVEMENT_TRACE/BORKO_TRACE/GATE_B1_5)
    # нужны целиком, печать первых 25 маркеров обрезает картину.
    _fh = _logging.FileHandler("movement_debug.log", mode="w", encoding="utf-8")
    _fh.setLevel(_logging.DEBUG)
    _fh.setFormatter(_logging.Formatter("%(levelname)s|%(message)s"))
    _svc.addHandler(_fh)

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
        # МЕРЖ, не замена: конфиговый AM (guarding_gate→city_gate и пр.)
        # уже в runtime — инъекция только проверочной записи (мандат:
        # механизм data-driven, не NPC-ID; конфиг и так несёт cross-loc).
        n.setdefault("activity_map", {}).update({
            "sleeping": {
                "location": "city_gate",
                "position": "tent_3",
                "display": "sleeping",
            }
        })
        n.setdefault("routine", {})["current"] = "idle"
        # L5: Needs(0.8) перезаписывают Schedule — форсируем сон:
        # ночное время (00:30) + body sleep_pressure (CouplingResolver).
        sc0 = h.game_loop.scene_manager.get_scene_state(_C, "tavern")
        if sc0 is not None:
            # SPATIAL-KNOWLEDGE: schedule-резолвер читает
            # environment.time_of_day (_parse_game_time:187), не game_time_seconds.
            # Но Phase 0.5 перезаписывает время каждый тик — поэтому ставим
            # ОБА поля и НЕ save'им (обход чужого бага _cache_gen): сцена —
            # живой объект RAM, tick её прочтёт.
            sc0["game_time_seconds"] = 0.5 * 3600.0   # 00:30
            sc0.setdefault("environment", {})["time_of_day"] = "ночь"
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
        def _present(loc: str) -> bool:
            scene = sm.get_scene_state(_C, loc) or {}
            positions = scene.get("npc_positions") or {}
            return isinstance(positions, dict) and _nid in positions
        in_city = _present("city_gate")
        still_in_tavern = _present("tavern")
        _orch = h.game_loop._tick_orch
        _pt = getattr(_orch, "_pending_transfers", {})
        _log(f"финал: in_city={in_city} still_tavern={still_in_tavern} "
             f"pending={ {k: sorted(v.keys()) for k, v in _pt.items()} }")
        if in_city and not still_in_tavern:
            _GREEN.append(f"CHAIN: {_nid} прошёл relocation через существующий pipeline (AM cross-loc)")
        elif in_city and still_in_tavern:
            _RED.append("CHAIN: TORN — в обеих сценах (регресс атомарности)")
        else:
            _RED.append("CHAIN RED: relocation не состоялся — bridge отсутствует/не активирован")
        _log(f"--- маркеров собрано: {len(_col.lines)} ---")
        for _l in _col.lines[:25]:
            _log(_l)
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