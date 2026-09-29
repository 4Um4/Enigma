# -*- coding: utf-8 -*-
"""
SUPERBOX-COGNITION-P3D (санкция Мастера): перцептивное внимание →
наблюдаемое поведение. Приняточный критерий — сцена глазами игрока.

  Фаза 0 (pass-by): игрок сбоку-сзади, стоит → v̂=0 → E≈0 → NPC живёт своей
    жизнью. «Прошёл мимо — никто не среагировал.»
  Фаза 1 (approach): шаги ВНУТРИ периферийной зоны за спину (2.95→2.4→2.0)
    → окно видит ДВИЖЕНИЕ → evidence копится → порог → OBSERVE/IDLE
    побеждает базовый интент + orient-материализация.
    «Замер, повернул голову, отложил молоток.»
  Фаза 2 (уход): игрок за FOV и периферией → LOST-затухание → возврат.
    «Скрылась за домом — вернулся к наковальне.»

Мир живой: цель может уйти в traversal в любой тик (p3d11) → эксперимент
с ретраями: новая цель на попытку, exclude уже пробованных.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/cognition_p3d_test.py
"""
import asyncio
import math
import os
import shutil
import sys
import tempfile
import types
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

os.environ["COGNITION_V0"] = "1"  # ДО app.*
os.environ["COGNITION_DIAG"] = "1"  # Задача 5: utility-трейс (env-гейт)

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

from app.domain.attention import AttentionObservation
from app.models.schemas import ChatTurnRequest, PlayerAction
from app.services.game_loop_builder import build_game_loop
from app.services.npc.attention_config import ATTENTION_EVIDENCE_THRESHOLD

CAMPAIGN = "Open_road"
LOCATION = "tavern"
WORLD_ID = "default"

_EXPERIMENT_ATTEMPTS = 4
_STEP_DEPTS = (2.95, 2.4, 2.0)  # шаги внутри периферийной зоны (≤3.0 м)
_PHASE2_DEPT = 4.5              # уход: за FOV/периферию, но резолвится узлами


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


def _orm_intent(world, npc_id) -> str:
    """Интент NPC. get_npc_states → list[dict] (legacy: ключ 'id',
    intent — готовая строка; зонд probe_states)."""
    try:
        eng = world.game_loop._get_life_engine()
        states = eng.get_npc_states(CAMPAIGN) or []
        st = next(
            (
                s
                for s in states
                if isinstance(s, dict)
                and (s.get("id") or s.get("npc_id")) == npc_id
            ),
            None,
        )
        if st is None:
            return ""
        if "intent" not in st:
            # Зонд probe_states: ключ 'intent' появляется только когда
            # интент выставлен; отсутствие = IDLE (дефолт ядра), не ''.
            return "idle"
        it = st.get("intent")
        return str(getattr(it, "value", it) or "").lower()
    except Exception as _e:  # noqa: BLE001 — диагностика канала
        print(f"[DIAG-INTENT] fail: {_e}")
        return ""


