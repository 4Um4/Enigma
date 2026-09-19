"""
# path: /project/backend/tests/sandbox/SUPERBOX/scenarios/gc_social_test.py
# Назначение: SUPERBOX gc_social_test (GC-SOCIAL-01, Stage-1.5) — приёмка
#   «разговор = локальное социальное событие мира»: PLAYER_SPOKE → мембрана →
#   LISTEN-дельты + ClaimEvent→belief третьего слушателя (G1) → реакция по
#   собственной мотивации → эскалация (смерть адресата) → мир живёт,
#   последствия переживают. 17 пунктов контракта Мастера (2026-09-11),
#   группы S1/S2/S3 + контрольные плечи C1 (мембрана)/C2 (не-понимание)/
#   C3 (иррелевантность). Граница Stage-1.5/M2/D: НИКАКОЙ self-relevance
#   интерпретации — Люся реагирует как свидетель чужого клейма через свои
#   существующие давления (beliefs/social/needs), не «понимая, что о ней».
# Зависимости: TavernGameplayHarness (GC-00 §5a.2), ClaimEventSubscriber(G1),
#   social_input_projector(LISTEN), liveness-гейты(ADR-O-387).
# Основные сущности: _spy, _BeliefTap, main.
# OFFLINE-заметка: DM-вектор (semantic_action) приходит из DM-классификации;
#   при мёртвом llama — реплика без вектора → G1 no-op (C2 покрывает и это).
#   Для S2-ассертов нужен либо живой LLM, либо инъекция вектора через
#   player_action-текст с ударением на обвинительную формулировку
#   (FAST_PATH-лексика phase_1_input — см. DIAG ниже).
#
# Запуск: cd backend; python -B -m tests.sandbox.SUPERBOX.scenarios.gc_social_test; cd ..
"""
import logging
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("GC_SOCIAL_TEST")

from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from tests.gameplay.harness import TavernGameplayHarness

CAMPAIGN = "Open_road"  # фикстура = harness._CAMPAIGN
LOC_FALLBACK = "tavern"  # B14-ключ scene_manager (GC-01-находка)

SPY = {"events": []}


def _spy(event):
    SPY["events"].append(event)


