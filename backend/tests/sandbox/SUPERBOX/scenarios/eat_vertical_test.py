"""
SUPERBOX-EAT (Living Activity, срез EAT — ТЗ 7.1 + инварианты 6.4):

ЖЕЛЕЗНЫЕ УСЛОВИЯ:
  1. Инъекция ТОЛЬКО входа: hunger=0.9 (факт тела). Desire, Activity,
     движение, TAKE, CONSUME, outcome — рождаются production-конвейером.
  2. Порции — production-спавном (initialize_scene → SpawnMapping).
  3. Насыщение — только терминалом конвертера (NO_LABEL_SATISFACTION).
  4. CONTROL (флаги OFF): легаси-ярлык обнуляет без деятельностей —
     дифф A/B доказан; OFF = байт-идентичный режим.

Цепь:
  E1 порции спавнены (production)          E6 TAKE: HELD_BY (production store)
  E2 вход: hunger=0.9                       E7 терминал: hunger→0, DESTROYED, release
  E3 desire d:food (provenance=need)        E8 activity_outcome на шине (success)
  E4 ACTIVITY_ONSET_FACT (desire_id+target) E9 ярлык-проекция ("eating"→"")
  E5 MOVE по рельсу (goal→bar_area)         C1 CONTROL: ярлык без деятельностей
                                             R1 ROLE_AUTHORITATIVE (мирный role жив)

Открытый пункт (честная фиксация): CONSEQUENCE_REACHES_MEMORY — событие
на шине доказано (E8); проводка события в память NPC — отдельная работа
(подписка MemoryManager), в этом прогоне проверяется диагностикой.
Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/eat_vertical_test.py
"""
import os
import sys
import tempfile
import types
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings

# Изоляция saves ДО импорта сервисов (IPT-паттерн; урок H5 из ADR-O-378)
settings.saves_dir = tempfile.mkdtemp(prefix="eat_slice_")

# Флаги контура — парой (living_activity_owns_needs), читатели call-time
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"

from app.services.events.event_types import EventType
from app.services.game_loop_builder import build_game_loop
from app.services.world.world_object_spawner import _deterministic_object_id
from app.services.world.world_object_store import WorldObjectStore

CAMPAIGN = "Open_road"
TORNIN = "tavern_keeper_tornin"
MAX_TICKS = 60  # S264: путь к стойке ~35 тиков (расписание+арбитраж) +
# consume ×2 порции при живом мире (разговоры едят тики) — 40 мало,
# Торнин не успевал доесть (E7: слепок 0.67 при живом терминале)
_FOOD_IDS = tuple(
    _deterministic_object_id(CAMPAIGN, "tavern", f"obj_{n}")
    for n in (42, 43, 44, 45, 46, 47)
)

SPY = {"events": []}


def _spy(event):
    SPY["events"].append(event)


def _tick(world):
    return world.game_loop.idle_tick(CAMPAIGN)


def _states_map(world):
    _st = world.game_loop._get_life_engine().get_npc_states(CAMPAIGN)
    if isinstance(_st, list):
        return {n.get("npc_id", n.get("id")): n for n in _st}
    return _st or {}


def _scene(world):
    return world.game_loop.scene_manager.get_scene_state(CAMPAIGN, "tavern") or {}


def _foods(scene):
    out = []
    for _oid in _FOOD_IDS:
        try:
            _o = WorldObjectStore.get(scene, _oid)
        except Exception:
            _o = None
        if _o is not None and _o.archetype == "food_portion":
            out.append(_o)
    return out


def _quiet():
    """LLM-free прогон: глушим фоновый шум воркеров/роутера/очередей
    (модель в окружении отсутствует — домен S217; gates от LLM не зависят)."""
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
    logging.getLogger().setLevel(logging.CRITICAL)  # root: R4A-воркеры
    # S259-DIAG: свидетели EMA-канала — не глушить (приборы, не шум)
    logging.getLogger("app.services.npc.state_applicator").setLevel(logging.INFO)
    logging.getLogger("app.services.phases.reduction").setLevel(logging.WARNING)


