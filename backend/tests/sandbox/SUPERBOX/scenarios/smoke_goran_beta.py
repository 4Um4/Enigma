"""
path: backend/tests/sandbox/SUPERBOX/scenarios/smoke_goran_beta.py
Назначение: SMOKE-GORAN (β) — Measurement Harness (перезапись, S216).
    Измерение способности ENIGMA превращать состояние мира в историю:
    THEFT → OBSERVE → BELIEF → WARN → PLAYER BELIEF → ACCUSE.
    Стимул — фиксация ВХОДА по прецеденту S214 (β-гибрид): авторинг воли
    (psyche["state"]="deceptive"), прямой production-compute с фиксированным
    OpportunityContext (M1/M2), инъекция steal-intent в production Фазу 6
    (C0: ОДИНАКОВЫЙ стимул в обоих плечах). Плечи отличаются ТОЛЬКО позицией
    Goran (замороженная геометрия, эшелоны 4/5 по S214-G9).
    НИКАКОГО monkey-patching решателя: DecisionHub/OpportunityEngine не патчуются.
    Живой пайплайн не передаёт opportunity_ctx (DEBT-OPP-PRODUCER) — потому
    стимул фиксируется на входе решателя, а не «выращивается» в тиках.
Зависимости: app.services.events.event_bus, game_loop_builder, phases.post_decision
Основные сущности: run_smoke_beta, run_scenario, analyze_results

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/smoke_goran_beta.py
"""
import sys
import types
import tempfile
import time
import logging
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

# S216 (прогоны 2-3): при редиректе в файл print (stdout) блочно-буферизуется,
# logging (stderr) — нет: порядок строк в логе НЕ хронологичен (доказано:
# goran WARN 1.99 в файле ДО маркера [β-T0:ctrl] — хронологически невозможно).
# Линейная буферизация делает порядок событий в лог-файле честным.
sys.stdout.reconfigure(line_buffering=True)

from app.core.config import settings
settings.environment = "development"

from app.domain.communication import CommunicationIntent, ExposureLevel
from app.domain.epistemology import Predicate
from app.domain.identity_events import EffectiveDrives
from app.models.npc_state import NPCStateAdapter
from app.models.player_action import ActionType, PlayerAction
from app.services.economy.opportunity_engine import (
    OPPORTUNITY_THRESHOLD,
    OpportunityContext,
    OpportunityEngine,
)
from app.services.events.event_bus import get_event_bus, reset_event_bus
from app.services.events.event_types import EventType
from app.services.game_loop_builder import build_game_loop
from app.services.npc.decision_hub import DecisionHub, EventContext
from app.services.npc.npc_loader import load_profile_from_legacy_json
from app.services.phases.post_decision import run_phase_6_post_decision
from app.services.spatial.spatial_query_service import SpatialQueryService

CAMPAIGN = "Open_road"
THIEF, GORAN = "thief_shadow", "merchant_goran"

# ── Замороженная геометрия (Real Data First: campaign_state.json, S216-раунд 5) ──
# Радиусы: наблюдение THEFT = 10.0 (_OBSERVATION_SIGHT_RADIUS, ADR-O-360),
# слух = 10.0 (HEARING_RADIUS). Игрок (4,2): 11.7 от вора — НЕ свидетель
# (вера только через testimony Goran'а — единственный канал, иначе Control
# не дискриминирует: игрок-свидетель даёт belief в обоих плечах, S214-G6
# conf=1.00 source=self); 7.4 от Goran — СЛЫШИТ WARN. Вторичные свидетели
# (borko 1.1 м, orm/lusya/tornin ~8 м от вора в конфиге) отодвинуты:
# single-variable Control — плечи отличаются только позицией Goran.
POS_THIEF = (11.5, 11.0)
POS_PLAYER = (4.0, 2.0)
POS_GORAN_EXP = (10.1, 6.1)    # 5.1 от вора → свидетель (S214-G4: conf≈0.9)
POS_GORAN_CTRL = (30.0, 31.0)  # 27.7 от вора → не свидетель (S214-G9)
POS_AWAY = (30.5, 30.5)        # подавление вторичных свидетелей/ораторов

