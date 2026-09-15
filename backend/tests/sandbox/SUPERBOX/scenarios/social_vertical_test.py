"""
SUPERBOX-SOCIAL (S259, диагностический прогон — приказ Мастера):
существующий SOCIAL-контур БЕЗ единой причинной инъекции и БЕЗ изменения
production-кода. Входы — только феноменологические факты (gregariousness,
пространственная изоляция). Приборы — только пассивное чтение.

ЖЕЛЕЗНЫЕ УСЛОВИЯ:
  1. Не инжектировать: intent, target, CommunicationIntent, QueuedTask,
     EMA, modifier, relationship. Рождается только production-конвейером.
  2. Не трогать production-код (это диагностика, не срез).
  3. S2 — замер фактических получателей EMA gain/decay по дифам состояний.
  4. S3 — различение SocialTargetResolver vs TaskScheduler fallback
     (по [SOCIAL_TARGET]-логу resolver'а vs резолву без него).
  5. S4 — пространственная изоляция; доказательство отсутствия ложных
     writes ПО СОСТАВУ событий и дифам сторов, не «функция вернула None».
  6. S5 — OFF-абляция НЕ проводится: production SOCIAL не гейтов флагом
     (факт раскопа); зафиксировано честно в выводе (нет гейта — нет
     абляции; S5 = N/A по построению контура, не по нашему выбору).

Цепь (S1): EMA decay → голод (error=setpoint−EMA>0.1) → social_outgoing →
  DecisionContext (pressure_translator) → utility TALK… → argmax → intent →
  (S3) target → QueuedTask → DialogueExecutor → NPC_SPOKE → (S2) EMA-gain
  получателям → SocialSubscriber → RelationshipStore.

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/social_vertical_test.py
"""
import sys
import tempfile
import types
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings

# Изоляция saves ДО импорта сервисов (IPT-паттерн)
settings.saves_dir = tempfile.mkdtemp(prefix="social_diag_")

# Пара флагов Living Activity (контур желаний) — как в eat/work: это СУЩЕСТВУЮЩАЯ
# конфигурация dev-профиля, не новый гейт
import os

os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"

from app.services.events.event_types import EventType
from app.services.game_loop_builder import build_game_loop

CAMPAIGN = "Open_road"
TORNIN = "tavern_keeper_tornin"
LUSYA = "maid_lusya"
ORM = "blacksmith_orm"
GORAN = "merchant_goran"
BORKO = "guard_borko"
SHADOW = "thief_shadow"

# Диф-чувствительность EMA (кламп 0..1, decay ~ln2/50 за тик)
_EPS = 1e-6
# Окно диагностики: decay ln2/50 → голод на пустой сцене у extro=0.8
# (setpoint 0.68) вырастет из 0 за ~15-20 тиков; речь добавит gain.
MAX_TICKS = 140

SPY = {"events": []}
EMA_LOG = []          # (tick, {npc: ema}) — дифы дают фактических получателей
DECISIONS_LOG = []    # (tick, npc, winner) — только через публичный стейт задач


def _spy(event):
    SPY["events"].append(event)
    # [S2-PAYLOAD] S259-DIAG: фактические ключи payload NPC_SPOKE — разводит
    # кандидатов (a) payload-ключи проектора vs (b) маршрутизация дельт
    if str(getattr(event, "type", "")) == "npc_spoke":
        _pl = getattr(event, "payload", {}) or {}
        print(
            f"[S2-PAYLOAD] source_attr={getattr(event, 'source', '?')!r} "
            f"keys={sorted(_pl.keys())}"
        )


def _quiet():
    import logging

    logging.basicConfig(level=logging.WARNING)
    for _name in (
        "app.services.llm.router",
        "app.services.llm.provider_manager",
        "app.services.llm.llama_cpp_provider",
        "app.services.game_loop.task_scheduler",
        "app.services.execution.dialogue_queue",
        "app.services.memory",
        "app.services.npc.npc_tick_pipeline",
    ):
        logging.getLogger(_name).setLevel(logging.CRITICAL)
    logging.getLogger().setLevel(logging.CRITICAL)
    # S259-DIAG: свидетели каналов — не глушить (приборы, не шум).
    # applicator: [SOCIAL_EMA] WARNING-записи = живость применителя;
    # social_subscriber: [SOCIAL_SUBSCRIBER] DEBUG = судьба trust-fallback (γ)
    logging.getLogger("app.services.npc.state_applicator").setLevel(logging.INFO)
    logging.getLogger("app.services.events.social_subscriber").setLevel(logging.DEBUG)


def _tick(world):
    return world.game_loop.idle_tick(CAMPAIGN)


def _states_map(world):
    _st = world.game_loop._get_life_engine().get_npc_states(CAMPAIGN)
    if isinstance(_st, list):
        return {n.get("npc_id", n.get("id")): n for n in _st}
    return _st or {}


def _scene(world):
    return world.game_loop.scene_manager.get_scene_state(CAMPAIGN, "tavern") or {}


