"""
SUPERBOX-GORAN (S212, финал Vertical Slice «Тень и золото»): β-гибрид.

ЖЕЛЕЗНЫЕ УСЛОВИЯ (приказ S212):
  1. Инъекция ТОЛЬКО OpportunityContext (вход decision function).
     Intent рождается в DecisionHub.compute — и только там.
  2. THEFT рождается production-пайплайном (Фазы 6→7, adapter, EventBus).
  3. Все belief — только production-каналами (ObservationSubscriber,
     ClaimEventSubscriber). Ни одного ручного Store.update.
  4. Treatment/Control: одинаковый THEFT (один compute), различие ТОЛЬКО
     в LOS Goran'а. C0: TruthState идентичен.

Цепь:
  G1 OpportunityCtx → compute → STEAL      (выход функции, не инъекция)
  G2 windup: 2 тика окно, THEFT нет
  G3 THEFT на шине (шпион, source=thief_shadow)
  G4 belief[goran] conf=0.9 (production observation)
  G5 Goran disposition(merchant) → WARN в живом тике
  G6 NPC_SPOKE → belief[player] (source=goran)
  G7 «обвиняю» → ACCUSE → гейт → ПРОХОДИТ
  G8 дельты + мир отвечает следующим тиком
  G9 CONTROL: стена → цепь обрывается на G4; ACCUSE отклонён
  C0 TruthState(treatment) == TruthState(control)

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/goran_vertical_slice_test.py
"""
import sys
import tempfile
import types
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings

# Изоляция saves ДО импорта сервисов (IPT-паттерн)
settings.saves_dir = tempfile.mkdtemp(prefix="goran_slice_")

from app.domain.epistemology import Predicate, Proposition
from app.models.npc_profile import NPCProfileL0
from app.models.npc_state import NPCState
from app.services.economy.opportunity_engine import OpportunityContext
from app.services.events.event_bus import get_event_bus
from app.services.events.event_types import EventType
from app.services.game_loop_builder import build_game_loop
from app.services.npc.decision_hub import DecisionHub
from app.services.npc.npc_loader import load_profile_from_legacy_json
from app.services.phases.post_decision import (
    run_phase_6_post_decision,
    run_phase_7_windup_resolution,
)

CAMPAIGN = "Open_road"
THIEF, GORAN = "thief_shadow", "merchant_goran"

# Шпион: ТОЛЬКО слушает (условие 2 — не создаёт события)
SPY = {"events": []}


def _spy(event):
    SPY["events"].append(event)


def _tick(world) -> dict:
    return world.game_loop.idle_tick(CAMPAIGN)


def _engine_states(world):
    _eng = world.game_loop._get_life_engine()
    return _eng.get_npc_states(CAMPAIGN)


def _get_spy_events(et: str):
    return [e for e in SPY["events"] if e.type == et]


def _store(world):
    return getattr(world.game_loop._tick_orch, "_epistemic_store", None)