# S214-G1: ИДЕАЛЬНЫЙ момент (фиксация входа). Математика: 0.35 + 0.001 + 0.20
# + 0.1125 = 0.6635 ≥ 0.65 — allies решают (без них 0.551 < порога).
_OPP = OpportunityContext(
    player_attention=0.0, distance=0.1, weapon_access=True, allies=3
)

# β-доставка (прогон 1): цепочка замкнулась ПОЗДНЕ фиксированного окна —
# player belief достиг 1.00 в пост-отчётных straggler-воркерах пула
# (BELIEF_REVISE 0.50→1.00 от клеймов Горана). Цикл «тик → execute_pending
# → settle» с поллингом веры игрока измеряет delivery latency честно; кап
# симметричен обоим плечам (Control выгорает кап = proof-of-absence).
_MAX_DELIVERY_TICKS = 20
_DELIVERY_TIMEOUT_SEC = 60.0   # §15.2: sandbox-исключение (wall-clock)
_DELIVERY_SETTLE_SEC = 1.0     # окно async-воркеров пула
_ACCUSE_CONFIDENCE = 0.5       # порог гейта §18 (compiler:21)

SPY = {"events": []}


def _spy(event):
    SPY["events"].append(event)


def _tick(world) -> dict:
    return world.game_loop.idle_tick(CAMPAIGN)


def _store(world):
    return getattr(world.game_loop._tick_orch, "_epistemic_store", None)


def _engine_states(world):
    _eng = world.game_loop._get_life_engine()
    return _eng.get_npc_states(CAMPAIGN)


def _states_map(world) -> dict:
    _st = _engine_states(world)
    if isinstance(_st, list):
        return {n.get("npc_id", n.get("id")): n for n in _st}
    return _st or {}


def _get_spy_events(et: str):
    return [e for e in SPY["events"] if e.type == et]


def _sched(world):
    return getattr(world.game_loop, "_task_scheduler", None) \
        or getattr(world.game_loop, "task_scheduler", None)


def _build_frozen_sq(world, goran_pos) -> SpatialQueryService:
    """Fake SpatialQueryService поверх снапшота сцены с нашей раскладкой.
    Стены не передаются (S214-G9 прецедент): гейт — только дистанция.
    Живые позиции NPC НЕ мутируем: все spatial-потребители получают эту
    проекцию через патч провайдеров (эшелоны 4/5)."""
    _scene = world.game_loop.scene_manager.get_scene_state(CAMPAIGN, "tavern") or {}
    _np = dict(_scene.get("npc_positions") or {})

    def _set(npc_id, xy):
        if npc_id in _np:
            _e = dict(_np[npc_id])
            _e["local_position"] = {"x": xy[0], "y": xy[1]}
            _np[npc_id] = _e

    # Вор обязан быть в позициях: sq.distance(entity, actor) кидает исключение
    # для отсутствующего actor → _get_witnesses молча теряет ВСЕХ свидетелей.
    if THIEF not in _np:
        _np[THIEF] = {"npc_id": THIEF, "name": "Тень",
                      "local_position": {"x": POS_THIEF[0], "y": POS_THIEF[1]}}
    _set(THIEF, POS_THIEF)
    _set("player", POS_PLAYER)
    _set(GORAN, goran_pos)
    for _other in _np:
        if _other not in (THIEF, "player", GORAN):
            _set(_other, POS_AWAY)
    return SpatialQueryService(npc_positions=_np)


def _freeze_spatial_consumers(world, sq) -> int:
    """S214-G9 эшелон-4: провайдеры — bound methods, захваченные при
    конструировании подписчиков; замена атрибута game_loop их НЕ перехватывает.
    Патчим _get_spatial_query на инстансах через реестр шины (_handlers).
    Генерически: ВСЕ spatial-потребители (Observation/Claim/Social/Reaction)
    видят одну замороженную геометрию — детерминизм зонда."""
    _bus = get_event_bus()
    _patched = 0
    for _hlist in getattr(_bus, "_handlers", {}).values():
        for _h in _hlist:
            _inst = getattr(_h, "__self__", None)
            if _inst is not None and hasattr(_inst, "_get_spatial_query"):
                _inst._get_spatial_query = lambda: sq
                _patched += 1
    # Эшелон-5: провайдер game_loop (для подписчиков, создаваемых позже) +
    # shared_context (немедленный эффект для текущего тика).
    world.game_loop._get_spatial_query_for_subscriber = lambda: sq
    _shared = getattr(world.game_loop._tick_orch, "_shared_context", None)
    if _shared is not None:
        _shared.spatial_query = sq
    return _patched


