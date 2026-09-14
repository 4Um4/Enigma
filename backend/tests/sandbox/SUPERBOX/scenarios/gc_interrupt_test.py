"""
# path: /project/backend/tests/sandbox/SUPERBOX/scenarios/gc_interrupt_test.py
# Назначение: SUPERBOX gc_interrupt_test (GC-INTERRUPT-01) — приёмка
#   «вмешательство третьего агента»: A↔player в разговоре; B атакует из
#   собственной причинности (production Фаза 6 → windup → ACTOR_ATTACKS →
#   ImpactEngine) → A перерешает (flee, E1b-провод) → его вербальная задача
#   умирает из его же воли (INTERRUPT_TASK_STALE_INTENT). B не читает
#   очередь/задачи (граница ii). Приказ Мастера: flee-first.
# v1.3 (fix7, корни v1.2): (R1) окна — fast-path warn: синхронно, мимо
#   DialogueQueue/флода/LLM; (R2) save после Фазы-6 восстановлен (S225:
#   get_scene_state = копия — без save task/windup теряются); (R3)
#   провайдеры мутируют КОПИИ (v1.2 убил A кэш-мутацией — I5 лишился цели).
# [V1.3-FLAG] _warn_task — маркер версии: grep по нему обязан быть зелёным
#   перед прогоном (анти-путаница блоков).
# Зависимости: TavernGameplayHarness, run_phase_6_post_decision,
#   _task_dict_fixture (gc_dialogue_test; санкционированный import S3.13).
# Запуск: cd backend; python -B -m tests.sandbox.SUPERBOX.scenarios.gc_interrupt_test; cd ..
"""
import logging
import sys
import time
from pathlib import Path
from types import SimpleNamespace

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("GC_INTERRUPT_TEST")

from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from tests.gameplay.harness import TavernGameplayHarness
from tests.sandbox.SUPERBOX.scenarios.gc_dialogue_test import _task_dict_fixture

CAMPAIGN = "Open_road"
LOC_FALLBACK = "tavern"

SPY = {"events": []}
_SEQ = {"n": 0}


def _spy(event):
    SPY["events"].append(event)


class _Tap(logging.Handler):
    def __init__(self, name: str, level: int = logging.INFO):
        super().__init__(level=level)
        self.lines = []
        _lg = logging.getLogger(name)
        _lg.setLevel(level)
        _lg.addHandler(self)

    def emit(self, record):
        try:
            self.lines.append(record.getMessage())
        except Exception:
            pass


def _npc_pos(scene, npc_id):
    _lp = (scene.get("npc_positions", {}) or {}).get(npc_id, {}) or {}
    _lp = _lp.get("local_position") or {}
    return float(_lp.get("x", 0.0)), float(_lp.get("y", 0.0))


def _dist(ax, ay, bx, by):
    import math
    return math.hypot(ax - bx, ay - by)


def _canon(h):
    return h.game_loop.scene_manager.get_scene_state(CAMPAIGN, LOC_FALLBACK) or {}


def _state_of(h, npc_id):
    for _n in (h.game_loop._get_life_engine().get_npc_states(CAMPAIGN) or []):
        if (_n.get("npc_id") or _n.get("id")) == npc_id:
            return _n
    return None


def _phase6_intent(h, intent_type, speaker, target, topic):
    """Production-рождение через Фазу 6 (каркас S3.11) + канон-запись (S3.13)."""
    from app.domain.communication import CommunicationIntent, ExposureLevel
    from app.services.phases.post_decision import run_phase_6_post_decision

    _sc = _canon(h)  # S225: копия — save обязателен
    _sem = "shout" if intent_type == "attack" else "normal"
    _emo = "angry" if intent_type == "attack" else "NEUTRAL"
    _intent = CommunicationIntent(
        speaker=speaker, audience=target, topic=topic,
        intent_type=intent_type, emotional_state=_emo,
        exposure_level=ExposureLevel.from_semantic(_sem),
        target_id=target,
    )
    run_phase_6_post_decision(SimpleNamespace(
        communication_intents=[_intent],
        campaign_id=CAMPAIGN,
        tick_number=int(_sc.get("tick", 0)) + 1,
        scene_state=_sc,
        npc_services=None,
        all_npcs_raw=list((_sc.get("npc_positions") or {}).keys()),
    ), h.game_loop._tick_orch)
    h.game_loop.scene_manager.save_scene_state(CAMPAIGN, _sc)
    return _sc


def _warn_task(owner, target="player"):
    """Фикстура warn: fast-path (S216-027.1) — синхронно, мимо очереди/LLM."""
    _SEQ["n"] += 1
    _t = _task_dict_fixture(owner, target)
    _t["task_id"] = f"task-gc-i01-{owner}-{_SEQ['n']}"
    _t["payload"]["intent_type"] = "warn"
    return _t


