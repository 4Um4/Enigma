# path: backend/tests/sandbox/SUPERBOX/scenarios/lc_gc01_world_speaks_test.py
# Назначение: LC-GC-01 «Мир молчит → мир говорит» (ADR-O-421 / LC-IMPL-1;
#   сценарий A по вердикту Мастера В7: need → activity → ACTIVITY_OUTCOME).
#   Драйвер терминала — timeout (60 тиков деятельности, :306 :49): честный
#   провальный исход при неудовлетворённой потребности (движенческий блокер
#   платформы — S330-досье d3_probe — не пропускает TAKE/эстественный
#   терминал; timeout-исход публикуется _publish_outcome безусловно :247).
#   G1 control_flag_off: флаг OFF — канал пуст ПРИ ЖИВОМ ГОВОРЯЩЕМ МИРЕ
#     (шина-шпион: activity_outcome публиковался); снимается fingerprint
#     авторитетного состояния для A/B.
#   G2 treatment_flag_on: флаг ON — канал несёт {cause,target,value} только
#     уже произошедшего; read-only A/B: fingerprint == Control при равных N;
#     утечка проекции в сцену отсутствует ('eat:ok'/'eat:fail' — формат,
#     изобретённый проекцией).
#   G3 negative_closed_needs: потребность закрыта (hunger инъекция 0.05
#     стабом продюсера — окно покороче 12 тиков) + контур жив (desires/
#     activity_state отсутствуют fail-loud, не вакуум).
# Зависимости: build_game_loop (eat-паттерн), fixture_loader (данные S252),
#   scene_init._update_player_position (production-писатель позиции аватара).
# Основные сущности: run_control, run_treatment, run_negative, main

import json
import os
import sys
import tempfile
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import settings
from tests.sandbox.fixture_loader import FIXTURE_DIR, has_fixture

if has_fixture():
    settings.data_dir = str(FIXTURE_DIR)
# Изоляция saves — per-мир в _new_world (eat-паттерн; урок H5 из ADR-O-378).

# Флаги контура деятельности — парой (eat-паттерн), читатели call-time.
# ON во ВСЕХ группах: негатив обязан доказывать «закрытые нужды → тишина»,
# не «мёртвый контур → тишина».
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"

from app.services.events.event_types import EventType
from app.services.game_loop_builder import build_game_loop

CAMPAIGN = "Open_road"
TORNIN = "tavern_keeper_tornin"
# Драйвер: onset ~15 + таймаут 60 тик + запас — окно с запасом 90 тиков
# (строгое > :306 — терминал не раньше 61-го тика деятельности).
MAX_TICKS = 90
PROJ_FLAG = "IDLE_EVENTS_PROJECTION_ENABLED"
_VALUE_OK = "eat:ok"
_VALUE_FAIL = "eat:fail"


@dataclass
class _GroupResult:
    name: str
    group_ok: bool
    detail: str


_CONTROL_FP: Dict[str, Any] = {}
_CONTROL_TICKS: int = -1


def _quiet() -> None:
    """LLM-free прогон (eat-прецедент): глушим шум воркеров/роутера/очередей."""
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
    logging.getLogger("app.services.npc.state_applicator").setLevel(logging.CRITICAL)


def _new_world(tag: str) -> types.SimpleNamespace:
    """Свежий мир (eat-паттерн): temp-saves, reset LifeEngine (урок eat C1
    — синглтон переживает пересборку), stub исполнителя диалогов."""
    import tempfile as _tf

    from app.services.npc.life_engine import reset_life_engine

    settings.saves_dir = _tf.mkdtemp(prefix=f"lc_gc01_{tag}_")
    reset_life_engine()
    world = types.SimpleNamespace(game_loop=build_game_loop(Path(settings.data_dir)))
    _sched = getattr(world.game_loop, "_task_scheduler", None)
    _executor = getattr(_sched, "_executor", None) or getattr(_sched, "executor", None)
    if _executor is not None and hasattr(_executor, "_router"):
        _executor._router = None  # eat E0: DialogueExecutor → stub-режим
    return world


def _states_map(world: Any) -> Dict[str, Any]:
    _st = world.game_loop._get_life_engine().get_npc_states(CAMPAIGN)
    if isinstance(_st, list):
        return {n.get("npc_id", n.get("id")): n for n in _st}
    return _st or {}


def _tornin_scene(world: Any) -> Dict[str, Any]:
    """Живая post-commit сцена (канон приёмки harness:237)."""
    _ts = getattr(
        getattr(world.game_loop, "scene_manager", None), "_tick_scenes", None
    ) or {}
    for _sc in _ts.values():
        if TORNIN in (_sc.get("npc_positions") or {}):
            return _sc
    if not _ts:
        raise AssertionError("lc_gc01: _tick_scenes пуст — сцена не коммитилась")
    return list(_ts.values())[0]


