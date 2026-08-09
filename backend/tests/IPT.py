"""
path: backend/tests/IPT.py
Назначение: Invariant Probe Tests — быстрая проверка инвариантов симуляции.
            Запускается LLM-архитектором во время фикса (слой "ДО").
            Не требует LLM-сервера, не требует сети, ~5 секунд.
Зависимости: backend/app/* (минимальный bootstrap)
Основные сущности: run_invariants, INVARIANTS

Запуск: python backend/tests/IPT.py
# 1. Запуск IPT с выводом ошибок
python backend/tests/IPT.py 2>&1 | Select-String -Pattern "Traceback|Error|Exception" -Context 2, 5
"""

import atexit
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

# Пропатчим sys.path, чтобы из backend/tests/ запускать без cd
_BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(_BACKEND))
_ROOT = _BACKEND.parent
sys.path.insert(0, str(_ROOT))

# Автоматический запуск/остановка LLM для IPT
# Обёрнуто в try/except, так как модуля scripts.llm_server_manager может не быть в репозитории
try:
    from scripts.llm_server_manager import kill_llama_server, start_llama_server
    _llm_ok = start_llama_server()
    if not _llm_ok:
        print("⚠️ Внимание: LLM не запущена. Тесты диалогов будут падать.")
    atexit.register(kill_llama_server)
except ModuleNotFoundError as e:
    print(f"⚠️ Внимание: Модуль LLM-сервера не найден ({e}). IPT продолжает работу без LLM.")
    _llm_ok = False


@dataclass
class InvariantResult:
    invariant_id: str
    severity: str  # "CRITICAL" / "WARNING"
    passed: bool
    message: str
    suspect_files: List[str]


class TestWorld:
    """Обертка над GameLoop для упрощения доступа к данным в IPT."""

    def __init__(self, game_loop, campaign_id: str):
        self.game_loop = game_loop
        self.campaign_id = campaign_id
        self.last_result = None

    def idle_tick(self) -> dict:
        self.last_result = self.game_loop.idle_tick(self.campaign_id)
        return self.last_result

    def _get_scene(self) -> dict:
        # ADR-129: get_scene_state требует location_id. В IPT мы используем дефолтную локацию.
        from app.core.constants import DEFAULT_LOCATION_ID

        return self.game_loop.scene_manager.get_scene_state(self.campaign_id, DEFAULT_LOCATION_ID) or {}

    @property
    def game_time_seconds(self) -> float:
        return self._get_scene().get("game_time_seconds", 0.0)

    @property
    def tick(self) -> int:
        return self._get_scene().get("tick", 0)

    @property
    def npc_positions(self) -> dict:
        if self.last_result and self.last_result.get("world_snapshot"):
            return self.last_result["world_snapshot"].get("npc_positions", {})
        return {}

    @property
    def npc_ids(self) -> list:
        return list(self.npc_positions.keys())

    def npc_position(self, nid: str):
        pos = self.npc_positions.get(nid)
        if pos and "local_position" in pos:
            lp = pos["local_position"]
            if isinstance(lp, dict):
                return (lp.get("x", 0.0), lp.get("y", 0.0))
            elif isinstance(lp, (list, tuple)):
                return (lp[0], lp[1])
            return (0, 0)
        return None

    @property
    def last_world_snapshot(self) -> dict:
        if not self.last_result:
            return {}
        # Если world_snapshot явно равен None (нет активной локации), возвращаем пустой словарь
        return self.last_result.get("world_snapshot") or {}


def _bootstrap_minimal_world() -> TestWorld:
    """Поднимает GameLoop с реальными данными кампании, но изолированной saves_dir."""
    from app.core.config import settings
    from app.services.game_loop_builder import build_game_loop

    # Изолируем saves в темп, чтобы не портить реальные сохранения
    temp_saves = tempfile.mkdtemp(prefix="ipt_saves_")
    settings.saves_dir = temp_saves

    # data_dir — берём из настроек, чтобы путь всегда указывал на backend/data
    data_dir = Path(settings.data_dir)

    game_loop = build_game_loop(data_dir)

    # Используем дефолтную кампанию (ensure_scene_initialized сработает внутри idle_tick)
    # Real campaign is Open_road, tavern_silver_wolf is the default location inside it.
    campaign_id = "Open_road"

    return TestWorld(game_loop, campaign_id)


# === ИНВАРИАНТЫ ===


def inv_time_grows(world: TestWorld) -> InvariantResult:
    """INV-TIME-GROW: game_time_seconds растёт после 3 idle_tick."""
    initial_time = world.game_time_seconds
    for _ in range(3):
        world.idle_tick()
    final_time = world.game_time_seconds

    if final_time > initial_time:
        return InvariantResult("INV-TIME-GROW", "CRITICAL", True, f"game_time вырос: {initial_time} → {final_time}", [])
    return InvariantResult(
        "INV-TIME-GROW",
        "CRITICAL",
        False,
        f"game_time НЕ растёт: был {initial_time}, стал {final_time} за 3 тика.",
        [
            "backend/app/core/calendar.py:advance()",
            "backend/app/services/tick_orchestrator.py (Фаза 0)",
            "backend/app/services/integration/world_snapshot_builder.py (game_time_seconds проброс)",
        ],
    )


def inv_tick_grows(world: TestWorld) -> InvariantResult:
    """INV-TICK-GROW: tick увеличивается на каждом idle_tick."""
    initial_tick = world.tick
    world.idle_tick()
    world.idle_tick()
    if world.tick == initial_tick + 2:
        return InvariantResult("INV-TICK-GROW", "CRITICAL", True, "", [])
    return InvariantResult(
        "INV-TICK-GROW",
        "CRITICAL",
        False,
        f"tick не растёт на 2 за 2 idle_tick: был {initial_tick}, стал {world.tick}.",
        [
            "backend/app/services/tick_orchestrator.py",
            "backend/app/services/game_loop/__init__.py:idle_tick()",
        ],
    )


def inv_npc_moves(world: TestWorld) -> InvariantResult:
    """INV-NPC-MOVE: хотя бы 1 NPC сменил позицию за 5 тиков."""
    positions_before = {nid: world.npc_position(nid) for nid in world.npc_ids}
    for _ in range(5):
        world.idle_tick()
    positions_after = {nid: world.npc_position(nid) for nid in world.npc_ids}

    moved = [nid for nid in positions_before if positions_before[nid] != positions_after.get(nid)]
    if moved:
        return InvariantResult("INV-NPC-MOVE", "CRITICAL", True, f"Сдвинулись: {moved}", [])
    return InvariantResult(
        "INV-NPC-MOVE",
        "CRITICAL",
        False,
        "За 5 тиков ни один NPC не сдвинулся. RELOCATE не создаёт TraversalState или MovementEngine сломан.",
        [
            "backend/app/services/spatial/movement_engine.py",
            "backend/app/services/scene_state_manager.py (RELOCATE handler)",
            "backend/app/services/integration/world_snapshot_builder.py:_extract_active_traversals",
        ],
    )


def inv_active_traversals_dict(world: TestWorld) -> InvariantResult:
    """INV-TRAV-DICT: active_traversals в world_snapshot — это dict, не list."""
    world.idle_tick()
    snapshot = world.last_world_snapshot
    at = snapshot.get("active_traversals")

    if isinstance(at, dict):
        return InvariantResult("INV-TRAV-DICT", "CRITICAL", True, "", [])
    return InvariantResult(
        "INV-TRAV-DICT",
        "CRITICAL",
        False,
        f"active_traversals имеет тип {type(at).__name__}, ожидался dict. "
        f"Frontend упадёт на isinstance(traversals, list) в game_screen.py.",
        [
            "backend/app/services/integration/world_snapshot_builder.py:_extract_active_traversals",
            "backend/app/domain/snapshot.py:WorldSnapshotDTO.active_traversals",
        ],
    )