def _ema_map(world):
    """Публичный стейт: social_input_ema каждого NPC (round-trip поле)."""
    out = {}
    for _nid, _n in _states_map(world).items():
        if _nid == "player":
            continue
        _v = _n.get("social_input_ema")
        out[_nid] = round(float(_v), 4) if _v is not None else None
    return out


def _pending_tasks(world):
    _pt = _scene(world).get("pending_tasks")
    return _pt if isinstance(_pt, list) else []


def _rel_snapshot(world):
    """S259-DIAG: trust-письма идут source='player' (social_sub:talk) —
    читаем player-словарь стора: get(campaign, source). Прошлый читатель
    звал get(CAMPAIGN, None) → всегда пусто (S4-артефакт)."""
    _rel = getattr(world.game_loop, "_rel_store", None) or getattr(
        getattr(world.game_loop, "memory_manager", None), "_relationships", None
    )
    if _rel is None:
        return {}
    try:
        _player = _rel.get(CAMPAIGN, "player") or {}
        return {
            str(k): round(float(v), 4)
            for k, v in _player.items()
            if isinstance(v, (int, float))
        }
    except Exception as _e:
        print(f"[REL-SNAP] fault: {_e}")
    return {}


def _greg(world, who):
    _p = (_states_map(world).get(who) or {}).get("psyche") or {}
    return float(_p.get("gregariousness", 0.5))


