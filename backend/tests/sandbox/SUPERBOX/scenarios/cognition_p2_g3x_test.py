# -*- coding: utf-8 -*-
"""
SUPERBOX-COGNITION-P2 G3-X (S295-хвост): контролируемый эксперимент
МАТЕРИАЛИЗАЦИИ ориентации (закрывает G3 PENDING живого контура).

Гипотеза: NPC, заметив приближающегося игрока (периферия, за спиной),
испускает attention_orient SceneChange(field="body_heading"), который
применяется каноническим путём (ATTENTION_BRIDGE → SSM generic-ветка)
и читается из scene_state как факт мира.

Железные условия:
  1. COGNITION_V0=1 в env ДО импортов app.*.
  2. Ноль инъекций состояния: движение игрока — через легальный run_turn
     (ChatTurnRequest, MVP-паттерн), выбор NPC — data-driven (стационарный,
     без хардкода id).
  3. Ядро не вертит аватаром (ControlSource) — heading игрока — негативный
     контроль.
  4. Стационарность NPC: candidate перепроверяется на каждом шаге; ушёл в
     движение → выбор нового кандидата (≤3 попыток) → иначе честный RED.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/cognition_p2_g3x_test.py
"""
import asyncio
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

os.environ["COGNITION_V0"] = "1"  # ДО app.*-импортов

from app.core.config import settings

# Изоляция saves (MVP-паттерн): копия, оригинал не тронут
_TEMP = tempfile.mkdtemp(prefix="cognition_g3x_")
_SAVES_DST = Path(_TEMP) / "saves"
_src = Path(settings.saves_dir)
if _src.exists():
    shutil.copytree(_src, _SAVES_DST, dirs_exist_ok=True)
settings.saves_dir = str(_SAVES_DST)

import atexit

atexit.register(lambda: shutil.rmtree(_TEMP, ignore_errors=True))

# LLM-слой (украдено из MVP/IPT): run_turn тянет DM-фазу
try:
    _REPO_ROOT = BACKEND_ROOT.parent
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from scripts.llm_server_manager import kill_llama_server, start_llama_server

    if not start_llama_server():
        print("[G3-X] ⚠ LLM не поднялась — DM-фаза будет деградировать, "
              "но семантика MOVE резолвится fast-path")
    atexit.register(kill_llama_server)
except ModuleNotFoundError as _e:
    print(f"[G3-X] llm_server_manager недоступен ({_e})")

from app.models.schemas import ChatTurnRequest, PlayerAction
from app.services.game_loop_builder import build_game_loop

CAMPAIGN = "Open_road"
LOCATION = "tavern"
WORLD_ID = "default"

# Геометрия эксперимента: игрок ставится ЗА СПИНОЙ NPC на 2.2 м
# (FOV 90° fail; периферия 3 м — ловит; ТЗ §5.2 «внезапное появление»).
_BEHIND_DIST = 2.2
_MAX_ATTEMPTS = 3


def _xy(entry) -> tuple:
    lp = (entry or {}).get("local_position") or {}
    x, y = lp.get("x"), lp.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return float(x), float(y)
    return None


def _heading(entry) -> float:
    h = (entry or {}).get("body_heading", 1.5708)
    return float(h) if isinstance(h, (int, float)) else 1.5708


def _scene(world):
    orch = getattr(world.game_loop, "_tick_orch", None)
    sm = getattr(orch, "_scene_manager", None)
    if sm is None:
        return None
    try:
        return sm.get_scene_state(CAMPAIGN, LOCATION)
    except Exception:
        return None


def _angdiff(a: float, b: float) -> float:
    d = abs(a - b)
    if d > math.pi:
        d = 2.0 * math.pi - d
    return d


def _moving_ids(world) -> set:
    ss = _scene(world) or {}
    return {
        nid
        for nid, tr in (ss.get("active_traversals") or {}).items()
        if (tr or {}).get("status") == "MOVING"
    }


def _idle_tics(world, n: int):
    for _ in range(n):
        world.game_loop.idle_tick(CAMPAIGN)


def _pick_stationary(world, prev_pos) -> "str | None":
    """Data-driven выбор: NPC без MOVING, позиция стабильна между тиками,
    вне радиуса игрока (чтобы приближение было событием, а не продолжением)."""
    ss = _scene(world) or {}
    pos = ss.get("npc_positions") or {}
    moving = _moving_ids(world)
    pxy = _xy(pos.get("player"))
    best, best_d = None, -1.0
    for nid, entry in pos.items():
        if nid == "player" or nid in moving:
            continue
        if prev_pos and not _stable(pos, prev_pos, nid):
            continue
        nxy = _xy(entry)
        if nxy is None:
            continue
        d = math.hypot(nxy[0] - pxy[0], nxy[1] - pxy[1]) if pxy else 99.0
        if d > best_d:
            best, best_d = nid, d
    return best