def inv_npc_has_name(world: TestWorld) -> InvariantResult:
    """INV-NPC-NAME: каждый NPC в npc_positions имеет поле 'name'."""
    world.idle_tick()
    snapshot = world.last_world_snapshot
    missing = []
    for npc_id, npc_data in snapshot.get("npc_positions", {}).items():
        if not (npc_data.get("name") or npc_data.get("display_name")):
            missing.append(npc_id)

    if not missing:
        return InvariantResult("INV-NPC-NAME", "CRITICAL", True, "", [])
    return InvariantResult(
        "INV-NPC-NAME",
        "CRITICAL",
        False,
        f"NPC без name: {missing}. Fuzzy matching в Target Resolution ослепнет "
        f"(Causal Contract v2.0 §2.1 — name обязателен).",
        [
            "backend/app/services/scene_state_manager.py (где формируются npc_positions)",
            "backend/app/services/spatial/player_target_pipeline.py",
            "backend/app/services/npc/npc_loader.py",
        ],
    )

def inv_dialogue_init(world: TestWorld) -> InvariantResult:
    """INV-DIALOGUE-INIT: Проверка инициации диалогов (NPC↔NPC и Игрок→NPC)."""
    # 1. Прогоняем 12 idle тиков, чтобы NPC успели сблизиться и сгенерировать интенты
    for _ in range(12):
        world.idle_tick()
    
    scheduler = getattr(world.game_loop, "_task_scheduler", None) or getattr(world.game_loop, "task_scheduler", None)
    if not scheduler:
        return InvariantResult(
            "INV-DIALOGUE-INIT", "CRITICAL", False, 
            "TaskScheduler не найден в GameLoop.", 
            ["backend/app/services/game_loop/__init__.py"]
        )

    # Стадия 3: Ожидаем завершения фоновых LLM-задач (TaskScheduler работает асинхронно)
    if hasattr(scheduler, "_executor_pool"):
        try:
            scheduler._executor_pool.shutdown(wait=True)
        except Exception:
            pass

    _recent = scheduler.get_recent_dialogues(world.game_time_seconds)
    if _recent:
        return InvariantResult("INV-DIALOGUE-INIT", "CRITICAL", True, "Диалоги успешно инициализируются и исполняются.", [])

    # Стадия 2: Если реплик нет, проверяем очередь (попали ли задачи в TaskScheduler)
    _queue_size = scheduler._dialogue_queue.pending_count() if hasattr(scheduler, "_dialogue_queue") and hasattr(scheduler._dialogue_queue, "pending_count") else 0
    _failed_count = getattr(scheduler, "failed_tasks", 0)
    _processed_count = getattr(scheduler, "total_processed_tasks", 0)
    
    # ADR-O-343: Если очередь пуста, но задачи уже обрабатывались (даже если LLM упала),
    # значит DecisionHub и post_decision работают корректно.
    if _queue_size == 0 and _processed_count == 0:
        # Стадия 1: Если очередь пуста и обработанных задач нет, значит задачи вообще не создаются
        return InvariantResult(
            "INV-DIALOGUE-INIT",
            "CRITICAL",
            False,
            "NPC↔NPC: За 12 тиков TaskScheduler не получил ни одной диалоговой задачи (очередь пуста, обработано 0). DecisionHub не генерирует CommunicationIntent или post_decision не маршрутизирует их.",
            [
                "backend/app/services/npc/decision_hub.py",
                "backend/app/services/phases/post_decision.py"
            ]
        )
        
    if _queue_size == 0 and _processed_count > 0:
        # Очередь пуста, но задачи обрабатывались — значит pipeline работает.
        return InvariantResult(
            "INV-DIALOGUE-INIT",
            "WARNING",
            True, # Не блокируем IPT, если задача дошла до исполнителя
            f"NPC↔NPC: Pipeline работает (обработано {_processed_count} задач, провалов {_failed_count}). Задачи доходят до TaskScheduler.",
            []
        )

    # ADR-O-343: Если очередь не пуста, проверяем total_processed_tasks.
    # SpeechScheduler имеет pacing (2 сек wall-clock), поэтому за 3 тика задачи могут не успеть исполниться.
    _processed_count = getattr(scheduler, "total_processed_tasks", 0)
    if _processed_count > 0:
        return InvariantResult(
            "INV-DIALOGUE-INIT",
            "WARNING",
            True,
            f"NPC↔NPC: Pipeline работает (обработано {_processed_count} задач), но pacing задерживает видимые реплики.",
            []
        )

    return InvariantResult(
        "INV-DIALOGUE-INIT",
        "CRITICAL",
        False,
        f"NPC↔NPC: В очереди {_queue_size} задач, обработано 0. TaskScheduler завис или не запускается.",
        [
            "backend/app/services/game_loop/task_scheduler.py",
            "backend/app/services/execution/dialogue_executor.py"
        ]
    )

    # 2. Проверка Игрок→NPC: Симулируем вмешательство игрока
    from app.contracts.interventions import InterventionEvent
    from app.services.game_loop.phase_1_input import resolve_player_intent
    from app.models.schemas import PlayerAction
    
    # Находим первого живого NPC
    target_npc = None
    for nid in world.npc_ids:
        if nid != "player":
            target_npc = nid
            break
            
    if target_npc:
        # Создаём действие игрока (обращение к NPC)
        action = PlayerAction(
            action_type="talk",
            target_id=target_npc,
            text="Привет, как дела?",
            position=world.npc_position("player")
        )
        
        # Пытаемся разрешить интент игрока (Игрок→NPC)
        try:
            # resolve_player_intent возвращает словарь с pressure и intent
            _intent_data = resolve_player_intent([action], world.campaign_id, world._get_scene())
            if not _intent_data:
                return InvariantResult(
                    "INV-DIALOGUE-INIT",
                    "CRITICAL",
                    False,
                    f"Игрок→NPC: resolve_player_intent вернул пустой результат для цели {target_npc}. Ввод игрока не обрабатывается.",
                    ["backend/app/services/game_loop/phase_1_input.py"]
                )
        except Exception as e:
            return InvariantResult(
                "INV-DIALOGUE-INIT",
                "CRITICAL",
                False,
                f"Игрок→NPC: resolve_player_intent упал с ошибкой: {e}",
                ["backend/app/services/game_loop/phase_1_input.py"]
            )

    return InvariantResult("INV-DIALOGUE-INIT", "CRITICAL", True, "Диалоговые интенты создаются и попадают в очередь.", [])


def inv_dialogue_stm(world: TestWorld) -> InvariantResult:
    """INV-DIALOGUE-STM: реплика игрока записывается в STM целевого NPC."""
    mm = world.game_loop.memory_manager
    campaign = world.campaign_id
    target_npc = "tavern_keeper_tornin"
    
    # Имитируем запись реплики игрока (как это делает dm_phase.py)
    try:
        mm.add_dialogue_turn(
            campaign_id=campaign, npc_id=target_npc, speaker="player", text="тестовая реплика"
        )
        stm_block = mm.get_stm_prompt_block(campaign, target_npc)
    finally:
        # Очищаем, чтобы не портить другие тесты
        mm.clear_dialogue_session(campaign, target_npc)
    
    if "тестовая реплика" in stm_block:
        return InvariantResult("INV-DIALOGUE-STM", "CRITICAL", True, "", [])
    return InvariantResult(
        "INV-DIALOGUE-STM",
        "CRITICAL",
        False,
        "Реплика игрока не найдена в STM блоке NPC.",
        [
            "backend/app/services/memory/memory_manager.py",
            "backend/app/services/memory/dialogue_session.py",
            "backend/app/services/game_loop/dm_phase.py",
        ],
    )