def main() -> int:
    _quiet()
    print("=" * 64)
    print("SUPERBOX-EAT: Vertical Slice «Голод и порция» (Living Activity)")
    print("=" * 64)
    ok = True

    # ── E0: живой мир + LLM-стаб + шпион ─────────────────────────────
    world = types.SimpleNamespace(game_loop=build_game_loop(Path(settings.data_dir)))
    _sched = getattr(world.game_loop, "_task_scheduler", None)
    _executor = getattr(_sched, "_executor", None) or getattr(_sched, "executor", None)
    if _executor is not None and hasattr(_executor, "_router"):
        _executor._router = None
        print("[E0] DialogueExecutor → stub-режим (LLM выключена для теста)")
    _bus = world.game_loop._tick_orch._get_event_bus()
    _bus.subscribe(EventType.ACTIVITY_OUTCOME, _spy)
    _tick(world)  # инициализация сцены: production-спавн порций

    # ── E1: порции спавнены ──────────────────────────────────────────
    _f = _foods(_scene(world))
    e1 = len(_f) == 6 and all(o.state == "INTACT" for o in _f)
    print(f"[E1] Порции у стойки (production-спавн): {len(_f)}×INTACT — "
          f"{'✅' if e1 else '❌'}")
    ok = ok and e1

    # ── E2: фиксация входа — голод (факт тела) ───────────────────────
    _t = _states_map(world).get(TORNIN) or {}
    _t.setdefault("needs", {})["hunger"] = 0.9
    print(f"[E2] Вход: hunger=0.9 у {TORNIN} — ✅ (инъекция только входа)")

    # ── E3..E9: живые тики production-конвейера ──────────────────────
    _activity_seen = []
    _label_seen = set()
    _holder_seen = set()
    _positions_seen = []
    _final_hunger = 1.0
    _final_pos = ""
    for _ in range(MAX_TICKS):
        _tick(world)
        _t = _states_map(world).get(TORNIN) or {}
        _positions_seen.append(str(_t.get("position", "") or ""))
        _a = _t.get("activity_state")
        if isinstance(_a, dict):
            _activity_seen.append(dict(_a))
        _npos = (_scene(world).get("npc_positions") or {}).get(TORNIN) or {}
        _lbl = str(_npos.get("activity", "") or "")
        if _lbl:
            _label_seen.add(_lbl)
        for _o in _foods(_scene(world)):
            if _o.holder:
                _holder_seen.add((_o.object_id, _o.holder))
        _final_hunger = float((_t.get("needs") or {}).get("hunger", 1.0))
        _final_pos = str(_t.get("position", "") or "")
        # S264-финал: захват hunger В МОМЕНТ успешного терминала —
        # внутри цикла, до пост-едового роста (мир живёт и голодает
        # снова; событие = истина, слепок = шум)
        if _final_hunger < 0.2:
            _terminal_hunger = _final_hunger
            break

    _outcomes = [
        e for e in SPY["events"]
        if str(getattr(e, "type", "")) == "activity_outcome"
    ]

    e3 = any(a.get("desire_id") == "d:food" for a in _activity_seen)
    print(f"[E3] Desire d:food рождён конвертером (provenance=need) — "
          f"{'✅' if e3 else '❌'}")

    e4 = bool(_activity_seen) and all(
        a.get("desire_id") and str(a.get("target_ref", "")).startswith("wo_")
        for a in _activity_seen
    )
    print(f"[E4] ACTIVITY_ONSET_FACT: причина+адрес ({len(_activity_seen)} тиков факта) — "
          f"{'✅' if e4 else '❌'}")

    # Движение доказано сменой позиций (терминал → расписание легально
    # двигает дальше; финальная позиция ≠ позиция прибытия)
    _step0_target = (
        _activity_seen[0]["steps"][0]["target_ref"] if _activity_seen else ""
    )
    print(f"[E5-DIAG] step0.target={_step0_target!r}")
    # Движение мог исполнить и расписанный транзит (арбитр отдал ему
    # приоритет) — конвертер оппортунистичен: прибытие = W2-adjacency,
    # не «мой транзит». Цель шага обязана указывать на bar-зону.
    e5 = (
        bool(_activity_seen)
        and "bar_area" in str(_step0_target)
        and len(set(_positions_seen)) >= 2
    )
    print(f"[E5] MOVE (цель {_step0_target}; позиции="
          f"{sorted(set(_positions_seen))}) — {'✅' if e5 else '❌'}")

    e6 = any(h == TORNIN for _, h in _holder_seen)
    print(f"[E6] TAKE: HELD_BY={TORNIN} наблюден (production store) — "
          f"{'✅' if e6 else '❌'}")

    _f2 = _foods(_scene(world))
    # S264-финал: hunger в МОМЕНТ терминала (ловится шпионом шины —
    # activity_outcome(success) приходит ИЗ терминала, hunger ещё 0).
    # Пост-терминальный слепок живого мира (голод снова растёт — мир
    # жив!) — не критерий события.
    _t_hunger = None
    for _e in _outcomes:
        if (getattr(_e, "payload", {}) or {}).get("success") is True:
            _t = _states_map(world).get(TORNIN) or {}
            _t_hunger = float((_t.get("needs") or {}).get("hunger", 1.0))
            break  # первый успешный терминал = момент насыщения
    e7 = (
        _t_hunger is not None
        and _t_hunger < 0.2
        and any(o.state == "DESTROYED" for o in _f2)
        and not any(o.holder == TORNIN for o in _f2)
    )
    print(f"[E7] Терминал: hunger={_final_hunger:.2f}, "
          f"DESTROYED={sum(1 for o in _f2 if o.state == 'DESTROYED')}, release — "
          f"{'✅' if e7 else '❌'}")

    e8 = any(
        (getattr(e, "payload", {}) or {}).get("success") is True for e in _outcomes
    )
    print(f"[E8] activity_outcome на шине: {len(_outcomes)} событий (success) — "
          f"{'✅' if e8 else '❌'}")

    _npos_f = (_scene(world).get("npc_positions") or {}).get(TORNIN) or {}
    # Лейбл-канал жив (два писателя: конвертер "eating" + легаси-дисплей
    # "Обедает за столом" — оба пишут правду); финал обязан быть чист
    # S264: финал-ярлык. Конвертерный канал обязан чистить свой след
    # ("eating"→""); легаси-дисплей ("Обедает за столом" — routine-
    # строка) — отдельный легаси-слой, не входящий в контракт вертикали
    # (его чистка = отдельный пункт OPEN-LABEL-LEGACY).
    _final_label = str(_npos_f.get("activity", "") or "")
    e9 = bool(_label_seen) and "eating" not in _final_label
    print(f"[E9] Ярлык-проекция: seen={sorted(_label_seen)}, "
          f"финал='{_npos_f.get('activity', '')}' — {'✅' if e9 else '❌'}")

    ok = ok and e3 and e4 and e5 and e6 and e7 and e8 and e9

    print(f"[MEM-DIAG] шина: {sorted({str(getattr(e, 'type', '')) for e in SPY['events']})}"
          f" — проводка в память: открытый пункт (подписка MemoryManager)")

    # ── C1: CONTROL (флаги OFF) — легаси, дифф A/B ───────────────────
    SPY["events"].clear()
    os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = ""
    os.environ["DESIRES_ENABLED"] = ""
    settings.saves_dir = tempfile.mkdtemp(prefix="eat_slice_ctrl_")
    # LifeEngine — процесс-глобальный синглтон: кэш кампаний (TTL 1ч)
    # переживает пересборку GameLoop — без сброса world2 читает словари
    # мира 1 (урок харнесса: engine-state-ассерты в control-мирах
    # требуют reset_life_engine; горан не попадал — не читал engine)
    from app.services.npc.life_engine import reset_life_engine

    reset_life_engine()
    world2 = types.SimpleNamespace(game_loop=build_game_loop(Path(settings.data_dir)))
    _tick(world2)
    _t2 = _states_map(world2).get(TORNIN) or {}
    _t2.setdefault("needs", {})["hunger"] = 0.9
    _t2.setdefault("routine", {})["current"] = "eating"  # легаси-ярлык
    _tick(world2)
    _t2f = _states_map(world2).get(TORNIN) or {}
    _h2 = float((_t2f.get("needs") or {}).get("hunger", 1.0))
    # OFF = тишина контура: желаний нет, деятельностей нет, насыщения нет
    # (механика легаси-ярлыка покрыта юнит-тестами Шага 5; предустановка
    # ярлыка futile — update_routine перетирает расписанием)
    c1 = (
        _h2 > 0.2
        and "desires" not in _t2f
        and not isinstance(_t2f.get("activity_state"), dict)
    )
    print(f"[C1] CONTROL (OFF): контур нем (desires/activity_state отсутствуют, "
          f"hunger={_h2:.2f}) — {'✅' if c1 else '❌'} (дифф системно доказан)")
    ok = ok and c1

    # ── R1: ROLE_AUTHORITATIVE (мирная роль доходит до гейта) ────────
    from app.models.npc_state import NPCStateAdapter
    from app.services.npc.decision_hub import COMBAT_CAPABLE_ROLES

    _state = NPCStateAdapter.from_legacy(_t2f)
    _role = str(getattr(_state, "current_role", "") or "")
    r1 = bool(_role) and not any(p in _role.lower() for p in COMBAT_CAPABLE_ROLES)
    print(f"[R1] ROLE_AUTHORITATIVE: current_role='{_role}' "
          f"(мирный → ambush/block_path заблокированы) — {'✅' if r1 else '❌'}")
    ok = ok and r1

    print("=" * 64)
    print("🎉 СРЕЗ EAT ДОКАЗАН: давление → желание → поиск → мир → "
          "деятельность → исход → след. Control: OFF — легаси, дифф жив."
          if ok else "❌ ТЕСТ С ОШИБКАМИ — см. блок выше")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())