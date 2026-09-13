"""
# path: /project/backend/tests/sandbox/SUPERBOX/scenarios/gc_dialogue_test.py
# Назначение: SUPERBOX gc_dialogue_test (GC-DIALOGUE-01, Stage-1) — приёмка
#   позвоночника живого разговора игрок↔NPC, 14 пунктов Мастера (канон
#   подтверждён 2026-09-11). Группы:
#   D1 — живой разговор (пп. 3-9): вход игрока ТОЛЬКО production REST
#       (harness.player_action → run_turn) → PLAYER_SPOKE на шине с radius
#       из SSOT → pair-STM адресата (dm_phase) → ответ NPC (NPC_SPOKE через
#       production execute_pending) → мир живёт (traversals/ambient/counters).
#   D2 — смерть прерывает mid-generation (пп. 10-11): диалоговая задача
#       владельца DEAD → EXPIRED (ADR-O-365 terminal-mapping, гейт B,
#       решение Мастера 2026-09-11) — посмертной реплики на шине нет.
#       Смерть = авторинг ВХОДНОГО body-состояния engine-кэша (β-прецедент
#       _author_thief_will S225: начальные условия агента, guard не участвует).
#   D3 — разговор выживает через STM (пп. 12-13): pair-сессии переживают
#       прерывание; тема в STM-блоке пары (NPC помнит тему, S145).
#   INTEGRITY (п. 14): ни одной инъекции belief/event/intent NPC-стороны.
#       NPC-идентификаторы — только фикстуры адресации (FT-1 прямая форма);
#       механизмы (резолв цели/STM/гейты) generic, без id-ветвлений.
#   Пп. 1-2 (TAB-фокус, пейсинг ×4 ≈125мс) — живая сессия, чеклист в хвосте.
# Зависимости: TavernGameplayHarness (GC-00 §5a.2), EventBus, TaskScheduler.
# Основные сущности: _spy, _SchedCapture, _author_death, main.
# OFFLINE-заметка: player-вход через REST/DM — при живом llama-server DM
#   реальный; при мёртвом dm_result может быть невалиден (RE-D2 guard) —
#   DIAG покажет. Метрика D1 — событие NPC_SPOKE НА ШИНЕ (уровень журнала
#   может фильтровать заглушки, V8-SOC-11).
#
# Запуск: cd backend; python -B -m tests.sandbox.SUPERBOX.scenarios.gc_dialogue_test; cd ..
"""
import logging
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("GC_DIALOGUE_TEST")

from app.domain.constants import action_perception_radius
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from tests.gameplay.harness import TavernGameplayHarness

CAMPAIGN = "Open_road"  # фикстура = harness._CAMPAIGN

SPY = {"events": []}


def _spy(event):
    SPY["events"].append(event)