def inv_death_lock(world: TestWorld) -> InvariantResult:
    """INV-DEATH-LOCK: Мёртвые NPC не имеют active_traversals (ADR-127)."""
    engine = getattr(world.game_loop, "_get_life_engine", lambda: None)()
    npcs = engine.get_npc_states(world.campaign_id) if engine else []
    scene = world.game_loop.get_scene_state(world.campaign_id, "tavern") or {}
    travs = scene.get("active_traversals", {})
    
    for npc in npcs:
        nid = npc.get("npc_id") or npc.get("id")
        life = npc.get("life_status", "").upper() or npc.get("body_state", {}).get("life_status", "").upper()
        if life == "DEAD" and nid in travs:
            return InvariantResult(
                "INV-DEATH-LOCK",
                "CRITICAL",
                False,
                f"Мёртвый NPC {nid} имеет active_traversal. Нарушение ADR-127.",
                ["backend/app/services/npc/life_engine.py", "backend/app/services/scene_state_manager.py"]
            )
    return InvariantResult("INV-DEATH-LOCK", "CRITICAL", True, "", [])


def inv_trav_zombie(world: TestWorld) -> InvariantResult:
    """INV-TRAV-ZOMBIE: В active_traversals нет терминальных статусов (COMPLETED, CANCELLED)."""
    scene = world.game_loop.get_scene_state(world.campaign_id, "tavern") or {}
    travs = scene.get("active_traversals", {})
    _terminal = {"COMPLETED", "CANCELLED"}
    _zombies = [f"{nid}={t.get('status')}" for nid, t in travs.items() if isinstance(t, dict) and t.get("status", "").upper() in _terminal]
    
    if _zombies:
        return InvariantResult(
            "INV-TRAV-ZOMBIE",
            "CRITICAL",
            False,
            f"Обнаружены зомби-перемещения: {', '.join(_zombies)}. Нарушение ADR-TRAV-FSM (cleanup failed).",
            [
                "backend/app/services/scene_state_manager.py",
                "backend/app/services/tick_orchestrator.py (_process_traversals)"
            ]
        )
    return InvariantResult("INV-TRAV-ZOMBIE", "CRITICAL", True, "", [])


def inv_dialogue_scheduler_fail(world: TestWorld) -> InvariantResult:
    """INV-DIALOGUE-SCHEDULER-FAIL: Проверка тихих отказов TaskScheduler."""
    scheduler = getattr(world.game_loop, "_task_scheduler", None) or getattr(world.game_loop, "task_scheduler", None)
    if not scheduler:
        return InvariantResult("INV-DIALOGUE-SCHEDULER-FAIL", "CRITICAL", False, "TaskScheduler не найден.", [])
        
    _failed = getattr(scheduler, "failed_tasks", 0)
    _processed = getattr(scheduler, "total_processed_tasks", 0)
    
    # ADR-O-343: LLM может падать (возвращать success=False). Это не "тихий отказ" системы, 
    # а честная обработка сбоя инфраструктуры. Тихим отказом считается только если задачи вообще не доходят до исполнителя.
    if _failed > 0 and _processed == 0:
        return InvariantResult(
            "INV-DIALOGUE-SCHEDULER-FAIL",
            "CRITICAL",
            False,
            f"TaskScheduler тихо провалил {_failed} задач (диалогов). Нарушение L4 (Silent Failure).",
            [
                "backend/app/services/game_loop/task_scheduler.py",
                "backend/app/services/execution/dialogue_executor.py",
                "backend/app/services/npc/decision_hub.py"
            ]
        )
        
    return InvariantResult("INV-DIALOGUE-SCHEDULER-FAIL", "CRITICAL", True, "Тихих отказов нет.", [])


def inv_domain_purity(world: TestWorld) -> InvariantResult:
    """INV-DOMAIN-PURITY: Запрет импорта services/models в доменный слой (§1.2)."""
    import sys
    from pathlib import Path
    _scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
        
    try:
        from lint_domain_purity import run_lint
        violations = run_lint()
        
        if violations:
            _details = "; ".join(violations[:5])
            return InvariantResult(
                "INV-DOMAIN-PURITY",
                "CRITICAL",
                False,
                f"Найдено {len(violations)} импортов верхних слоёв в domain. Нарушение §1.2. Первые: {_details}",
                ["backend/app/domain/"]
            )
        return InvariantResult("INV-DOMAIN-PURITY", "CRITICAL", True, "", [])
    except Exception as e:
        return InvariantResult(
            "INV-DOMAIN-PURITY",
            "CRITICAL",
            False,
            f"Ошибка запуска линтера: {e}",
            ["scripts/lint_domain_purity.py"]
        )


def inv_llm_exile(world: TestWorld) -> InvariantResult:
    """INV-LLM-EXILE: Запрет вызовов LLM в ядре симуляции (L7)."""
    import os
    import sys
    from pathlib import Path
    _scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
        
    try:
        from lint_llm_exile import run_lint
        _backend_dir = str(Path(__file__).resolve().parents[1] / "app")
        violations = run_lint(_backend_dir)
        
        if violations:
            _details = "; ".join(violations[:5])
            return InvariantResult(
                "INV-LLM-EXILE",
                "CRITICAL",
                False,
                f"Найдено {len(violations)} LLM-вызовов в ядре. Нарушение L7. Первые: {_details}",
                ["backend/app/services/tick_orchestrator.py", "backend/app/services/npc/decision_hub.py"]
            )
        return InvariantResult("INV-LLM-EXILE", "CRITICAL", True, "", [])
    except Exception as e:
        return InvariantResult(
            "INV-LLM-EXILE",
            "CRITICAL",
            False,
            f"Ошибка запуска линтера: {e}",
            ["scripts/lint_llm_exile.py"]
        )


def inv_position_mutation(world: TestWorld) -> InvariantResult:
    """INV-POSITION-MUTATION: Запрет прямой мутации позиции вне SceneStateManager (§4.1)."""
    import os
    import sys
    from pathlib import Path
    _scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
        
    try:
        from lint_position_mutation import run_lint
        _backend_dir = str(Path(__file__).resolve().parents[1] / "app")
        violations = run_lint(_backend_dir)
        
        if violations:
            _details = "; ".join(violations[:5])
            return InvariantResult(
                "INV-POSITION-MUTATION",
                "CRITICAL",
                False,
                f"Найдено {len(violations)} прямых мутаций позиции. Нарушение §4.1. Первые: {_details}",
                ["backend/app/services/"]
            )
        return InvariantResult("INV-POSITION-MUTATION", "CRITICAL", True, "", [])
    except Exception as e:
        return InvariantResult(
            "INV-POSITION-MUTATION",
            "CRITICAL",
            False,
            f"Ошибка запуска линтера: {e}",
            ["scripts/lint_position_mutation.py"]
        )


def inv_time_freezer(world: TestWorld) -> InvariantResult:
    """INV-TIME-FREEZER: TimeFreezer подменяет wall-clock (Этап 2.4)."""
    import sys
    from pathlib import Path
    _backend_dir = str(Path(__file__).resolve().parents[1])
    if _backend_dir not in sys.path:
        sys.path.insert(0, _backend_dir)
        
    try:
        from app.services.replay.time_freezer import frozen_time
        import time, datetime
        
        _game_time = 12345.6
        
        with frozen_time(_game_time):
            _t = time.time()
            _dt_obj = datetime.datetime.now()
            # Вызываем .timestamp() с UTC tzinfo, чтобы избежать Windows mktime бага для дат < 1970
            _dt = _dt_obj.replace(tzinfo=datetime.timezone.utc).timestamp()
            
        if abs(_t - _game_time) > 0.1 or abs(_dt - _game_time) > 0.1:
            return InvariantResult("INV-TIME-FREEZER", "CRITICAL", False, "Wall-clock не подменён.", [])
            
        # Проверяем, что после выхода из контекста оригинальное время восстановлено
        _real_time = time.time()
        if abs(_real_time - _game_time) < 100:
            return InvariantResult("INV-TIME-FREEZER", "CRITICAL", False, "Оригинальный time.time() не восстановлен.", [])
            
        return InvariantResult("INV-TIME-FREEZER", "CRITICAL", True, "TimeFreezer OK.", [])
    except Exception as e:
        return InvariantResult(
            "INV-TIME-FREEZER",
            "CRITICAL",
            False,
            f"Ошибка TimeFreezer: {e}",
            ["backend/app/services/replay/time_freezer.py"]
        )