def _pick_stationary(world, prev_pos, exclude=None):
    """Data-driven выбор: стационарный, НЕ беглец (сцене нужна конкуренция
    с работой — фильтр ВНУТРИ выборщика, иначе «самый дальний» возвращается
    детерминированно трижды — p3d10), не пробованный (ретрай-контур)."""
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
        if _orm_intent(world, nid) == "flee":
            continue
        if exclude and nid in exclude:
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
    """Максимум approach_evidence NPC по паре с player + признак порога."""
    top = 0.0
    for _subj, st in (_attention(world).get(npc_id) or {}).items():
        if _subj != "player":
            continue
        e = float(st.get("approach_evidence", 0.0))
        if e > top:
            top = e
    return top, top >= ATTENTION_EVIDENCE_THRESHOLD


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

    def _put_player(x, y, action="остаюсь на месте"):
        req = ChatTurnRequest(
            world_id=WORLD_ID,
            campaign_id=CAMPAIGN,
            location=LOCATION,
            actions=[PlayerAction(player_name="ВВорг", action=action)],
            player_position=(x, y),
        )
        return world.game_loop.run_turn(req)

    idle(2)

    # ── Эксперимент с ретраями: мир живой, цель уходит в traversal в
    # любой тик → попытка = pick → Фаза 0 → Фаза 1; успех = G1.
    tried: set = set()
    target = None
    nxy = None
    h = 1.5708
    baseline_intent = ""
    # Шаг 1 (вердикт Мастера): глобальные аккумуляторы — объявление ЗДЕСЬ,
    # аккумуляция ВНУТРИ цикла без повторных сбросов (замечание №1).
    evidence_peak = 0.0
    became_attentive = False
    _saw_observe = False
    g0 = True

    for attempt in range(1, _EXPERIMENT_ATTEMPTS + 1):
        # ── Pick (до 3 внутренних проб на стабильность) ──
        prev = (_scene(world) or {}).get("npc_positions") or {}
        cand = None
        for _pick_try in range(3):
            cand = _pick_stationary(world, prev, exclude=tried)
            if cand is None:
                idle(1)
                prev = (_scene(world) or {}).get("npc_positions") or {}
                continue
            idle(1)
            now = (_scene(world) or {}).get("npc_positions") or {}
            a, b = _xy(now.get(cand)), _xy(prev.get(cand))
            if a is None or b is None or a != b:
                prev = now
                continue
            break
        if cand is None:
            print(f"[PICK] попытка {attempt}: стационарного не-flee NPC нет")
            idle(2)
            continue
        target = cand
        tried.add(target)
        ss = _scene(world) or {}
        pos = ss.get("npc_positions") or {}
        nxy = _xy(pos.get(target))
        h = _heading(pos.get(target))
        baseline_intent = _orm_intent(world, target)
        print(
            f"[PICK] попытка {attempt}: цель {target} "
            f"(intent='{baseline_intent}')"
        )

        # ── Фаза 0: pass-by (сбоку-сзади 5 м, стоит → v̂=0 → E≈0) ──
        print("--- Фаза 0: проходит мимо ---")
        px0 = nxy[0] + 5.0 * math.sin(h) + 1.0 * math.cos(h)
        py0 = nxy[1] - 5.0 * math.cos(h) + 1.0 * math.sin(h)
        await _put_player(px0, py0)
        idle(2)
        e0, _hit0 = _evidence(world, target)
        _g0 = e0 < ATTENTION_EVIDENCE_THRESHOLD
        g0 = g0 and _g0
        print(
            f"[G0] {'PASS' if _g0 else 'FAIL'}: evidence={e0:.3f} < порога "
            f"— «прошёл мимо, никто не среагировал»"
        )
        if not _g0:
            continue

        # ── Фаза 1: детерминированный контроллер (Задача 2, санкция
        # Мастера). Движение через ПУБЛИЧНЫЙ интерфейс клиента:
        # player_position в каждом run_turn (T1.7: scene_init.py:80 пишет
        # local_position напрямую — ровно то, что делает реальный фронтенд).
        # Фронтальный заход (игрок в FOV с первого шага), шаг 1.2 м/тик →
        # монотонное сближение в окне → e_t≈+0.77/тик → порог за 2 тика.
        # Каждый run_turn = полный тик → подряд = непрерывное движение.
        print("--- Фаза 1: идёт к нему ---")
        # Аккумуляция без сброса: глобальные максимумы/флаги живут через
        # все попытки (max-накопление фактического evidence в APPROACH-
        # цикле уже есть; здесь только контроль отсутствия re-инициализации).
        _STEP, _STOP = 1.2, 1.8
        # (Старт шагания — от текущей позиции игрока _pxy; мёртвые _sx/_sy
        # удалены — ни один потребитель, Vulture-канон S118.)
        for _tick_i in range(10):
            _ss = _scene(world) or {}
            _pos_now = _ss.get("npc_positions") or {}
            _pxy, _txy = _xy(_pos_now.get("player")), _xy(_pos_now.get(target))
            if _pxy is None or _txy is None:
                idle(1)
                continue
            # Цель ушла в traversal → попытка неинформативна → ретрай.
            if (
                ((_ss.get("active_traversals") or {}).get(target) or {})
                .get("status")
                == "MOVING"
            ):
                print(
                    f"[PICK] попытка {attempt}: {target} ушёл в движение "
                    f"— ретрай с новой целью"
                )
                break
            _d = math.hypot(_txy[0] - _pxy[0], _txy[1] - _pxy[1])
            if _d <= _STOP:
                idle(1)
                e, _ = _evidence(world, target)
                evidence_peak = max(evidence_peak, e)
                break
            _step = min(_STEP, _d - _STOP)
            await _put_player(
                _pxy[0] + (_txy[0] - _pxy[0]) / _d * _step,
                _pxy[1] + (_txy[1] - _pxy[1]) / _d * _step,
            )
            e, _ = _evidence(world, target)
            evidence_peak = max(evidence_peak, e)
            print(
                f"[APPROACH] t={_tick_i + 1} dist={_d:.2f} "
                f"E={e:.3f} intent='{_orm_intent(world, target)}'"
            )
            if e >= ATTENTION_EVIDENCE_THRESHOLD:
                became_attentive = True
            # Данные p3d17 (Задача 5): после пробоя СТАГНАЦИЯ гасит E за
            # один тик (0.85·0.65 − 0.15 = 0.40 < порога) → cog={} →
            # реакция не приходит. Перцептивный лаг (увидел → осмыслил →
            # сделал) требует ПРОДОЛЖАЮЩЕГОСЯ движения: идём до _STOP,
            # поллим победителя хаба каждый тик (Задача 3: цепь
            # modifiers → DecisionHub → исполнение при живом стимуле).
            _it_now = _orm_intent(world, target)
            # Аккумуляция: or-семантика И причинный гейт — считаем только
            # тики при became_attentive (E≥порога). Иначе чужой базлайн
            # ('observe' у borko до всякого приближения) засчитывался как
            # победа внимания (p3d19-загрязнение отчётности).
            _saw_observe = _saw_observe or (
                became_attentive and _it_now in ("observe", "idle")
            )
            if became_attentive and _it_now in ("observe", "idle"):
                break
        if became_attentive:
            # Полный рамп E→1.0: один тик статики держит E≈0.70 ≥ 0.6 —
            # окно реакции ещё живо; читаем финальный intent.
            idle(1)
            if _orm_intent(world, target) in ("observe", "idle"):
                _saw_observe = True
            # УСПЕХ = финал эксперимента: break сохраняет target/nxy/h
            # УСПЕШНОЙ попытки — пост-гейты (G2/G3/Фаза 2) читают мир
            # именно её. Без break p3d19 перезаписывал target попыткой 4
            # (orm ушёл в движение до Фазы 0) → G3 читал чужой мир.
            break

    if target is None or nxy is None:
        print("P3D ИТОГО: RED (целей не нашлось)")
        return 1

    # ── Диагностика (Часть VIII.5): окно + offline-пересчёт ──────────
    _ss_now = _scene(world) or {}
    _att_now = _ss_now.get("attention_states") or {}
    _pos_now = _ss_now.get("npc_positions") or {}
    _pair = (_att_now.get(target) or {}).get("player") or {}
    _win = _pair.get("observation_window") or []
    _pxy, _txy = _xy(_pos_now.get("player")), _xy(_pos_now.get(target))
    print(f"[DIAG-WIN] win={[(o[0], round(o[1], 2)) for o in _win]}")
    if _pxy and _txy:
        from app.services.spatial.spatial_runtime import line_of_sight as _los

        _d_live = math.hypot(_txy[0] - _pxy[0], _txy[1] - _pxy[1])
        print(
            f"[DIAG-WIN] live_dist={_d_live:.2f} "
            f"LOS={_los(distance=_d_live, scene_state=_ss_now, ax=_pxy[0], ay=_pxy[1], bx=_txy[0], by=_txy[1])}"
        )
    if len(_win) >= 2:
        from app.domain.attention_inference import (
            evidence_delta as _ed,
        )
        from app.domain.attention_inference import (
            infer_approach as _ia,
        )
        from app.services.npc.attention_config import (
            ATTENTION_APPROACH_SCALE_M,
            ATTENTION_EVIDENCE_ALIGN_W,
            ATTENTION_EVIDENCE_RADIAL_REF,
            ATTENTION_EVIDENCE_RADIAL_W,
            ATTENTION_EVIDENCE_STILL_PENALTY,
            ATTENTION_EVIDENCE_TURN_W,
        )

        _inf = _ia(
            [
                AttentionObservation(
                    tick=o[0], distance=o[1], bearing=o[2],
                    subject_heading=o[3], rel_dx=o[4], rel_dy=o[5],
                )
                for o in _win
            ],
            _win[-1][4],
            _win[-1][5],
        )
        _e_t = _ed(
            _inf,
            False,
            radial_w=ATTENTION_EVIDENCE_RADIAL_W,
            align_w=ATTENTION_EVIDENCE_ALIGN_W,
            turn_w=ATTENTION_EVIDENCE_TURN_W,
            still_penalty=ATTENTION_EVIDENCE_STILL_PENALTY,
            radial_ref=ATTENTION_EVIDENCE_RADIAL_REF,
            approach_scale_m=ATTENTION_APPROACH_SCALE_M,
        )
        print(
            f"[DIAG-WIN] offline: speed={_inf.speed:.3f} "
            f"radial={_inf.radial_speed:.3f} align={_inf.alignment_to_me} "
            f"d*={_inf.predicted_min_distance} → e_t={_e_t:.3f}"
        )

    # ── Гейты ──────────────────────────────────────────────────────────
    g1 = became_attentive
    ok = ok and g1
    print(
        f"[G1] {'PASS' if g1 else 'FAIL'}: evidence_peak={evidence_peak:.3f} "
        f"≥ порога {ATTENTION_EVIDENCE_THRESHOLD} — «он понял, что она идёт к нему»"
    )
    _intent_now = _orm_intent(world, target)
    # Задача 6: «NPC демонстрирует наблюдаемое изменение деятельности».
    # Intent потиковый (хаб пересчитывает каждый тик) — наблюдаемый факт
    # победы внимания: hub выбрал observe/idle В ЛЮБОЙ тик внимательного
    # окна (полл + winner=-трейс COG_UTIL) ИЛИ держит его финально.
    g2 = became_attentive and (
        _saw_observe or _intent_now in ("observe", "idle")
    )
    ok = ok and g2
    print(
        f"[G2] {'PASS' if g2 else 'FAIL'}: intent='{_intent_now}' "
        f"(было '{baseline_intent}'), наблюдён_observe={_saw_observe} "
        f"— «перестал работать и смотрит»"
    )
    # G3: orient-материализация (attention_orient → body_heading).
    # Якорь bearing — ТЕКУЩАЯ позиция цели (могла сместиться после pick:
    # p3d22 — schedule жил до E-пробоя).
    _p_now = _xy((_scene(world) or {}).get("npc_positions", {}).get("player"))
    _txy_now = _xy((_scene(world) or {}).get("npc_positions", {}).get(target))
    _h_now = _heading((_scene(world) or {}).get("npc_positions", {}).get(target))
    g3 = False
    if _p_now and _txy_now:
        _b = math.atan2(_p_now[1] - _txy_now[1], _p_now[0] - _txy_now[0])
        g3 = _angdiff(_h_now, _b) < 0.15
    ok = ok and g3
    print(
        f"[G3] {'PASS' if g3 else 'FAIL'}: heading[{target}]={_h_now:.4f} "
        f"vs bearing(player)={_b:.4f} — «повернулся к ней»"
    )

    # ── Фаза 2: УХОД → LOST-затухание → возврат к жизни ───────────────
    print("--- Фаза 2: она уходит ---")
    await _put_player(nxy[0] - _PHASE2_DEPT * math.cos(h),
                      nxy[1] - _PHASE2_DEPT * math.sin(h))
    idle(8)  # пик 0.8: 0.85⁸≈0.27 → hit=False; cog={} → инерция
    # observe демпфируется каноном → хаб возвращает baseline-интент
    # (сценарий Д: «постепенно возвращается к своей жизни»)
    e2, hit2 = _evidence(world, target)
    intent2 = _orm_intent(world, target)
    g4 = (not hit2) and (intent2 != "observe" or intent2 == baseline_intent)
    ok = ok and bool(g4)
    print(
        f"[G4] {'PASS' if g4 else 'FAIL'}: evidence={e2:.3f} (угасла), "
        f"intent='{intent2}' — «вернулся к наковальне»"
    )

    print("=" * 64)
    print(f"P3D ИТОГО: {'GREEN' if ok else 'RED'}")
    print(
        "СЦЕНА ГЛАЗАМИ ИГРОКА: Орм был занят своим делом. Люся прошла "
        "мимо — он и не поднял глаз. Она развернулась и пошла прямо к "
        "нему — он замер, повернул голову и смотрел ей навстречу. Она "
        "ушла — он вернулся к своей жизни."
        if ok
        else "Сцена не состоялась."
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))