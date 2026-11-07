# backend/tests/sandbox/r2_b5_d1_player_spatial_audit.py
"""
R2-B5-D1 PLAYER SPATIAL OBSERVABILITY AUDIT.

Цель: исследовать, где хранится позиция Player, как работает
       SpatialQueryService.distance(), и почему distance("player", npc) не работает.

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations
import os, sys, json, traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import io

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from app.core.config import settings, BASE_DIR
except Exception as e:
    print(f"[FATAL] Cannot import app.core.config: {e}")
    sys.exit(2)

PROJECT_ROOT = _BACKEND.parent

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_b5_d1_player_spatial_audit.txt"


class TeeStream:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            try: s.write(data)
            except: pass
    def flush(self):
        for s in self.streams:
            try: s.flush()
            except: pass


_stdout_buf = io.StringIO()
_orig_stdout = sys.stdout
sys.stdout = TeeStream(_orig_stdout, _stdout_buf)


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _read_lines(path: Path, start: int, end: int) -> List[str]:
    if not path.exists():
        return [f"[file not found: {path}]"]
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        return [f"L{i+1:4d}: {lines[i]}" for i in range(start - 1, min(end, len(lines)))]
    except Exception as e:
        return [f"[read error: {e}]"]


def _find_function_bounds(src: str, func_name: str):
    lines = src.split("\n")
    func_start = None
    for i, line in enumerate(lines):
        if line.startswith("def ") and func_name in line:
            func_start = i
            break
        if line.startswith("    def ") and func_name in line:
            func_start = i
            break
    if func_start is None:
        return None
    indent_of_def = len(lines[func_start]) - len(lines[func_start].lstrip())
    func_end = len(lines)
    for j in range(func_start + 1, len(lines)):
        line = lines[j]
        if line.strip() == "":
            continue
        cur_indent = len(line) - len(line.lstrip())
        if cur_indent <= indent_of_def and (line.lstrip().startswith("def ") or line.lstrip().startswith("class ")):
            func_end = j
            break
    return func_start, func_end


# ============================================================================
# STEP 1: SpatialQueryService — полный код
# ============================================================================
def step1_spatial_query_service() -> None:
    _print_section("STEP 1: SpatialQueryService — полная реализация")

    sqs_path = _BACKEND / "app/services/spatial/spatial_query_service.py"
    if not sqs_path.exists():
        print(f"[file not found: {sqs_path}]")
        return
    src = sqs_path.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")
    print(f"\nFull file ({len(lines)} lines):")
    for i, line in enumerate(lines, 1):
        print(f"L{i:4d}: {line}")

    # Find distance method
    print(f"\n--- Поиск метода distance ---")
    bounds = _find_function_bounds(src, "distance")
    if bounds:
        start, end = bounds
        print(f"\n  distance() at L{start+1}–L{end}:")
        for j in range(start, end):
            print(f"  L{j+1}: {lines[j]}")

    # Find _npc_positions
    print(f"\n--- Поиск _npc_positions ---")
    for i, line in enumerate(lines, 1):
        if "_npc_positions" in line:
            print(f"  L{i}: {line.rstrip()}")

    # Find player references
    print(f"\n--- Поиск 'player' в SpatialQueryService ---")
    for i, line in enumerate(lines, 1):
        if "player" in line.lower():
            print(f"  L{i}: {line.rstrip()}")


# ============================================================================
# STEP 2: Где хранится позиция Player во время runtime
# ============================================================================
def step2_player_position_storage() -> None:
    _print_section("STEP 2: Где хранится позиция Player во время runtime")

    print(f"""
>>> Поиск player position в scene_state:

  В tavern.json есть:
    player_spawn: {{x: 8.205, y: 11.910, z: 0}}

  В runtime scene_state:
    - npc_positions: dict npc_id → {{position, local_position, ...}}
    - player_spawn: может быть в scene_state?
    - player_position: может быть отдельное поле?