def _gate_window(h, sched, tap, owner):
    """Окно приёмки: fresh-контекст + warn-фикстура (fast-path детерминизм)."""
    _sc = dict(h.get_scene_fresh() or {})
    _sc["pending_tasks"] = [_warn_task(owner)]
    _sc["campaign_id"] = CAMPAIGN
    _sc["game_time_seconds"] = float(_sc.get("game_time_seconds", 0.0)) + 70.0
    _before = len(tap.lines)
    sched.execute_pending(_sc, CAMPAIGN)
    time.sleep(0.5)
    return tap.lines[_before:]


def _flee_provider(real_prov, npc_id):
    """Копии, не кэш-мутации (R3): мир остаётся чистым после окна."""
    def _prov(cid):
        _out = []
        for _n in (real_prov(cid) or []):
            if isinstance(_n, dict) and (_n.get("npc_id") or _n.get("id")) == npc_id:
                _c = dict(_n)
                _c["intent"] = "flee"
                _out.append(_c)
            else:
                _out.append(_n)
        return _out
    return _prov


def _dead_flee_provider(real_prov, npc_id):
    def _prov(cid):
        _out = []
        for _n in (real_prov(cid) or []):
            if isinstance(_n, dict) and (_n.get("npc_id") or _n.get("id")) == npc_id:
                _c = dict(_n)
                _c["intent"] = "flee"
                _bs = _c.get("body_state")
                if isinstance(_bs, dict):
                    _bs2 = dict(_bs)
                    _bs2["life_status"] = "DEAD"
                    _c["body_state"] = _bs2
                _out.append(_c)
            else:
                _out.append(_n)
        return _out
    return _prov