def _author_thief_will(world) -> bool:
    """S212/S214: will_state — ВХОДНОЕ состояние агента (авторинг начальных
    условий, не runtime-мутация NPCState — guard не участвует). Контракт
    адаптера: psyche["state"] (npc_state:1117); psyche бывает СТРОКОЙ
    (S55-археология) — нормализуем. Мутация вложенного dict живого
    engine-state персистит (shallow-copy вложение не разрывает)."""
    _thief = _states_map(world).get(THIEF)
    if not _thief:
        return False
    _psyche = _thief.get("psyche")
    if not isinstance(_psyche, dict):
        _psyche = {}
    _psyche["state"] = "deceptive"
    _thief["psyche"] = _psyche
    return True


def _g1_decision_check(world) -> dict:
    """M1/M2: живая production decision function с фиксированным входом
    (S214-G1). scores_trace различает оставшиеся гейты: {"veto": 0.0} —
    сознание; steal ≈ −9 — сон-штраф пайплайна; steal нет в trace — гейт
    availability."""
    _opp = OpportunityEngine().calculate(ctx=_OPP, will_state="deceptive")
    _thief = _states_map(world).get(THIEF) or {"npc_id": THIEF}
    _profile = load_profile_from_legacy_json(dict(_thief))
    _state = NPCStateAdapter.from_legacy(dict(_thief))
    _wt = EventContext(
        event_type=EventType.WORLD_TICK, actor_id="world", success=True,
        intensity=0.2, distance=10.0, witness_count=1, location="tavern",
    )
    _ed = None
    if hasattr(EffectiveDrives, "from_dict"):
        _ed = EffectiveDrives.from_dict(dict(_profile.drives_base))
    else:
        _kw = {k: v for k, v in dict(_profile.drives_base).items()
               if k in getattr(EffectiveDrives, "__dataclass_fields__", {})}
        _ed = EffectiveDrives(**_kw) if _kw else None
    _res = DecisionHub(seed=1).compute(
        state=_state, personality=_profile, event=_wt,
        effective_drives=_ed, opportunity_ctx=_OPP,
    )
    _iv = getattr(getattr(_res, "intent", None), "value", None)
    _trace = getattr(_res, "scores_trace", {}) or {}
    print(f"[β-G1] opp_score={_opp.score} "
          f"unlocked={sorted(_opp.unlocked_intents)}")
    print(f"[β-G1] intent={_iv} score={float(getattr(_res, 'score', 0.0)):.3f}")
    print(f"[β-G1] trace={_trace}")
    return {
        "opp_score": _opp.score,
        "opp_unlocked": "steal" in _opp.unlocked_intents,
        "intent": _iv,
        "score": float(getattr(_res, "score", 0.0)),
        "trace": _trace,
    }


def _inject_steal_intent(world) -> None:
    """S214-G1.5: CommunicationIntent → production Фаза 6 → windup (2 тика).
    C0: ОДИНАКОВЫЙ intent-объект в обоих плечах (стимул не зависит от руки)."""
    _scene = world.game_loop.scene_manager.get_scene_state(CAMPAIGN, "tavern") or {}
    _intent = CommunicationIntent(
        speaker=THIEF, audience="gold_chest", topic="theft",
        intent_type="steal", emotional_state="neutral",
        exposure_level=ExposureLevel.from_semantic("whisper"),
        target_id="gold_chest",
    )
    run_phase_6_post_decision(types.SimpleNamespace(
        communication_intents=[_intent],
        campaign_id=CAMPAIGN,
        tick_number=int(_scene.get("tick", 0)) + 1,
        scene_state=_scene,
        npc_services=None,
        all_npcs_raw=list((_scene.get("npc_positions") or {}).keys()),
    ), world.game_loop._tick_orch)