def _stable(pos_a: dict, pos_b: dict, npc_id: str) -> bool:
    a, b = _xy(pos_a.get(npc_id)), _xy(pos_b.get(npc_id))
    return a is not None and b is not None and a == b


async def main_async() -> int:
    print("=" * 64)
    print("SUPERBOX-COGNITION-P2 G3-X: материализация orient (живой мир)")
    print("=" * 64)
    ok = True

    from app.services.llm.provider_manager import initialize_model_pool

    initialize_model_pool()

    world = types.SimpleNamespace(
        game_loop=build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    )
    _idle_tics(world, 2)  # init сцены + стабильный снимок

    # ── Выбор стационарного NPC (до 3 попыток) ──────────────────────
    target = None
    prev_pos = (_scene(world) or {}).get("npc_positions") or {}
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        target = _pick_stationary(world, prev_pos)
        if target is None:
            print(f"[PICK] попытка {attempt}: кандидатов нет — тик и ретрай")
            _idle_tics(world, 1)
            prev_pos = (_scene(world) or {}).get("npc_positions") or {}
            continue
        # Перепроверка стационарности следующим тиком
        _idle_tics(world, 1)
        now_pos = (_scene(world) or {}).get("npc_positions") or {}
        if _moving_ids(world) & {target} or not _stable(now_pos, prev_pos, target):
            print(f"[PICK] попытка {attempt}: {target} сдвинулся — ретрай")
            prev_pos = now_pos
            target = None
            continue
        print(f"[PICK] цель: {target} (стационарен 2 тика)")
        break
    if target is None:
        print("[PICK] FAIL: стационарного NPC не найдено за 3 попытки")
        return 1

    # ── Постановка игрока за спину цели через легальный run_turn ────
    ss = _scene(world) or {}
    pos = ss.get("npc_positions") or {}
    nxy = _xy(pos.get(target))
    h = _heading(pos.get(target))
    # За спиной = противоположно body_heading
    pxy = (nxy[0] - _BEHIND_DIST * math.cos(h), nxy[1] - _BEHIND_DIST * math.sin(h))

    req = ChatTurnRequest(
        world_id=WORLD_ID,
        campaign_id=CAMPAIGN,
        location=LOCATION,
        actions=[PlayerAction(player_name="ВВорг", action="остаюсь на месте")],
        player_position=pxy,
    )
    await world.game_loop.run_turn(req)
    print(f"[SETUP] player поставлен за спину {target}: {pxy}")

    # Восприятие: 2 тика (детекция периферией + orient-применение)
    _idle_tics(world, 2)

    # ── Assert-цепочка ───────────────────────────────────────────────
    ss2 = _scene(world) or {}
    pos2 = ss2.get("npc_positions") or {}
    att = ss2.get("attention_states") or {}

    # A: детекция игрока NPC (периферия, за спиной)
    pair = (att.get(target) or {}).get("player") or {}
    phase = pair.get("phase", "MISSING")
    a_ok = phase in ("detected", "oriented", "approaching", "near")
    ok = ok and a_ok
    print(f"[A] {'PASS' if a_ok else 'FAIL'}: attention[{target}][player].phase={phase}")

    # B: МАТЕРИАЛИЗАЦИЯ — heading NPC повернут на игрока
    win = pair.get("observation_window") or []
    b_ok = False
    if pos2.get(target) and win:
        cur_h = _heading(pos2.get(target))
        pxy_now = _xy(pos2.get("player"))
        nxy_now = _xy(pos2.get(target))
        if pxy_now and nxy_now:
            live_bearing = math.atan2(
                pxy_now[1] - nxy_now[1], pxy_now[0] - nxy_now[0]
            )
            diff = _angdiff(cur_h, live_bearing)
            b_ok = diff < 0.06  # единственный писатель heading — attention_orient
        ok = ok and b_ok
        print(
            f"[B] {'PASS' if b_ok else 'FAIL'}: heading[{target}]="
            f"{_heading(pos2.get(target)):.4f} vs bearing(player)={live_bearing:.4f} "
            f"(diff={diff:.4f})"
        )
    else:
        ok = False
        print("[B] FAIL: нет наблюдения в окне или цели в позиции")

    # C: ядро не вертит аватаром
    p_ss = _scene(world) or {}
    p_h = _heading((p_ss.get("npc_positions") or {}).get("player"))
    c_ok = _angdiff(p_h, _heading(pos.get("player"))) < 0.01
    ok = ok and c_ok
    print(f"[C] {'PASS' if c_ok else 'FAIL'}: heading игрока неизменен")

    # D: first_seen существует
    d_ok = bool(pair.get("first_seen_tick"))
    ok = ok and d_ok
    print(f"[D] {'PASS' if d_ok else 'FAIL'}: first_seen={pair.get('first_seen_tick')}")

    print("=" * 64)
    print(f"G3-X ИТОГО: {'GREEN' if ok else 'RED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    import types

    sys.exit(asyncio.run(main_async()))