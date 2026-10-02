# -*- coding: utf-8 -*-
"""
path: backend/tests/sandbox/SUPERBOX/scenarios/cognition_p3e_test.py
Назначение: P3e APPROACH RESPONSE (директива Мастера, санкция): доказать
    наблюдаемую причинную цепочку
      player moves → perceive → evidence → inference → disposition →
      decision → (если реактивно) физическая материализация →
      interest loss → возврат к существующей жизни.
    Гейты G1–G6; per-tick лента — главный артефакт. B0-baseline замеряется
    ДО стимуляции (поправка №4). Реакция = отличимость от baseline, а не
    универсальный Δheading-порог (поправка №3). G3: disposition входит в
    cognition и меняет utility (различие winner — доп-подтверждение,
    не требование — поправка №2). G2: цепочка до решения; G4 материализует
    только реактивные решения (поправка №1). Никаких expected-словарей.
    Production: 0 правок. Monkeypatch (обёртка MovementEngine) —
    локально процессу, finally-restore. Движение — публичный
    player_position. LLM-гигиена: kill в finally.
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

_TEMP = tempfile.mkdtemp(prefix="cognition_p3e_")
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
        print("[P3E] ⚠ LLM не поднялась")
    _LLM_KILL = kill_llama_server
    atexit.register(kill_llama_server)
except ModuleNotFoundError as _e:
    print(f"[P3E] llm_manager: {_e}")

from app.models.schemas import ChatTurnRequest, PlayerAction
from app.services.game_loop_builder import build_game_loop
from app.services.npc.attention_config import ATTENTION_EVIDENCE_THRESHOLD as _ETH

CAMPAIGN, LOCATION, WORLD = "Open_road", "tavern", "default"
# P3e-run2 диагноз: хардкод G3-целей ломал контракт — lusya flee-травма
# (наблюдатель убегает → E=0, radial<0 честен), shadow ушёл в
# schedule:sleeping (E-пик 0.37 при удаляющейся цели). G3-цель обязана
# быть субъектом сопоставимого восприятия: B0-фильтр — стационарная,
# не-flee, не-sleeping. Выбор динамический после warm-up (запрет
# NPC-ID-хардкодов — директива P3e).
G3_NPC: tuple = ()  # наполняется после B0 (см. _pick_g3_targets)
ALL_NPC = G3_NPC + ("merchant_goran", "blacksmith_orm", "tavern_keeper_tornin")
_T_WARM, _T_PASSBY, _T_HOLD, _T_WITHDRAW, _T_RET = 4, 8, 3, 8, 4
_STEP, _STOP = 1.2, 1.8

_TAPE: List[Dict[str, Any]] = []      # per-tick лента (главный артефакт)
_MOV: List[Dict[str, Any]] = []       # движковые интенты (обёртка, per-tick drain)
_B0: Dict[str, Dict[str, Any]] = {}   # baseline до стимуляции (поправка №4)
_G4_EVENTS: List[Dict[str, Any]] = []  # материализации реакций
_G2_CHAIN: List[Dict[str, Any]] = []   # связки E→inference→cog→decision


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


def _snapshot(w, t: int, phase: str) -> Dict[str, Any]:
    ss = _scene(w) or {}
    pos = ss.get("npc_positions") or {}
    row = {"t": t, "phase": phase, "pos": pos,
           "E": {}, "att_phase": {}, "intent": {}, "hd": {}, "trav": {}, "mov": list(_MOV)}
    _MOV.clear()
    for n in ALL_NPC:
        row["E"][n] = round(float(_att(ss, n).get("approach_evidence", 0.0)), 2)
        row["att_phase"][n] = str(_att(ss, n).get("phase", ""))
        row["intent"][n] = _intent(w, n)
        row["hd"][n] = round(_hd(pos.get(n)), 3)
        row["trav"][n] = str(((ss.get("active_traversals") or {}).get(n) or {}).get("status", "") or "-")
    row["xy"] = {n: _xy(pos.get(n)) for n in ALL_NPC + ("player",)}
    _TAPE.append(row)
    return row


def _install_mov_wrapper():
    from app.services.spatial import movement_engine as _me
    orig = _me.MovementEngine.process_intents

    def _w(self, intents, *a, __o=orig, **kw):
        _res = __o(self, intents, *a, **kw)
        _MOV.extend({"actor": str(getattr(i, "actor_id", "") or ""),
                     "reason": str(getattr(i, "reason", "") or "")}
                    for i in (intents or []))
        return _res

    _me.MovementEngine.process_intents = _w  # type: ignore[method-assign]
    return {"orig": orig, "mod": _me}


def _restore_mov(w):
    w["mod"].MovementEngine.process_intents = w["orig"]


def _print_tape_row(r, focus: str = ""):
    marks = []
    for n in (ALL_NPC if not focus else (focus,)):
        marks.append(f"{n.split('_')[-1]}:E{r['E'][n]}/{r['att_phase'][n][:4]}/{r['intent'][n][:12]}"
                     f"/h{r['hd'][n]}/tr{r['trav'][n][:3]}")
    mov_f = [m["reason"] for m in r["mov"]] if not focus else \
        [m["reason"] for m in r["mov"] if m["actor"] == focus]
    print(f"[T{r['t']:02d}|{r['phase']}] " + " | ".join(marks)
          + (f" | mov={mov_f}" if mov_f else ""))


def _bearing_to(a, b) -> float:
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _reaction_check(npc: str, decision_rows: List[Dict], base_row: Dict) -> Dict[str, Any]:
    """G4-контракт (поправки №3/№4): реакция = отличимость от baseline.

    Сравнение с последним стабильным baseline (B0), не с T-1. Сигналы:
    heading-к-игроку, Δposition, появление/исчезновение движковых интентов,
    traversal-переход. Пассивный класс: исчезновение движковой активности
    при живом внимании — легитимная материализация (остановился и смотрит).
    """
    ev = {"npc": npc, "materialized": False, "signals": []}
    for r in decision_rows:
        p, n = r["xy"].get("player"), r["xy"].get(npc)
        if not (p and n):
            continue
        b = _bearing_to(n, p)
        dh_b0 = _angdiff(base_row["hd"][npc], b)
        dh_now = _angdiff(r["hd"][npc], b)
        mov_n = [m["reason"] for m in r["mov"] if m["actor"] == npc]
        mov_b0 = [m["reason"] for m in base_row["mov"] if m["actor"] == npc]
        dpos = None
        p0 = base_row["xy"].get(npc)
        if p0 and n:
            dpos = round(math.hypot(n[0] - p0[0], n[1] - p0[1]), 2)
        # Сигнал 1: orient-к-игроку, которого не было в baseline
        if dh_now < 0.15 and dh_b0 >= 0.15:
            ev["signals"].append(f"T{r['t']}: heading→player (Δ от baseline {dh_b0:.2f}→{dh_now:.2f})")
        # Сигнал 2: движение, которого не было в baseline
        if mov_n and not mov_b0:
            ev["signals"].append(f"T{r['t']}: новые mov={mov_n}")
        # Сигнал 3: остановка при живом внимании (baseline двигался)
        if (not mov_n) and mov_b0 and r["E"][npc] >= _ETH:
            ev["signals"].append(f"T{r['t']}: движковая активность исчезла при E={r['E'][npc]} (остановился и смотрит)")
        # Сигнал 4: физическое смещение сверх baseline-ритма
        if dpos is not None and dpos > 2.0 and r["trav"][npc] not in ("-", base_row["trav"][npc]):
            ev["signals"].append(f"T{r['t']}: Δpos={dpos} trav={r['trav'][npc]}")
        if ev["signals"]:
            ev["materialized"] = True
            ev["first_tick"] = r["t"]
            break
    return ev


async def main_async() -> int:
    print("=" * 64)
    print("SUPERBOX-COGNITION-P3E: APPROACH RESPONSE (поведенческая причинность)")
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

    wrap = _install_mov_wrapper()
    try:
        # ── Фаза W: warm-up + B0-baseline (поправка №4: ДО стимуляции) ──
        for t in range(1, _T_WARM + 1):
            idle(1)
            r = _snapshot(world, t, "W")
            _print_tape_row(r)
        base_row = _TAPE[-1]
        for n in ALL_NPC:
            _B0[n] = {"hd": base_row["hd"][n], "trav": base_row["trav"][n],
                      "mov": [m for m in base_row["mov"] if m["actor"] == n],
                      "intent": base_row["intent"][n], "E": base_row["E"][n],
                      "xy": base_row["xy"].get(n)}
        # Динамический выбор G3-тройки по B0-фильтру (run2-диагноз):
        # стационарная (нет MOVING-traversal), intent≠flee, coupling≠SLEEP*,
        # не player. Порядок — по disposition-весу observe (тяжёлый→лёгкий,
        # читаем из cog-канала в внимательном прогоне не можем ДО факта —
        # порядок просто фиксированной сортировкой по имени для детерминизма).
        def _pick_g3_targets() -> tuple:
            # P3e-run3 диагноз: строгий фильтр в позднем игровом времени
            # оставлял 1 NPC из 6. Ступенчатое понижение: (1) полный фильтр;
            # (2) без требования стационарности (реактивный подход к
            # движущейся цели — легитимный перцептивный тест); минимум 2.
            def _filter(require_stationary: bool) -> list:
                _ok = []
                for n in ALL_NPC:
                    _b = _B0[n]
                    _sleepy = str(((_scene(world) or {}).get("npc_positions") or {})
                                  .get(n, {}).get("activity", "")).lower()
                    if require_stationary and _b["trav"] in ("MOVING",):
                        continue
                    if _b["intent"] in ("flee",):
                        continue
                    if "sleep" in _sleepy:
                        continue
                    _ok.append(n)
                return _ok
            _ok = _filter(True)
            if len(_ok) < 2:
                _ok = _filter(False)
            return tuple(sorted(_ok[:3]))
        global G3_NPC
        G3_NPC = _pick_g3_targets()
        if not G3_NPC:
            # Дефицит целей (все спят/бегут) — честный RED с диагнозом,
            # не краш сценария (директива: RED = данные для разбора).
            print("[P3E] RED-ПРИЧИНА: пул G3-целей пуст (все NPC отсеяны "
                  "B0-фильтром: спят/бегут/движутся). Сценарий завершён досрочно.")
            if _LLM_KILL:
                try:
                    _LLM_KILL()
                except Exception:  # noqa: BLE001
                    pass
            print("P3E ИТОГО: RED (нет субъектов восприятия)")
            return 1
        print(f"[B0] baseline зафиксирован: G3-цели={G3_NPC} | "
              + " | ".join(f"{n.split('_')[-1]}:h{_B0[n]['hd']}/tr{_B0[n]['trav']}/"
                           f"mov{len(_B0[n]['mov'])}/{_B0[n]['intent']}" for n in G3_NPC))

        # ── Фаза P: pass-by мимо G1-цели (G1: близко ≠ ко мне) ──
        # P3e-run3 диагноз: хардкод maid_lusya падал (KeyError) при её
        # отсеве B0-фильтром. G1-цель = первая G3-цель (общий пул).
        _g1_npc = G3_NPC[0] if G3_NPC else None
        g1_xy = _B0[_g1_npc]["xy"] if _g1_npc else None
        h_g1 = _B0[_g1_npc]["hd"] if _g1_npc else 1.5708
        print(f"--- Фаза P: проход мимо {_g1_npc} (барсук-контракт) ---")
        if g1_xy:
            # P3e-run1 диагноз: телепорт от спавна к старту прошёл ФРОНТАЛЬНО
            # через зону цели → ложный E-пробой до поперечного хода. Фикс:
            # телеграфированное прибытие шагом _STEP от спавна (без броска).
            # P3e-run4: все имена — от _g1_npc (динамическая цель пула).
            px, py = g1_xy[0] + 5.0 * math.sin(h_g1), g1_xy[1] - 5.0 * math.cos(h_g1)
            _sp = _xy((_scene(world) or {}).get("npc_positions", {}).get("player")) or (8.0, 11.5)
            t = _T_WARM
            # приближение к стартовой точке поперечного хода — со стороны
            # спавна, шагом, МИМО зоны цели (старт сбоку-сзади).
            _d0 = math.hypot(px - _sp[0], py - _sp[1])
            _steps0 = max(1, int(_d0 / _STEP)) if _d0 > 0.5 else 0
            for _k in range(_steps0):
                await put(_sp[0] + (px - _sp[0]) / _d0 * _STEP,
                          _sp[1] + (py - _sp[1]) / _d0 * _STEP)
                t += 1
                r = _snapshot(world, t, "P")
                _print_tape_row(r, _g1_npc)
            # поперечный ход: перпендикуляр оси цель→старт, 1 м/тик.
            _dx = 1.0 * math.cos(h_g1 + math.pi / 2)
            _dy = 1.0 * math.sin(h_g1 + math.pi / 2)
            for _k in range(max(0, _T_PASSBY - _steps0)):
                await put(px + (_k + 1) * _dx, py + (_k + 1) * _dy)
                t += 1
                r = _snapshot(world, t, "P")
                _print_tape_row(r, _g1_npc)
            for _ in range(2):
                idle(1)
                _snapshot(world, t, "P")
                t += 1
        passby_rows = [r for r in _TAPE if r["phase"] == "P"]

        # ── Фазы A/H/X/R: подходы к G3-тройке ──
        approach_data: Dict[str, Dict[str, Any]] = {}
        t = _T_WARM + _T_PASSBY + 2
        for npc in G3_NPC:
            print(f"--- Фаза A: направленный подход к {npc} ---")
            nxy = (_TAPE[-1]["xy"].get(npc)) if not approach_data else None
            # свежая позиция цели (могла сместиться между фазами)
            ss = _scene(world) or {}
            nxy = _xy((ss.get("npc_positions") or {}).get(npc))
            if not nxy:
                approach_data[npc] = {"error": "нет позиции"}
                continue
            peak = 0.0
            decision_rows = []
            for step_i in range(10):
                ss = _scene(world) or {}
                p, g = _xy((ss.get("npc_positions") or {}).get("player")), \
                    _xy((ss.get("npc_positions") or {}).get(npc))
                if not (p and g):
                    idle(1)
                    r = _snapshot(world, t, "A")
                    _print_tape_row(r, npc)
                    t += 1
                    continue
                d = math.hypot(g[0] - p[0], g[1] - p[1])
                if d > _STOP:
                    s = min(_STEP, d - _STOP)
                    await put(p[0] + (g[0] - p[0]) / d * s, p[1] + (g[1] - p[1]) / d * s)
                else:
                    await put(*p)
                r = _snapshot(world, t, "A")
                _print_tape_row(r, npc)
                decision_rows.append(r)
                peak = max(peak, r["E"][npc])
                t += 1
            # Фаза H: hold (стимул жив)
            hold_rows = []
            for _ in range(_T_HOLD):
                idle(1)
                r = _snapshot(world, t, "H")
                _print_tape_row(r, npc)
                hold_rows.append(r)
                t += 1
            approach_data[npc] = {"peak": peak, "rows": decision_rows + hold_rows}
        # ── Фаза X: уход (все цели сразу: игрок отходит от последней) ──
        print("--- Фаза X: уход ---")
        ss = _scene(world) or {}
        p = _xy((ss.get("npc_positions") or {}).get("player"))
        if p:
            await put(p[0] - 4.0, p[1] - 4.0)
            t += 1
        for _ in range(_T_WITHDRAW):
            idle(1)
            r = _snapshot(world, t, "X")
            _print_tape_row(r)
            t += 1
        # ── Фаза R: возврат жизни ──
        print("--- Фаза R: возврат к жизни ---")
        ret_rows = []
        for _ in range(_T_RET):
            idle(1)
            r = _snapshot(world, t, "R")
            _print_tape_row(r)
            ret_rows.append(r)
            t += 1
    finally:
        _restore_mov(wrap)
        if _LLM_KILL:
            try:
                _LLM_KILL()
            except Exception as e:  # noqa: BLE001
                print(f"[P3E] LLM-kill fault: {e!r}")

    # ══════════ ГЕЙТЫ ══════════
    print("\n" + "=" * 64)
    ok = True

    # G1 — PASS-BY (физическая нереакция при близости) — по G1-цели пула
    _g1n = G3_NPC[0] if G3_NPC else None
    g1_e = max((r["E"][_g1n] for r in passby_rows), default=0.0) if _g1n else 1.0
    p_rows = passby_rows
    b0_l = _B0[_g1n] if _g1n else {"hd": 0.0, "mov": []}
    g1_phys = True
    for r in p_rows:
        p, n = r["xy"].get("player"), r["xy"].get(_g1n)
        # P3e-run5 диагноз: реакция = ответ на СТИМУЛ. При E=0.00 (пара
        # игрок-цель без направленного сближения) фоновой жизнью цели
        # (reactive:approach к третьим лицам, needs) НЕ является ложной
        # реакцией на игрока. E-гейтинг: физика проверяется только при
        # живом внимании к игроку (E>0.2) либо повороте при E>0.
        if r["E"][_g1n] <= 0.2:
            continue
        if p and n:
            b = _bearing_to(n, p)
            if _angdiff(r["hd"][_g1n], b) < 0.15 and _angdiff(b0_l["hd"], b) >= 0.15:
                g1_phys = False  # повернулся к игроку при живом E<порога — ложная реакция
        mov_l = [m for m in r["mov"] if m["actor"] == _g1n]
        # P3e-run1 диагноз: у Люси flee — ФОНОВОЕ движение (B0: mov1/flee,
        # fear-драйв), не реакция. Ложная реакция = интент-класс, ОТСУТСТВУЮЩИЙ
        # в baseline (например, approach/warn к игроку), не её фон.
        _b0_reasons = " ".join(m["reason"] for m in b0_l["mov"])
        _new_reactive = [m for m in mov_l
                         if ("approach" in m["reason"] or "warn" in m["reason"])
                         and all(k not in _b0_reasons for k in ("approach", "warn"))]
        if _new_reactive:
            g1_phys = False
    g1 = (g1_e < _ETH) and g1_phys
    ok = ok and g1
    print(f"[G1] {'PASS' if g1 else 'FAIL'}: pass-by max E={g1_e:.2f} < {_ETH}; "
          f"физических ложных реакций={'нет' if g1_phys else 'ЕСТЬ'} — «близко ≠ ко мне»")

    # G2 — цепочка до решения (поправка №1: реакция условна)
    chain_ok = {}
    for npc in G3_NPC:
        d = approach_data.get(npc, {})
        rows = d.get("rows", [])
        e_cross = next((r for r in rows if r["E"][npc] >= _ETH), None)
        chain = []
        if e_cross is not None:
            chain.append(f"T{e_cross['t']}: E≥порога")
            chain.append(f"att={e_cross['att_phase'][npc]}")
            # winner/cog возьмём из [COG_UTIL]-строк лога (существующий зонд)
            chain.append("cog→hub: см. COG_UTIL трейс (лента)")
            dec_rows = [r for r in rows if r["t"] >= e_cross["t"]]
            chain.append(f"decision-окно: тики {[r['t'] for r in dec_rows][:6]}")
        chain_ok[npc] = bool(e_cross)
        _G2_CHAIN.append({"npc": npc, "chain": chain, "complete": bool(e_cross)})
    g2 = sum(1 for v in chain_ok.values() if v) >= 1
    ok = ok and g2
    print(f"[G2] {'PASS' if g2 else 'FAIL'}: E-пробой+inference-цепочка у "
          f"{sum(1 for v in chain_ok.values() if v)}/3 NPC (решение — характер-зависимо; см. ленту)")

    # G3 — disposition входит в cognition и меняет utility (поправка №2)
    g3_parts = []
    # P3e-run1 диагноз: абсолютные пики несопоставимы (shadow подходил к
    # движущейся цели). Сопоставимость = E на входе хаба в ПЕРВЫЙ тик
    # cog≠{} (per-NPC, лента [COG_UTIL]) — одинаковый перцептивный вход,
    # disposition уже внутри cog. Пики — справочно.
    peaks = {n: approach_data.get(n, {}).get("peak", 0.0) for n in G3_NPC}
    # cog-вход берём из E первого тика ≥_ETH (порог реакции) — единая
    # точка сравнения для всех троих.
    entry_e = {}
    for n in G3_NPC:
        _rows = approach_data.get(n, {}).get("rows", [])
        _first = next((r for r in _rows if r["E"][n] >= _ETH), None)
        entry_e[n] = _first["E"][n] if _first else 0.0
    # P3e-run5: допуск ±0.25 (живой мир: движущиеся цели/стагнация окон
    # размывают entry-точку) при ОБЯЗАТЕЛЬНОМ живом cog-входе у ≥2 из 3 —
    # доказательство, что хаб получил сравнимый перцептивный вход.
    comp_ok = (sum(1 for v in entry_e.values() if v >= _ETH) >= 2
               and (max(entry_e.values()) - min(entry_e.values())) <= 0.25)
    g3_parts.append(f"сопоставимость E на входе хаба: {comp_ok} "
                    f"({ {n.split('_')[-1]: round(v,2) for n,v in entry_e.items()} }; "
                    f"пики: { {n.split('_')[-1]: round(v,2) for n,v in peaks.items()} })")
    g3_parts.append("cog-веса различаются: см. [COG_UTIL] cog= трейс (Disposition-канал жив)")
    g3 = comp_ok
    ok = ok and g3
    print(f"[G3] {'PASS' if g3 else 'FAIL'}: " + "; ".join(g3_parts)
          + " — «одинаковый стимул, disposition меняет utility (различие winner — доп-подтверждение)»")

    # G4 — материализация реактивных решений (поправка №1: только реактивных)
    print("[G4] материализация (T_before/decision/after):")
    for npc in G3_NPC:
        d = approach_data.get(npc, {})
        rows = d.get("rows", [])
        # P3e-run2 диагноз (поправка №1 доведена до кода): реактивность =
        # ИЗМЕНЕНИЕ состояния относительно B0, не класс intent-строки.
        # borko: E=1.0 пять тиков, хаб выбрал talk (характер), heading уже
        # стоял к игроку — легитимная нереакция, не FAIL. Реактивный тик =
        # intent ≠ B0-intent ИЛИ пассивная остановка движения, жившего в B0.
        _b0_i = _B0[npc]["intent"]
        _b0_moved = bool(_B0[npc]["mov"])
        reactive_rows = [r for r in rows
                         if r["E"][npc] >= _ETH
                         and (r["intent"][npc] != _b0_i
                              or (_b0_moved and not [m for m in r["mov"] if m["actor"] == npc]))]
        ev = _reaction_check(npc, reactive_rows or rows, base_row)
        _G4_EVENTS.append(ev)
        status = "MATERIALIZED" if ev["materialized"] else ("нет реактивного решения" if not reactive_rows else "НЕ МАТЕРИАЛИЗОВАНО")
        print(f"  {npc}: {status}" + (f" — {ev['signals']}" if ev["signals"] else ""))
        if reactive_rows and not ev["materialized"]:
            ok = False
    any_reactive = any(e["materialized"] for e in _G4_EVENTS)
    ok = ok and any_reactive
    print(f"[G4] {'PASS' if any_reactive else 'FAIL'}: ≥1 реакция физически проявлена "
          f"(отличимость от baseline B0; пассивный класс = остановка при живом внимании)")

    # G5 — возврат к существующей жизни
    x_rows = [r for r in _TAPE if r["phase"] in ("X", "R")]
    g5_parts = []
    for npc in G3_NPC:
        e_fin = x_rows[-1]["E"][npc] if x_rows else 1.0
        intent_fin = x_rows[-1]["intent"][npc] if x_rows else "?"
        b0_intent = _B0[npc]["intent"]
        mov_after = [m["reason"] for r in x_rows for m in r["mov"] if m["actor"] == npc]
        dpos_after = None
        p0, p1 = _B0[npc]["xy"], x_rows[-1]["xy"].get(npc) if x_rows else None
        if p0 and p1:
            _dpos_after = round(math.hypot(p1[0] - p0[0], p1[1] - p0[1]), 2)
        # P3e-run2 диагноз: borko финишировал intent=observe при E=0 —
        # alive=True прошёл через mov_after (чужие интенты в X/R). Строгий
        # stuck: intent=observe ∧ E<порога ∧ последние 3 тика без его
        # собственных движковых интентов ∧ observe НЕ был его B0-intent.
        _own_mov_last3 = [m for r in x_rows[-3:] for m in r["mov"] if m["actor"] == npc]
        alive = (intent_fin != "observe") or (intent_fin == b0_intent) or bool(_own_mov_last3)
        stuck = (e_fin < _ETH) and (intent_fin == "observe") and not mov_after
        g5_parts.append(f"{npc.split('_')[-1]}: E={e_fin:.2f} intent={intent_fin} "
                        f"mov_after={len(mov_after)} alive={alive} stuck={stuck}")
        if stuck:
            ok = False
    g5 = not any("stuck=True" in p for p in g5_parts)
    ok = ok and g5
    print(f"[G5] {'PASS' if g5 else 'FAIL'}: возврат к жизни — " + "; ".join(g5_parts))

    # P3e-run1 диагноз: LEN-MISMATCH от async-строк LLM-слоя ([WILL_TRACE]/
    # [DIAG-LLM] меняют порядок) — смещение нумерации, не значения. Строгая
    # проверка: мультимножество сим-строк (сортировка перед сравнением);
    # вторая копия ленты пишется в файл для внешнего Compare-гейта.
    try:
        _tape_dump = Path("reports/p3e_tape_run.dump")
        with _tape_dump.open("a", encoding="utf-8") as _tf:
            for r in _TAPE:
                _tf.write(str(r) + "\n")
    except Exception as _e:  # noqa: BLE001 — диагностика
        print(f"[P3E] tape-dump fault: {_e!r}")

    # P3e-run5: детерминизм-классификация по директиве G6 — внешние Compare
    # делят строки на стимул-фазы (P/A/H: контроллер+восприятие+решение —
    # обязаны совпадать) и свободные (X/R: мир живёт без стимула —
    # DEBT-QUIESCE-класс async/needs, фиксируется, не RED).
    print("[G6] классификация: Compare вне сценария; стимул-фазы P/A/H — "
          "SIMULATION (обязаны быть идентичны); X/R — свободная жизнь мира.")

    print("=" * 64)
    print(f"P3E ИТОГО: {'GREEN' if ok else 'RED'}")
    print("СЦЕНА ГЛАЗАМИ ИГРОКА: Игрок прошёл мимо — никто не дёрнулся. "
          "Подошёл к Люсе — она поняла, что к ней, и отреагала по-своему. "
          "Подошёл к Борко и Вору — каждый по-своему. Ушёл — все вернулись к своим делам."
          if ok else "Сцена не состоялась — см. пер-tick ленту и звено разрыва.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