def _inject_player_near_tornin(world: Any) -> None:
    """Наблюдатель рядом с актором: production-писатель позиции аватара
    (scene_init._update_player_position); ε-офсет — против вырожденного LOS."""
    from app.services.game_loop.scene_init import _update_player_position

    _scene = _tornin_scene(world)
    _lp = ((_scene.get("npc_positions") or {}).get(TORNIN) or {}).get("local_position") or {}
    _update_player_position(
        _scene, (float(_lp.get("x", 0.0)) + 0.5, float(_lp.get("y", 0.0)) + 0.5)
    )


def _drive(
    world: Any,
    hunger_value: Optional[float],
    max_ticks: int,
    break_on_terminal: bool,
) -> Tuple[List[List[Dict[str, Any]]], int]:
    """Тиковый цикл eat-паттерна: прайм-тик (спавн) → инъекция входа
    (fail-loud read-back; продюсер life_engine:516-519 растит hunger —
    стартовый ≈0: потребность обязана создаваться драйвером, как eat E2)
    → player-follow → idle_tick → сбор канала 'events'."""
    world.game_loop.idle_tick(CAMPAIGN)
    if hunger_value is not None:
        # Инъекция ТОЛЬКО входа (eat E2-прецедент), fail-loud read-back:
        # кэш LifeEngine — авторитет; тихая потеря входа запрещена (урок
        # S330-класса слепых драйверов). Стартовый hunger Торнина ≈0.1 —
        # без инъекции цикл ломается на тике 1 (<0.2).
        _t = _states_map(world).get(TORNIN)
        if _t is None:
            raise AssertionError(
                f"lc_gc01: {TORNIN} отсутствует в кэше LifeEngine — "
                "инъекция входа невозможна (голод не будет создан)"
            )
        _t.setdefault("needs", {})["hunger"] = hunger_value
        _t.setdefault("body_state", {})["hunger"] = hunger_value * 100.0
        _back = float((_t.get("needs") or {}).get("hunger", -1.0))
        if abs(_back - hunger_value) > 1e-9:
            raise AssertionError(
                f"lc_gc01: инъекция hunger={hunger_value} не прочиталась "
                f"обратно ({_back}) — оторванный dict, драйвер слеп"
            )
    events_by_tick: List[List[Dict[str, Any]]] = []
    for _ in range(max_ticks):
        _inject_player_near_tornin(world)
        _r = world.game_loop.idle_tick(CAMPAIGN)
        events_by_tick.append([dict(e) for e in (_r.get("events") or [])])
        if break_on_terminal:
            _t = _states_map(world).get(TORNIN) or {}
            if float((_t.get("needs") or {}).get("hunger", 1.0)) < 0.2:
                break
    return events_by_tick, len(events_by_tick)


def _fingerprint(world: Any) -> Dict[str, Any]:
    """Авторитетное состояние мира для read-only A/B (физика/нужды/объекты;
    эпистемика не сравнивается — UUID-шум вне домена гейта; полнота
    добирается утечка-детектором + микро-deepcopy-замком коммита A)."""
    _scene = _tornin_scene(world)
    _t = _states_map(world).get(TORNIN) or {}
    return {
        "tick": _scene.get("tick"),
        "game_time_seconds": _scene.get("game_time_seconds"),
        "npc_positions": {
            _k: (_v or {}).get("local_position")
            for _k, _v in (_scene.get("npc_positions") or {}).items()
        },
        "world_objects": _scene.get("world_objects"),
        "hunger": float((_t.get("needs") or {}).get("hunger", 1.0)),
    }


def _scene_has_projection_artifacts(world: Any) -> bool:
    """Утечка проекции в мир: строки формата value — изобретены проекцией."""
    _s = json.dumps(_tornin_scene(world), default=str, ensure_ascii=False, sort_keys=True)
    return _VALUE_OK in _s or _VALUE_FAIL in _s


def _needs_something(world: Any) -> bool:
    """Проверка не-вакуумности: потребность жива (hunger ≥ 0.5) —
    контроль предусловия драйвера (не догоняем красный из мёртвого мира)."""
    _t = _states_map(world).get(TORNIN) or {}
    return float((_t.get("needs") or {}).get("hunger", 1.0)) >= 0.5