class _SchedCapture(logging.Handler):
    """Пассивный сбор логов TaskScheduler (D2: маркер liveness-gate)."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records = []

    def emit(self, record):
        try:
            self.records.append(record.getMessage())
        except Exception:
            pass


def _npc_pos(scene, npc_id):
    _lp = (scene.get("npc_positions", {}) or {}).get(npc_id, {}) or {}
    _lp = _lp.get("local_position") or {}
    return float(_lp.get("x", 0.0)), float(_lp.get("y", 0.0))


def _dist(ax, ay, bx, by):
    import math
    return math.hypot(ax - bx, ay - by)


def _author_death(h, npc_id):
    """D2: авторинг ВХОДНОГО body-состояния (β-прецедент S225 — начальные
    условия агента в engine-кэше; не runtime-мутация NPCState, guard вне
    контура). Провайдер liveness-гейта (_resolve_npcs_snapshot) читает тот
    же кэш — гейт обязан увидеть DEAD."""
    _states = h.game_loop._get_life_engine().get_npc_states(CAMPAIGN) or []
    for _n in _states:
        if _n.get("npc_id") == npc_id or _n.get("id") == npc_id:
            _bs = _n.get("body_state")
            if not isinstance(_bs, dict):
                _bs = {}
                _n["body_state"] = _bs
            _bs["life_status"] = "DEAD"
            _bs["current_hp"] = 0
            return True
    return False


def _queue_owners(sched):
    """DIAG: владельцы задач в DialogueQueue (pacing держит их между тиками)."""
    _owners = set()
    try:
        for _item in getattr(sched._dialogue_queue, "_heap", []) or []:
            _p = getattr(_item, "payload", {}) or {}
            _o = _p.get("speaker_id") or (_p.get("task_dict", {}) or {}).get("owner_id")
            if _o:
                _owners.add(_o)
    except Exception:
        pass
    return _owners


def _task_dict_fixture(owner: str, target: str = "maid_lusya") -> dict:
    # Production-форма сериализации Фазы 6 (зеркалит замок liveness); fallback,
    # если живая очередь не отдала задачу жертвы. Enum-значения через .value
    # (урок S252 — не угадывать строки).
    from app.domain.execution import TaskKind, TaskPriority, TaskState

    return {
        "task_id": f"task-d2-{owner}", "tick": 1, "counter": 0,
        "kind": TaskKind.DIALOGUE.value, "priority": TaskPriority.NORMAL.value,
        "state": TaskState.PENDING.value, "creator_system": "DecisionHub",
        "owner_id": owner, "target_ids": [target],
        "payload": {
            "topic": "золото", "target_id": target,
            "exposure_semantic": "normal", "intent_type": "talk",
            "emotional_state": "NEUTRAL", "npc_npc_context": "",
            "thread_id": "thread-d2", "prepared_prompt": "",
            "proposition": None,
        },
        "created_tick": 1,
    }


def _stm_block(h, npc_id):
    return h.game_loop.memory_manager.get_stm_prompt_block_pair(CAMPAIGN, npc_id, "player")


def main() -> int:
    print("=" * 64)
    print("SUPERBOX gc_dialogue_test: GC-DIALOGUE-01 (Stage-1, 14 пунктов)")
    print("=" * 64)
    ok = True
    _cap = _SchedCapture()
    # C-fix2 (№143): маркер liveness-гейта пишется на INFO; корень сценария
    # WARNING — без явного уровня логгера записи фильтруются ДО хендлера.
    _ts_log = logging.getLogger("app.services.game_loop.task_scheduler")
    _ts_log.setLevel(logging.INFO)
    _ts_log.addHandler(_cap)

    with TavernGameplayHarness() as h:
        h.new_game()
        # C-fix (зонд №138): сцена материализуется тиком (ensure_scene → commit);
        # чтение сразу после new_game видело пустой npc_positions. Прогрев —
        # один production idle_tick (прецедент GORAN G0: "_tick(world) #
        # инициализация сцены"), затем fresh-чтение; фоллбек — живой срез
        # LifeEngine-кэша (inspect-контур, read-only).
        h.advance_ticks(1)
        _bus = get_event_bus()
        _bus.subscribe(EventType.PLAYER_SPOKE, _spy)
        _bus.subscribe(EventType.NPC_SPOKE, _spy)

        scene = h.get_scene_fresh() or {}
        if not (scene.get("npc_positions") or {}):
            _np_fallback = {}
            for _n in h.game_loop._get_life_engine().get_npc_states(CAMPAIGN) or []:
                _nid = _n.get("npc_id") or _n.get("id")
                if _nid:
                    _lp = _n.get("local_position") or {}
                    _np_fallback[_nid] = {"local_position": _lp}
            if _np_fallback:
                scene = dict(scene)
                scene["npc_positions"] = _np_fallback
                print(f"[D1-FALLBACK] сцена собрана из LifeEngine-кэша: "
                      f"{len(_np_fallback)} NPC")
        _ids = sorted(
            n for n in (scene.get("npc_positions", {}) or {})
            if n != "player"
        )
        if not _ids:
            print("[D1] ❌ сцена без NPC — фикстура не собрана")
            return 1

        # ── D1: живой разговор (пп. 3-9) ────────────────────────────
        # Адресат = ближний к центру NPC (механизм выбора, не хардкод ветки).
        _cx = sum(_npc_pos(scene, n)[0] for n in _ids) / len(_ids)
        _cy = sum(_npc_pos(scene, n)[1] for n in _ids) / len(_ids)
        _addressee = min(_ids, key=lambda n: _dist(*_npc_pos(scene, n), _cx, _cy))
        _victim = max(_ids, key=lambda n: _dist(*_npc_pos(scene, n), _cx, _cy))
        _ax, _ay = _npc_pos(scene, _addressee)
        print(f"[D1-SETUP] addressee={_addressee} victim={_victim} "
              f"addressee_pos=({_ax:.1f},{_ay:.1f})")

        # П. 0.5 (размещение игрока): production B1.4-приёмник (S244) —
        # единственный легальный канал player-position; игрок в 1.2 м.
        # C-fix2 (№143): B1.4-приёмник ищет сцену по КЛЮЧУ scene_manager —
        # это 'tavern' (канон DriftLab/GORAN), не harness-location
        # 'tavern_silver_wolf' (расхождение зарегистрировано harness.py:50).
        # Иначе «scene not found» → запись молча отменена (лог №143).
        _loc = h.location
        if not h.game_loop.scene_manager.get_scene_state(CAMPAIGN, _loc):
            _loc = "tavern"
        h.game_loop.save_scene_state(CAMPAIGN, {
            "location_id": _loc,
            "npc_positions": {"player": {
                "local_position": {"x": _ax + 1.2, "y": _ay}
            }},
        })
        # C-fix3 (№144): писали в сцену '_loc' — её и читаем; get_scene_fresh
        # возвращает harness-копию 'tavern_silver_wolf' со спавном (живой
        # контур при этом видел игрока рядом с адресатом: SPATIAL_DATA 3.49).
        _scene_chk = h.game_loop.scene_manager.get_scene_state(CAMPAIGN, _loc) or {}
        _px, _py = _npc_pos(_scene_chk, "player")
        _pd = _dist(_px, _py, _ax, _ay)
        print(f"[D1-SETUP] player=({_px:.1f},{_py:.1f}) в сцене '{_loc}' "
              f"dist(player,addressee)={_pd:.2f} (цель <= 6.0; "
              f"{'OK' if _pd <= 6.0 else 'НЕ ПРОШЛО — см. B14-RECV/SC-3'})")

        _topic_a = "новости"
        _text_a = f"{_addressee}, привет! Расскажи последние {_topic_a} таверны."
        # C-fix4 (№145): анти-подделка — «ответил» значит ПОСЛЕ речи игрока;
        # ambient-пре-реплика адресата не считается (№145: ✅ из executed
        # ДО player_action — ложноположительный).
        _mark_d1 = len(SPY["events"])
        _resp = h.player_action(_text_a)
        print(f"[D1-DM] dm_response={str(getattr(_resp, 'dm_response', ''))[:120]!r}")

        _ps_events = [e for e in SPY["events"] if getattr(e, "type", "") == EventType.PLAYER_SPOKE.value]
        d1a = bool(_ps_events)
        if d1a:
            _e = _ps_events[-1]
            _at = (_e.payload or {}).get("action_type", "dialogue")
            _want_r = action_perception_radius(_at)
            d1b = float(_e.radius) == float(_want_r)
            print(f"[D1] PLAYER_SPOKE на шине — ✅ (action_type={_at}, "
                  f"radius={_e.radius} == SSOT {_want_r})" if d1b else
                  f"[D1] radius={_e.radius} != SSOT({_at})={_want_r} — ❌")
        else:
            d1b = False
            print("[D1] PLAYER_SPOKE на шине — ❌ (dm_result невалиден? смотри DIAG)")
        ok = ok and d1a and d1b

        _block_a = _stm_block(h, _addressee)
        d1c = _topic_a in _block_a
        print(f"[D1] pair-STM адресата несёт речь игрока — "
              f"{'✅' if d1c else '❌'} (блок {len(_block_a)} симв., "
              f"тема '{_topic_a}' {'есть' if d1c else 'НЕТ'})")
        ok = ok and d1c

        # Ответ NPC: тики копят canonical-задачи → execute_pending (API раунда,
        # прецедент SUPERBOX-016/GORAN-G5) → async-воркер → шина.
        _sched = h.game_loop._get_task_scheduler()
        _addr_reply = []
        for _round in range(8):
            h.advance_ticks(1)
            time.sleep(2.4)  # SpeechScheduler pacing (2с/пара) + R4A-воркер
            _sc = h.get_scene_fresh() or {}
            _sched.execute_pending(_sc, CAMPAIGN)
            time.sleep(0.6)
            # C-fix4 (№145): «ответил» = NPC_SPOKE адресата ПОСЛЕ речи игрока
            # И адресованный игроку (target_id=="player") — ambient-реплика
            # в чужую сторону не считается ответом (№144: resolver вёл
            # merchant→blacksmith — ближайший; игрок в 1.2 м — шанс честный).
            _addr_reply = [
                e for e in SPY["events"][_mark_d1:]
                if getattr(e, "type", "") == EventType.NPC_SPOKE.value
                and getattr(e, "source", "") == _addressee
                and (getattr(e, "payload", {}) or {}).get("target_id") == "player"
            ]
            if _addr_reply:
                break
        _addr_any = [
            (getattr(e, "source", ""),
             (getattr(e, "payload", {}) or {}).get("target_id"))
            for e in SPY["events"][_mark_d1:]
            if getattr(e, "type", "") == EventType.NPC_SPOKE.value
        ]
        print(f"[D1] адресат ответил игроку (NPC_SPOKE→player, после речи) — "
              f"{'✅' if _addr_reply else '❌'}; реплики после речи (src→tgt): {_addr_any}")
        ok = ok and bool(_addr_reply)

        _c = h.counters
        d1d = (_c.ticks > 0) and (_c.npc_moved > 0 or _c.traversals_created > 0)
        print(f"[D1] мир живёт — {'✅' if d1d else '❌'} "
              f"(ticks={_c.ticks}, moved={_c.npc_moved}, traversals={_c.traversals_created})")
        ok = ok and d1d

        # (C-fix3: старый D2-блок удалён — дублировал player_action; единая
        #  последовательность ниже, после [D2-ISO])

        # C-fix2 (№143), три части:
        # (1) ИЗОЛЯЦИЯ очереди ДО player_action (прецедент SPY.clear между
        #     плечами GORAN): 20-deep ambient-задник D1 при dequeue ~1/вызов
        #     не даёт задаче жертвы дойти до гейта (№143: 8 раундов — мимо).
        #     Инфра-очередь, не NPC-состояния — п.14 INTEGRITY не затронут.
        # (2) СМЕРТЬ ДО FLUSH: задача жертвы создаётся тиком player-turn в
        #     pending_tasks; перенос в DialogueQueue делает только
        #     execute_pending — авторим смерть ДО него, гейт бьёт на dequeue,
        #     до пула/LLM (mid-generation interrupt by construction).   
        # (3) СВИДЕТЕЛЬ БЕЗ ТИКОВ: каждый тик плодит новый ambient-задник.
        try:
            _sched._dialogue_queue._heap.clear()
            print("[D2-ISO] DialogueQueue очищен между группами (изоляция)")
        except Exception as _iso_err:
            print(f"[D2-ISO] очередь не очищена: {_iso_err}")

        _topic_v = "золото"
        _text_v = f"{_victim}, ты слышал про {_topic_v}?"
        h.player_action(_text_v)
        _block_v_pre = _stm_block(h, _victim)
        print(f"[D2-SETUP] жертве адресована речь; STM-блок жертвы "
              f"{len(_block_v_pre)} симв. (тема {'есть' if _topic_v in _block_v_pre else 'НЕТ'})")

        # C-fix3 (№144): задача жертвы рождается тиком (Фаза 5→6) ПОКА ОНА
        # ЖИВА — «без тиков» лишил D2 входа (queue_owners=[] всегда). Тики
        # создают задачу → очередь изолируется до задачи жертвы → смерть →
        # dequeue → гейт. Инфра-очередь, NPC-состояния не тронуты (п.14).
        _vic_in_queue = False
        for _ in range(6):
            h.advance_ticks(1)
            time.sleep(0.8)
            if _victim in _queue_owners(_sched):
                _vic_in_queue = True
                break
        print(f"[D2-SETUP] задача жертвы в DialogueQueue — "
              f"{'✅' if _vic_in_queue else '❌ (зонд: DecisionHub не выбрал разговор)'}")
        ok = ok and _vic_in_queue

        # Хирургическая изоляция: в очереди остаётся ТОЛЬКО задача жертвы —
        # ambient-задник не конкурирует за dequeue (прецедент: очистка выше).
        try:
            import heapq as _hq
            _keep = [
                _it for _it in list(_sched._dialogue_queue._heap)
                if ((_it.payload or {}).get("speaker_id")
                    or ((_it.payload or {}).get("task_dict", {}) or {}).get("owner_id")) == _victim
            ]
            _sched._dialogue_queue._heap = _keep
            _hq.heapify(_sched._dialogue_queue._heap)
            print(f"[D2-ISO] очередь изолирована: {len(_keep)} задач(и) жертвы")
        except Exception as _iso2_err:
            print(f"[D2-ISO] изоляция не удалась: {_iso2_err}")

        # C-fix4 (№146): dequeue_next держит NPC-cooldown по game_time_seconds,
        # а D2-цикл тики не двигает (изоляция очереди) → задача жертвы не
        # доставалась никогда (№145: queue_owners=[жертва], 0 executed, гейт
        # не достигнут). Снятие cooldown-записи — инфра-очередь, тот же класс
        # что heap-изоляция; NPC-состояния/события не тронуты (п.14). admit()
        # PACING — wall-clock, проходится ретраями цикла.
        try:
            _sched._dialogue_queue._recent_npc_speak.pop(_victim, None)
            print("[D2-ISO] cooldown жертвы снят (dequeue разблокирован)")
        except Exception as _cd_err:
            print(f"[D2-ISO] cooldown-снятие не удалось: {_cd_err}")

        _death_ok = _author_death(h, _victim)
        _gate_sees = _sched._owner_is_dead(CAMPAIGN, _victim)
        print(f"[D2] смерть авторинга={_death_ok}, liveness-гейт видит DEAD={_gate_sees}")

        # C-fix6 (№157): engine-кэш перезагружается тиком из персистенса —
        # мутация _author_death эфемерна (№149/№157: SOCIAL_EMA и задачи
        # жертвы продолжаются после авторинга; провайдер на worker-времени
        # уже видел ALIVE). DI-шов гейта — провайдер: фиксируем его ответ
        # (прецедент freeze β-харнесса S225) — гейт читает DEAD
        # детерминированно на каждом хопе. Production-смерть (VitalState →
        # персистенс → reload) доставляет гейту тот же контракт; предмет
        # доказательства D2 — сам гейт, а не путь смерти.
        _real_provider = _sched._npc_states_provider

        def _dead_victim_provider(cid):
            _states = _real_provider(cid) or []
            for _n in _states:
                if isinstance(_n, dict) and (_n.get("npc_id") or _n.get("id")) == _victim:
                    _bs = _n.get("body_state")
                    if isinstance(_bs, dict):
                        _bs["life_status"] = "DEAD"
            return _states

        _sched._npc_states_provider = _dead_victim_provider
        print(f"[D2] провайдер гейта зафиксирован: {_victim}=DEAD (DI-шов)")
        _mark = len(SPY["events"])

        # C-fix7 (№163/№164, якорь вербатим с диска): детерминированный D2 —
        # ПРЯМОЙ вызов production-API execute_pending (прецедент GORAN-G5/
        # SUPERBOX-016: «вызов API = режим контура, не инъекция»). Вскрытие
        # №163 живого цикла: (а) admit() стоит ДО liveness-гейта — DEDUP (TTL 4с)
        # молча CANCEL'ит задачу жертвы мимо гейта (след: бесследное
        # исчезновение из heap без маркера и без исполнения); (б) PACING-
        # ретраи при ≤1 dequeue/тик делают задачу недосягаемой за окно зонда;
        # (в) «посмертная» реплика №163 — in-flight straggler пула: гейт
        # прошёл ДО смерти честно (владелец жил), LLM завершилась после
        # (класс DEBT-ABORT-404, S220; чистое окно ниже её исключает).
        # Прямой вызов: сон 4.5с гасит DEDUP-TTL и PACING-latency; +70с к
        # game_time (копия сцены) форсирует minute-reset и cooldown; пустой
        # heap → единственный dequeue = задача жертвы → B5-гейт (провайдер
        # зафиксирован: DEAD) → EXPIRED + маркер за один вызов.
        print(f"[D2-DIAG] sched-инстанс единый: "
              f"{_sched is h.game_loop._get_task_scheduler()}")
        time.sleep(4.5)
        _task_v = None
        for _it in list(_sched._dialogue_queue._heap):
            _td = (_it.payload or {}).get("task_dict") or {}
            if (_td.get("owner_id") or (_it.payload or {}).get("speaker_id")) == _victim:
                _task_v = _td
                break
        if _task_v is None:
            _task_v = _task_dict_fixture(_victim)
            print("[D2-DIAG] задача жертвы из heap не извлечена — fixture-fallback")
        _sched._dialogue_queue._heap.clear()
        _sched._dialogue_queue._recent_npc_speak.pop(_victim, None)
        _sc_d2 = dict(h.get_scene_fresh() or {})
        _sc_d2["pending_tasks"] = [_task_v]
        _sc_d2["campaign_id"] = CAMPAIGN
        _sc_d2["game_time_seconds"] = float(_sc_d2.get("game_time_seconds", 0.0)) + 70.0
        _sched.execute_pending(_sc_d2, CAMPAIGN)
        time.sleep(0.5)
        _gate_hit = any("liveness-gate" in m and _victim in m for m in _cap.records)
        if not _gate_hit:
            print(f"[D2-DIAG] маркер не пойман; queue_owners="
                  f"{sorted(_queue_owners(_sched))}; последние записи: "
                  f"{[m for m in _cap.records[-5:]]}")
        print(f"[D2] задача жертвы → EXPIRED (гейт, mid-generation interrupt) — "
              f"{'✅' if _gate_hit else '❌'}")
        ok = ok and _gate_hit and _death_ok

        # Окно ПОСЛЕ гейта: settle 3с (in-flight straggler пула завершается —
        # его гейт-проверка прошла ДО смерти честно; класс DEBT-ABORT-404,
        # зарегистрирован S220), затем 2 тика: pipeline исключил жертву
        # (count=6, №162) → новых задач нет → окно чисто by construction.
        time.sleep(3.0)
        _mark_post = len(SPY["events"])
        for _ in range(2):
            h.advance_ticks(1)
            time.sleep(0.8)
        _post = [e for e in SPY["events"][_mark_post:]
                 if getattr(e, "type", "") == EventType.NPC_SPOKE.value
                 and getattr(e, "source", "") == _victim]
        d2b = not _post
        print(f"[D2] посмертных реплик жертвы ПОСЛЕ гейта (чистое окно) — "
              f"{'0 ✅' if d2b else str(len(_post)) + ' ❌'}")
        ok = ok and d2b

        _sc = h.get_scene_fresh() or {}
        _sched.drain_commitment_outbox(_sc)
        _hist = str(_sc.get("commitment_history", {}))
        # ADR-O-365 (D-8): ambient-задачи — non-ownership слой, зеркала в
        # commitment_history нет by design; канонический свидетель EXPIRED —
        # INFO-маркер гейта + отсутствие посмертной реплики.
        print(f"[D2-DIAG] EXPIRED-свидетель: маркер гейта "
              f"{'✅' if _gate_hit else '❌'}; commitment_history для ambient "
              f"{'запись есть' if 'EXPIRED' in _hist and _victim in _hist else 'отсутствует (ожидаемо, D-8)'}")

        # ── D3: разговор выживает через STM (пп. 12-13) ─────────────
        _block_v_post = _stm_block(h, _victim)
        d3a = _topic_v in _block_v_post
        print(f"[D3] pair-STM жертвы пережила смерть (тема '{_topic_v}') — "
              f"{'✅' if d3a else '❌'}")
        d3b = _topic_a in _stm_block(h, _addressee)
        print(f"[D3] адресат помнит тему разговора ('{_topic_a}') — "
              f"{'✅' if d3b else '❌'}")
        ok = ok and d3a and d3b

    print("=" * 64)
    if ok:
        print("VERDICT: GREEN — позвоночник живого разговора доказан (D1/D2/D3)")
    else:
        print("VERDICT: RED — см. блок выше (DIAG-зонды укажут звено)")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())