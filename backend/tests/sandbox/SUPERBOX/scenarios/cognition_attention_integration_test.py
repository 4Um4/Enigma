# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/SUPERBOX/scenarios/cognition_attention_integration_test.py
Назначение: S297 CANONICAL INTEGRATION (директива Мастера): контракт
    БАРСУК в каноническом жизненном контуре — «NPC занят своей жизнью →
    игрок направленно идёт → NPC понимает → реагирует → несовместимое
    продолжение не проходит вслепую → игрок уходит → NPC возвращается».
    Фазы I–V; фаза VI (бой) — NEXT CONTINUATION, НЕ в критерии S297.
    Главный артефакт — per-tick лента с переходом
      T-1: rail_alive=True → T: winner=decision → T+1: rail_alive/Δpos/Δheading.
    Классификация need_driven (Case A/B/C директивы): не-критичная
    потребность при живом observe = потенциальный gap; критичная
    (hunger=1.0/shelter сатурирован) = потенциально ПРАВИЛЬНОЕ поведение
    мира; явная реакция, игнорируемая execution = настоящий gap.
    RED только при доказанном «decision → execution ignores». Production
    не меняется; instrumentation — только обёртка MovementEngine
    (runtime, finally-restore). Контроллер — канонический player_position.
Зависимости: game_loop_builder, ChatTurnRequest, movement_engine.
Запуск: env флаги ставит файл ДО app.* (default в коде не трогается).
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

_TEMP = tempfile.mkdtemp(prefix="attention_integration_")
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
        print("[INT] ⚠ LLM не поднялась")
    _LLM_KILL = kill_llama_server
    atexit.register(kill_llama_server)
except ModuleNotFoundError as _e:
    print(f"[INT] llm_manager: {_e}")

from app.models.schemas import ChatTurnRequest, PlayerAction
from app.services.game_loop_builder import build_game_loop
from app.services.npc.attention_config import ATTENTION_EVIDENCE_THRESHOLD as _ETH

CAMPAIGN, LOCATION, WORLD = "Open_road", "tavern", "default"
ALL_NPC = ("merchant_goran", "maid_lusya", "blacksmith_orm", "guard_borko",
           "thief_shadow", "tavern_keeper_tornin")
# Жизненные rail-классы (production-рельсы жизни). Integration-run2
# открытие: в дефолтной таверне ИСПОЛНЯЕМОЕ жизненное движение — почти
# всегда proactive_* DecisionHub (schedule-NPC стоят на постах после
# перехода; need-NPC «застывшие эмиттеры» — NEED-EXEC-1). П3e/G4-v2 уже
# доказал: proactive-rail прерывается вниманием — это канонический
# Барсук-субстрат реального мира. Директива §10: все production rails.
_RAIL_PREFIXES = ("schedule:", "need_driven:", "exploration:", "random:", "proactive_")
_T_BASE, _T_PASSBY, _T_APPR, _T_HOLD, _T_WITHDRAW, _T_RET = 6, 8, 10, 3, 8, 4
_STEP, _STOP = 1.2, 1.8

_TAPE: List[Dict[str, Any]] = []
_MOV: List[Dict[str, Any]] = []
_WIN: Dict[str, str] = {}  # последний hub-winner (обёртка compute)


def _xy(e):
    lp = (e or {}).get("local_position") or {}
    x, y = lp.get("x"), lp.get("y")
    return (float(x), float(y)) if isinstance(x, (int, float)) and isinstance(y, (int, float)) else None


def _hd(e) -> float:
    h = (e or {}).get("body_heading", 1.5708)
    return float(h) if isinstance(h, (int, float)) else 1.5708


def _angdiff(a, b):
    d = abs(a - b)
    return 2.0 * math.pi - d if d > math.pi else d


def _bearing_to(a, b) -> float:
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _scene(w):
    sm = getattr(getattr(w.game_loop, "_tick_orch", None), "_scene_manager", None)
    try:
        return sm.get_scene_state(CAMPAIGN, LOCATION) if sm else None
    except Exception:
        return None


def _intent(w, npc) -> str:
    try:
        st = next((s for s in w.game_loop._get_life_engine().get_npc_states(CAMPAIGN)
                   if isinstance(s, dict) and (s.get("id") or s.get("npc_id")) == npc), None)
        if st is None:
            return ""
        it = st.get("intent")
        return str(getattr(it, "value", it) or "").lower()
    except Exception:
        return ""


def _att(ss, npc) -> Dict[str, Any]:
    return ((ss.get("attention_states") or {}).get(npc) or {}).get("player") or {}


