"""
path: backend/tests/IPT.py
Назначение: Invariant Probe Tests — быстрая проверка инвариантов симуляции.
            Запускается LLM-архитектором во время фикса (слой "ДО").
            Не требует LLM-сервера, не требует сети, ~5 секунд.
Зависимости: backend/app/* (минимальный bootstrap)
Основные сущности: run_invariants, INVARIANTS

Запуск: python backend/tests/IPT.py
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
from scripts.llm_server_manager import kill_llama_server, start_llama_server

_llm_ok = start_llama_server()
if not _llm_ok:
    print("⚠️ Внимание: LLM не запущена. Тесты диалогов будут падать.")
atexit.register(kill_llama_server)


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
        return self.last_result.get("world_snapshot", {}) if self.last_result else {}


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
    """INV-DIALOGUE-SCHEDULER-FAIL: TaskScheduler не должен глотать провалы диалогов (L4)."""
    # ADR-O-342: Проверяем, что за время IPT ни одна задача не была тихо провалена.
    scheduler = getattr(world.game_loop, "_task_scheduler", None) or getattr(world.game_loop, "task_scheduler", None)
    if not scheduler:
        return InvariantResult(
            "INV-DIALOGUE-SCHEDULER-FAIL",
            "CRITICAL",
            False,
            "TaskScheduler не найден в GameLoop.",
            ["backend/app/services/game_loop/__init__.py"]
        )
    
    if scheduler.failed_tasks > 0:
        return InvariantResult(
            "INV-DIALOGUE-SCHEDULER-FAIL",
            "CRITICAL",
            False,
            f"TaskScheduler тихо провалил {scheduler.failed_tasks} задач (диалогов). Нарушение L4 (Silent Failure).",
            [
                "backend/app/services/game_loop/task_scheduler.py",
                "backend/app/services/execution/dialogue_executor.py",
                "backend/app/services/npc/decision_hub.py"
            ]
        )
    
    return InvariantResult("INV-DIALOGUE-SCHEDULER-FAIL", "CRITICAL", True, "", [])


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


INVARIANTS: List[Callable] = [
    inv_time_grows,
    inv_tick_grows,
    inv_npc_moves,
    inv_active_traversals_dict,
    inv_npc_has_name,
    inv_dialogue_stm,
    inv_dialogue_scheduler_fail,
    inv_trav_zombie,
    inv_death_lock,
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