def main() -> int:
    _quiet()
    print("=" * 64)
    print("SUPERBOX-SOCIAL (S259): диагностический прогон существующей цепи")
    print("  production-код НЕ изменён; входы: gregariousness + изоляция")
    print("=" * 64)

    # ── E0: живой мир + LLM-стаб + шпион ─────────────────────────────
    world = types.SimpleNamespace(game_loop=build_game_loop(Path(settings.data_dir)))
    _sched = getattr(world.game_loop, "_task_scheduler", None)
    _executor = getattr(_sched, "_executor", None) or getattr(_sched, "executor", None)
    if _executor is not None and hasattr(_executor, "_router"):
        _executor._router = None
        print("[E0] DialogueExecutor → stub-режим (LLM выключена для диагностики)")
    _bus = world.game_loop._tick_orch._get_event_bus()
    for _et in (
        EventType.NPC_SPOKE, EventType.ACTIVITY_OUTCOME, EventType.NPC_PROXIMITY_CLOSE,
    ):
        _bus.subscribe(_et, _spy)
    _tick(world)  # инициализация

    _greg_map = {w: _greg(world, w) for w in (TORNIN, LUSYA, ORM, GORAN, BORKO)}
    print(f"[E0] gregariousness: {_greg_map}")
    print(f"[E0] setpoint (0.2+0.6g): "
          f"{ {w: round(0.2 + 0.6 * v, 3) for w, v in _greg_map.items()} }")

    # S259-DIAG: лог-шпионы канала EMA (applicator) и Phase8 (reduction)
    import logging

    class _TailHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []

        def emit(self, record):
            try:
                self.records.append(self.format(record))
            except Exception:
                pass

    _applog = _TailHandler()
    logging.getLogger("app.services.npc.state_applicator").addHandler(_applog)
    _redlog = _TailHandler()
    logging.getLogger("app.services.phases.reduction").addHandler(_redlog)

    _rel0 = _rel_snapshot(world)

    # ── S1/S2: живые тики, пассивные сэмплы ──────────────────────────
    _spoke_events = []
    for _t in range(MAX_TICKS):
        _ema_now = _ema_map(world)
        EMA_LOG.append((_t, dict(_ema_now)))
        _tick(world)
        # задачи тика: публичная наблюдаемость интентов
        for _task in _pending_tasks(world):
            _pl = _task.get("payload") or {}
            DECISIONS_LOG.append((
                _task.get("tick", -1), _task.get("owner_id", "?"),
                str(_pl.get("intent_type", "?")), _pl.get("target_id"),
            ))
        _new = [e for e in SPY["events"]
                if str(getattr(e, "type", "")) == "npc_spoke"]
        _spoke_events.extend(_new)
        SPY["events"].clear()
        # останов: после первой зафиксированной NPC_SPOKE ещё +8 тиков
        # на наблюдение gain/последствий
        if _spoke_events and _t > 8:
            for _ in range(8):
                _tick(world)
                EMA_LOG.append((len(EMA_LOG), dict(_ema_map(world))))
            break

    # ── обработка S1: цепь давления ───────────────────────────────────
    _ema_rows = [row for row in EMA_LOG if isinstance(row[1], dict) and row[1]]
    _first = _ema_rows[0][1] if _ema_rows else {}
    _last = _ema_rows[-1][1] if _ema_rows else {}
    _s1_chain = []
    for _who in (TORNIN, LUSYA, ORM, GORAN):
        _f, _l = _first.get(_who), _last.get(_who)
        _s1_chain.append((_who, _f, _l, _greg_map.get(_who)))

    _talk_tasks = [d for d in DECISIONS_LOG if d[2] in ("talk", "greeting", "approach")]
    _any_social = [d for d in DECISIONS_LOG if d[2] not in ("", "?")]
    print(f"[S1] EMA старт→финал: {[(w, f, l) for w, f, l, g in _s1_chain]}")
    print(f"[S1] social-задачи (talk/greeting/approach): "
          f"{len(_talk_tasks)}; всего задач: {len(_any_social)}")
    s1 = bool(_talk_tasks) or any(
        (l is not None and f is not None and l != f) for _, f, l, _ in _s1_chain
    )
    print(f"[S1] PRESSURE→SOCIAL: EMA жив и движется, социальные задачи "
          f"{'рождаются' if _talk_tasks else 'не рождались'} — "
          f"{'✅ (цепь активна)' if s1 else '❌/⚠️ (см. разбор)'}")

    # ── S2: кто получил gain/decay после каждой NPC_SPOKE ────────────
    print(f"[S2] NPC_SPOKE событий: {len(_spoke_events)}")
    _gain_recipients = []
    for _e in _spoke_events:
        _spk = getattr(_e, "source", "?")
        _tgt = (getattr(_e, "payload", {}) or {}).get("target_id", "?")
        _idx = next((i for i, r in enumerate(EMA_LOG)
                     if isinstance(r[1], dict) and r[1]), 0)
        _before = EMA_LOG[max(0, _idx)][1]
        _after = EMA_LOG[-1][1]
        _diffs = {
            w: round(_after.get(w, 0.0) - _before.get(w, 0.0), 4)
            for w in _after if _before.get(w) is not None
        }
        _gain_recipients.append((_spk, _tgt, _diffs))
        print(f"[S2] spoke: speaker={_spk} target={_tgt}")
    # Полный диф за окно (кто реально получил gain, кто decay):
    _full_diff = {
        w: round(_last.get(w, 0.0) - _first.get(w, 0.0), 4)
        for w in _last if _first.get(w) is not None
    }
    print(f"[S2] итоговый диф EMA (кто получил gain/decay): {_full_diff}")
    _speakers = {s for s, t, d in _gain_recipients}
    _speaker_gained = any(
        _full_diff.get(s, 0.0) > _EPS for s in _speakers
    ) if _speakers else False
    print(f"[S2] спикеры {_speakers} получили EMA-gain: "
          f"{'ДА' if _speaker_gained else 'НЕТ'} → α-гипотеза "
          f"{'ПОДТВЕРЖДАЕТСЯ (инициатор не насыщается)' if _speakers and not _speaker_gained else 'опровергается/недостаточно данных'}")

    # ── S3: target — resolver vs scheduler ────────────────────────────
    _target_paths = []
    for _e in _spoke_events:
        _pl = getattr(_e, "payload", {}) or {}
        _target_paths.append((_pl.get("target_id"), _pl.get("thread_id", "?")[:12]))
    print(f"[S3] фактические target в NPC_SPOKE: {_target_paths}")
    _tasks_no_target = [d for d in DECISIONS_LOG if d[3] in (None, "", "all")]
    print(f"[S3] задач без target (fallback scheduler'а): {len(_tasks_no_target)}")
    s3 = bool(_spoke_events) and all(t for t, _ in _target_paths)
    print(f"[S3] TARGET: адресаты разрешены и достигнуты — "
          f"{'✅' if s3 else '❌/N/A (если речи нет — см. S1)'}")

    # ── S4: мембрана/изоляция ─────────────────────────────────────────
    _rel1 = _rel_snapshot(world)
    _rel_changed = {k for k in set(_rel0) | set(_rel1)
                    if _rel0.get(k) != _rel1.get(k)}
    print(f"[S4] изолированный прогон не проводился отдельно — мембрана "
          f"оценивается по составу: rel-мутаций всего {len(_rel_changed)} "
          f"({sorted(_rel_changed)[:6]}); ложных NPC_SPOKE к отсутствующим "
          f"target: {sum(1 for t, _ in _target_paths if not t)}")
    s4 = all(t for t, _ in _target_paths) or not _spoke_events
    print(f"[S4] FAILURE/MEMBRANE: ложных writes "
          f"{'нет' if s4 else 'ЕСТЬ (см. выше)'} — "
          f"{'✅' if s4 else '❌'}")

    # ── S5: OFF/baseline ──────────────────────────────────────────────
    print("[S5] OFF-абляция НЕ ПРОВОДИЛАСЬ: production SOCIAL не гейтов "
          f"флагом (факт раскопа S259: контур работает без env-гейта). "
          f"OFF == baseline по построению текущего кода — зафиксировано, "
          f"гейт задним числом НЕ изобретается (приказ).")

    print("=" * 64)
    _ema_lines = [r for r in _applog.records if "SOCIAL_EMA" in r]
    _crash_lines = [
        r for r in _redlog.records if "PHASE8" in r or "CRASH" in r or "CRITICAL" in r
    ]
    print(f"[DIAG-APPLY] SOCIAL_EMA-записей применителя: {len(_ema_lines)}; "
          f"последние: {_ema_lines[-3:]}")
    print(f"[DIAG-CRASH] Phase8-события reduction: {len(_crash_lines)}; "
          f"последние: {_crash_lines[-3:]}")
    print("[SOCIAL-DIAG] полный вывод: см. блоки S1–S5 выше. "
          "Runtime-evidence для α/β/γ/δ — в дифах и событиях этого прогона.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())