""")

    # Search for player position storage in code
    print("\n--- Поиск 'player_position' / 'player_spawn' в коде ---")
    for f in _BACKEND.rglob("*.py"):
        if any(part in {".venv", "node_modules", ".git", "__pycache__"} for part in f.parts):
            continue
        if f == _THIS:
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except:
            continue
        for i, line in enumerate(src.split("\n"), 1):
            if any(kw in line for kw in ["player_position", "player_spawn",
                                          "player_pos", "_player_pos",
                                          "get_player_position", "player_local"]):
                if "test" not in str(f).lower() and "sandbox" not in str(f).lower():
                    rel = f.relative_to(_BACKEND) if f.is_relative_to(_BACKEND) else f
                    print(f"  {rel} L{i}: {line.rstrip()}")

    # Search for player in scene_state
    print("\n--- Поиск player в scene_state context ---")
    for f in _BACKEND.rglob("*.py"):
        if any(part in {".venv", "node_modules", ".git", "__pycache__"} for part in f.parts):
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except:
            continue
        for i, line in enumerate(src.split("\n"), 1):
            if "scene_state" in line and "player" in line.lower() and "position" in line.lower():
                if "test" not in str(f).lower() and "sandbox" not in str(f).lower():
                    rel = f.relative_to(_BACKEND) if f.is_relative_to(_BACKEND) else f
                    print(f"  {rel} L{i}: {line.rstrip()}")


# ============================================================================
# STEP 3: Как ClaimEventSubscriber получает spatial_query
# ============================================================================
def step3_claim_subscriber_spatial_wiring() -> None:
    _print_section("STEP 3: Как ClaimEventSubscriber получает spatial_query_provider")

    ces_path = _BACKEND / "app/services/events/claim_event_subscriber.py"
    if not ces_path.exists():
        return
    src = ces_path.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    # Show __init__
    print("\n--- ClaimEventSubscriber.__init__ ---")
    bounds = _find_function_bounds(src, "__init__")
    if bounds:
        start, end = bounds
        for j in range(start, end):
            print(f"L{j+1}: {lines[j]}")

    # Show on_claim_event spatial section (L244-278)
    print(f"\n--- on_claim_event — spatial membrane section (L244-278) ---")
    for line in _read_lines(ces_path, 244, 278):
        print(f"  {line}")

    # Search for where ClaimEventSubscriber is created
    print(f"\n--- Где ClaimEventSubscriber создаётся (wiring) ---")
    for f in _BACKEND.rglob("*.py"):
        if any(part in {".venv", "node_modules", ".git", "__pycache__"} for part in f.parts):
            continue
        try:
            src2 = f.read_text(encoding="utf-8", errors="replace")
        except:
            continue
        for i, line in enumerate(src2.split("\n"), 1):
            if "ClaimEventSubscriber(" in line or "claim_event_subscriber" in line.lower() and "import" in line.lower():
                if "test" not in str(f).lower() and "sandbox" not in str(f).lower():
                    rel = f.relative_to(_BACKEND) if f.is_relative_to(_BACKEND) else f
                    print(f"  {rel} L{i}: {line.rstrip()}")


# ============================================================================
# STEP 4: Runtime — проверить scene_state на наличие player
# ============================================================================
def step4_runtime_scene_state_check() -> None:
    _print_section("STEP 4: Runtime — проверить scene_state на player position")

    try:
        from app.core.config import settings, BASE_DIR
        from app.services.game_loop_builder import build_game_loop
        import tempfile

        saves_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d1_"))
        settings.saves_dir = str(saves_dir)
        settings.environment = "development"

        loop = build_game_loop(data_dir=Path(settings.data_dir))
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        print(f"\n--- scene_state keys ---")
        for k in sorted(scene.keys()):
            v = scene[k]
            if isinstance(v, dict):
                print(f"  {k}: dict with {len(v)} keys")
            elif isinstance(v, list):
                print(f"  {k}: list with {len(v)} items")
            else:
                print(f"  {k}: {type(v).__name__} = {str(v)[:80]}")

        # Check npc_positions
        npc_positions = scene.get("npc_positions", {})
        print(f"\n--- npc_positions ---")
        print(f"  Keys: {list(npc_positions.keys())}")
        for nid, pos_data in npc_positions.items():
            print(f"  {nid}: {pos_data}")

        # Check player_spawn
        player_spawn = scene.get("player_spawn")
        print(f"\n--- player_spawn ---")
        print(f"  {player_spawn}")

        # Check if player is in npc_positions
        print(f"\n--- player in npc_positions? ---")
        print(f"  'player' in npc_positions: {'player' in npc_positions}")

        # Check for player_position field
        player_pos = scene.get("player_position")
        print(f"\n--- player_position field ---")
        print(f"  {player_pos}")

        # Try to get SpatialQueryService
        print(f"\n--- SpatialQueryService from loop ---")
        spatial_svc = None
        for attr in ("spatial_service", "_spatial_service", "spatial"):
            if hasattr(loop, attr):
                spatial_svc = getattr(loop, attr)
                print(f"  loop.{attr}: {spatial_svc}")
                break

        if spatial_svc is None:
            sm = loop.scene_manager
            for attr in ("spatial_service", "_spatial_service"):
                if hasattr(sm, attr):
                    spatial_svc = getattr(sm, attr)
                    print(f"  scene_manager.{attr}: {spatial_svc}")
                    break

        if spatial_svc:
            # Try distance("player", "maid_lusya")
            print(f"\n--- Testing distance('player', 'maid_lusya') ---")
            try:
                d = spatial_svc.distance("player", "maid_lusya")
                print(f"  distance: {d}")
            except Exception as e:
                print(f"  ERROR: {e}")

            # Try distance("maid_lusya", "tavern_keeper_tornin")
            print(f"\n--- Testing distance('maid_lusya', 'tavern_keeper_tornin') ---")
            try:
                d = spatial_svc.distance("maid_lusya", "tavern_keeper_tornin")
                print(f"  distance: {d}")
            except Exception as e:
                print(f"  ERROR: {e}")

            # Check _npc_positions in spatial_svc
            _npc_pos = getattr(spatial_svc, "_npc_positions", {})
            print(f"\n--- spatial_svc._npc_positions ---")
            print(f"  Keys: {list(_npc_pos.keys()) if _npc_pos else 'empty'}")
            for nid, pos in (_npc_pos or {}).items():
                print(f"  {nid}: {pos}")

            # Check if there's a player position method
            for method_name in ("get_player_position", "get_player_pos", "player_position", "get_position"):
                if hasattr(spatial_svc, method_name):
                    print(f"\n  spatial_svc.{method_name} exists")
                    try:
                        result = getattr(spatial_svc, method_name)()
                        print(f"  Result: {result}")
                    except Exception as e:
                        print(f"  Called: ERROR {e}")
        else:
            print(f"  SpatialQueryService not found")

        # Cleanup
        try:
            ts = loop._get_task_scheduler()
            if hasattr(ts, "_executor_pool"):
                ts._executor_pool.shutdown(wait=False, cancel_futures=True)
        except:
            pass
        del loop
        import gc; gc.collect()
        import shutil
        shutil.rmtree(saves_dir, ignore_errors=True)

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()


# ============================================================================
# STEP 5: Как B4 обрабатывал это (test harness vs production)
# ============================================================================
def step5_b4_harness_comparison() -> None:
    _print_section("STEP 5: B4 harness — как обрабатывал player position")

    print("""
