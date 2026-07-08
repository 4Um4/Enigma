"""
path: backend/tests/IPT.py
Назначение: Invariant Probe Tests — быстрая проверка инвариантов симуляции.
            Запускается LLM-архитектором во время фикса (слой "ДО").
            Не требует LLM-сервера, не требует сети, ~5 секунд.
Зависимости: backend/app/* (минимальный bootstrap)
Основные сущности: run_invariants, INVARIANTS

Запуск: python backend/tests/IPT.py
"""

import sys
import time
import traceback
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

# Пропатчим sys.path, чтобы из backend/tests/ запускать без cd
_BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(_BACKEND))


@dataclass
class InvariantResult:
    invariant_id: str
    severity: str       # "CRITICAL" / "WARNING"
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
            return (lp[0], lp[1]) if isinstance(lp, list) else (0, 0)
        return None

    @property
    def last_world_snapshot(self) -> dict:
        return self.last_result.get("world_snapshot", {}) if self.last_result else {}


def _bootstrap_minimal_world() -> TestWorld:
    """Поднимает GameLoop с реальными данными кампании, но изолированной saves_dir."""
    from app.services.game_loop_builder import build_game_loop
    from app.core.config import settings
    
    # Изолируем saves в темп, чтобы не портить реальные сохранения
    temp_saves = tempfile.mkdtemp(prefix="ipt_saves_")
    settings.saves_dir = temp_saves
    
    # data_dir — обычно корень проекта
    project_root = _BACKEND.parent
    data_dir = project_root / "data"
    if not data_dir.exists():
        data_dir = project_root
        
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
        return InvariantResult(
            "INV-TIME-GROW", "CRITICAL", True,
            f"game_time вырос: {initial_time} → {final_time}",
            []
        )
    return InvariantResult(
        "INV-TIME-GROW", "CRITICAL", False,
        f"game_time НЕ растёт: был {initial_time}, стал {final_time} за 3 тика.",
        [
            "backend/app/core/calendar.py:advance()",
            "backend/app/services/tick_orchestrator.py (Фаза 0)",
            "backend/app/services/integration/world_snapshot_builder.py (game_time_seconds проброс)",
        ]
    )


def inv_tick_grows(world: TestWorld) -> InvariantResult:
    """INV-TICK-GROW: tick увеличивается на каждом idle_tick."""
    initial_tick = world.tick
    world.idle_tick()
    world.idle_tick()
    if world.tick == initial_tick + 2:
        return InvariantResult("INV-TICK-GROW", "CRITICAL", True, "", [])
    return InvariantResult(
        "INV-TICK-GROW", "CRITICAL", False,
        f"tick не растёт на 2 за 2 idle_tick: был {initial_tick}, стал {world.tick}.",
        [
            "backend/app/services/tick_orchestrator.py",
            "backend/app/services/game_loop/__init__.py:idle_tick()",
        ]
    )


def inv_npc_moves(world: TestWorld) -> InvariantResult:
    """INV-NPC-MOVE: хотя бы 1 NPC сменил позицию за 5 тиков."""
    positions_before = {nid: world.npc_position(nid) for nid in world.npc_ids}
    for _ in range(5):
        world.idle_tick()
    positions_after = {nid: world.npc_position(nid) for nid in world.npc_ids}
    
    moved = [nid for nid in positions_before 
             if positions_before[nid] != positions_after[nid]]
    if moved:
        return InvariantResult(
            "INV-NPC-MOVE", "CRITICAL", True,
            f"Сдвинулись: {moved}", []
        )
    return InvariantResult(
        "INV-NPC-MOVE", "CRITICAL", False,
        f"За 5 тиков ни один NPC не сдвинулся. RELOCATE не создаёт TraversalState "
        f"или MovementEngine сломан.",
        [
            "backend/app/services/spatial/movement_engine.py",
            "backend/app/services/scene_state_manager.py (RELOCATE handler)",
            "backend/app/services/integration/world_snapshot_builder.py:_extract_active_traversals",
        ]
    )


def inv_active_traversals_dict(world: TestWorld) -> InvariantResult:
    """INV-TRAV-DICT: active_traversals в world_snapshot — это dict, не list."""
    world.idle_tick()
    snapshot = world.last_world_snapshot
    at = snapshot.get("active_traversals")
    
    if isinstance(at, dict):
        return InvariantResult("INV-TRAV-DICT", "CRITICAL", True, "", [])
    return InvariantResult(
        "INV-TRAV-DICT", "CRITICAL", False,
        f"active_traversals имеет тип {type(at).__name__}, ожидался dict. "
        f"Frontend упадёт на isinstance(traversals, list) в game_screen.py.",
        [
            "backend/app/services/integration/world_snapshot_builder.py:_extract_active_traversals",
            "backend/app/domain/snapshot.py:WorldSnapshotDTO.active_traversals",
        ]
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
        "INV-NPC-NAME", "CRITICAL", False,
        f"NPC без name: {missing}. Fuzzy matching в Target Resolution ослепнет "
        f"(Causal Contract v2.0 §2.1 — name обязателен).",
        [
            "backend/app/services/scene_state_manager.py (где формируются npc_positions)",
            "backend/app/services/spatial/player_target_pipeline.py",
            "backend/app/services/npc/npc_loader.py",
        ]
    )


INVARIANTS: List[Callable] = [
    inv_time_grows,
    inv_tick_grows,
    inv_npc_moves,
    inv_active_traversals_dict,
    inv_npc_has_name,
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