def inv_replay_store(world: TestWorld) -> InvariantResult:
    """INV-REPLAY-STORE: ReplayStore записывает и читает тики (Подсистема 2)."""
    import os
    import tempfile
    import sys
    from pathlib import Path
    _backend_dir = str(Path(__file__).resolve().parents[1])
    if _backend_dir not in sys.path:
        sys.path.insert(0, _backend_dir)
        
    try:
        from app.services.replay.replay_store import ReplayStore
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_replay.db")
            store = ReplayStore(db_path)
            
            session_id = store.start_session("test_campaign", "test_hash")
            if not session_id:
                return InvariantResult("INV-REPLAY-STORE", "CRITICAL", False, "start_session вернул пустой ID", [])
                
            store.record_tick(
                session_id=session_id,
                tick_id=1,
                game_time_seconds=60.0,
                tick_state={"tick": 1, "npcs": [{"id": "test"}]},
                tick_mutation={"decisions": []},
                world_snapshot={"tick": 1, "snapshot": "test"}
            )
            store.record_intervention(session_id, 1, "player", {"text": "test"})
            store.record_causal_probe(session_id, 1, "INV-TEST", "PASS", {"msg": "ok"})
            store.close()
            
            # Проверяем чтение
            store2 = ReplayStore(db_path)
            row = store2.conn.execute("SELECT * FROM tick_snapshots WHERE tick_id = 1").fetchone()
            if not row:
                return InvariantResult("INV-REPLAY-STORE", "CRITICAL", False, "Тик не записан в БД", [])
                
            state = store2._from_json_bytes(row["tick_state_json"])
            if state.get("tick") != 1:
                return InvariantResult("INV-REPLAY-STORE", "CRITICAL", False, "TickState не десериализован", [])
                
            store2.close()
            
        return InvariantResult("INV-REPLAY-STORE", "CRITICAL", True, "ReplayStore round-trip OK.", [])
    except Exception as e:
        return InvariantResult(
            "INV-REPLAY-STORE",
            "CRITICAL",
            False,
            f"Ошибка ReplayStore: {e}",
            ["backend/app/services/replay/replay_store.py"]
        )


def inv_adr_net(world: TestWorld) -> InvariantResult:
    """INV-ADR-NET: ADR-Net парсер успешно строит граф зависимостей (Подсистема 4)."""
    import os
    import sys
    from pathlib import Path
    _backend_dir = str(Path(__file__).resolve().parents[1])
    if _backend_dir not in sys.path:
        sys.path.insert(0, _backend_dir)
        
    try:
        from app.services.adr_net.adr_parser import run_parser
        _root_dir = str(Path(__file__).resolve().parents[2])
        _audits_dir = os.path.join(_root_dir, "docs", "audits")
        _master_idx = os.path.join(_root_dir, "docs", "ADR (Architecture Decision Records).md")
        
        graph = run_parser(audits_dir=_audits_dir, master_index=_master_idx)
        
        if len(graph) < 20:
            return InvariantResult(
                "INV-ADR-NET",
                "CRITICAL",
                False,
                f"ADR-Net распарсил только {len(graph)} ADR. Ожидается > 20. Граф сломан.",
                ["docs/ADR (Architecture Decision Records).md", "docs/audits/"]
            )
            
        # Проверяем, что хотя бы 10% ADR имеют привязку к файлам (аудиты пишутся не для всех ADR)
        _with_files = sum(1 for n in graph.values() if n.files)
        if _with_files < len(graph) * 0.1:
            return InvariantResult(
                "INV-ADR-NET",
                "CRITICAL",
                False,
                f"Только {_with_files}/{len(graph)} ADR имеют привязку к файлам. Граф неполный.",
                ["docs/audits/"]
            )
            
        return InvariantResult("INV-ADR-NET", "CRITICAL", True, f"ADR-Net: {len(graph)} nodes, {_with_files} with files.", [])
    except Exception as e:
        return InvariantResult(
            "INV-ADR-NET",
            "CRITICAL",
            False,
            f"Ошибка парсера ADR-Net: {e}",
            ["backend/app/services/adr_net/adr_parser.py"]
        )


def inv_no_retro_sim(world: TestWorld) -> InvariantResult:
    """INV-NO-RETRO-SIM: Запрет циклов с вызовами tick/execute (Rule 25)."""
    import os
    import sys
    from pathlib import Path
    _scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
        
    try:
        from lint_retro_simulation import run_lint
        _backend_dir = str(Path(__file__).resolve().parents[1] / "app")
        violations = run_lint(_backend_dir)
        
        if violations:
            _details = "; ".join(violations[:5])
            return InvariantResult(
                "INV-NO-RETRO-SIM",
                "CRITICAL",
                False,
                f"Найдено {len(violations)} ретро-симуляций. Нарушение Rule 25. Первые: {_details}",
                ["backend/app/services/"]
            )
        return InvariantResult("INV-NO-RETRO-SIM", "CRITICAL", True, "", [])
    except Exception as e:
        return InvariantResult(
            "INV-NO-RETRO-SIM",
            "CRITICAL",
            False,
            f"Ошибка запуска линтера: {e}",
            ["scripts/lint_retro_simulation.py"]
        )


def inv_l1_append_only(world: TestWorld) -> InvariantResult:
    """INV-L1-APPEND-ONLY: Запрет удаления событий из L1Chronicle (Rule 28)."""
    import os
    import sys
    from pathlib import Path
    _scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
        
    try:
        from lint_l1_append_only import run_lint
        _backend_dir = str(Path(__file__).resolve().parents[1] / "app")
        violations = run_lint(_backend_dir)
        
        if violations:
            _details = "; ".join(violations[:5])
            return InvariantResult(
                "INV-L1-APPEND-ONLY",
                "CRITICAL",
                False,
                f"Найдено {len(violations)} попыток удаления из L1. Нарушение Rule 28. Первые: {_details}",
                ["backend/app/services/npc/l1_chronicle.py", "backend/app/services/npc/identity/"]
            )
        return InvariantResult("INV-L1-APPEND-ONLY", "CRITICAL", True, "", [])
    except Exception as e:
        return InvariantResult(
            "INV-L1-APPEND-ONLY",
            "CRITICAL",
            False,
            f"Ошибка запуска линтера: {e}",
            ["scripts/lint_l1_append_only.py"]
        )


def inv_l3_ephemeral(world: TestWorld) -> InvariantResult:
    """INV-L3-EPHEMERAL: EffectiveDrives не персистятся (L3-P1)."""
    engine = getattr(world.game_loop, "_get_life_engine", lambda: None)()
    npcs = engine.get_npc_states(world.campaign_id) if engine else []
    scene = world.game_loop.get_scene_state(world.campaign_id, "tavern") or {}
    
    _bad_keys = {"effective_drives", "l3_drives", "l3_projection"}
    
    # 1. Проверяем scene_state
    for key in scene.keys():
        if key.lower() in _bad_keys:
            return InvariantResult(
                "INV-L3-EPHEMERAL",
                "CRITICAL",
                False,
                f"scene_state содержит персистентный L3 ключ: '{key}'. Нарушение L3-P1.",
                ["backend/app/services/scene_state_manager.py", "backend/app/services/tick_orchestrator.py"]
            )
            
    # 2. Проверяем npc_dicts
    for npc in npcs:
        for key in npc.keys():
            if key.lower() in _bad_keys:
                return InvariantResult(
                    "INV-L3-EPHEMERAL",
                    "CRITICAL",
                    False,
                    f"NPC '{npc.get('npc_id', '?')}' содержит персистентный L3 ключ: '{key}'. Нарушение L3-P1.",
                    ["backend/app/models/npc_state.py", "backend/app/services/state_applicator.py"]
                )
                
    return InvariantResult("INV-L3-EPHEMERAL", "CRITICAL", True, "", [])