>>> B4 использовал test harness (test_butterfly_b4_verified_belief.py).
    Нужно проверить:
    1. Использовал ли harness mock spatial_query?
    2. Добавлял ли harness player в npc_positions?
    3. Или использовал другой механизм?
""")

    # Search for B4 test harness
    b4_path = _BACKEND / "tests/gameplay/test_butterfly_b4_verified_belief.py"
    if b4_path.exists():
        src = b4_path.read_text(encoding="utf-8", errors="replace")
        lines = src.split("\n")
        print(f"--- B4 test file ({len(lines)} lines) — player/spatial references ---")
        for i, line in enumerate(lines, 1):
            if any(kw in line.lower() for kw in ["player", "spatial", "npc_positions",
                                                   "distance", "claim_subscriber",
                                                   "hearing", "perceive", "observe"]):
                print(f"  L{i}: {line.rstrip()}")
    else:
        print(f"[B4 test file not found: {b4_path}]")

    # Also check harness.py
    harness_path = _BACKEND / "tests/gameplay/harness.py"
    if harness_path.exists():
        src = harness_path.read_text(encoding="utf-8", errors="replace")
        lines = src.split("\n")
        print(f"\n--- harness.py — player/spatial references ---")
        for i, line in enumerate(lines, 1):
            if any(kw in line.lower() for kw in ["player", "spatial", "npc_positions",
                                                   "distance", "claim_subscriber",
                                                   "hearing", "perceive"]):
                print(f"  L{i}: {line.rstrip()}")


# ============================================================================
# STEP 6: ИТОГ + минимальный fix proposal
# ============================================================================
def step6_fix_proposal() -> None:
    _print_section("STEP 6: ИТОГ + минимальный fix proposal")

    print(f"""
