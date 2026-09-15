"""
path: /project/backend/tests/sandbox/f3_combat_smoke.py
Назначение: IRON RIVER F3 — боевой детерминизм-смоук: одна атака игрока
    в изолированном прогоне → детерминированный hp/pain цели (P0-3:
    uuid4+hash() seed заменён KernelRNG-деривацией; same id → same seed).
    Прогон ДВАЖДЫ: равные F3SMOKE-строки = P0-3 закрыт.
Зависимости: app.services.game_loop_builder, app.domain.events.EventDTO
Запуск: cd backend; python tests/sandbox/f3_combat_smoke.py
"""
import sys, tempfile, types, os, json, shutil
from pathlib import Path

sys.path.insert(0, ".")
from app.core.config import settings

# LLM-free: глушим шум ДО сборки мира
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

# IRON RIVER D-3: полное temp-окружение (копия data/, чистый world_tick)
# disk-урок (WinError 112): копия без replay.db/logs + автоочистка
import atexit

_data_src = Path(settings.data_dir)
_data_tmp = Path(tempfile.mkdtemp(prefix="f3_data_"))
_ignore = shutil.ignore_patterns("replay.db", "*.jsonl", "logs")
shutil.copytree(_data_src, _data_tmp, dirs_exist_ok=True, ignore=_ignore)
atexit.register(lambda: shutil.rmtree(_data_tmp, ignore_errors=True))
_wt = _data_tmp / "sessions" / "Open_road" / "world_tick.json"
if _wt.exists():
    _wt.unlink()
settings.saves_dir = tempfile.mkdtemp(prefix="f3_saves_")

from app.services.game_loop_builder import build_game_loop

w = types.SimpleNamespace(game_loop=build_game_loop(_data_tmp))
gl = w.game_loop

# stub-режим исполнителя (LLM выключена для смоука)
_sched = getattr(gl, "_task_scheduler", None)
_exec = getattr(_sched, "_executor", None) or getattr(_sched, "executor", None)
if _exec is not None and hasattr(_exec, "_router"):
    _exec._router = None

gl.idle_tick("Open_road")  # прогрев сцены

from app.domain.events import EventDTO
from app.services.events.event_types import EventType

_bus = gl._tick_orch._get_event_bus()

# Атака игрока по Торнину — production-контракт S122-ветки орка:
# детерминированный id (F3-1), timestamp=1 (каузальная ось тика).
_evt = EventDTO(
    id="evt:1:player:tavern_keeper_tornin:attack",
    type=EventType.PLAYER_ATTACKED.value,
    source="player",
    timestamp=1,
    payload={
        "target_id": "tavern_keeper_tornin",
        "target_reference": "трактирщик",
        "intensity": 0.8,
        "actor_id": "player",
    },
    visibility="public",
    radius=15.0,
    persistence_level="working",
)
_bus.publish(_evt)
gl.idle_tick("Open_road")  # Фаза 8: CombatSubscriber → ImpactEngine

_st = gl._get_life_engine().get_npc_states("Open_road")
_torn = next(
    (n for n in _st if n.get("npc_id") == "tavern_keeper_tornin"), {}
)
_bs = _torn.get("body_state", {}) or {}
_res = {
    "hp": _bs.get("current_hp"),
    "pain": _bs.get("pain"),
    "shock": _bs.get("shock_impulse"),
}
print("F3SMOKE " + json.dumps(_res, sort_keys=True))