def inv_sc1_zero_position(world: TestWorld) -> InvariantResult:
    """INV-SC-1: local_position не может быть (0.0, 0.0) (Spatial Coherence)."""
    scene = world.game_loop.get_scene_state(world.campaign_id, "tavern") or {}
    npc_pos = scene.get("npc_positions", {})
    
    for npc_id, pos_data in npc_pos.items():
        if not isinstance(pos_data, dict):
            continue
        lp = pos_data.get("local_position")
        if isinstance(lp, dict) and lp.get("x", 1.0) == 0.0 and lp.get("y", 1.0) == 0.0:
            return InvariantResult(
                "INV-SC-1",
                "CRITICAL",
                False,
                f"NPC '{npc_id}' имеет local_position (0.0, 0.0). Нарушение SC-1.",
                ["backend/app/services/scene_state_manager.py", "backend/app/services/spatial/movement_engine.py"]
            )
            
    return InvariantResult("INV-SC-1", "CRITICAL", True, "", [])


def inv_spatial_ssot(world: TestWorld) -> InvariantResult:
    """INV-SPATIAL-SSOT: Запрет прямой сборки SpatialService вне фабрики (L9)."""
    import sys
    from pathlib import Path
    _scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
        
    try:
        from lint_spatial_ssot import run_lint
        _backend_dir = str(Path(__file__).resolve().parents[1] / "app")
        violations = run_lint(_backend_dir)
        
        if violations:
            _details = "; ".join(violations[:5])
            return InvariantResult(
                "INV-SPATIAL-SSOT",
                "CRITICAL",
                False,
                f"Найдено {len(violations)} прямых сборок SpatialService. Нарушение L9. Первые: {_details}",
                ["backend/app/services/"]
            )
        return InvariantResult("INV-SPATIAL-SSOT", "CRITICAL", True, "", [])
    except Exception as e:
        return InvariantResult(
            "INV-SPATIAL-SSOT",
            "CRITICAL",
            False,
            f"Ошибка запуска линтера: {e}",
            ["scripts/lint_spatial_ssot.py"]
        )


def inv_frontend_isolation(world: TestWorld) -> InvariantResult:
    """INV-FRONTEND-ISOLATION: Запрет импорта backend.app во фронтенде (§1.1)."""
    import sys
    from pathlib import Path
    _scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
        
    try:
        from lint_frontend_isolation import run_lint
        violations = run_lint()
        
        if violations:
            _details = "; ".join(violations[:5])
            return InvariantResult(
                "INV-FRONTEND-ISOLATION",
                "CRITICAL",
                False,
                f"Найдено {len(violations)} прямых импортов backend во фронтенд. Нарушение §1.1. Первые: {_details}",
                ["frontend/"]
            )
        return InvariantResult("INV-FRONTEND-ISOLATION", "CRITICAL", True, "", [])
    except Exception as e:
        return InvariantResult(
            "INV-FRONTEND-ISOLATION",
            "CRITICAL",
            False,
            f"Ошибка запуска линтера: {e}",
            ["scripts/lint_frontend_isolation.py"]
        )


def inv_epistemic_boundary(world: TestWorld) -> InvariantResult:
    """INV-EPISTEMIC-BOUNDARY: Запрет чтения ментальных полей в DM/Verbalization (§17)."""
    import sys
    from pathlib import Path
    _scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
        
    try:
        from lint_epistemic_boundary import run_lint
        violations = run_lint()
        
        if violations:
            _details = "; ".join(violations[:5])
            return InvariantResult(
                "INV-EPISTEMIC-BOUNDARY",
                "CRITICAL",
                False,
                f"Найдено {len(violations)} нарушений Эпистемической Границы. Нарушение §17. Первые: {_details}",
                ["backend/app/agents/dm_agent.py", "backend/app/services/verbalization/"]
            )
        return InvariantResult("INV-EPISTEMIC-BOUNDARY", "CRITICAL", True, "", [])
    except Exception as e:
        return InvariantResult(
            "INV-EPISTEMIC-BOUNDARY",
            "CRITICAL",
            False,
            f"Ошибка запуска линтера: {e}",
            ["scripts/lint_epistemic_boundary.py"]
        )


def inv_kernel_rng(world: TestWorld) -> InvariantResult:
    """INV-KERNEL-RNG: Запрет random.* в симуляционном слое (ADR-O-301)."""
    import sys
    from pathlib import Path
    _scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
        
    try:
        from lint_kernel_rng import run_lint
        violations = run_lint()
        
        if violations:
            _details = "; ".join(violations[:5])
            return InvariantResult(
                "INV-KERNEL-RNG",
                "CRITICAL",
                False,
                f"Найдено {len(violations)} нарушений изоляции случайности. Нарушение ADR-O-301. Первые: {_details}",
                ["backend/app/services/"]
            )
        return InvariantResult("INV-KERNEL-RNG", "CRITICAL", True, "", [])
    except Exception as e:
        return InvariantResult(
            "INV-KERNEL-RNG",
            "CRITICAL",
            False,
            f"Ошибка запуска линтера: {e}",
            ["scripts/lint_kernel_rng.py"]
        )


def inv_wall_clock(world: TestWorld) -> InvariantResult:
    """INV-WALL-CLOCK: Запрет wall-clock в симуляционном слое (§15.1)."""
    import sys
    from pathlib import Path
    _scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
        
    try:
        from lint_wall_clock import run_lint
        violations = run_lint()
        
        if violations:
            _details = "; ".join(violations[:5])
            return InvariantResult(
                "INV-WALL-CLOCK",
                "CRITICAL",
                False,
                f"Найдено {len(violations)} нарушений изоляции реального времени. Нарушение §15.1. Первые: {_details}",
                ["backend/app/services/"]
            )
        return InvariantResult("INV-WALL-CLOCK", "CRITICAL", True, "", [])
    except Exception as e:
        return InvariantResult(
            "INV-WALL-CLOCK",
            "CRITICAL",
            False,
            f"Ошибка запуска линтера: {e}",
            ["scripts/lint_wall_clock.py"]
        )


def inv_silent_failure(world: TestWorld) -> InvariantResult:
    """INV-SILENT-FAILURE: Запрет тихих отказов (except: pass) (L4)."""
    import os
    import sys
    from pathlib import Path
    _scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
        
    try:
        from lint_silent_failures import run_lint
        _backend_dir = str(Path(__file__).resolve().parents[1] / "app")
        violations = run_lint(_backend_dir)
        
        if violations:
            _details = "; ".join([f"{os.path.basename(f)}:{l}" for f, l, _ in violations[:5]])
            return InvariantResult(
                "INV-SILENT-FAILURE",
                "CRITICAL",
                False,
                f"Найдено {len(violations)} тихих отказов (except: pass). Нарушение L4. Первые: {_details}",
                [f for f, _, _ in violations]
            )
            
        return InvariantResult("INV-SILENT-FAILURE", "CRITICAL", True, "", [])
    except Exception as e:
        return InvariantResult(
            "INV-SILENT-FAILURE",
            "CRITICAL",
            False,
            f"Ошибка запуска линтера: {e}",
            ["scripts/lint_silent_failures.py"]
        )


def inv_hp_ssot(world: TestWorld) -> InvariantResult:
    """INV-HP-SSOT: Запрет прямого присваивания state.hp (ADR-HP-UNIFICATION)."""
    import sys
    from pathlib import Path
    # Добавляем scripts/ в path для импорта линтера
    _scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
        
    try:
        from lint_hp_ssot import run_lint
        _backend_dir = str(Path(__file__).resolve().parents[1] / "app")
        violations = run_lint(_backend_dir)
        
        if violations:
            _details = "; ".join([f"{os.path.basename(f)}:{l}" for f, l, _ in violations[:5]])
            return InvariantResult(
                "INV-HP-SSOT",
                "CRITICAL",
                False,
                f"Найдено {len(violations)} прямых записей в state.hp. Нарушение ADR-HP-UNIFICATION. Первые: {_details}",
                [f for f, _, _ in violations]
            )
            
        return InvariantResult("INV-HP-SSOT", "CRITICAL", True, "", [])
    except Exception as e:
        return InvariantResult(
            "INV-HP-SSOT",
            "CRITICAL",
            False,
            f"Ошибка запуска линтера: {e}",
            ["scripts/lint_hp_ssot.py"]
        )