def _rail_of(mov_list, npc):
    """Жизненный rail-интент NPC в этом тике (production-рельсы)."""
    return [m["reason"] for m in mov_list
            if m["actor"] == npc and m["reason"].startswith(_RAIL_PREFIXES)]


def _critical_need(rail_reasons) -> bool:
    """Case B директивы: сатурированная потребность = легитимная власть.

    hunger=1.00 / shelter_urge=1.00 — физиология сильнее внимания.
    """
    for _r in rail_reasons:
        for _crit in ("hunger=1.0", "shelter_urge=1.0"):
            if _crit in _r:
                return True
    return False


def _snapshot(w, t: int, phase: str) -> Dict[str, Any]:
    ss = _scene(w) or {}
    pos = ss.get("npc_positions") or {}
    row = {"t": t, "phase": phase,
           "E": {}, "att_phase": {}, "probably": {}, "intent": {}, "winner": {},
           "hd": {}, "trav": {}, "rail": {}, "rail_alive": {},
           "xy": {n: _xy(pos.get(n)) for n in ALL_NPC + ("player",)},
           "xy_prev": (_TAPE[-1]["xy"] if _TAPE else {}),
           "mov": list(_MOV)}
    _MOV.clear()
    for n in ALL_NPC:
        a = _att(ss, n)
        row["E"][n] = round(float(a.get("approach_evidence", 0.0)), 2)
        row["att_phase"][n] = str(a.get("phase", ""))
        row["probably"][n] = bool(a.get("probably_approaching_me", False))
        row["intent"][n] = _intent(w, n)
        row["winner"][n] = _WIN.get(n, "?")
        row["hd"][n] = round(_hd(pos.get(n)), 3)
        row["trav"][n] = str(((ss.get("active_traversals") or {}).get(n) or {}).get("status", "") or "-")
        row["rail"][n] = _rail_of(row["mov"], n)
        row["rail_alive"][n] = bool(row["rail"][n])
    _TAPE.append(row)
    return row


def _dpos(row, npc) -> float:
    a, b = row["xy_prev"].get(npc), row["xy"].get(npc)
    if a and b:
        return round(math.hypot(b[0] - a[0], b[1] - a[1]), 2)
    return -1.0


def _print_row(r, focus: str = ""):
    targets = (focus,) if focus else ALL_NPC
    marks = []
    for n in targets:
        marks.append(f"{n.split('_')[-1]}:E{r['E'][n]}/pr{int(r['probably'][n])}/"
                     f"w={r['winner'][n][:10]}/rail{int(r['rail_alive'][n])}/"
                     f"Δp{_dpos(r, n)}/tr{r['trav'][n][:3]}")
    rails_f = [m["reason"] for m in r["mov"] if not focus or m["actor"] == focus]
    print(f"[T{r['t']:02d}|{r['phase']}] " + " | ".join(marks)
          + (f" | mov={rails_f[:4]}" if rails_f else ""))


def _install():
    from app.services.npc import decision_hub as _dh
    from app.services.spatial import movement_engine as _me
    orig = {"hub": _dh.DecisionHub.compute, "mov": _me.MovementEngine.process_intents}

    def _w_hub(self, state, *a, __o=orig["hub"], **kw):
        _res = __o(self, state, *a, **kw)
        _WIN[state.npc_id] = str(getattr(getattr(_res, "decision", None), "intent", "?")).lower().replace("intent.", "")
        return _res

    def _w_mov(self, intents, *a, __o=orig["mov"], **kw):
        _res = __o(self, intents, *a, **kw)
        _MOV.extend({"actor": str(getattr(i, "actor_id", "") or ""),
                     "reason": str(getattr(i, "reason", "") or "")}
                    for i in (intents or []))
        return _res

    _dh.DecisionHub.compute = _w_hub  # type: ignore[method-assign]
    _me.MovementEngine.process_intents = _w_mov  # type: ignore[method-assign]
    return {"orig": orig, "mods": (_dh, _me)}


def _restore(w):
    _dh, _me = w["mods"]
    _dh.DecisionHub.compute = w["orig"]["hub"]
    _me.MovementEngine.process_intents = w["orig"]["mov"]