def run_control() -> _GroupResult:
    global _CONTROL_TICKS
    os.environ.pop(PROJ_FLAG, None)
    try:
        _quiet()
        world = _new_world("ctrl")
        _spy: List[Any] = []
        _bus = world.game_loop._tick_orch._get_event_bus()
        _bus.subscribe(EventType.ACTIVITY_OUTCOME, _spy.append)
        events_by_tick, n_ticks = _drive(world, 0.9, MAX_TICKS, True)
        _world_spoke = bool(_spy)
        _channel_silent = all(not _evs for _evs in events_by_tick)
        _control_fp = _fingerprint(world)
        _CONTROL_FP.clear()
        _CONTROL_FP.update(_control_fp)
        _CONTROL_TICKS = n_ticks
        _ok = _world_spoke and _channel_silent
        return _GroupResult(
            "control_flag_off",
            _ok,
            f"мир говорил (шина activity_outcome={len(_spy)}), "
            f"канал молчит={_channel_silent}, тиков={n_ticks}, "
            f"голод жив={_needs_something(world)}",
        )
    finally:
        os.environ.pop(PROJ_FLAG, None)


def run_treatment() -> _GroupResult:
    os.environ[PROJ_FLAG] = "1"
    try:
        _quiet()
        world = _new_world("trtm")
        events_by_tick, n_ticks = _drive(world, 0.9, MAX_TICKS, True)
        _flat = [e for _evs in events_by_tick for e in _evs]
        _shape_ok = all(set(e) == {"cause", "target", "value"} for e in _flat)
        _tornin_spoke = any(
            e.get("cause") == "activity_outcome"
            and e.get("target") == TORNIN
            and e.get("value") in (_VALUE_OK, _VALUE_FAIL)
            for e in _flat
        )
        _fp = _fingerprint(world)
        _readonly_ok = _fp == _CONTROL_FP
        _ticks_ok = n_ticks == _CONTROL_TICKS
        _leak_free = not _scene_has_projection_artifacts(world)
        _ok = (
            bool(_flat)
            and _shape_ok
            and _tornin_spoke
            and _readonly_ok
            and _ticks_ok
            and _leak_free
        )
        _fp_diff = sorted(
            k for k in set(_CONTROL_FP) | set(_fp)
            if _CONTROL_FP.get(k) != _fp.get(k)
        )
        return _GroupResult(
            "treatment_flag_on",
            _ok,
            f"канал говорил (событий={len(_flat)}, тиков={n_ticks}/{_CONTROL_TICKS}), "
            f"форма3={_shape_ok}, Торнин={_tornin_spoke}, read-only={_readonly_ok}"
            + (f" diff={_fp_diff}" if _fp_diff else "")
            + f", утечка={not _leak_free}",
        )
    finally:
        os.environ.pop(PROJ_FLAG, None)


def run_negative() -> _GroupResult:
    os.environ[PROJ_FLAG] = "1"
    try:
        _quiet()
        world = _new_world("neg")
        # Окно 4 тика: наблюдаемый рост hunger ≈0.08/тик (продюсер
        # life_engine:516-519) — 0.05+4×0.08≈0.37 держится ниже порога
        # desire-onset 0.5 всё окно; тишина = «закрытые нужды», не вакуум
        # (контур жив — доказано Control/Treatment этого же прогона).
        events_by_tick, n_ticks = _drive(world, 0.05, 4, False)
        _silent = all(not _evs for _evs in events_by_tick)
        # Не-вакуумный контроль: контур жив (флаги ON), потребность закрыта
        # → нет food-желания → нет eat-деятельности → нет исхода. Другие
        # деятельности (shelter) легальны и не проецируются в v1-словаре —
        # канал обязан молчать всё окно.
        _t2 = _states_map(world).get(TORNIN) or {}
        _hunger_still_closed = float(
            (_t2.get("needs") or {}).get("hunger", 1.0)
        ) < 0.5
        _ok = _silent and _hunger_still_closed
        return _GroupResult(
            "negative_closed_needs",
            _ok,
            f"потребность закрыта → тишина={_silent} "
            f"(hunger={(_t2.get('needs') or {}).get('hunger')}, "
            f"тиков={n_ticks})",
        )
    finally:
        os.environ.pop(PROJ_FLAG, None)


def main() -> int:
    print("=" * 64)
    print("SUPERBOX-LC-GC-01: «Мир молчит → мир говорит» (ADR-O-421, LC-IMPL-1)")
    print("=" * 64)
    results = [run_control(), run_treatment(), run_negative()]
    for r in results:
        print(f"[LC_GC01] {r.name}: {'OK' if r.group_ok else 'FAIL'} — {r.detail}")
    ok = all(r.group_ok for r in results)
    print(f"Итог: {'GREEN' if ok else 'RED'} = {sum(r.group_ok for r in results)}/{len(results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())