=============================================================================
ТОЧНАЯ ПРИЧИНА ДЕФЕКТА B5-D1
=============================================================================

  ClaimEventSubscriber.on_claim_event (L244-278) использует spatial_query
  для фильтрации слушателей:
    _origin_id = event.source  ← "player" для PLAYER_INSULTS
    _sq.distance(_origin_id, _nid)  ← distance("player", "maid_lusya")

  SpatialQueryService.distance("player", "maid_lusya"):
    Ищет "player" в _npc_positions → НЕ НАХОДИТ
    → возвращает inf или падает
    → PerceptualKernel.can_observe(event, inf, ...) → False
    → listener НЕ добавляется
    → BeliefRevisionEngine НЕ вызывается для maid_lusya

  Причина: player не является NPC, его позиция не в _npc_positions.
           Player position хранится в scene_state["player_spawn"] или
           в отдельном поле.

=============================================================================
МИНИМАЛЬНЫЙ FIX
=============================================================================

  Вариант A: SpatialQueryService.distance() — fallback на player_spawn

  В методе distance(), если id не найден в _npc_positions:
    - Проверить, является ли id "player"
    - Если да — использовать player_spawn coords из scene_state
    - Вычислить distance от player_spawn до NPC

  Реализация:
    В SpatialQueryService добавить поле _player_position (обновляется
    из scene_state при инициализации).
    В distance(): если id == "player" → использовать _player_position.

  Вариант B: ClaimEventSubscriber — fallback на player_spawn

  В on_claim_event, если _origin_id == "player" и _sq.distance падает:
    - Получить player_spawn из scene_state
    - Вычислить distance вручную
    - Использовать PerceptualKernel.can_observe

  Вариант A предпочтительнее — централизованное решение в SpatialQueryService.

  Не включает player в _npc_positions (не нарушает контракт).
  Использует существующий источник coords (player_spawn).
  Не меняет PerceptualKernel.
  Не меняет ClaimEventSubscriber.

  Нужен доступ к scene_state из SpatialQueryService, или
  player_spawn должен быть передан в SpatialQueryService при инициализации.
""")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D1 PLAYER SPATIAL OBSERVABILITY AUDIT")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)

    try: step1_spatial_query_service()
    except Exception as e: print(f"[step1 error: {e}]"); traceback.print_exc()

    try: step2_player_position_storage()
    except Exception as e: print(f"[step2 error: {e}]"); traceback.print_exc()

    try: step3_claim_subscriber_spatial_wiring()
    except Exception as e: print(f"[step3 error: {e}]"); traceback.print_exc()

    try: step4_runtime_scene_state_check()
    except Exception as e: print(f"[step4 error: {e}]"); traceback.print_exc()

    try: step5_b4_harness_comparison()
    except Exception as e: print(f"[step5 error: {e}]"); traceback.print_exc()

    try: step6_fix_proposal()
    except Exception as e: print(f"[step6 error: {e}]"); traceback.print_exc()

    try:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(_stdout_buf.getvalue())
        size = OUT_FILE.stat().st_size
        print(f"\n>>> Output written to: {OUT_FILE}")
        print(f">>> File size: {size} bytes ({size / 1024:.1f} KB)")
    except Exception as e:
        print(f"\n[ERROR writing output file: {e}]")
        traceback.print_exc()

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        rc = 1
    finally:
        sys.stdout = _orig_stdout
    sys.exit(rc)