def run_scenario(goran_in_los: bool, arm: str) -> dict:
    """Прогон одного плеча. Жизненный цикл — S214-каскад."""
    SPY["events"].clear()

    # Изоляция миров (S214-G9): свой saves_dir на плечо (иначе SQLite
    # UNIQUE-violation/database-locked) + сброс шины-синглтона
    # (reset_event_bus — санкционированный тест-API; S214-хак __wrapped__
    # был no-op: get_event_bus — plain global, не lru_cache).
    settings.saves_dir = tempfile.mkdtemp(prefix=f"smoke_goran_beta_{arm}_")
    reset_event_bus()
    world = types.SimpleNamespace(game_loop=build_game_loop(Path(settings.data_dir)))

    # S214-G0: stub-роутер — canonical-реплики без LLM (NPC_SPOKE несёт
    # intent_type/proposition от S197/S203-механики, не от LLM).
    _s = _sched(world)
    if _s:
        for _ex in getattr(_s, "_executors", {}).values():
            if hasattr(_ex, "_router"):
                _ex._router = None
        _amb = getattr(_s, "_ambient_executor", None)
        if _amb is not None and hasattr(_amb, "_router"):
            _amb._router = None

    _bus = get_event_bus()
    for _et in EventType:
        _bus.subscribe(_et, _spy)

    _tick(world)  # warmup: инициализация сцены (ensure_scene_initialized)

    # Заморозка геометрии ДО кражи; патч провайдеров (эшелоны 4/5).
    _goran_pos = POS_GORAN_EXP if goran_in_los else POS_GORAN_CTRL
    _sq = _build_frozen_sq(world, _goran_pos)
    _patched = _freeze_spatial_consumers(world, _sq)
    _will_ok = _author_thief_will(world)
    print(f"[β-T0:{arm}] patched_providers={_patched} will_authored={_will_ok} "
          f"dist(goran,thief)={_sq.distance(GORAN, THIEF):.1f} "
          f"dist(player,thief)={_sq.distance('player', THIEF):.1f} "
          f"dist(player,goran)={_sq.distance('player', GORAN):.1f}")

    # M1/M2: production decision function (фиксированный вход).
    g1 = _g1_decision_check(world)

    # C0: стимул — одинаков в обоих плечах.
    _inject_steal_intent(world)

    for _ in range(3):
        _tick(world)    # windup(2) → THEFT → наблюдение → belief Goran

    # Доставка с поллингом: каждый тик сабмитит свежие pending_tasks
    # (закрывает и H-D1 — settle каждый цикл, и H-D2 — сабмит поздних
    # задач). Выход — по вере игрока ≥ порога гейта (игрок действует,
    # когда услышал), иначе кап.
    _t0 = time.monotonic()
    _delivery_ticks = 0
    _player_conf = 0.0
    while (_delivery_ticks < _MAX_DELIVERY_TICKS
           and time.monotonic() - _t0 < _DELIVERY_TIMEOUT_SEC):
        _tick(world)
        _delivery_ticks += 1
        _scene_p = world.game_loop.scene_manager.get_scene_state(
            CAMPAIGN, "tavern") or {}
        if _s is not None:
            _s.execute_pending(_scene_p, CAMPAIGN)
        time.sleep(_DELIVERY_SETTLE_SEC)
        _player_conf = _conf_about(_store(world), "player", THIEF)
        # β-зонд (ЧАСТЬ VIII.5): различает H-E1 (латентность: records=0, а
        # строки BELIEF_REVISE(player) в логе ещё не появлялись — видно по
        # LineNumber) и H-E2 (чужой store: BELIEF_REVISE(player) в логе ЕСТЬ
        # внутри окна, а records опрашиваемого стора = 0).
        _n_recs = len(_records_about(_store(world), "player", THIEF))
        _goran_acts_n = sum(
            1 for e in _get_spy_events("npc_spoke")
            if e.source == GORAN
            and (e.payload or {}).get("intent_type") in ("warn", "report"))
        print(f"[β-POLL:{arm}] tick={_delivery_ticks} "
              f"wall={time.monotonic() - _t0:.1f}s conf={_player_conf:.2f} "
              f"records={_n_recs} goran_warn_spokes={_goran_acts_n} "
              f"pending={len(_scene_p.get('pending_tasks') or [])}")
        if _player_conf >= _ACCUSE_CONFIDENCE:
            break
    _delivery_sec = time.monotonic() - _t0
    print(f"[β-DELIVERY:{arm}] ticks={_delivery_ticks} "
          f"wall={_delivery_sec:.1f}s player_conf={_player_conf:.2f}")

    # ACCUSE (§18-гейт): фиксируем и исход, и причину отказа.
    _accuse_passed, _accuse_reason = False, "compiler/resolver missing"
    _mvp = getattr(world.game_loop, "mvp_controller", None)
    _compiler = getattr(_mvp, "action_compiler", None)
    if _compiler is not None:
        _compiler._campaign_id = CAMPAIGN
        if getattr(_compiler, "_epistemic_resolver", None) is not None:
            _r = _compiler.process_action(PlayerAction(
                action_id=f"beta-accuse-{arm}", tick=99, actor_id="player",
                action_type=ActionType.ACCUSE, target_id=THIEF,
                description="обвиняю Тень в краже",
            ))
            _accuse_passed = _r is None
            _accuse_reason = "passed" if _r is None else str(_r)
        else:
            _accuse_reason = "epistemic_resolver not wired"
    print(f"[β-ACCUSE:{arm}] passed={_accuse_passed} reason={_accuse_reason}")

    _tick(world)  # мир отвечает (G8-стиль)

    return {
        "arm": arm,
        "events": list(SPY["events"]),
        "accuse_passed": _accuse_passed,
        "accuse_reason": _accuse_reason,
        "store": _store(world),
        "g1": g1,
        "delivery_ticks": _delivery_ticks,
        "delivery_sec": _delivery_sec,
        "player_conf_final": _player_conf,
    }