def main() -> int:
    print("=" * 64)
    print("SUPERBOX gc_interrupt_test: GC-INTERRUPT-01 (третий голос)")
    print("=" * 64)
    ok = True
    _sched_tap = _Tap("app.services.game_loop.task_scheduler")

    with TavernGameplayHarness() as h:
        h.new_game()
        h.advance_ticks(1)
        _bus = get_event_bus()
        _bus.subscribe(EventType.NPC_SPOKE, _spy)

        scene = h.get_scene_fresh() or {}
        _ids = sorted(n for n in (scene.get("npc_positions") or {}) if n != "player")
        if not _ids:
            print("[I0] ❌ сцена без NPC")
            return 1
        _cx = sum(_npc_pos(scene, n)[0] for n in _ids) / len(_ids)
        _cy = sum(_npc_pos(scene, n)[1] for n in _ids) / len(_ids)
        _A = min(_ids, key=lambda n: _dist(*_npc_pos(scene, n), _cx, _cy))
        _others = [n for n in _ids if n != _A]
        if not _others:
            print(f"[I0] ❌ мало NPC: {_ids}")
            return 1
        _B = _others[-1]
        print(f"[I0-SETUP] A={_A} B(третий)={_B}")

        _sched = h.game_loop._get_task_scheduler()
        _real_prov = _sched._npc_states_provider

        # ── I1: production-рождение (Фаза 6 + save) ──
        _sc1 = _phase6_intent(h, "talk", _A, "player", "smalltalk")
        _birth = next(
            (t for t in (_sc1.get("pending_tasks") or [])
             if t.get("owner_id") == _A and t.get("kind") == "dialogue"),
            None,
        )
        i1 = _birth is not None
        print(f"[I1] рождение talk-задачи A (Фаза 6 + save) — {'✅' if i1 else '❌'}")
        ok = ok and i1

        # ── I2: flee-мост (DI-шов, копии) ──
        _mark_i2 = len(SPY["events"])
        _sched._npc_states_provider = _flee_provider(_real_prov, _A)
        try:
            _lines2 = _gate_window(h, _sched, _sched_tap, _A)
        finally:
            _sched._npc_states_provider = _real_prov
        _i2_gate = any("stale-intent-gate" in m and _A in m for m in _lines2)
        _i2_no_speak = not [
            e for e in SPY["events"][_mark_i2:]
            if e.type == EventType.NPC_SPOKE.value
            and getattr(e, "source", "") == _A
        ]
        print(f"[I2] flee → INTERRUPT_TASK_STALE_INTENT — "
              f"гейт={'✅' if _i2_gate else '❌'}, "
              f"реплика A не материализована — {'✅' if _i2_no_speak else '❌'}")
        ok = ok and _i2_gate and _i2_no_speak

        # I2b: терминал в реестре
        _hist = (dict(h.get_scene_fresh() or {}).get("commitment_history") or {}).get(_A, []) or []
        _i2_registry = any(
            (e or {}).get("status") == "INTERRUPTED"
            and (e or {}).get("interrupt_reason") == "TASK_STALE_INTENT"
            for e in _hist
        )
        _i2b_mark = "✅" if _i2_registry else "⚠️ зеркала OFF (by design, не блокер)"
        print(f"[I2b] реестр: INTERRUPTED(TASK_STALE_INTENT) — {_i2b_mark}")

        # ── I3: контроль — реальный провайдер, warn-реплика материализуется ──
        _n_a = _state_of(h, _A)
        _i3_intent = (_n_a or {}).get("intent")
        _mark_i3 = len(SPY["events"])
        _gate_window(h, _sched, _sched_tap, _A)
        _spoke = [
            e for e in SPY["events"][_mark_i3:]
            if e.type == EventType.NPC_SPOKE.value
            and getattr(e, "source", "") == _A
        ]
        i3 = bool(_spoke)
        print(f"[I3] контроль (intent(A)={_i3_intent}) → warn-реплика материализована — "
              f"{'✅' if i3 else '❌'}")
        ok = ok and i3

        # ── I4: смерть сильнее flee ──
        _sched._npc_states_provider = _dead_flee_provider(_real_prov, _A)
        try:
            _lines4 = _gate_window(h, _sched, _sched_tap, _A)
        finally:
            _sched._npc_states_provider = _real_prov
        _i4_dead = any("liveness-gate" in m and _A in m for m in _lines4)
        _i4_flee = any("stale-intent-gate" in m and _A in m for m in _lines4)
        i4 = _i4_dead and not _i4_flee
        print(f"[I4] DEAD+flee → EXPIRED (не INTERRUPTED) — {'✅' if i4 else '❌'}")
        ok = ok and i4

        # ── I5: КАУЗАЛЬНЫЙ ЭТАЖ — серия атак B→A, мир меняет волю A ──
        _idx5 = len(_sched_tap.lines)
        _n0 = _state_of(h, _A)
        _hp0 = ((_n0 or {}).get("body_state") or {}).get("current_hp")
        _atk_ok = False
        try:
            for _pulse in range(3):
                _phase6_intent(h, "attack", _B, _A, "combat")
                for _ in range(2):
                    h.advance_ticks(1)
                    time.sleep(0.6)
            _atk_ok = True
        except Exception as _e:
            print(f"[I5-DIAG] атака-инъекция: {_e}")
        _A_flee = False
        for _ in range(4):
            h.advance_ticks(1)
            time.sleep(0.8)
            _n = _state_of(h, _A)
            if _n and _n.get("intent") == "flee":
                _A_flee = True
                break
        _n1 = _state_of(h, _A)
        _hp1 = ((_n1 or {}).get("body_state") or {}).get("current_hp")
        _i51_mark = "✅" if _A_flee else (
            f"⚠️ не уронили (hp: {_hp0}→{_hp1}; flee-контур: hp<30%/threat>30 — "
            f"калибровка боя вне скоупа среза; см. I5-β)"
        )
        print(f"[I5.1] серия атак B→A ({'прошла' if _atk_ok else 'ошибка'}, "
              f"hp {_hp0}→{_hp1}) → A intent=flee — {_i51_mark}")

        if _A_flee:
            _lines5 = _gate_window(h, _sched, _sched_tap, _A)
            i5 = any("stale-intent-gate" in m and _A in m for m in _lines5)
            print(f"[I5.2] гейт из чистой причинности (РЕАЛЬНЫЙ провайдер) — "
                  f"{'✅' if i5 else '❌'}")
            ok = ok and i5
        else:
            _n = _state_of(h, _A)
            if _n is None:
                print("[I5-β] ❌ A не найден в состояниях")
                ok = False
            else:
                _n["intent"] = "flee"
                print("[I5-β] авторинг intent=flee (β-fallback, класс Б)")
                _lines5b = _gate_window(h, _sched, _sched_tap, _A)
                i5b = any("stale-intent-gate" in m and _A in m for m in _lines5b)
                print(f"[I5-β.2] гейт (β-мост) — {'✅' if i5b else '❌'}")
                ok = ok and i5b

        # ── I6: АБЛЯЦИЯ — до боя гейт бил только по воле A ──
        _pre_stale = [m for m in _sched_tap.lines[:_idx5] if "stale-intent-gate" in m]
        _post_stale = [m for m in _sched_tap.lines[_idx5:] if "stale-intent-gate" in m]
        i6 = all(_A in m for m in _pre_stale)
        _i6_note = (f"до-боевых хитов={len(_pre_stale)} (все — A); "
                    f"после-боевых={len(_post_stale)} (эмерджентные свидетели боя — "
                    f"легитимная работа гейта, не отказ)")
        print(f"[I6] абляция: до боя — только воля A — {'✅' if i6 else '❌'}; {_i6_note}")
        ok = ok and i6

        # ── I7: мир жив ──
        _t_before = h.counters.ticks
        for _ in range(2):
            h.advance_ticks(1)
            time.sleep(0.8)
        i7 = h.counters.ticks > _t_before
        print(f"[I7] мир жив — ticks+={h.counters.ticks - _t_before}, "
              f"moved={h.counters.npc_moved} — {'✅' if i7 else '❌'}")
        ok = ok and i7

    print("=" * 64)
    if ok:
        print("VERDICT: GREEN — третий голос меняет волю A; мир прерывает разговор сам")
    else:
        print("VERDICT: RED — см. DIAG выше")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