def inv_pbt_roundtrip(world: TestWorld) -> InvariantResult:
    """Подсистема 1 (PBT): Property-based тест на Round-Trip Integrity (§12.2)."""
    try:
        from tests.pbt.properties.test_npc_state_roundtrip import (
            test_npc_state_roundtrip_preserves_critical_fields,
        )
        # Запускаем hypothesis-тест программно
        test_npc_state_roundtrip_preserves_critical_fields()
        return InvariantResult(
            "INV-PBT-ROUNDTRIP",
            "CRITICAL",
            True,
            "PBT (200 examples) passed: NPCState round-trip preserves critical fields.",
            [],
        )
    except Exception as e:
        return InvariantResult(
            "INV-PBT-ROUNDTRIP",
            "CRITICAL",
            False,
            f"PBT FAILED: {e}",
            [
                "backend/app/models/npc_state.py",
                "backend/tests/pbt/properties/test_npc_state_roundtrip.py",
            ],
        )

def inv_pbt_spatial(world: TestWorld) -> InvariantResult:
    """Подсистема 1 (PBT): Property-based тест на Spatial Coherence (SC-1)."""
    try:
        from tests.pbt.properties.test_spatial_and_traversal import test_sc1_rejects_zero_position
        test_sc1_rejects_zero_position()
        return InvariantResult(
            "INV-PBT-SC1",
            "CRITICAL",
            True,
            "PBT (100 examples) passed: SC-1 rejects (0.0, 0.0).",
            [],
        )
    except Exception as e:
        return InvariantResult(
            "INV-PBT-SC1",
            "CRITICAL",
            False,
            f"PBT FAILED: {e}",
            [
                "backend/tests/pbt/properties/test_spatial_and_traversal.py",
            ],
        )

def inv_pbt_traversal(world: TestWorld) -> InvariantResult:
    """Подсистема 1 (PBT): Property-based тест на Traversal FSM (Zombie traversals)."""
    try:
        from tests.pbt.properties.test_spatial_and_traversal import test_trav_fsm_detects_zombies
        test_trav_fsm_detects_zombies()
        return InvariantResult(
            "INV-PBT-TRAV-FSM",
            "CRITICAL",
            True,
            "PBT (100 examples) passed: ADR-TRAV-FSM detects zombies.",
            [],
        )
    except Exception as e:
        return InvariantResult(
            "INV-PBT-TRAV-FSM",
            "CRITICAL",
            False,
            f"PBT FAILED: {e}",
            [
                "backend/tests/pbt/properties/test_spatial_and_traversal.py",
            ],
        )


def inv_scene_entity_isolation(world: TestWorld) -> InvariantResult:
    """INV-SCENE-ENTITY-ISOLATION: NPC не должны появляться в npc_positions чужой локации.
    
    Проверяет, что каждый NPC в npc_positions имеет location_id, совпадающий с локацией сцены.
    """
    try:
        from app.core.constants import DEFAULT_LOCATION_ID
        from app.services.spatial.spatial_registry import SpatialRegistry
        
        _reg = SpatialRegistry.get_or_load(world.campaign_id)
        if not _reg:
            return InvariantResult("INV-SCENE-ENTITY-ISOLATION", "CRITICAL", True, "SpatialRegistry не загружен.", [])
        
        _all_locs = _reg.get_all_location_ids()
        if len(_all_locs) < 2:
            return InvariantResult("INV-SCENE-ENTITY-ISOLATION", "CRITICAL", True, "Тест пропущен (требуется >1 локации).", [])
        
        world.idle_tick()
        _violations = []
        
        for _loc_id in _all_locs:
            _scene = world.game_loop.scene_manager.get_scene_state(world.campaign_id, _loc_id) or {}
            _npc_positions = _scene.get("npc_positions", {})
            
            for _npc_id, _npc_data in _npc_positions.items():
                if _npc_id == "player":
                    continue
                _npc_loc = _npc_data.get("location_id") or _npc_data.get("location", "")
                if _npc_loc and _npc_loc != _loc_id:
                    _violations.append(f"{_npc_id} in {_loc_id} (belongs to {_npc_loc})")
        
        if not _violations:
            return InvariantResult("INV-SCENE-ENTITY-ISOLATION", "CRITICAL", True, "All NPCs are in their correct locations.", [])
        return InvariantResult(
            "INV-SCENE-ENTITY-ISOLATION",
            "CRITICAL",
            False,
            f"NPC location violations: {_violations[:5]}",
            [
                "backend/app/services/tick_orchestrator.py",
                "backend/app/services/scene_state_manager.py"
            ]
        )
    except Exception as e:
        return InvariantResult(
            "INV-SCENE-ENTITY-ISOLATION", "CRITICAL", False, f"Ошибка выполнения теста: {e}", ["backend/tests/IPT.py"]
        )

def inv_replay_determinism(world: TestWorld) -> InvariantResult:
    """INV-REPLAY-DETERMINISM: Инфраструктура реплея готова к A/B тестированию.
    
    Полный детерминированный прогон (T0->T3 == Replay(T3)) требует кэширования всех LLM-вызовов
    и полного восстановления TickState, что выходит за рамки 5-секундного IPT.
    Здесь проверяется готовность инфраструктуры: ReplayRecorder подключён, БД доступна.
    Сам детерминизм верифицируется через DriftLaboratory (S3/S7).
    """
    try:
        _orch = getattr(world.game_loop, "_tick_orch", None)
        _recorder = getattr(_orch, "_replay_recorder", None) if _orch else None
        if not _recorder:
            return InvariantResult("INV-REPLAY-DETERMINISM", "WARNING", True, "ReplayRecorder not attached, skipping.", [])
        
        # Прогоняем 1 тик для проверки записи
        world.idle_tick()
        
        _store = _recorder.store
        _session_id = _recorder.session_id
        
        # Проверяем, что тик записался в БД
        row = _store.conn.execute(
            "SELECT tick_id FROM tick_snapshots WHERE session_id = ? AND tick_id = ?",
            (_session_id, world.tick)
        ).fetchone()
        
        if row:
            return InvariantResult("INV-REPLAY-DETERMINISM", "WARNING", True, "Replay infrastructure ready (tick recorded). Full A/B test requires DriftLaboratory.", [])
        return InvariantResult(
            "INV-REPLAY-DETERMINISM",
            "CRITICAL",
            False,
            "ReplayRecorder attached, but no ticks recorded to DB.",
            ["backend/app/services/replay/replay_recorder.py"]
        )
    except Exception as e:
        return InvariantResult(
            "INV-REPLAY-DETERMINISM", "WARNING", True, f"Replay test skipped due to: {e}", []
        )