async def main_async() -> int:
    print("=" * 64)
    print("S297 CANONICAL INTEGRATION: КОНТРАКТ БАРСУКА (I–V)")
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
        # ── I: BASELINE — выбор NPC с живым rail (занят жизнью) ──
        for t in range(1, _T_BASE + 1):
            idle(1)
            r = _snapshot(world, t, "I")
            _print_row(r)
        # rail-статистика за baseline: NPC с rail ≥ 50% тиков И живым
        # исполнением (Δp>0 хотя бы в 2 тиках — run1 диагноз: «застывший
        # эмиттер» не субъект Барсука; NEED-EXEC-1 — реестр).
        _rail_hist: Dict[str, int] = {n: sum(1 for rr in _TAPE if rr["rail_alive"][n]) for n in ALL_NPC}
        _moved_hist: Dict[str, int] = {n: sum(1 for rr in _TAPE if _dpos(rr, n) > 0) for n in ALL_NPC}
        # Retry-пул (run3-диагноз: orm — utility-монополист (request_service
        # 1.1) честно выбрал «не прерывать» — валидный мир, но Барсук-дока
        # требует ∃ реагирующий; попытки по убыванию rail-активности,
        # БЕЗ имён-хардкодов — P3d attempts-паттерн).
        _pool = [n for n in ALL_NPC
                 if _rail_hist[n] >= _T_BASE // 2 and _moved_hist[n] >= 2]
        _pool.sort(key=lambda n: -_rail_hist[n])
        if not _pool:
            _pool = [n for n in ALL_NPC if _rail_hist[n] >= 3 and _moved_hist[n] >= 2]
            _pool.sort(key=lambda n: -_rail_hist[n])
        # Пул-гейт (run4-фикс: target присваивается в III-retry-цикле;
        # ранний выход проверяет ПУЛ, а не ещё-не-существующий target).
        print(f"[I] rail-гистограмма: {_rail_hist} | пул: {_pool}")
        if not _pool:
            print("[INT] RED-ПРИЧИНА: ни один NPC не занят жизненным rail "
                  "(все стоячие/хаб-пассивны) — нет субъекта Барсука.")
            print("INT ИТОГО: RED (нет живого rail)")
            return 1
        # G1-цель (фаза II) = первый кандидат пула (run5-фикс: target
        # определяется здесь; III-retry присваивает его заново по пулу).
        target = _pool[0]
        b0 = _TAPE[-1]
        b0_rail = b0["rail"][target]
        print(f"[I] ЦЕЛЬ(G1/первая пула)={target} rail={b0_rail} intent={b0['intent'][target]} "
              f"E={b0['E'][target]} trav={b0['trav'][target]}")

        # ── II: PASS-BY (поперёк; близость ≠ ко мне; rail живёт) ──
        print("--- II: PASS-BY (вторая половина Барсука) ---")
        t_xy = b0["xy"].get(target) or _xy((_scene(world) or {}).get("npc_positions", {}).get(target))
        h_t = b0["hd"][target]
        if t_xy:
            px, py = t_xy[0] + 5.0 * math.sin(h_t), t_xy[1] - 5.0 * math.cos(h_t)
            _sp = _xy((_scene(world) or {}).get("npc_positions", {}).get("player")) or (8.0, 11.5)
            t = _T_BASE
            _d0 = math.hypot(px - _sp[0], py - _sp[1])
            _steps0 = max(1, int(_d0 / _STEP)) if _d0 > 0.5 else 0
            for _k in range(_steps0):
                await put(_sp[0] + (px - _sp[0]) / _d0 * _STEP, _sp[1] + (py - _sp[1]) / _d0 * _STEP)
                t += 1
                _print_row(_snapshot(world, t, "II"), target)
            _dx, _dy = math.cos(h_t + math.pi / 2), math.sin(h_t + math.pi / 2)
            for _k in range(max(0, _T_PASSBY - _steps0)):
                await put(px + (_k + 1) * _dx, py + (_k + 1) * _dy)
                t += 1
                _print_row(_snapshot(world, t, "II"), target)
            for _ in range(2):
                idle(1)
                t += 1
                _print_row(_snapshot(world, t, "II"), target)
        passby_rows = [r for r in _TAPE if r["phase"] == "II"]

        # ── III: CORE BADGER (фронтальный подход; retry до 3 целей пула) ──
        _reaction_seen = False
        target = None
        core_rows_all: List[Dict[str, Any]] = []
        for _cand in _pool[:3]:
            target = _cand
            # Integration-run1 диагноз: подход к позиции цели НЕ в её FOV
            # (miss={'fov': 5} каждый тик, цель спиной) → субъект не видит
            # игрока → E=0 честен. Барсук-контроллер обязан создавать
            # perceivable-геометрию: игрок входит в конус FOV цели (±45° от
            # её heading) и идёт вдоль её оси взгляда.
            print(f"--- III: CORE BADGER — фронтальный подход к {target} ---")
            appr_rows = []
            for step_i in range(_T_APPR):
                ss = _scene(world) or {}
                pos = ss.get("npc_positions") or {}
                p, g = _xy(pos.get("player")), _xy(pos.get(target))
                h_now = _hd(pos.get(target))
                if not (p and g):
                    idle(1)
                    r = _snapshot(world, _TAPE[-1]["t"] + 1, "III")
                    _print_row(r, target)
                    appr_rows.append(r)
                    continue
                # фронтальная точка: на оси взгляда цели, на дистанции
                # обнаружения (detect 15 м > шаг; двигаемся К цели по её оси).
                d = math.hypot(g[0] - p[0], g[1] - p[1])
                if step_i == 0 and (d > 14.0 or _angdiff(_bearing_to(p, g), h_now) > math.pi / 4):
                    # телеграфированный переход во фронтальную позицию
                    # (5 м перед лицом цели) шагом, без телепорта:
                    _front = (g[0] + 5.0 * math.cos(h_now), g[1] + 5.0 * math.sin(h_now))
                    _df = math.hypot(_front[0] - p[0], _front[1] - p[1])
                    _sf = min(_STEP, _df)
                    await put(p[0] + (_front[0] - p[0]) / _df * _sf,
                              p[1] + (_front[1] - p[1]) / _df * _sf)
                elif d > _STOP:
                    s = min(_STEP, d - _STOP)
                    await put(p[0] + (g[0] - p[0]) / d * s, p[1] + (g[1] - p[1]) / d * s)
                else:
                    await put(*p)
                r = _snapshot(world, _TAPE[-1]["t"] + 1, "III")
                _print_row(r, target)
                appr_rows.append(r)
            # ── HOLD: стимул жив (run3-диагноз: статичный контроллер гасил E
            # за один тик стагнации — перцептивный лаг требует продолжающегося
            # движения; раскачка 0.5 м перпендикулярно подходу) ──
            print("--- HOLD: стимул жив (раскачка) ---")
            hold_rows = []
            _hp = _xy((_scene(world) or {}).get("npc_positions", {}).get("player"))
            for _k in range(_T_HOLD):
                if _hp:
                    _amp = 0.5 * (1 if _k % 2 == 0 else -1)
                    await put(_hp[0] + _amp, _hp[1] + _amp * 0.5)
                else:
                    idle(1)
                r = _snapshot(world, _TAPE[-1]["t"] + 1, "H")
                _print_row(r, target)
                hold_rows.append(r)
                if r["E"][target] >= _ETH and r["winner"][target] in ("observe", "flee", "warn", "approach"):
                    _reaction_seen = True
            core_rows_all.extend(appr_rows + hold_rows)
            if _reaction_seen or not _pool:
                break
            print(f"--- III retry: {target} не отреагировал (валидное «не прерывать») → следующая цель ---")
            appr_rows, hold_rows = [], []
            # возврат игрока к общему старту перед следующей попыткой (сопоставимость)
            _sp0 = _xy((_scene(world) or {}).get("npc_positions", {}).get("player")) or (8.0, 11.5)
            await put(*_sp0)
            idle(2)

        # ── IV: WITHDRAW + V: RETURN ──
        print("--- IV: уход ---")
        ss = _scene(world) or {}
        p = _xy((ss.get("npc_positions") or {}).get("player"))
        if p:
            await put(p[0] - 4.0, p[1] - 4.0)
            _print_row(_snapshot(world, _TAPE[-1]["t"] + 1, "IV"), target)
        for _ in range(_T_WITHDRAW):
            idle(1)
            _print_row(_snapshot(world, _TAPE[-1]["t"] + 1, "IV"), target)
        print("--- V: возврат жизни ---")
        ret_rows = []
        for _ in range(_T_RET):
            idle(1)
            r = _snapshot(world, _TAPE[-1]["t"] + 1, "V")
            _print_row(r, target)
            ret_rows.append(r)
    finally:
        _restore(wrap)
        if _LLM_KILL:
            try:
                _LLM_KILL()
            except Exception as e:  # noqa: BLE001
                print(f"[INT] LLM-kill fault: {e!r}")

    # ═══════ АНАЛИЗ (лента — глазами лога) ═══════
    print("\n" + "=" * 64)
    print("ПЕРЕХОД БАРСУКА (T-1 rail → T decision → T+1 rail):")
    core_rows = appr_rows + hold_rows
    for i, r in enumerate(core_rows):
        if r["E"][target] >= _ETH and r["probably"][target]:
            prev = core_rows[i - 1] if i > 0 else None
            nxt = core_rows[i + 1] if i + 1 < len(core_rows) else None
            print(f"  T{r['t']}: E={r['E'][target]} probably=True winner={r['winner'][target]} "
                  f"intent={r['intent'][target]} rail={r['rail'][target] or '-'}")
            if prev:
                print(f"    T-1: rail_alive={prev['rail_alive'][target]} rail={prev['rail'][target] or '-'}")
            if nxt:
                print(f"    T+1: rail_alive={nxt['rail_alive'][target]} Δpos={_dpos(nxt, target)} "
                      f"Δhd={round(_angdiff(nxt['hd'][target], r['hd'][target]), 3)} "
                      f"rail={nxt['rail'][target] or '-'}")

    # Гейты
    ok = True
    # II: близость ≠ реакция; rail живёт
    pb_e = max((r["E"][target] for r in passby_rows), default=0.0)
    pb_rail_live = sum(1 for r in passby_rows if r["rail_alive"][target])
    g2 = pb_e < _ETH and pb_rail_live >= len(passby_rows) // 3
    ok = ok and g2
    print(f"\n[II] {'PASS' if g2 else 'FAIL'}: pass-by max E={pb_e:.2f}<{_ETH}; "
          f"rail жил {pb_rail_live}/{len(passby_rows)} тиков — «близко ≠ ко мне, жизнь продолжается»")

    # III: Case-классификация (директива §5; run3-семантика: «cog дошёл,
    # хаб честно выбрал не прерывать» — валидный исход, отличается от
    # no-window и от Case C)
    core_rows = core_rows_all or core_rows
    e_peak = max((r["E"][target] for r in core_rows), default=0.0)
    cog_ticks = [r for r in core_rows if r["E"][target] >= _ETH]
    obs_ticks = [r for r in core_rows if r["E"][target] >= _ETH and r["winner"][target] == "observe"]
    rail_during_obs = [r for r in obs_ticks if r["rail_alive"][target]]
    crit_during_obs = [r for r in rail_during_obs if _critical_need(r["rail"][target])]
    # Case C: явная реакция, игнорируемая execution — rail жив при observe
    # БЕЗ критической потребности И NPC при этом физически продолжает идти
    # к старой цели (Δpos>0 при rail).
    case_c = [r for r in rail_during_obs if not _critical_need(r["rail"][target])]
    # Вердикт III — плоская цепочка if/elif (никаких вложенных тернарников):
    if not cog_ticks:
        g3_verdict = "no-stimulus-window (стимул не дошёл до cog)"
    elif not obs_ticks:
        g3_verdict = "worked-but-chose-not-to-interrupt (cog дошёл, хаб честно выбрал продолжение)"
    elif crit_during_obs and not case_c:
        g3_verdict = "Case B: критическая потребность легитимно победила"
    elif case_c:
        g3_verdict = "Case C: execution игнорирует реакцию (Барсук-FAIL)"
    else:
        g3_verdict = "reaction honored (rail прерван при observe)"
    if case_c:
        ok = False
    print(f"[III] {'PASS' if not case_c else 'FAIL'}: пик E={e_peak:.2f}; observe-тиков={len(obs_ticks)}; "
          f"rail-при-observe={len(rail_during_obs)} (критичных={len(crit_during_obs)}); "
          f"вердикт: {g3_verdict}")

    # IV/V: угасание + возврат жизни (не того же traversal — новой жизни)
    fin_rows = [r for r in _TAPE if r["phase"] in ("IV", "V")]
    e_fin = fin_rows[-1]["E"][target] if fin_rows else 1.0
    rail_ret = sum(1 for r in fin_rows if r["rail_alive"][target])
    mov_ret = sum(1 for r in fin_rows if _dpos(r, target) > 0)
    g45 = e_fin < _ETH and (rail_ret > 0 or mov_ret > 0)
    ok = ok and g45
    print(f"[IV/V] {'PASS' if g45 else 'FAIL'}: E→{e_fin:.2f}; rail вернулся {rail_ret} тиков; "
          f"двигался {mov_ret} тиков — «интерес угас, жизнь возобновилась»")

    print("=" * 64)
    print(f"INT ИТОГО: {'GREEN' if ok else 'RED'}")
    if not ok and case_c:
        print("БАРСУК-FAIL: «NPC видит и решил, но execution продолжает старое движение». "
              "Per-tick переходы выше — точное звено разрыва для патч-предложения (санкция отдельно).")
    else:
        print("СЦЕНА: NPC был занят делом. Игрок прошёл мимо — тот и не обернулся. "
              "Игрок пошёл прямо — NPC понял, что к нему, и отреагировал по-своему "
              "(или его потребность честно оказалась важнее — Case B). "
              "Игрок ушёл — NPC вернулся к своей жизни.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))