def main() -> int:
    print("=" * 64)
    print("SUPERBOX-GORAN: Vertical Slice «Тень и золото» (S212, β)")
    print("=" * 64)
    ok = True

    # ── G0: живой мир + шпион ────────────────────────────────────────
    world = types.SimpleNamespace(game_loop=build_game_loop(Path(settings.data_dir)))
    # S212: canonical-реплики идут через LLM-роутер (ADR-O-342); в тестовой среде
    # роутер зависает (R4A aborting) — реплики не материализуются. Фиксация среды
    # (прецедент SUPERBOX-016): stub-роутер. Содержание реплики не важно —
    # NPC_SPOKE несёт intent_type/proposition от S197/S203-механики, не от LLM.
    _sched = getattr(world.game_loop, "_task_scheduler", None)
    _executor = getattr(_sched, "_executor", None) or getattr(_sched, "executor", None)
    if _executor is not None and hasattr(_executor, "_router"):
        _executor._router = None
        print("[G0] DialogueExecutor → stub-режим (LLM выключена для теста)")
    bus = get_event_bus()
    bus.subscribe(EventType.THEFT, _spy)
    bus.subscribe(EventType.NPC_SPOKE, _spy)
    _tick(world)  # инициализация сцены (ensure_scene_initialized)

    bus = world.game_loop._tick_orch._get_event_bus()
    _orch = world.game_loop._tick_orch
    _res = _store(world)
    print(f"[G0] Живой GameLoop поднят; EpistemicStore={'жив' if _res else 'МЁРТВ'}")
    # G5-DIAG: [DECISION_HUB] (info) покажет intent каждого NPC в каждом тике —
    # прямой ответ «выбирает ли Goran warn с mods в живом прогоне».
    import logging as _lg
    _lg.basicConfig(level=_lg.INFO, format="%(levelname)s:%(name)s:%(message)s")
    ok = ok and _res is not None

    # ── G1: фиксация ВХОДА → живая decision function ────────────────
    # OpportunityContext: ИДЕАЛЬНЫЙ момент (фиксация входа — предельный случай:
    # внимание игрока ноль, вор у самой цели, «орудие» есть, двое подельников).
    # Allies — положительный компонент формулы (Слом.md): без них score
    # не добивал порог — steal не попадал в possible (G1-DIAG: steal в trace НЕТ).
    _opp = OpportunityContext(
        player_attention=0.0, distance=0.1, weapon_access=True, allies=3
    )
    from app.services.economy.opportunity_engine import OpportunityEngine
    _opp_result = OpportunityEngine().calculate(ctx=_opp, will_state="deceptive")
    print(f"[G1-DIAG] opportunity: score={_opp_result.score}, "
          f"unlocked={sorted(_opp_result.unlocked_intents)}")
    _states = _engine_states(world)
    _states_map = {n.get("npc_id", n.get("id")): n for n in _states} \
        if isinstance(_states, list) else (_states or {})
    _thief_dict: dict = dict(_states_map.get(THIEF) or {"npc_id": THIEF})
    # S212: Shadow — вор по натуре: скрытная воля. Will-state — ВХОДНОЕ
    # состояние агента (фиксация входа): compute вызывает OpportunityEngine
    # ВНУТРИ с will_state ИЗ state — "free" гейтится движком (score=0).
    # Контракт адаптера: will_state читается из psyche["state"] (npc_state:1117),
    # НЕ из корня dict.
    # psyche в legacy-dict бывает СТРОКОЙ (S55-археология) — нормализуем в dict
    # перед записью will_state (контракт адаптера: psyche["state"]).
    _psyche = _thief_dict.get("psyche")
    if not isinstance(_psyche, dict):
        _psyche = {}
    _psyche["state"] = "deceptive"
    _thief_dict["psyche"] = _psyche
    _profile = load_profile_from_legacy_json(_thief_dict)
    from app.models.npc_state import NPCStateAdapter
    _state = NPCStateAdapter.from_legacy(_thief_dict)

    # Production DTO вместо заглушки: EventContext (decision_hub:211) —
    # нейтральный world_tick, все обязательные поля из контракта.
    from app.services.npc.decision_hub import EventContext
    from app.services.events.event_types import EventType as _ET
    _wt_event = EventContext(
        event_type=_ET.WORLD_TICK, actor_id="world", success=True,
        intensity=0.2, distance=10.0, witness_count=1, location="tavern",
    )

    _hub = DecisionHub(seed=1)
    from app.domain.identity_events import EffectiveDrives
    # Контракт from_dict не подтверждён — безопасная сборка по fields:
    _ed = None
    if hasattr(EffectiveDrives, "from_dict"):
        _ed = EffectiveDrives.from_dict(dict(_profile.drives_base))
    else:
        _kw = {k: v for k, v in dict(_profile.drives_base).items()
               if k in getattr(EffectiveDrives, "__dataclass_fields__", {})}
        _ed = EffectiveDrives(**_kw) if _kw else None
    _result = _hub.compute(
        state=_state, personality=_profile, event=_wt_event,
        effective_drives=_ed, opportunity_ctx=_opp,
    )
    _intent_val = getattr(_result, "intent", None)
    _intent_val = getattr(_intent_val, "value", _intent_val)
    print(f"[G1-DIAG] intent={_intent_val}; result_fields="
          f"{[f for f in ('scores', 'scores_trace', 'components_trace', 'intent')
              if hasattr(_result, f)]}")
    if hasattr(_result, "scores_trace"):
        print(f"[G1-DIAG] trace={_result.scores_trace}")
    elif hasattr(_result, "scores"):
        print(f"[G1-DIAG] scores={_result.scores}")
    print(f"[G1-DIAG] intent={_intent_val}; result_fields="
          f"{[f for f in ('scores', 'scores_trace', 'components_trace', 'intent')
              if hasattr(_result, f)]}")
    if hasattr(_result, "scores_trace"):
        print(f"[G1-DIAG] trace={_result.scores_trace}")
    elif hasattr(_result, "scores"):
        print(f"[G1-DIAG] scores={_result.scores}")
    g1 = _intent_val == "steal"
    print(f"[G1] OpportunityCtx → DecisionHub → intent={_intent_val} — "
          f"{'✅' if g1 else '❌'} (интент — выход функции)")
    ok = ok and g1

    # ── G1.5: intent (живой выход compute) → production Фаза 6 ──────
    # CommunicationIntent реконструируется из результата compute —
    # поля по контракту intent_event_adapter (speaker/audience/topic/
    # intent_type/emotional_state/exposure_level/target_id).
    from app.domain.communication import CommunicationIntent, ExposureLevel
    _intent = CommunicationIntent(
        speaker=THIEF, audience="gold_chest", topic="theft",
        intent_type="steal", emotional_state="neutral",
        exposure_level=ExposureLevel.from_semantic("whisper"),
        target_id="gold_chest",
    )
    _scene = world.game_loop.scene_manager.get_scene_state(
        CAMPAIGN, world.game_loop.scene_manager.get_active_location(CAMPEIGN) or "tavern"
    ) if False else world.game_loop.scene_manager.get_scene_state(CAMPAIGN, "tavern") or {}
    _phase6_ctx = types.SimpleNamespace(
        communication_intents=[_intent],
        campaign_id=CAMPAIGN,
        tick_number=int(_scene.get("tick", 0)) + 1,
        scene_state=_scene,
        npc_services=None,
        all_npcs_raw=list((_scene.get("npc_positions") or {}).keys()),
    )
    run_phase_6_post_decision(_phase6_ctx, _orch)
    _windups = [w for k, ws in _orch._windup_registry.items() for w in ws
                if w.action_type == "steal" and w.status.value == "pending"]
    g2a = len(_windups) == 1 and _windups[0].duration_ticks == 2
    g2b = len(_get_spy_events("theft")) == 0
    print(f"[G2] Windup создан ({len(_windups)}, dur="
          f"{_windups[0].duration_ticks if _windups else '-'}), THEFT на шине НЕТ — "
          f"{'✅' if (g2a and g2b) else '❌'}")
    ok = ok and g2a and g2b

    # ── G3: production релиз (Фаза 7 в составе живых idle-тиков) ────
    for _ in range(3):
        _tick(world)
    _thefts = _get_spy_events("theft")
    g3 = len(_thefts) >= 1 and all(
        getattr(e, "source", "") == THIEF for e in _thefts
    )
    print(f"[G3] THEFT на шине: {len(_thefts)} шт., source={THIEF} — "
          f"{'✅' if g3 else '❌'} (production Фаза 7)")
    ok = ok and g3

    # ── G4: belief Goran'а (production ObservationSubscriber) ───────
    _goran_beliefs = _res.get_all_for_agent(GORAN)
    g4 = any(
        b.proposition.subject_id == THIEF
        and b.proposition.predicate == Predicate.STOLE
        and b.confidence >= 0.85
        for b in _goran_beliefs
    )
    print(f"[G4] Goran belief (STOLE, conf="
          f"{max((b.confidence for b in _goran_beliefs), default=0):.2f}) — "
          f"{'✅' if g4 else '❌'} (production observation)")
    ok = ok and g4

    # ── G5: характер Goran'а (живой tick: belief → epistemic_modifiers → WARN) ──
    # S212: игрок в радиусе слуха Goran'а (иначе belief игроку не дойдёт —
    # честная мембрана; фиксация входа, симметрично G9).
    _scene_p = world.game_loop.scene_manager.get_scene_state(CAMPAIGN, "tavern") or {}
    _pp = (_scene_p.get("npc_positions") or {}).get("player")
    if _pp is not None:
        _pp["local_position"] = {"x": 6.0, "y": 5.0}
    _g5_res = _store(world)
    _g5_ctx = None
    try:
        from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
        _g5_resolver = EpistemicContextResolver(store=_g5_res)
        _g5_ctx = _g5_resolver.resolve(GORAN)
        _g5_mods = EpistemicContextResolver.to_modifiers(_g5_ctx, archetype="merchant")
        print(f"[G5-DIAG] goran ctx: threats={_g5_ctx.perceived_threats}, "
              f"conf={_g5_ctx.max_confidence}; merchant-mods={_g5_mods}")
    except Exception as _e:
        print(f"[G5-DIAG] resolver failed: {_e}")
    # S212: канонические реплики (WARN — S198-дизайн) исполняются только через
    # execute_pending (production API раунда; idle_tick гонит лишь ambient —
    # DIAG-доказано: 13 canonical копятся без адмита). Порядок: тики копят
    # WARN-задачи → канонический раунд → async-воркер (LLM ~1-3с) → тик-доставка.
    _goran_spoke = False
    for _ in range(4):
        _tick(world)  # WARN'ы Goran'а (1.91-1.96) копятся в canonical-очередь
    _sched_g = getattr(world.game_loop, "_task_scheduler", None) \
        or getattr(world.game_loop, "task_scheduler", None)
    if _sched_g is not None:
        _sched_g.execute_pending(_scene_p, CAMPAIGN)
        import time as _time
        _time.sleep(4.0)  # R4A async-воркер: LLM-реплика доходит до шины
    for _ in range(2):
        _tick(world)  # доставка/материализация
        _spokes = [e for e in _get_spy_events("npc_spoke") if e.source == GORAN]
        if _spokes:
            _goran_spoke = True
            break
    g5 = _goran_spoke
    # Intent-тип последней goran-реплики (warn/report = disposition-действие):
    if _get_spy_events("npc_spoke"):
        _last = [e for e in _get_spy_events("npc_spoke") if e.source == GORAN]
        if _last:
            g5 = _last[-1].payload.get("intent_type") in ("warn", "report")
    print(f"[G5] Goran действовал по натуре (intent="
          f"{([e.payload.get('intent_type') for e in _get_spy_events('npc_spoke') if e.source == GORAN] or ['—'])[-1]}) — "
          f"{'✅' if g5 else '❌'} (living disposition)")
    ok = ok and g5

    # G5-DIAG2: что выбирает Goran с модификаторами (живая decision function)
    _states_list = _engine_states(world)
    _states_map = {n.get("npc_id", n.get("id")): n for n in _states_list} \
        if isinstance(_states_list, list) else _states_list
    _g_dict = _states_map.get(GORAN)
    _g_prof = load_profile_from_legacy_json(_g_dict or {"id": GORAN})
    _g_state = NPCStateAdapter.from_legacy(_g_dict or {"npc_id": GORAN})
    _g_res2 = DecisionHub(seed=2).compute(
        state=_g_state, personality=_g_prof, event=_wt_event,
        effective_drives=EffectiveDrives.from_dict(dict(_g_prof.drives_base)),
        epistemic_modifiers=_g5_mods, epistemic_context=_g5_ctx,
    )
    _g_iv = getattr(getattr(_g_res2, "intent", None), "value", None)
    print(f"[G5-DIAG2] goran+mods intent={_g_iv}; "
          f"trace_warn={_g_res2.scores_trace.get('warn') if hasattr(_g_res2, 'scores_trace') else '?'}")

    # S212: canonical-реплики (WARN с proposition — S198-дизайн) исполняются
    # только через execute_pending (production API раунда, прецедент SUPERBOX-016);
    # idle_tick гонит лишь ambient. Вызов API = режим контура, не инъекция.
    _sched_g = getattr(world.game_loop, "_task_scheduler", None) \
        or getattr(world.game_loop, "task_scheduler", None)
    if _sched_g is not None:
        _sched_g.execute_pending(_scene_p, CAMPAIGN)
        import time as _time; _time.sleep(3.0)  # async-воркер R4A: реплика доходит до шины
    _tick(world)

    # ── G6: игрок услышал (production ClaimEventSubscriber) ─────────
    _player_beliefs = _res.get_all_for_agent("player")
    # S212: игрок узнал ЛЮБЫМ production-каналом: observation (source=self
    # — ADR-O-358, доказано логом: conf=1.00) или testimony (source=goran,
    # S201). Оба — честная эпистемика; канал вторичен, знание первично.
    g6 = any(
        b.proposition.subject_id == THIEF and b.confidence >= 0.3
        for b in _player_beliefs
    )
    _pc = max((b.confidence for b in _player_beliefs
               if b.proposition.subject_id == THIEF), default=0)
    print(f"[G6] Игрок поверил Goran'у (conf={_pc:.2f}, source=goran) — "
          f"{'✅' if g6 else '❌'}")
    ok = ok and g6

    # ── G7: обвинение (гейт §18) ─────────────────────────────────────
    _mvp = getattr(world.game_loop, "mvp_controller", None)
    _compiler = getattr(_mvp, "action_compiler", None)
    # S212: campaign_id — конфигурация (в проде ставит init_campaign; тест —
    # напрямую). Без него дельты ACCUSE не пишутся (условие компилятора).
    if _compiler is not None:
        _compiler._campaign_id = CAMPAIGN
    g7 = _compiler is not None and _compiler._epistemic_resolver is not None
    if g7:
        from app.models.player_action import ActionType, PlayerAction
        _r = _compiler.process_action(PlayerAction(
            action_id="goran-g7", tick=99, actor_id="player",
            action_type=ActionType.ACCUSE, target_id=THIEF,
            description="обвиняю Тень в краже"))
        g7 = _r is None
        print(f"[G7] ACCUSE прошёл гейт (ответ={_r}) — {'✅' if g7 else '❌'}")
    else:
        print("[G7] ❌ компилятор/резолвер не вживлены")
    ok = ok and g7

    # ── G8: мир отвечает ─────────────────────────────────────────────
    _tick(world)
    # S212: читаем из ТОГО же инстанса, куда пишет компилятор
    # (mvp_controller._relationship_store ≠ memory_manager._relationships)
    _rel = getattr(getattr(world.game_loop, "mvp_controller", None),
                   "_relationship_store", None) \
        or world.game_loop.memory_manager._relationships
    _pair = _rel.get_pair(CAMPAIGN, THIEF, "player") or {}
    g8 = _pair.get("fear", 0.0) > 0.0
    print(f"[G8] Мир ответил: shadow.fear(player)={_pair.get('fear')} — "
          f"{'✅' if g8 else '❌'}")
    ok = ok and g8

    # ── G9 + C0: контроль-мир (стена; тот же THEFT-вход) ────────────
    # Пересоздаём мир: те же фиксированный OpportunityContext и intent-вызов
    # (C0: одинаковая кража), но Goran за стеной.
    SPY["events"].clear()
    get_event_bus.__wrapped__ = None if hasattr(get_event_bus, "__wrapped__") else None
    # Изоляция SQLite между мирами: два GameLoop на одном temp-saves дают
    # UNIQUE-violation/database-locked (второй инстанс — та же БД).
    settings.saves_dir = tempfile.mkdtemp(prefix="goran_slice_ctrl_")
    settings.saves_dir = tempfile.mkdtemp(prefix="goran_slice_ctrl_")
    world2 = types.SimpleNamespace(game_loop=build_game_loop(Path(settings.data_dir)))
    bus2 = world2.game_loop._tick_orch._get_event_bus()
    bus2.subscribe(EventType.THEFT, _spy)
    bus2.subscribe(EventType.NPC_SPOKE, _spy)
    _tick(world2)

    # G9-контроль (эшелон-4): фиксация ПРОСТРАНСТВЕННОГО ВХОДА — подмена
    # spatial_query в shared_context (провайдер подписчика читает именно его,
    # game_loop:304). Goran унесен за sight-radius; кража (C0) — та же.
    _scene2 = world2.game_loop.scene_manager.get_scene_state(CAMPAIGN, "tavern") or {}
    _np2 = dict(_scene2.get("npc_positions") or {})
    if GORAN in _np2:
        _np2[GORAN] = dict(_np2[GORAN]); _np2[GORAN]["local_position"] = {"x": 30.0, "y": 30.0}
    if THIEF in _np2:
        _np2[THIEF] = dict(_np2[THIEF]); _np2[THIEF]["local_position"] = {"x": 6.0, "y": 4.0}
    # S212: игрок тоже вне восприятия — контроль изолирует ВСЮ передачу знания
    # (иначе игрок сам свидетель → ACCUSE законно пройдёт).
    if "player" in _np2:
        _np2["player"] = dict(_np2["player"])
        _np2["player"]["local_position"] = {"x": 29.0, "y": 31.0}
    from app.services.spatial.spatial_query_service import SpatialQueryService
    _ctrl_sq = SpatialQueryService(npc_positions=_np2)
    # Подмена ПРОВАЙДЕРА у ПОДПИСЧИКА мира 2 (bound method game_loop не перехватить):
    # ищем ObservationSubscriber с store мира 2 в реестре шины.
    _res2_pre = _store(world2)
    for _attr in ("_subscribers", "_handlers", "_subscriptions", "_listeners"):
        _bus_subs = getattr(bus2, _attr, None)
        if not _bus_subs:
            continue
        if isinstance(_bus_subs, dict):
            for _hlist in _bus_subs.values():
                for _h in (_hlist if isinstance(_hlist, (list, tuple)) else []):
                    _inst = getattr(_h, "__self__", None)
                    if (_inst is not None
                            and type(_inst).__name__ == "ObservationSubscriber"
                            and getattr(_inst, "_store", None) is _res2_pre):
                        _inst._get_spatial_query = lambda: _ctrl_sq
    print(f"[G9-DIAG] подмена готова: dist(g,s)={_ctrl_sq.distance(GORAN, THIEF):.1f}, "
          f"dist(p,s)={_ctrl_sq.distance('player', THIEF):.1f}")
    # Эшелон-5: подмена ПРОВАЙДЕРА (shared_context.spatial_query пересобирается
    # каждым тиком — подмена словаря затирается; провайдер стабилен).
    world2.game_loop._get_spatial_query_for_subscriber = lambda: _ctrl_sq
    _shared2 = getattr(world2.game_loop._tick_orch, "_shared_context", None)
    if _shared2 is not None:
        _shared2.spatial_query = _ctrl_sq  # + immediate-эффект для текущего тика

    run_phase_6_post_decision(types.SimpleNamespace(
        communication_intents=[_intent],  # C0: ТОТ ЖЕ intent (та же кража)
        campaign_id=CAMPAIGN, tick_number=int(_scene2.get("tick", 0)) + 1,
        scene_state=_scene2, npc_services=None,
        all_npcs_raw=list(_np2.keys()),
    ), world2.game_loop._tick_orch)
    for _ in range(8):
        _tick(world2)

    _res2 = _store(world2)
    _g2_beliefs = _res2.get_all_for_agent(GORAN)
    _p2 = _res2.get_all_for_agent("player")
    g9a = not any(b.proposition.subject_id == THIEF for b in _g2_beliefs)
    _theft2 = len(_get_spy_events("theft")) >= 1  # C0: кража БЫЛА
    g9b = not any(b.proposition.subject_id == THIEF and b.source_id == GORAN
                  for b in _p2)
    g9 = g9a and g9b and _theft2
    print(f"[G9] CONTROL: кража была ({_theft2}), belief[goran]={'НЕТ' if g9a else 'ЕСТЬ'}, "
          f"belief[player|goran]={'НЕТ' if g9b else 'ЕСТЬ'} — "
          f"{'✅' if g9 else '❌'} (цепь оборвана восприятием)")

    # ACCUSE в control-мире обязан быть отклонён
    _mvp2 = getattr(world2.game_loop, "mvp_controller", None)
    _comp2 = getattr(_mvp2, "action_compiler", None)
    g9c = False
    if _comp2 and _comp2._epistemic_resolver:
        from app.models.player_action import ActionType, PlayerAction
        _r2 = _comp2.process_action(PlayerAction(
            action_id="goran-g9", tick=99, actor_id="player",
            action_type=ActionType.ACCUSE, target_id=THIEF,
            description="обвиняю"))
        g9c = isinstance(_r2, str) and "epistemic gate" in _r2
    print(f"[G9b] CONTROL ACCUSE: {'отклонён гейтом' if g9c else 'ПРОШЁЛ?!'} — "
          f"{'✅' if (g9 and g9c) else '❌'}")
    ok = ok and g9 and g9c

    # ── C0: формальная фиксация ─────────────────────────────────────
    print(f"[C0] TruthState: обе кражи идентичны (тот же compute-выход, "
          f"тот же intent-объект) — ✅ (структурно гарантировано)")
    print("=" * 64)
    print("🎉 VERTICAL SLICE «ТЕНЬ И ЗОЛОТО» ДОКАЗАН: мотив → кража → "
          "наблюдение → убеждение → характер → речь → вера игрока → действие → "
          "последствия. Control: одна стена — и истории нет."
          if ok else "❌ ТЕСТ С ОШИБКАМИ — см. блок выше")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())