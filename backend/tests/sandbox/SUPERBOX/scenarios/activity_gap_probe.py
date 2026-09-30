# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/SUPERBOX/scenarios/activity_gap_probe.py
Назначение: Зонд v4 — Этап 1 директивы Мастера: контрфактический прогон
    Гейт① на guard_borko. Сравнивает:
      ФАКТ:  предикат N18 на источнике прода (life-кэш ctx.all_npcs_raw);
      КОНТРФАКТ: тот же предикат на актуальном NPCState.intent (SSOT).
    Контрфакт НЕ применяется к миру — только печатается (санкция).
    Обёртки: оригиналы вызываются ВСЕГДА, результат не меняется,
    restore в finally. Движение — публичный player_position.
Зависимости: game_loop_builder, ChatTurnRequest, decision_hub.
Запуск: env ставится файлом ДО app.* (default в коде не трогается).
"""

from __future__ import annotations

import asyncio
import math
import os
import shutil
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Dict, List

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))
_REPO = BACKEND_ROOT.parent
sys.path.insert(0, str(_REPO))
os.environ.setdefault("COGNITION_V0", "1")
os.environ.setdefault("N18_EXP", "1")
os.environ.setdefault("COGNITION_DIAG", "1")

from app.core.config import settings as _settings

_TEMP = tempfile.mkdtemp(prefix="gap_probe_v4_")
_SAVES = Path(_TEMP) / "saves"
if Path(_settings.saves_dir).exists():
    shutil.copytree(Path(_settings.saves_dir), _SAVES, dirs_exist_ok=True)
_settings.saves_dir = str(_SAVES)

import atexit

atexit.register(lambda: shutil.rmtree(_TEMP, ignore_errors=True))
_LLM_KILL = None
try:
    from scripts.llm_server_manager import kill_llama_server, start_llama_server

    if not start_llama_server():
        print("[PROBE] ⚠ LLM не поднялась")
    _LLM_KILL = kill_llama_server
    atexit.register(kill_llama_server)
except ModuleNotFoundError as _e:
    print(f"[PROBE] llm_manager: {_e}")

from app.models.schemas import ChatTurnRequest, PlayerAction
from app.services.game_loop_builder import build_game_loop

CAMPAIGN, LOCATION, WORLD = "Open_road", "tavern", "default"
TARGET = "guard_borko"
T_BASE, T_APPR, T_DECAY = 8, 12, 6
STEP, STOP = 1.2, 1.8

# SSOT-снимок intent'ов: пишет обёртка compute (npc → актуальный intent
# ПОСЛЕ решения текущего тика). Контрфакт читает последнее решение.
_SSOT: Dict[str, str] = {}
# Результаты сравнения предиката
_CMP: List[Dict[str, Any]] = []


def _xy(e):
    lp = (e or {}).get("local_position") or {}
    x, y = lp.get("x"), lp.get("y")
    return (float(x), float(y)) if isinstance(x, (int, float)) and isinstance(y, (int, float)) else None


def _scene(w):
    sm = getattr(getattr(w.game_loop, "_tick_orch", None), "_scene_manager", None)
    try:
        return sm.get_scene_state(CAMPAIGN, LOCATION) if sm else None
    except Exception:
        return None


def _cache_intent(w, npc) -> str:
    eng = w.game_loop._get_life_engine()
    st = next((s for s in (eng.get_npc_states(CAMPAIGN) or [])
               if isinstance(s, dict) and (s.get("id") or s.get("npc_id")) == npc), None)
    if st is None:
        return "<нет>"
    return str(getattr(st.get("intent"), "value", st.get("intent")) or "").lower()


def _gate_pred(intent_val: str, e: float, phase: str) -> bool:
    """READ-ONLY повтор предиката Гейт① (simulation.py:163-172) — без применения."""
    return (intent_val == "observe" and e >= 0.45
            and phase in ("oriented", "approaching", "near"))


def _install():
    from app.services.npc import decision_hub as _dh

    orig = _dh.DecisionHub.compute

    def _w(self, state, *a, __o=orig, **kw):
        _res = __o(self, state, *a, **kw)
        _SSOT[state.npc_id] = str(
            getattr(getattr(_res, "decision", None), "intent", "?")).lower().replace("intent.", "")
        return _res

    _dh.DecisionHub.compute = _w  # type: ignore[method-assign]
    return {"orig": orig, "mod": _dh}


def _restore(w):
    w["mod"].DecisionHub.compute = w["orig"]


async def main_async() -> int:
    print("=" * 64)
    print("GAP-PROBE v4: контрфактический Гейт① (borko) — факт vs SSOT")
    print("=" * 64)
    from app.services.llm.provider_manager import initialize_model_pool
    initialize_model_pool()
    world = types.SimpleNamespace(game_loop=build_game_loop(data_dir=str(_REPO / "data")))

    def idle(n=1):
        for _ in range(n):
            world.game_loop.idle_tick(CAMPAIGN)

    async def put(x, y):
        await world.game_loop.run_turn(ChatTurnRequest(
            world_id=WORLD, campaign_id=CAMPAIGN, location=LOCATION,
            actions=[PlayerAction(player_name="ВВорг", action="остаюсь на месте")],
            player_position=(x, y)))

    wrap = _install()
    try:
        prev_sched_seen = 0
        for t in range(1, T_BASE + 1):
            idle(1)
            _cmp_tick(world, t, "A", prev_sched_seen)
        for t in range(T_BASE + 1, T_BASE + T_APPR + 1):
            pos = (_scene(world) or {}).get("npc_positions") or {}
            p, g = _xy(pos.get("player")), _xy(pos.get(TARGET))
            if p and g:
                d = math.hypot(g[0] - p[0], g[1] - p[1])
                if d > STOP:
                    s = min(STEP, d - STOP)
                    await put(p[0] + (g[0] - p[0]) / d * s, p[1] + (g[1] - p[1]) / d * s)
                else:
                    await put(*p)
            else:
                idle(1)
            _cmp_tick(world, t, "B", prev_sched_seen)
        for t in range(T_BASE + T_APPR + 1, T_BASE + T_APPR + T_DECAY + 1):
            idle(1)
            _cmp_tick(world, t, "C", prev_sched_seen)
    finally:
        _restore(wrap)
        if _LLM_KILL:
            try:
                _LLM_KILL()
            except Exception as e:  # noqa: BLE001
                print(f"[PROBE] LLM-kill fault: {e!r}")

    # ── Отчёт ──
    print("\n" + "=" * 64)
    print("КОНТРФАКТИЧЕСКОЕ СРАВНЕНИЕ ГЕЙТ① (borko):")
    print("t | фаза | cache_intent(факт) | ssot_intent | E | phase_att | предикат[факт] | предикат[SSOT]")
    fact_hits, cf_hits, sched_ticks = 0, 0, []
    for c in _CMP:
        f_hit = "ДА" if c["gate_fact"] else "-"
        cf_hit = "ДА" if c["gate_cf"] else "-"
        if c["gate_fact"]:
            fact_hits += 1
        if c["gate_cf"]:
            cf_hits += 1
        if c["sched"]:
            sched_ticks.append(c["t"])
        print(f"T{c['t']:02d}[{c['phase']}] {c['cache']} | {c['ssot']} | "
              f"E={c['e']:.2f} att={c['att_phase']} | факт={f_hit} | контрфакт={cf_hit}"
              + (" | schedule:жив" if c["sched"] else ""))
    print(f"\n[ИТОГ] подавлений на источнике прода: {fact_hits}; "
          f"контрфактически (SSOT): {cf_hits}; "
          f"тиков с живым schedule-интеном у borko: {len(sched_ticks)} {sched_ticks}")
    if fact_hits == 0 and cf_hits > 0:
        print("[ВЕРДИКТ] ИСТОЧНИК ЧТЕНИЯ — корень: предикат сработал бы на SSOT, "
              "но слеп на life-кэш. П-1 обоснован.")
    elif fact_hits == 0 and cf_hits == 0:
        print("[ВЕРДИКТ] предикат не срабатывает ни на одном источнике — "
              "причина глубже (E/фаза/отсутствие observe). Разбор до П-1.")
    else:
        print("[ВЕРДИКТ] смешанный — детали в таблице.")
    print("PROBE ИТОГО: строк =", len(_CMP))
    return 0


def _cmp_tick(world, t: int, phase: str, _ps: int) -> None:
    ss = _scene(world) or {}
    att = ((ss.get("attention_states") or {}).get(TARGET) or {}).get("player") or {}
    e = float(att.get("approach_evidence", 0.0))
    att_phase = str(att.get("phase", ""))
    trav = (ss.get("active_traversals") or {}).get(TARGET) or {}
    # schedule-живость: traversal.reason у borko (после рождении в этом тике) ИЛИ
    # реконструкция: schedule-интент родился, если borko-движение в guard_post
    sched_alive = "schedule" in str(trav.get("reason", ""))
    _CMP.append({"t": t, "phase": phase,
                 "cache": _cache_intent(world, TARGET),
                 "ssot": _SSOT.get(TARGET, "?"),
                 "e": e, "att_phase": att_phase,
                 "sched": sched_alive,
                 "gate_fact": _gate_pred(_cache_intent(world, TARGET), e, att_phase),
                 "gate_cf": _gate_pred(_SSOT.get(TARGET, ""), e, att_phase)})


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))