def _conf_about(store, agent: str, subject: str) -> float:
    """Максимальный confidence агента в proposition(subject, STOLE, *).
    S214-G4/G6 прецедент: канонический API стора — get_all_for_agent."""
    if not store:
        return 0.0
    _best = 0.0
    for _b in store.get_all_for_agent(agent):
        if (_b.proposition.subject_id == subject
                and _b.proposition.predicate == Predicate.STOLE):
            _best = max(_best, _b.confidence)
    return _best


def _records_about(store, agent: str, subject: str) -> list:
    if not store:
        return []
    return [b for b in store.get_all_for_agent(agent)
            if b.proposition.subject_id == subject]


def analyze_results(ctrl_res: dict, exp_res: dict) -> None:
    _ev = exp_res["events"]
    _thefts = [e for e in _ev if e.type == EventType.THEFT.value]
    _spokes = [e for e in _ev if e.type == EventType.NPC_SPOKE.value]
    g1 = exp_res["g1"]

    # M1: opportunity (production OpportunityEngine, фиксированный вход)
    opp_rate = 1.0 if (g1["opp_score"] >= OPPORTUNITY_THRESHOLD
                       and g1["opp_unlocked"]) else 0.0
    # M2: steal intent (production DecisionHub.compute)
    steal_rate = 1.0 if g1["intent"] == "steal" else 0.0
    # M3: theft conversion (production Фаза 6→7 в живых тиках)
    theft_conv = 1.0 if _thefts else 0.0
    # M4: witness (observation-канал: у Goran есть запись о воре)
    goran_conf = _conf_about(exp_res["store"], GORAN, THIEF)
    witness_rate = 1.0 if _records_about(exp_res["store"], GORAN, THIEF) else 0.0
    # M5: belief conversion
    belief_conv = 1.0 if goran_conf >= 0.5 else 0.0
    # M6: response (Goran действовал по натуре: warn|report, S214-G5)
    goran_acts = [e for e in _spokes if e.source == GORAN
                  and (e.payload or {}).get("intent_type") in ("warn", "report")]
    response_rate = 1.0 if goran_acts else 0.0
    # M7: player belief (testimony — единственный канал: игрок вне наблюдения)
    player_conf = _conf_about(exp_res["store"], "player", THIEF)
    player_rate = 1.0 if player_conf >= 0.5 else 0.0
    # M8: accusation (эпистемический гейт §18)
    acc_rate = 1.0 if exp_res["accuse_passed"] else 0.0
    # M9: false accusation (вор виновен by design)
    false_acc = 0.0
    # M10: causal chain completion
    chain = all([theft_conv, witness_rate, belief_conv, response_rate,
                 player_rate, acc_rate])

    # Control (C0 + G9/G9b-ассерты S214)
    _ce = ctrl_res["events"]
    ctrl_thefts = [e for e in _ce if e.type == EventType.THEFT.value]
    ctrl_goran_conf = _conf_about(ctrl_res["store"], GORAN, THIEF)
    ctrl_player_conf = _conf_about(ctrl_res["store"], "player", THIEF)
    ctrl_spokes = [e for e in _ce if e.type == EventType.NPC_SPOKE.value]
    ctrl_goran_acts = [e for e in ctrl_spokes if e.source == GORAN
                       and (e.payload or {}).get("intent_type") in ("warn", "report")]
    ctrl_acc_rejected = (not ctrl_res["accuse_passed"]) and \
        ("epistemic gate" in str(ctrl_res["accuse_reason"]))

    print(f"G1: opp={g1['opp_score']} intent={g1['intent']} "
          f"score={g1['score']:.3f}")
    print(f"Delivery latency: exp {exp_res['delivery_ticks']} тиков / "
          f"{exp_res['delivery_sec']:.1f}s | ctrl {ctrl_res['delivery_ticks']} "
          f"тиков / {ctrl_res['delivery_sec']:.1f}s (кап = proof-of-absence)")
    print(f"Goran spoke intent_types: "
          f"{[(e.payload or {}).get('intent_type') for e in _spokes if e.source == GORAN]}")
    print("\n[EXPERIMENT: Goran IN LOS]")
    print(f"  1. Opportunity rate: {opp_rate:.2f} (score={g1['opp_score']})")
    print(f"  2. Steal intent rate: {steal_rate:.2f} (intent={g1['intent']})")
    print(f"  3. Theft conversion: {theft_conv:.2f} (thefts={len(_thefts)})")
    print(f"  4. Witness rate: {witness_rate:.2f} (observation-канал)")
    print(f"  5. Belief conversion: {belief_conv:.2f} (Goran conf={goran_conf:.2f})")
    print(f"  6. Response rate: {response_rate:.2f} "
          f"(goran warn/report={len(goran_acts)})")
    print(f"  7. Player belief rate: {player_rate:.2f} (conf={player_conf:.2f})")
    print(f"  8. Accusation rate: {acc_rate:.2f} "
          f"(reason={exp_res['accuse_reason']})")
    print(f"  9. False accusation rate: {false_acc:.2f}")
    print(f" 10. Causal chain completion: {'YES' if chain else 'NO'}")

    # Диагностика testimony-канала (M7 — впервые в полном живом контуре:
    # S214-G6 получил веру игрока наблюдением, не свидетельством).
    for _b in _records_about(exp_res["store"], "player", THIEF):
        print(f"    [β-M7-DIAG] player record: source={_b.source_id} "
              f"conf={_b.confidence:.2f} tick={_b.last_updated_tick}")

    print("\n[CONTROL: Goran OUT OF LOS]")
    print(f"  C0 thefts: {len(ctrl_thefts)} (стимул идентичен)")
    print(f"  Goran belief conf: {ctrl_goran_conf:.2f} (Expected: 0.00)")
    print(f"  Goran warn/report acts: {len(ctrl_goran_acts)} (Expected: 0)")
    print(f"  Player belief conf: {ctrl_player_conf:.2f} (Expected: 0.00)")
    print(f"  ACCUSE rejected by epistemic gate: {ctrl_acc_rejected} "
          f"(reason={ctrl_res['accuse_reason']})")

    print("\n" + "=" * 40)
    if (chain and len(ctrl_thefts) >= 1 and ctrl_goran_conf == 0.0
            and not ctrl_goran_acts and ctrl_acc_rejected):
        print(" VERDICT: GREEN (Causal chain emerges, Control holds)")
    else:
        print(" VERDICT: RED (Chain broken or Control failed)")
    print("=" * 40)


def run_smoke_beta():
    logging.basicConfig(level=logging.INFO)
    print("=" * 64)
    print(" SMOKE-GORAN (β): CONTROL (Goran вне LOS)")
    print("=" * 64)
    ctrl_res = run_scenario(goran_in_los=False, arm="ctrl")

    print("\n" + "=" * 64)
    print(" SMOKE-GORAN (β): EXPERIMENT (Goran в LOS)")
    print("=" * 64)
    exp_res = run_scenario(goran_in_los=True, arm="exp")

    print("\n" + "=" * 64)
    print(" SMOKE-GORAN (β) REPORT")
    print("=" * 64)
    analyze_results(ctrl_res, exp_res)


if __name__ == "__main__":
    run_smoke_beta()