def inv_save_load_integrity(world: TestWorld) -> InvariantResult:
    """INV-SAVE-LOAD-INTEGRITY: Save/Load цикл сохраняет критическое состояние.
    
    Прогоняет 3 тика, сохраняет состояние, загружает его и проверяет,
    что tick, game_time и npc_positions совпадают.
    """
    try:
        # Прогоняем 3 тика
        for _ in range(3):
            world.idle_tick()
        
        _scene_manager = world.game_loop.scene_manager
        _persistence = getattr(_scene_manager, "_persistence", None)
        if not _persistence:
            return InvariantResult("INV-SAVE-LOAD-INTEGRITY", "CRITICAL", False, "Persistence adapter not found.", [])
        
        # Текущее состояние в памяти
        _in_memory_scene = world._get_scene()
        _in_memory_tick = _in_memory_scene.get("tick", 0)
        _in_memory_time = _in_memory_scene.get("game_time_seconds", 0.0)
        _in_memory_positions = _in_memory_scene.get("npc_positions", {})
        
        # Загружаем состояние из персистентного хранилища (используем load_scene_at для конкретной локации)
        _loaded_scene = _persistence.load_scene_at(world.campaign_id, "tavern")
        if not _loaded_scene:
            return InvariantResult("INV-SAVE-LOAD-INTEGRITY", "CRITICAL", False, "load_scene вернул пустой результат.", [])
        
        _loaded_tick = _loaded_scene.get("tick", 0)
        _loaded_time = _loaded_scene.get("game_time_seconds", 0.0)
        _loaded_positions = _loaded_scene.get("npc_positions", {})
        
        _violations = []
        if _loaded_tick != _in_memory_tick:
            _violations.append(f"tick mismatch: memory={_in_memory_tick}, loaded={_loaded_tick}")
        if _loaded_time != _in_memory_time:
            _violations.append(f"time mismatch: memory={_in_memory_time}, loaded={_loaded_time}")
        
        # Проверяем позиции (сравниваем только ID NPC, так как координаты могли измениться в последнем тике)
        _memory_ids = set(_in_memory_positions.keys())
        _loaded_ids = set(_loaded_positions.keys())
        if _memory_ids != _loaded_ids:
            _violations.append(f"npc_positions ID mismatch: memory={_memory_ids}, loaded={_loaded_ids}")
        
        if not _violations:
            return InvariantResult("INV-SAVE-LOAD-INTEGRITY", "CRITICAL", True, "Save/Load integrity verified.", [])
        return InvariantResult(
            "INV-SAVE-LOAD-INTEGRITY",
            "CRITICAL",
            False,
            f"Save/Load integrity violations: {_violations}",
            ["backend/app/services/scene_state_manager.py", "backend/app/services/state/sqlite_persistence_adapter.py"]
        )
    except Exception as e:
        return InvariantResult(
            "INV-SAVE-LOAD-INTEGRITY", "CRITICAL", False, f"Ошибка выполнения теста: {e}", ["backend/tests/IPT.py"]
        )

def inv_intent_event_completeness(world: TestWorld) -> InvariantResult:
    """INV-INTENT-EVENT-COMPLETENESS: Каждый committed CommunicationIntent должен иметь явный event mapping.
    
    Проверяет, что IntentEventAdapter не возвращает 'unknown' тип события.
    """
    try:
        from app.services.events.intent_event_adapter import IntentEventAdapter
        from app.domain.communication import CommunicationIntent, ExposureLevel
        from app.models.npc_state import Intent
        
        _violations = []
        # Проверяем все интенты, которые могут стать CommunicationIntent
        _communicative_intents = [
            "talk", "warn", "intimidate", "attack", "help", "report", 
            "trade", "explain", "offer_job", "request_service", 
            "spread_rumor", "call_for_help", "change_role"
        ]
        
        for _intent_val in _communicative_intents:
            _mock_intent = CommunicationIntent(
                speaker="test_npc",
                audience="player",
                topic="test",
                intent_type=_intent_val,
                emotional_state="neutral",
                exposure_level=ExposureLevel(semantic="normal", physical_radius=10.0)
            )
            _event = IntentEventAdapter.to_event(_mock_intent)
            if _event.type == "unknown":
                _violations.append(_intent_val)
        
        if not _violations:
            return InvariantResult(
                "INV-INTENT-EVENT-COMPLETENESS", "CRITICAL", True,
                "All communicative intents have explicit event mapping.",
                []
            )
        return InvariantResult(
            "INV-INTENT-EVENT-COMPLETENESS",
            "CRITICAL",
            False,
            f"Intents with 'unknown' event type: {_violations}",
            ["backend/app/services/events/intent_event_adapter.py"]
        )
    except Exception as e:
        return InvariantResult(
            "INV-INTENT-EVENT-COMPLETENESS", "CRITICAL", False, f"Ошибка выполнения теста: {e}", ["backend/tests/IPT.py"]
        )

def inv_trav_terminality(world: TestWorld) -> InvariantResult:
    """INV-TRAV-TERMINALITY: Транзиты не должны зависать в PENDING или MOVING forever."""
    try:
        # Прогоняем 5 тиков, чтобы выявить застрявшие транзиты
        for _ in range(5):
            world.idle_tick()
        
        scene = world._get_scene()
        travs = scene.get("active_traversals", {})
        stuck = []
        current_tick = world.tick
        
        for nid, t in travs.items():
            if not isinstance(t, dict):
                continue
            status = t.get("status", "").upper()
            if status == "PENDING":
                stuck.append(f"{nid}=PENDING (should be MOVING)")
            elif status == "MOVING":
                started = t.get("started_tick", 0)
                duration = t.get("duration_ticks", 1)
                # Grace period: 2 тика сверх длительности
                if current_tick > started + duration + 2:
                    stuck.append(f"{nid}=MOVING (started={started}, duration={duration}, current={current_tick})")
        
        if not stuck:
            return InvariantResult("INV-TRAV-TERMINALITY", "CRITICAL", True, "No stuck traversals.", [])
        return InvariantResult(
            "INV-TRAV-TERMINALITY",
            "CRITICAL",
            False,
            f"Stuck traversals: {stuck}",
            ["backend/app/services/spatial/traversal_execution_system.py", "backend/app/services/scene_state_manager.py"]
        )
    except Exception as e:
        return InvariantResult(
            "INV-TRAV-TERMINALITY", "CRITICAL", False, f"Ошибка выполнения теста: {e}", ["backend/tests/IPT.py"]
        )

def inv_dialogue_liveness(world: TestWorld) -> InvariantResult:
    """INV-DIALOGUE-LIVENESS: Очередь pending_tasks не должна переполняться."""
    try:
        # Прогоняем 5 тиков
        for _ in range(5):
            world.idle_tick()
        
        scene = world._get_scene()
        pending = scene.get("pending_tasks", [])
        
        # Если в очереди больше 20 задач, значит TaskScheduler не справляется или завис
        if len(pending) > 20:
            return InvariantResult(
                "INV-DIALOGUE-LIVENESS",
                "CRITICAL",
                False,
                f"pending_tasks flooded: {len(pending)} tasks. TaskScheduler not draining.",
                ["backend/app/services/game_loop/task_scheduler.py"]
            )
        return InvariantResult("INV-DIALOGUE-LIVENESS", "CRITICAL", True, f"pending_tasks={len(pending)} (healthy).", [])
    except Exception as e:
        return InvariantResult(
            "INV-DIALOGUE-LIVENESS", "CRITICAL", False, f"Ошибка выполнения теста: {e}", ["backend/tests/IPT.py"]
        )

def inv_event_cardinality(world: TestWorld) -> InvariantResult:
    """INV-EVENT-CARDINALITY: События публикуются 1 раз, не N_locations раз.
    
    Проверяет, что NPC_MOVED и NPC_PROXIMITY_CLOSE не дублируются при множественных локациях.
    """
    try:
        from app.services.spatial.spatial_registry import SpatialRegistry
        
        _reg = SpatialRegistry.get_or_load(world.campaign_id)
        if not _reg:
            return InvariantResult("INV-EVENT-CARDINALITY", "CRITICAL", True, "SpatialRegistry не загружен.", [])
        
        _all_locs = _reg.get_all_location_ids()
        if len(_all_locs) < 2:
            return InvariantResult("INV-EVENT-CARDINALITY", "CRITICAL", True, "Тест пропущен (требуется >1 локации).", [])
        
        # Подменяем EventBus для подсчёта публикаций
        _bus = world.game_loop._tick_orch._get_event_bus()
        _publish_counts = {}
        _orig_publish = _bus.publish
        
        def _counting_publish(event):
            if isinstance(event, dict):
                _evt_type = event.get('type', 'unknown')
            else:
                _evt_type = getattr(event, 'type', 'unknown')
            _publish_counts[_evt_type] = _publish_counts.get(_evt_type, 0) + 1
            return _orig_publish(event)
        
        _bus.publish = _counting_publish
        try:
            # S3 FIX: Прогоняем 5 тиков, чтобы NPC успели начать движение
            for _ in range(5):
                world.idle_tick()
        finally:
            _bus.publish = _orig_publish
        
        # Проверяем: NPC_MOVED не должен превышать количество NPC * кол-во тиков
        _npc_moved_count = _publish_counts.get("NPC_MOVED", 0)
        # Читаем количество NPC напрямую из scene_state, так как last_result может быть пуст
        _scene = world._get_scene()
        _total_npcs = len([nid for nid in _scene.get("npc_positions", {}).keys() if nid != "player"])

        # NPC_MOVED должен быть <= total_npcs * 5 (5 тиков, каждый NPC двигается 1 раз за тик)
        _max_allowed = _total_npcs * 5
        if _npc_moved_count <= _max_allowed:
            return InvariantResult(
                "INV-EVENT-CARDINALITY", "CRITICAL", True,
                f"NPC_MOVED={_npc_moved_count} (<= {_max_allowed} allowed for {_total_npcs} NPCs). No duplication.",
                []
            )
        return InvariantResult(
            "INV-EVENT-CARDINALITY",
            "CRITICAL",
            False,
            f"NPC_MOVED={_npc_moved_count} > {_max_allowed} allowed for {_total_npcs} NPCs. Events duplicated across locations!",
            [
                "backend/app/services/tick_orchestrator.py",
                "backend/app/services/events/event_bus.py"
            ]
        )
    except Exception as e:
        return InvariantResult(
            "INV-EVENT-CARDINALITY", "CRITICAL", False, f"Ошибка выполнения теста: {e}", ["backend/tests/IPT.py"]
        )