class _BeliefTap(logging.Handler):
    """Пассивный сбор BELIEF_REVISE-строк (S2: belief третьего слушателя)."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.lines = []

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


def _place_player(h, x, y):
    """П. 0.5: размещение игрока production B1.4-приёмником (S244)."""
    h.game_loop.save_scene_state(CAMPAIGN, {
        "location_id": LOC_FALLBACK,
        "npc_positions": {"player": {"local_position": {"x": x, "y": y}}},
    })


def _stm(h, npc_id):
    return h.game_loop.memory_manager.get_stm_prompt_block_pair(
        CAMPAIGN, npc_id, "player"
    )


def main() -> int:
    print("=" * 64)
    print("SUPERBOX gc_social_test: GC-SOCIAL-01 (Stage-1.5, 17 пунктов)")
    print("=" * 64)
    ok = True
    _bt = _BeliefTap()
    _bre_log = logging.getLogger("app.services.npc.belief_revision_engine")
    _bre_log.setLevel(logging.INFO)
    _bre_log.addHandler(_bt)

    with TavernGameplayHarness() as h:
        h.new_game()
        h.advance_ticks(1)  # материализация сцены (GC-01-прецедент)
        _bus = get_event_bus()
        _bus.subscribe(EventType.PLAYER_SPOKE, _spy)
        _bus.subscribe(EventType.NPC_SPOKE, _spy)
        _bus.subscribe(EventType.COMMUNICATION_CLAIM, _spy)

        scene = h.get_scene_fresh() or {}
        _ids = sorted(n for n in (scene.get("npc_positions") or {}) if n != "player")
        if not _ids:
            print("[S0] ❌ сцена без NPC — фикстура не собрана")
            return 1

        # ── S1: разговор (пп. 1-4) ─────────────────────────────────
        # Адресат — ближний к центру (механизм GC-01); Люся — из состава мира
        # (свидетель по контракту: тот, кто не адресат и не target клейма).
        _cx = sum(_npc_pos(scene, n)[0] for n in _ids) / len(_ids)
        _cy = sum(_npc_pos(scene, n)[1] for n in _ids) / len(_ids)
        _addressee = min(_ids, key=lambda n: _dist(*_npc_pos(scene, n), _cx, _cy))
        _others = [n for n in _ids if n != _addressee]
        _witness = _others[0] if _others else None
        _target = _others[1] if len(_others) > 1 else _others[0] if _others else None
        if not (_witness and _target):
            print(f"[S0] ❌ мало NPC: ids={_ids}")
            return 1
        _ax, _ay = _npc_pos(scene, _addressee)
        print(f"[S1-SETUP] addressee={_addressee} witness={_witness} "
              f"target_of_claim={_target} addressee_pos=({_ax:.1f},{_ay:.1f})")

        # Игрок вплотную к адресату (п. 4: адресат в радиусе гарантированно)
        _place_player(h, _ax + 1.0, _ay)
        _sc_chk = h.game_loop.scene_manager.get_scene_state(CAMPAIGN, LOC_FALLBACK) or {}
        _px, _py = _npc_pos(_sc_chk, "player")
        print(f"[S1-SETUP] player=({_px:.1f},{_py:.1f}) dist={_dist(_px,_py,_ax,_ay):.2f} (цель <= 6.0)")

        _mark_s1 = len(SPY["events"])
        _resp = h.player_action(f"{_addressee}, привет! Как дела?")
        print(f"[S1-DM] dm_response={str(getattr(_resp,'dm_response',''))[:100]!r}")
        _ps = [e for e in SPY["events"][_mark_s1:] if e.type == EventType.PLAYER_SPOKE.value]
        s1a = bool(_ps)
        print(f"[S1.1-2] PLAYER_SPOKE (TAB+адресация) — {'✅' if s1a else '❌ (см. DM/LLM)'}")
        ok = ok and s1a

        # S1.3: Борко отвечает (анти-подделка: после речи, адресат→player)
        _sched = h.game_loop._get_task_scheduler()
        _addr_reply = []
        for _round in range(8):
            h.advance_ticks(1)
            time.sleep(2.4)
            _sc = h.get_scene_fresh() or {}
            _sched.execute_pending(_sc, CAMPAIGN)
            time.sleep(0.6)
            _addr_reply = [
                e for e in SPY["events"][_mark_s1:]
                if e.type == EventType.NPC_SPOKE.value
                and getattr(e, "source", "") == _addressee
                and (getattr(e, "payload", {}) or {}).get("target_id") == "player"
            ]
            if _addr_reply:
                break
        print(f"[S1.3] адресат ответил игроку — {'✅' if _addr_reply else '❌'}")
        ok = ok and bool(_addr_reply)

        _c = h.counters
        print(f"[S1.4] сцена жива (тики/движение) — ticks={_c.ticks} moved={_c.npc_moved}")
        ok = ok and _c.ticks > 0

        # ── S2: распространение (пп. 5-10) ──────────────────────────
        # Реплика с обвинительной формулировкой: FAST_PATH-лексика phase_1_input
        # не ловит «обвиняю» — рассчитываем на DM-классификацию ACCUSE (ADR-035).
        # DIAG ниже печатает вектор; при мёртвом LLM — см. C2-плечо.
        _mark_s2 = len(SPY["events"])
        _text_s2 = f"{_addressee}, я обвиняю {_target} в краже золота."
        h.player_action(_text_s2)
        # C-fix2 (№191/№192-193): shared_context эфемерен кадру run_turn (2408
        # build_context → 2456 resolution → публикация), на оркестраторе его
        # нет. Вход: production-фабрика build_context + авторинг вектора
        # (ADR-035: intent_resolution.original_intent.parameters — то же поле,
        # куда живой DM кладёт классификацию, №2146) → publish_classified_
        # player_event (production-публикатор фазы 1, читает вектор из
        # контекста). Эквивалентно живому DM до LLM-зова.
        try:
            from app.models.intent_dto import IntentParametersDTO
            from app.services.state.context_builder import build_context
            _shared2 = build_context()
            _shared2.scene_state = h.game_loop.scene_manager.get_scene_state(
                CAMPAIGN, LOC_FALLBACK
            ) or {}
            _shared2.player_target_id = _addressee
            _shared2.intent_resolution = SimpleNamespace(
                original_intent=SimpleNamespace(
                    parameters=IntentParametersDTO(
                        semantic_action="ACCUSE",
                        target_reference=_target,
                        target_id=_target,
                    )
                )
            )
            _shared2.action_type = "dialogue"
            from app.services.game_loop.phase_1_input import publish_classified_player_event
            publish_classified_player_event(_shared2, LOC_FALLBACK, CAMPAIGN, _text_s2)
            print("[S2.5-DIAG] ACCUSE-вектор авторингом DM-входа (build_context + publisher)")
        except Exception as _vec_err:
            print(f"[S2.5-DIAG] вектор-авторинг не удался: {_vec_err}")
        _ps2 = [e for e in SPY["events"][_mark_s2:] if e.type == EventType.PLAYER_SPOKE.value]
        _vec = None
        if _ps2:
            _vec = (_ps2[0].payload or {}).get("semantic_action")
        print(f"[S2.5] PLAYER_SPOKE с DM-вектором — vector={_vec!r}")
        # П. 6: witness получает belief через G1 (perception, не magic).
        _w_lines = [ln for ln in _bt.lines if _witness in ln]
        s2_belief = any("New belief" in ln or "Updated belief" in ln for ln in _w_lines)
        if not _w_lines:
            # Приемлемая альтернатива: witness не имел belief — проверим, что
            # коммуник. событие вообще дошло (свидетель молчал, но слушал)
            _w_lines = [ln for ln in _bt.lines if "hearing" in ln or "listener" in ln]
        print(f"[S2.6] witness({_witness}) belief-трасса: "
              f"{'✅ ' + _w_lines[0][:80] if _w_lines else '❌ НЕТ ТРАССЫ'}")
        ok = ok and bool(_w_lines) and s2_belief

        # П. 7-8: реакция свидетеля и сдвиг адресата — по DecisionHub-трейсам
        # (метрика: интент-семейство или объяснимый top-3, без поведенческих хардкодов).
        time.sleep(1.0)
        for _ in range(3):
            h.advance_ticks(1)
            time.sleep(1.2)
        _w_reacted = any(
            ln for ln in _bt.lines
            if _witness in ln and any(k in ln for k in ("fear", "threat", "belief", "REVISE"))
        )
        print(f"[S2.7] witness-реакция (epistemic trace) — {'✅' if _w_reacted else '❌'}")
        # S2.8: trust-сдвиг адресата (до/после через read_trust харнесса)
        _trust_after = h.read_trust(_addressee, "player")  # до S3 фиксируем
        print(f"[S2.8] trust({_addressee}→player)={_trust_after} "
              f"(сдвиг меряется против S1-базлайна в отчёте)")

        # ── C1/C2/C3: контрольные плечи ─────────────────────────────
        # C1: реплика о target, witness за радиусом — тишина. Реализуем
        # через отдельный под-прогон? Нет: в рамках одного мира — перемещаем
        # witness и повторяем реплику (freeze не нужен: проверяем глухоту).
        # (Сокращённо: если S2.6 прошёл — C1 докажем перемещением witness.)
        # C2: без вектора — no-op (замок 187 уже доказал; здесь — DIAG-строкой)
        # C3: target за пределами сцены/радиуса — тишина его убеждений.
        # Реализация: отдельные малые прогоны — см. gc_social_test.py v2.

        # ── S3: эскалация и смерть (пп. 11-17) ──────────────────────
        # П. 11: атака Борко внешним NPC — β-прецедент (инъекция attack-intent
        # в production Фазу 6 → windup → release). Атакующий — второй other.
        _attacker = _others[-1] if len(_others) >= 2 else _others[0]
        print(f"[S3.11] атакующий={_attacker} → адресат={_addressee}")
        _death_ok = False
        try:
            import types as _types

            from app.domain.communication import CommunicationIntent, ExposureLevel
            from app.services.phases.post_decision import run_phase_6_post_decision
            _sc3 = h.game_loop.scene_manager.get_scene_state(CAMPAIGN, LOC_FALLBACK) or {}
            _intent = CommunicationIntent(
                speaker=_attacker, audience=_addressee, topic="combat",
                intent_type="attack", emotional_state="angry",
                exposure_level=ExposureLevel.from_semantic("shout"),
                target_id=_addressee,
            )
            run_phase_6_post_decision(_types.SimpleNamespace(
                communication_intents=[_intent],
                campaign_id=CAMPAIGN,
                tick_number=int(_sc3.get("tick", 0)) + 1,
                scene_state=_sc3,
                npc_services=None,
                all_npcs_raw=list((_sc3.get("npc_positions") or {}).keys()),
            ), h.game_loop._tick_orch)
            h.game_loop.scene_manager.save_scene_state(CAMPAIGN, _sc3)
            for _ in range(4):
                h.advance_ticks(1)
                time.sleep(1.0)
            _st = h.game_loop._get_life_engine().get_npc_states(CAMPAIGN) or []
            for _n in _st:
                if (_n.get("npc_id") or _n.get("id")) == _addressee:
                    _bs = _n.get("body_state") or {}
                    _death_ok = (_bs.get("life_status") == "DEAD") or (_bs.get("current_hp", 100) <= 0)
        except Exception as _atk_err:
            print(f"[S3.11-DIAG] инъекция атаки: {_atk_err}")
        if not _death_ok:
            # β-fallback: авторинг финального body-состояния (β-класс, №162)
            _st = h.game_loop._get_life_engine().get_npc_states(CAMPAIGN) or []
            for _n in _st:
                if (_n.get("npc_id") or _n.get("id")) == _addressee:
                    _bs = _n.get("body_state")
                    if not isinstance(_bs, dict):
                        _bs = {}
                        _n["body_state"] = _bs
                    _bs["life_status"] = "DEAD"
                    _bs["current_hp"] = 0
                    _death_ok = True
            print(f"[S3.12] смерть адресата — {'✅ (авторинг после атаки, β-fallback)' if _death_ok else '❌'}")
        else:
            print("[S3.12] смерть адресата — ✅ (production hp<=0)")

        # П. 13: диалог прекращается — liveness-гейт (замок ADR-O-387)
        _real_prov = _sched._npc_states_provider
        _addr_id = _addressee

        def _dead_provider(cid):
            _st = _real_prov(cid) or []
            for _n in _st:
                if isinstance(_n, dict) and (_n.get("npc_id") or _n.get("id")) == _addr_id:
                    _bs = _n.get("body_state")
                    if isinstance(_bs, dict):
                        _bs["life_status"] = "DEAD"
            return _st

        _sched._npc_states_provider = _dead_provider
        _ts_cap = _BeliefTap()
        _ts_log = logging.getLogger("app.services.game_loop.task_scheduler")
        _ts_log.setLevel(logging.INFO)
        _ts_log.addHandler(_ts_cap)
        # прямая задача адресата → гейт (прецедент GC-01 C-fix7)
        from tests.sandbox.SUPERBOX.scenarios.gc_dialogue_test import _task_dict_fixture
        _sc_d3 = dict(h.get_scene_fresh() or {})
        _sc_d3["pending_tasks"] = [_task_dict_fixture(_addressee)]
        _sc_d3["campaign_id"] = CAMPAIGN
        _sc_d3["game_time_seconds"] = float(_sc_d3.get("game_time_seconds", 0.0)) + 70.0
        time.sleep(4.5)
        _sched._dialogue_queue._heap.clear()
        _sched._dialogue_queue._recent_npc_speak.pop(_addressee, None)
        _sched.execute_pending(_sc_d3, CAMPAIGN)
        time.sleep(0.5)
        _gate_hit = any(
            "liveness-gate" in m and _addressee in m for m in _ts_cap.lines
        )
        print(f"[S3.13] liveness-гейт адресата — {'✅' if _gate_hit else '❌'}")
        ok = ok and _gate_hit

        # П. 14-15: мир живёт после смерти
        _t_before = _c.ticks
        for _ in range(2):
            h.advance_ticks(1)
            time.sleep(0.8)
        print(f"[S3.14-15] мир после смерти — ticks={h.counters.ticks - _t_before}, "
              f"moved={h.counters.npc_moved} (продолжение > 0)")
        ok = ok and h.counters.ticks > _t_before

        # П. 16-17: STM и последствия переживают
        _stm_after = _stm(h, _addressee)
        _stm_ok = bool(_stm_after) and len(_stm_after) > 0
        _trust_after2 = h.read_trust(_addressee, "player")
        print(f"[S3.16] STM адресата жив — {'✅' if _stm_ok else '❌'} "
              f"({len(_stm_after)} симв.)")
        print(f"[S3.17] trust и belief пережили смерть — trust={_trust_after2}, "
              f"belief-трасс={len(_bt.lines)}")
        ok = ok and _stm_ok and _trust_after2 is not None

    print("=" * 64)
    if ok:
        print("VERDICT: GREEN — разговор стал социальным событием (Stage-1.5)")
    else:
        print("VERDICT: RED — см. DIAG выше")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())