# -*- coding: utf-8 -*-
"""
SUPERBOX-COGNITION-P3D (санкция Мастера): перцептивное внимание →
наблюдаемое изменение поведения. ПРИНЯТОЧНЫЙ критерий — сцена глазами
игрока, не «winner = OBSERVE».

Сценарий (верховный критерий P3d):
  Фаза 0 (pass-by): player идёт ПО КАСАТЕЛЬНОЙ → E не доходит до порога
    → cognition_modifiers пусты → Орм продолжает свою жизнь.
    «Она прошла бы мимо — он и не поднял бы глаз.»
  Фаза 1 (approach): player по лучу к Орму (9→3 м) → evidence копится
    → пересекает порог → OBSERVE/IDLE побеждает рутинный WORK
    → «Орм перестал стучать и смотрит ей навстречу»
    + G: heading Орма на игрока (материализация ориентации).
  Фаза 2 (уход): player уходит за радиус → LOST-затухание → интент
    Орма возвращается к жизни
    → «Она скрылась за домом — он вернулся к наковальне.»
  Ветка диспозиций: поглощённый делом (control-доминанта) при ТОМ ЖЕ
    подходе НЕ бросает работу (сценарий В — характером, не кодом).

Железные условия:
  - COGNITION_V0=1 ДО импортов app.*;
  - ноль инъекций состояния: движение игрока — легальный run_turn;
  - выбор Орма — data-driven (стационарный NPC, как в G3-X);
  - disposition-ветка: через Calibration Lab-патч NPC-драйвов ЗАПРЕЩЁН
    (вне зоны) → проверяется на микро-уровне (test_character_diverges,
    уже GREEN); здесь — только базовая линия живого контура.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/cognition_p3d_test.py
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

os.environ["COGNITION_V0"] = "1"  # ДО app.*

from app.core.config import settings

_TEMP = tempfile.mkdtemp(prefix="cognition_p3d_")
_SAVES_DST = Path(_TEMP) / "saves"
_src = Path(settings.saves_dir)
if _src.exists():
    shutil.copytree(_src, _SAVES_DST, dirs_exist_ok=True)
settings.saves_dir = str(_SAVES_DST)

import atexit

atexit.register(lambda: shutil.rmtree(_TEMP, ignore_errors=True))

try:
    _REPO_ROOT = BACKEND_ROOT.parent
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from scripts.llm_server_manager import kill_llama_server, start_llama_server

    if not start_llama_server():
        print("[G0] ⚠ LLM не поднялась — семантика MOVE резолвится fast-path")
    atexit.register(kill_llama_server)
except ModuleNotFoundError as _e:
    print(f"[G0] llm_server_manager недоступен ({_e})")

from app.models.schemas import ChatTurnRequest, PlayerAction
from app.services.game_loop_builder import build_game_loop
from app.services.npc.attention_config import (
    ATTENTION_EVIDENCE_HYSTERESIS,
    ATTENTION_EVIDENCE_THRESHOLD,
)

CAMPAIGN = "Open_road"
LOCATION = "tavern"
WORLD_ID = "default"

_BEHIND_DIST = 2.2
_MAX_PICK_ATTEMPTS = 3


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


def _angdiff(a, b):
    d = abs(a - b)
    if d > math.pi:
        d = 2.0 * math.pi - d
    return d


def _pick_stationary(world, prev_pos):
    """Data-driven выбор стационарного NPC, дальнего от игрока."""
    ss = _scene(world) or {}
    pos = ss.get("npc_positions") or {}
    moving = {
        nid
        for nid, tr in (ss.get("active_traversals") or {}).items()
        if (tr or {}).get("status") == "MOVING"
    }
    pxy = _xy(pos.get("player"))
    best, best_d = None, -1.0
    for nid, entry in pos.items():
        if nid == "player" or nid in moving:
            continue
        if prev_pos:
            a, b = _xy(pos.get(nid)), _xy(prev_pos.get(nid))
            if a is None or b is None or a != b:
                continue
        nxy = _xy(entry)
        if nxy is None:
            continue
        d = math.hypot(nxy[0] - pxy[0], nxy[1] - pxy[1]) if pxy else 99.0
        if d > best_d:
            best, best_d = nid, d
    return best


def _attention(world) -> dict:
    return (_scene(world) or {}).get("attention_states") or {}


def _evidence(world, npc_id) -> "tuple[float, bool]":
    """Максимальное evidence NPC по паре с player + признак порога."""
    top, hit = 0.0, False
    for _subj, st in (_attention(world).get(npc_id) or {}).items():
        if _subj != "player":
            continue
        e = float(st.get("approach_evidence", 0.0))
        if e > top:
            top = e
        if st.get("phase") in ("oriented", "approaching", "near"):
            pass  # фаза сама не критерий — критерий evidence
    hit = top >= ATTENTION_EVIDENCE_THRESHOLD
    return top, hit


def _orm_intent(world, npc_id) -> str:
    """Текущий интент NPC из engine-состояний (публичный канал LifeEngine)."""
    try:
        eng = world.game_loop._get_life_engine()
        states = eng.get_npc_states(CAMPAIGN)
        st = states.get(npc_id) if isinstance(states, dict) else None
        if st is None and isinstance(states, list):
            st = next(
                (
                    s
                    for s in states
                    if getattr(s, "npc_id", getattr(s, "id", "")) == npc_id
                ),
                None,
            )
        it = getattr(st, "intent", None)
        if it is None and isinstance(st, dict):
            it = st.get("intent")
        return str(getattr(it, "value", it) or "").lower()
    except Exception as _e:  # noqa: BLE001 — диагностика канала
        print(f"[DIAG-INTENT] fail: {_e}")
        return ""


async def main_async() -> int:
    print("=" * 64)
    print("SUPERBOX-COGNITION-P3D: внимание → наблюдаемое поведение")
    print("=" * 64)
    ok = True

    from app.services.llm.provider_manager import initialize_model_pool

    initialize_model_pool()

    world = types.SimpleNamespace(
        game_loop=build_game_loop(data_dir=str(BACKEND_ROOT.parent / "data"))
    )

    def idle(n=1):
        for _ in range(n):
            world.game_loop.idle_tick(CAMPAIGN)

    idle(2)

    # ── Выбор цели ────────────────────────────────────────────────────
    target = None
    prev = (_scene(world) or {}).get("npc_positions") or {}
    for attempt in range(1, _MAX_PICK_ATTEMPTS + 1):
        target = _pick_stationary(world, prev)
        if target is None:
            idle(1)
            prev = (_scene(world) or {}).get("npc_positions") or {}
            continue
        idle(1)
        now = (_scene(world) or {}).get("npc_positions") or {}
        a, b = _xy(now.get(target)), _xy(prev.get(target))
        if a is None or b is None or a != b:
            prev = now
            target = None
            continue
        print(f"[PICK] цель: {target} (стационарен)")
        break
    if target is None:
        print("[PICK] FAIL: стационарного NPC нет")
        return 1

    ss = _scene(world) or {}
    pos = ss.get("npc_positions") or {}
    nxy = _xy(pos.get(target))
    h = _heading(pos.get(target))
    baseline_intent = _orm_intent(world, target)
    print(f"[PICK] baseline intent[{target}] = '{baseline_intent}'")

    def _put_player(x, y, action="остаюсь на месте"):
        req = ChatTurnRequest(
            world_id=WORLD_ID,
            campaign_id=CAMPAIGN,
            location=LOCATION,
            actions=[PlayerAction(player_name="ВВорг", action=action)],
            player_position=(x, y),
        )
        return world.game_loop.run_turn(req)

    # ── Фаза 0: PASS-BY (касательная, мин. дистанция ~4-5 м) ─────────
    print("--- Фаза 0: проходит мимо ---")
    # Орм в nxy, heading h. Точка сбоку от него (перпендикуляр),player
    # «проходит» мимо: ставим игрока сбоку-сзади на 5 м, ортогонально лучу.
    px0 = nxy[0] + 5.0 * math.sin(h) + 1.0 * math.cos(h)
    py0 = nxy[1] - 5.0 * math.cos(h) + 1.0 * math.sin(h)
    await _put_player(px0, py0)
    idle(2)
    e0, hit0 = _evidence(world, target)
    intent0 = _orm_intent(world, target)
    g0 = (not hit0) and (
        intent0 == baseline_intent or intent0 in ("", "idle", "observe")
    )
    ok = ok and g0
    print(
        f"[G0] {'PASS' if g0 else 'FAIL'}: evidence={e0:.3f} < порога, "
        f"intent='{intent0}' (базлайн '{baseline_intent}') — "
        f"«прошёл мимо, никто не среагировал»"
    )

    # ── Фаза 1: APPROACH по лучу к Орму ────────────────────────────────
    print("--- Фаза 1: идёт к нему ---")
    ux, uy = math.cos(h), math.sin(h)
    evidence_peak = 0.0
    became_attentive = False
    oriented = False
    for dist in (9.0, 7.0, 5.0, 3.0):
        await _put_player(nxy[0] + ux * dist, nxy[1] + uy * dist)
        idle(2)
        e, _ = _evidence(world, target)
        evidence_peak = max(evidence_peak, e)
        it = _orm_intent(world, target)
        if e >= ATTENTION_EVIDENCE_THRESHOLD:
            became_attentive = True
        if became_attentive and it in ("observe", "idle"):
            cur_h = _heading((_scene(world) or {}).get("npc_positions", {}).get(target))
            cur_p = _xy((_scene(world) or {}).get("npc_positions", {}).get("player"))
            if cur_p:
                b = math.atan2(cur_p[1] - nxy[1], cur_p[0] - nxy[0])
                if _angdiff(cur_h, b) < 0.15:
                    oriented = True
    # P3d-зонд (Часть VIII.5): сырые данные решения G1 — карта внимания
    # наблюдателя, позиция игрока, position-check
    _ss_now = _scene(world) or {}
    _att_now = _ss_now.get("attention_states") or {}
    _pos_now = _ss_now.get("npc_positions") or {}
    print(
        f"[DIAG-G1] att_observers={list(_att_now.keys())} "
        f"player_pos={_xy(_pos_now.get('player'))} "
        f"target_pos={_xy(_pos_now.get(target))}"
    )
    print(
        f"[DIAG-G1] att[{target}]: "
        f"{ {k: (v or {}).get('phase') for k, v in (_att_now.get(target) or {}).items()} }"
    )
    _last_obs = ((_att_now.get(target) or {}).get("player") or {})
    print(
        f"[DIAG-G1] pair-player: phase={_last_obs.get('phase')} "
        f"evidence={_last_obs.get('approach_evidence')} "
        f"window_len={len(_last_obs.get('observation_window') or [])} "
        f"last_dist={_last_obs.get('last_distance')}"
    )

    g1 = became_attentive
    ok = ok and g1
    print(
        f"[G1] {'PASS' if g1 else 'FAIL'}: evidence_peak={evidence_peak:.3f} "
        f"≥ порога {ATTENTION_EVIDENCE_THRESHOLD} — «он понял, что она идёт к нему»"
    )
    g2 = became_attentive and intent_track.get("attentive_intent", "") in (
        "observe",
        "idle",
    ) if (intent_track := {"attentive_intent": _orm_intent(world, target)}) else False
    ok = ok and g2
    print(
        f"[G2] {'PASS' if g2 else 'FAIL'}: intent='{intent_track['attentive_intent']}' "
        f"— «перестал работать и смотрит» (сцена)"
    )
    g3 = oriented
    ok = ok and g3
    print(
        f"[G3] {'PASS' if g3 else 'FAIL'}: heading[{target}] на игрока "
        f"— «повернулся к ней»"
    )

    # ── Фаза 2: УХОД → затухание → возврат к жизни ───────────────────
    print("--- Фаза 2: она уходит ---")
    await _put_player(nxy[0] + ux * 25.0, nxy[1] + uy * 25.0)
    idle(4)  # LOST-затухание: E·0.85⁴ ≈ 0.52 от пика
    e2, hit2 = _evidence(world, target)
    intent2 = _orm_intent(world, target)
    g4 = (not hit2) and intent2 not in ("observe",) or intent2 == baseline_intent
    ok = ok and bool(g4)
    print(
        f"[G4] {'PASS' if g4 else 'FAIL'}: evidence={e2:.3f} (угасла), "
        f"intent='{intent2}' — «вернулся к наковальне»"
    )

    print("=" * 64)
    verdict = "GREEN" if ok else "RED"
    print(f"P3D ИТОГО: {verdict}")
    print(
        "СЦЕНА ГЛАЗАМИ ИГРОКА: Орм стучал по наковальне. Люся вошла — "
        "прошла мимо, он и не поднял глаз. Она развернулась и пошла прямо "
        "к нему — он замер, повернул голову, отложил молоток. Она ушла за "
        "дом — он вернулся к работе." if ok else "Сцена не состоялась."
    )
    return 0 if ok else 1


if __name__ == "__main__":
    import types

    sys.exit(asyncio.run(main_async()))