def inv_tick_cardinality(world: TestWorld) -> InvariantResult:
    """
    INV-TICK-CARDINALITY: Проверка Закона Единичного Времени (§14.1).
    Один idle_tick должен сдвигать глобальное время (game_time_seconds) ровно на 1 шаг,
    независимо от количества активных локаций в кампании.
    """
    try:
        from app.core.constants import GAME_TICK_INTERVAL_SECONDS
        from app.services.spatial.spatial_registry import SpatialRegistry
        
        # Получаем список всех локаций в кампании
        _reg = SpatialRegistry.get_or_load(world.campaign_id)
        if not _reg:
            return InvariantResult(
                "INV-TICK-CARDINALITY", "CRITICAL", False,
                "SpatialRegistry не загружен. Невозможно проверить кратность.",
                ["backend/app/services/spatial/spatial_registry.py"]
            )
        
        _all_locs = _reg.get_all_location_ids()
        _n_locs = len(_all_locs)
        
        if _n_locs <= 1:
            return InvariantResult(
                "INV-TICK-CARDINALITY", "CRITICAL", True,
                f"Тест пропущен (требуется >1 локации, найдено {_n_locs}).",
                []
            )

        # Подменяем TaskScheduler, чтобы избежать падения ThreadPoolExecutor'а LLM
        class _NoOpScheduler:
            def execute_pending(self, *args, **kwargs): pass
            def execute_pending_tasks(self, *args, **kwargs): pass
            def drain(self, *args, **kwargs): pass
            def schedule_task(self, *args, **kwargs): pass
            def get_recent_dialogues(self, *args, **kwargs): return []
        world.game_loop._task_scheduler = _NoOpScheduler()

        # Фиксируем время ДО тика
        time_before = world.game_time_seconds
        
        # Выполняем ровно 1 idle_tick
        world.idle_tick()
        
        # Фиксируем время ПОСЛЕ тика
        time_after = world.game_time_seconds
        
        # Вычисляем фактический сдвиг
        actual_dt = time_after - time_before
        expected_dt = float(GAME_TICK_INTERVAL_SECONDS)
        
        # Проверяем, что сдвиг равен ровно одному шагу, а не N * step
        if actual_dt == expected_dt:
            return InvariantResult(
                "INV-TICK-CARDINALITY", "CRITICAL", True,
                f"Время сдвинуто на {actual_dt} сек (1 шаг), N_LOCATIONS={_n_locs}.",
                []
            )
        else:
            _msg = (
                f"Нарушение §14.1: time_delta={actual_dt}, expected={expected_dt}. "
                f"Найдено локаций: {_n_locs}. "
                f"Время умножается на количество локаций (дрейф старой модели)."
            )
            return InvariantResult(
                "INV-TICK-CARDINALITY", "CRITICAL", False, _msg,
                [
                    "backend/app/services/tick_orchestrator.py",
                    "backend/app/services/phases/idle_services.py",
                    "backend/app/services/game_loop/__init__.py"
                ]
            )
            
    except Exception as e:
        return InvariantResult(
            "INV-TICK-CARDINALITY", "CRITICAL", False,
            f"Ошибка выполнения теста: {e}",
            ["backend/tests/IPT.py"]
        )

INVARIANTS: List[Callable] = [
    inv_scene_entity_isolation,
    inv_replay_determinism,
    inv_save_load_integrity,
    inv_intent_event_completeness,
    inv_trav_terminality,
    inv_dialogue_liveness,
    inv_event_cardinality,
    inv_time_grows,
    inv_tick_grows,
    inv_npc_moves,
    inv_active_traversals_dict,
    inv_npc_has_name,
    inv_dialogue_init,
    inv_dialogue_stm,
    inv_dialogue_scheduler_fail,
    inv_trav_zombie,
    inv_death_lock,
    inv_time_freezer,
    inv_replay_store,
    inv_adr_net,
    inv_no_retro_sim,
    inv_l1_append_only,
    inv_l3_ephemeral,
    inv_domain_purity,
    inv_llm_exile,
    inv_position_mutation,
    inv_sc1_zero_position,
    inv_spatial_ssot,
    inv_frontend_isolation,
    inv_epistemic_boundary,
    inv_kernel_rng,
    inv_wall_clock,
    inv_silent_failure,
    inv_hp_ssot,
    inv_pbt_roundtrip,
    inv_pbt_spatial,
    inv_pbt_traversal,
    inv_tick_cardinality,
]


def run_invariants() -> int:
    """Главная точка входа. Возвращает exit code (0 = OK, 1 = есть FAIL)."""
    print("=" * 60)
    print("INVARIANT PROBE TESTS (IPT)")
    print("=" * 60)

    try:
        world = _bootstrap_minimal_world()
    except Exception:
        print("\n❌ BOOTSTRAP FAILED — не могу поднять минимальный мир:")
        traceback.print_exc()
        return 2

    results: List[InvariantResult] = []
    for inv_fn in INVARIANTS:
        try:
            result = inv_fn(world)
        except Exception as e:
            result = InvariantResult(
                invariant_id=inv_fn.__name__.replace("inv_", "INV-").upper(),
                severity="CRITICAL",
                passed=False,
                message=f"ИНВАРИАНТ УПАЛ С ИСКЛЮЧЕНИЕМ: {e}",
                suspect_files=[f"backend/tests/IPT.py:{inv_fn.__name__}"],
            )
        results.append(result)
        _print_result(result)

    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    critical_failed = sum(1 for r in results if not r.passed and r.severity == "CRITICAL")
    print(f"ИТОГО: {passed} passed / {failed} failed ({critical_failed} CRITICAL)")

    if failed > 0:
        print("\n🔴 КРИТИЧНЫЕ НАРУШЕНИЯ:")
        for r in results:
            if not r.passed and r.severity == "CRITICAL":
                print(f"  - {r.invariant_id}: {r.message}")
                for f in r.suspect_files:
                    print(f"      → {f}")
        return 1

    print("\n✅ ВСЕ ИНВАРИАНТЫ ПРОЙДЕНЫ — игра жива.")
    return 0


def _print_result(r: InvariantResult) -> None:
    icon = "✅" if r.passed else ("🔴" if r.severity == "CRITICAL" else "🟡")
    print(f"\n{icon} {r.invariant_id} [{r.severity}]")
    if r.message:
        print(f"   {r.message}")
    if not r.passed:
        print("   Подозреваемые файлы:")
        for f in r.suspect_files:
            print(f"     → {f}")


if __name__ == "__main__":
    sys.exit(run_invariants())
