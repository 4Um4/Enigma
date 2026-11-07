# backend/tests/sandbox/r2_b5_d1_perception_forensic.py
"""
R2-B5-D1 SPATIAL PERCEPTION FORENSIC PROBE.

Цель: установить точную причину, по которой maid_lusya не попадает в listeners
       при обработке PLAYER_INSULTS.

4 проверки:
  1. PerceptualKernel.can_observe() — полная реализация
  2. Runtime distance — фактические значения в момент обработки
  3. Runtime provider — _get_spatial_query, _sq, can_observe
  4. Все NPC — distance, can_observe, listeners

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations
import os, sys, json, traceback, logging, math, copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
import io
from unittest.mock import patch

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
OUT_FILE = OUT_FILE_DIR / "r2_b5_d1_perception_forensic.txt"


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
# ПРОВЕРКА 1: PerceptualKernel.can_observe() — полная реализация
# ============================================================================
def check1_perceptual_kernel() -> Dict[str, Any]:
    _print_section("ПРОВЕРКА 1: PerceptualKernel.can_observe() — полная реализация")
    result = {"check": "1", "pass": False}

    # Search for PerceptualKernel
    pk_path = None
    for f in _BACKEND.rglob("*.py"):
        if any(part in {".venv", "node_modules", ".git", "__pycache__"} for part in f.parts):
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except:
            continue
        if "class PerceptualKernel" in src or "def can_observe" in src:
            pk_path = f
            break

    if pk_path is None:
        print("[PerceptualKernel not found]")
        result["error"] = "PerceptualKernel not found"
        return result

    print(f"\n  Found at: {pk_path.relative_to(_BACKEND)}")
    src = pk_path.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    # Print full file if small, otherwise just the class
    if len(lines) < 300:
        print(f"\n--- Full file ({len(lines)} lines) ---")
        for i, line in enumerate(lines, 1):
            print(f"L{i:4d}: {line}")
    else:
        # Print can_observe method + surrounding context
        bounds = _find_function_bounds(src, "can_observe")
        if bounds:
            start, end = bounds
            print(f"\n--- can_observe (L{start+1}–L{end}) ---")
            for j in range(start, end):
                print(f"L{j+1}: {lines[j]}")
        else:
            print("[can_observe not found in file]")
            # Print all method definitions
            for i, line in enumerate(lines, 1):
                if "def " in line:
                    print(f"  L{i}: {line.rstrip()}")

    # Search for HEARING_RADIUS in this file
    print(f"\n--- HEARING_RADIUS references ---")
    for i, line in enumerate(lines, 1):
        if "HEARING_RADIUS" in line or "hearing_radius" in line.lower():
            print(f"  L{i}: {line.rstrip()}")

    # Search for radius usage
    print(f"\n--- radius references ---")
    for i, line in enumerate(lines, 1):
        if "radius" in line.lower() and ("event" in line.lower() or "payload" in line.lower() or "self" in line.lower()):
            print(f"  L{i}: {line.rstrip()}")

    result["pass"] = True
    return result


# ============================================================================
# ПРОВЕРКА 2: Runtime distance — фактические значения
# ============================================================================
def check2_runtime_distance() -> Dict[str, Any]:
    _print_section("ПРОВЕРКА 2: Runtime distance — фактические значения в момент PLAYER_INSULTS")
    result = {"check": "2", "pass": False}

    try:
        from app.core.config import settings, BASE_DIR
        from app.services.game_loop_builder import build_game_loop
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO
        import tempfile

        saves_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d1_forensic_"))
        settings.saves_dir = str(saves_dir)
        settings.environment = "development"

        loop = build_game_loop(data_dir=Path(settings.data_dir))
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        # Get npc_positions BEFORE any ticks
        npc_positions = scene.get("npc_positions", {})

        print(f"\n--- Runtime npc_positions (from scene_state) ---")
        print(f"  npc_positions keys: {list(npc_positions.keys())}")
        for nid, pos_data in npc_positions.items():
            lp = pos_data.get("local_position", {})
            x = lp.get("x", "?") if isinstance(lp, dict) else "?"
            y = lp.get("y", "?") if isinstance(lp, dict) else "?"
            print(f"  {nid}: position={pos_data.get('position')}, local=({x}, {y})")

        # Specifically check player
        player_pos = npc_positions.get("player", {})
        player_lp = player_pos.get("local_position", {})
        px = player_lp.get("x", 0) if isinstance(player_lp, dict) else 0
        py = player_lp.get("y", 0) if isinstance(player_lp, dict) else 0
        print(f"\n--- Player coords ---")
        print(f"  player: local_position=({px}, {py})")
        print(f"  player position (node): {player_pos.get('position')}")

        # Specifically check maid_lusya
        lusya_pos = npc_positions.get("maid_lusya", {})
        lusya_lp = lusya_pos.get("local_position", {})
        lx = lusya_lp.get("x", 0) if isinstance(lusya_lp, dict) else 0
        ly = lusya_lp.get("y", 0) if isinstance(lusya_lp, dict) else 0
        print(f"\n--- maid_lusya coords ---")
        print(f"  maid_lusya: local_position=({lx}, {ly})")
        print(f"  maid_lusya position (node): {lusya_pos.get('position')}")

        # Compute distance
        dist = math.hypot(float(px) - float(lx), float(py) - float(ly))
        print(f"\n--- Distance player ↔ maid_lusya ---")
        print(f"  dx = {px} - {lx} = {float(px) - float(lx):.6f}")
        print(f"  dy = {py} - {ly} = {float(py) - float(ly):.6f}")
        print(f"  distance = hypot({float(px) - float(lx):.6f}, {float(py) - float(ly):.6f}) = {dist:.6f}m")
        print(f"  HEARING_RADIUS = 10.0")
        print(f"  distance <= HEARING_RADIUS: {dist <= 10.0}")
        print(f"  distance <= event.radius (999.0): {dist <= 999.0}")

        # Get SpatialQueryService
        print(f"\n--- SpatialQueryService ---")
        spatial_svc = None
        for attr in ("spatial_service", "_spatial_service"):
            if hasattr(loop, attr):
                spatial_svc = getattr(loop, attr)
                break
        if spatial_svc is None:
            sm = loop.scene_manager
            for attr in ("spatial_service", "_spatial_service"):
                if hasattr(sm, attr):
                    spatial_svc = getattr(sm, attr)
                    break

        if spatial_svc:
            print(f"  Found: {type(spatial_svc).__name__}")

            # Try distance
            print(f"\n--- spatial_svc.distance('player', 'maid_lusya') ---")
            try:
                d = spatial_svc.distance("player", "maid_lusya")
                print(f"  Result: {d}")
                print(f"  Type: {type(d).__name__}")
            except Exception as e:
                print(f"  ERROR: {e}")
                traceback.print_exc()

            # Check _npc_positions in spatial_svc
            _npc_pos_svc = getattr(spatial_svc, "_npc_positions", {})
            print(f"\n--- spatial_svc._npc_positions ---")
            print(f"  Keys: {list(_npc_pos_svc.keys()) if _npc_pos_svc else 'empty'}")
            if _npc_pos_svc:
                for nid, pos in _npc_pos_svc.items():
                    print(f"  {nid}: {pos}")

            # Check if player is in _npc_positions
            print(f"\n  'player' in _npc_positions: {'player' in _npc_pos_svc}")
        else:
            print(f"  NOT FOUND")

        # Now try to actually publish PLAYER_INSULTS and spy on ClaimEventSubscriber
        print(f"\n--- Publishing PLAYER_INSULTS and spying on on_claim_event ---")

        # Monkey-patch ClaimEventSubscriber.on_claim_event to capture runtime state
        try:
            from app.services.events.claim_event_subscriber import ClaimEventSubscriber
        except:
            ClaimEventSubscriber = None

        captured_state: Dict[str, Any] = {}

        if ClaimEventSubscriber:
            # Find the subscriber instance in loop
            claim_sub = None
            tick_orch = loop._tick_orch
            # Search for claim_subscriber in tick_orch or event_bus
            for attr_name in dir(tick_orch):
                if "claim" in attr_name.lower():
                    val = getattr(tick_orch, attr_name, None)
                    if isinstance(val, ClaimEventSubscriber):
                        claim_sub = val
                        print(f"  Found ClaimEventSubscriber at tick_orch.{attr_name}")
                        break

            if claim_sub:
                # Monkey-patch on_claim_event
                orig_on_claim = claim_sub.on_claim_event

                def _spy_on_claim(event):
                    payload = getattr(event, "payload", {})
                    prop_data = payload.get("proposition", {})

                    captured_state["event_source"] = getattr(event, "source", "?")
                    captured_state["event_type"] = str(getattr(event, "type", "?"))
                    captured_state["payload_action_type"] = payload.get("action_type")
                    captured_state["payload_target_id"] = payload.get("target_id")
                    captured_state["payload_radius"] = payload.get("radius")
                    captured_state["proposition"] = prop_data

                    # Get spatial query
                    sq_provider = getattr(claim_sub, "_get_spatial_query", None)
                    captured_state["has_spatial_provider"] = sq_provider is not None

                    if sq_provider:
                        sq = sq_provider() if callable(sq_provider) else None
                        captured_state["has_sq"] = sq is not None

                        if sq:
                            _npc_pos = getattr(sq, "_npc_positions", {})
                            captured_state["sq_npc_positions_keys"] = list(_npc_pos.keys()) if _npc_pos else []

                            # Check player position
                            player_data = _npc_pos.get("player", {})
                            captured_state["sq_player_data"] = player_data

                            # Compute distance for each NPC
                            _origin_id = getattr(event, "source", "player")
                            captured_state["origin_id"] = _origin_id

                            distances = {}
                            for nid in _npc_pos.keys():
                                if nid == _origin_id:
                                    continue
                                try:
                                    d = sq.distance(_origin_id, nid)
                                    distances[nid] = d
                                except Exception as e:
                                    distances[nid] = f"ERROR: {e}"
                            captured_state["distances"] = distances

                            # Check can_observe for each NPC
                            try:
                                from app.models.npc_state import PerceptualKernel
                            except:
                                PerceptualKernel = None

                            if PerceptualKernel:
                                can_observe_results = {}
                                for nid, d in distances.items():
                                    if isinstance(d, (int, float)):
                                        try:
                                            result = PerceptualKernel.can_observe(
                                                event, d, nid, payload.get("target_id"))
                                            can_observe_results[nid] = {"distance": d, "can_observe": result}
                                        except Exception as e:
                                            can_observe_results[nid] = {"distance": d, "error": str(e)}
                                    else:
                                        can_observe_results[nid] = {"distance": d, "can_observe": "N/A (distance error)"}
                                captured_state["can_observe_results"] = can_observe_results

                    # Call original
                    return orig_on_claim(event)

                claim_sub.on_claim_event = _spy_on_claim
                print(f"  Spy attached to ClaimEventSubscriber.on_claim_event")
            else:
                print(f"  ClaimEventSubscriber instance not found in tick_orch")

        # Clear event bus
        try:
            get_event_bus().clear()
        except:
            pass

        # Publish PLAYER_INSULTS
        payload = {
            "action_type": "player_insults", "target_id": "tavern_keeper_tornin",
            "content": "оскорбление", "event_tick": 1, "visibility": "public",
            "radius": 999.0, "location": "tavern", "campaign_id": "Open_road",
            "raw_input": "оскорбление",
        }
        evt = EventDTO.create(event_type=EventType.PLAYER_INSULTS, source="player",
                              payload=payload, persistence_level="working")
        get_event_bus().publish(evt)
        print(f"\n  PLAYER_INSULTS published")

        # Print captured state
        print(f"\n--- Captured state from on_claim_event spy ---")
        for k, v in captured_state.items():
            if k in ("distances", "can_observe_results"):
                print(f"  {k}:")
                if isinstance(v, dict):
                    for nid, val in v.items():
                        print(f"    {nid}: {val}")
            else:
                print(f"  {k}: {v}")

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

        result["pass"] = True
        result["captured"] = captured_state
        return result

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()
        result["error"] = str(e)
        return result


# ============================================================================
# ПРОВЕРКА 3: Runtime provider — _get_spatial_query
# ============================================================================
def check3_runtime_provider(captured: Dict) -> Dict[str, Any]:
    _print_section("ПРОВЕРКА 3: Runtime provider — _get_spatial_query, _sq, can_observe")
    result = {"check": "3", "pass": False}

    print(f"""
--- Данные из captured_state ---

  has_spatial_provider: {captured.get('has_spatial_provider', 'N/A')}
  has_sq: {captured.get('has_sq', 'N/A')}
  sq_npc_positions_keys: {captured.get('sq_npc_positions_keys', 'N/A')}
  origin_id: {captured.get('origin_id', 'N/A')}

  sq_player_data: {captured.get('sq_player_data', 'N/A')}

--- Distances from player to each NPC ---
""")
    distances = captured.get("distances", {})
    for nid, d in distances.items():
        print(f"  {nid}: {d}")

    print(f"""
--- can_observe results ---
""")
    can_observe = captured.get("can_observe_results", {})
    for nid, res in can_observe.items():
        print(f"  {nid}: {res}")

    result["pass"] = True
    return result


# ============================================================================
# ПРОВЕРКА 4: Все NPC — distance, can_observe, listeners
# ============================================================================
def check4_all_npcs(captured: Dict) -> Dict[str, Any]:
    _print_section("ПРОВЕРКА 4: Все NPC — distance, can_observe, listeners")
    result = {"check": "4", "pass": False}

    distances = captured.get("distances", {})
    can_observe = captured.get("can_observe_results", {})

    print(f"\n{'NPC':<25} {'distance':>10} {'can_observe':>12} {'HEARING_RADIUS':>15} {'event.radius':>15} {'in_listeners':>15}")
    print("-" * 92)

    HEARING_RADIUS = 10.0
    event_radius = captured.get("payload_radius", 999.0)

    for nid in sorted(set(list(distances.keys()) + list(can_observe.keys()))):
        d = distances.get(nid, "?")
        co = can_observe.get(nid, {})
        co_result = co.get("can_observe", "?") if isinstance(co, dict) else "?"
        co_dist = co.get("distance", "?") if isinstance(co, dict) else "?"

        in_listeners = co_result if isinstance(co_result, bool) else "?"

        print(f"  {nid:<25} {str(d):>10} {str(co_result):>12} {HEARING_RADIUS:>15.1f} {event_radius:>15.1f} {str(in_listeners):>15}")

    print(f"""
--- Итог ---

  event.radius = {event_radius}
  HEARING_RADIUS = {HEARING_RADIUS}

  Если can_observe использует event.radius (999.0):
    → ВСЕ NPC в радиусе → ВСЕ слушатели
    → maid_lusya ДОЛЖНА быть в listeners

  Если can_observe использует HEARING_RADIUS (10.0):
    → Только NPC в радиусе 10m → maid_lusya может НЕ быть в listeners
    → зависит от фактического distance
""")

    result["pass"] = True
    return result


# ============================================================================
# ИТОГ
# ============================================================================
def final_verdict(captured: Dict) -> None:
    _print_section("ИТОГ — однозначный вывод")

    distances = captured.get("distances", {})
    can_observe = captured.get("can_observe_results", {})

    # Find maid_lusya specifically
    ml_dist = distances.get("maid_lusya", "?")
    ml_co = can_observe.get("maid_lusya", {})
    ml_co_result = ml_co.get("can_observe", "?") if isinstance(ml_co, dict) else "?"
    ml_co_dist = ml_co.get("distance", "?") if isinstance(ml_co, dict) else "?"

    has_sq = captured.get("has_sq", False)
    has_provider = captured.get("has_spatial_provider", False)

    print(f"""
=============================================================================
ОДНОЗНАЧНЫЙ ВЫВОД
=============================================================================

1. КАКОЙ ИМЕННО ФИЛЬТР ИСКЛЮЧАЕТ ЛЮСЮ:
""")

    if not has_provider:
        print(f"   → _get_spatial_query = None (provider не существует)")
        print(f"   → on_claim_event fallback: target_id добавляется в listeners")
        print(f"   → maid_lusya НЕ target_id (target = tavern_keeper_tornin)")
        print(f"   → maid_lusya НЕ в listeners")
        print(f"   → Причина: spatial_query_provider не настроен в production")
    elif not has_sq:
        print(f"   → _get_spatial_query существует, но возвращает None")
        print(f"   → on_claim_event fallback: target_id добавляется в listeners")
        print(f"   → maid_lusya НЕ в listeners")
    elif isinstance(ml_co_result, bool) and not ml_co_result:
        print(f"   → PerceptualKernel.can_observe вернул False для maid_lusya")
        print(f"   → distance = {ml_co_dist}")
        if isinstance(ml_dist, (int, float)):
            if ml_dist > 10.0:
                print(f"   → distance {ml_dist:.4f}m > HEARING_RADIUS 10.0m → НЕ в радиусе")
                print(f"   → event.radius = {captured.get('payload_radius', '?')}, но can_observe использует HEARING_RADIUS")
            else:
                print(f"   → distance {ml_dist:.4f}m <= HEARING_RADIUS 10.0m, но can_observe всё равно False")
                print(f"   → Другая причина в can_observe (visibility, perception tier, etc.)")
    elif isinstance(ml_co_result, bool) and ml_co_result:
        print(f"   → PerceptualKernel.can_observe вернул True для maid_lusya")
        print(f"   → maid_lusya ДОЛЖНА быть в listeners")
        print(f"   → Если она не в listeners — проблема в другом месте (не в can_observe)")
    else:
        print(f"   → can_observe результат неизвестен: {ml_co_result}")
        print(f"   → distance = {ml_dist}")

    print(f"""
2. ПОЧЕМУ event.radius=999.0 НЕ ОБЕСПЕЧИВАЕТ ВОСПРИЯТИЕ:
""")

    event_radius = captured.get("payload_radius", "?")
    if isinstance(ml_dist, (int, float)) and ml_dist > 10.0:
        print(f"   → event.radius = {event_radius}, но can_observe проверяет HEARING_RADIUS = 10.0")
        print(f"   → event.radius используется для can_observe event.radius parameter,")
        print(f"     но PerceptualKernel.can_observe может использовать оба:")
        print(f"       if dist <= min(event.radius, HEARING_RADIUS): can_observe = True")
        print(f"     → Если так, то 999.0 не помогает, т.к. HEARING_RADIUS = 10.0 ограничивает")
    else:
        print(f"   → Нужно проверить PerceptualKernel.can_observe код (Проверка 1)")

    print(f"""
3. ЯВЛЯЕТСЯ ЛИ ПОВЕДЕНИЕ ОЖИДАЕМЫМ ИГРОВЫМ ПРАВИЛОМ ИЛИ ДЕФЕКТОМ:
""")

    if isinstance(ml_dist, (int, float)) and ml_dist > 10.0:
        print(f"   → Поведение ВЫГЛЯДИТ как игровое правило: NPC слышит только в радиусе 10м")
        print(f"   → Player стоит у entrance (8.2, 11.9), maid_lusya у fireplace (8.0, 1.8)")
        print(f"   → Расстояние ~10.1m — чуть больше 10.0m порога")
        print(f"   → НО: PLAYER_INSULTS — это публичное событие (visibility='public', radius=999.0)")
        print(f"   → Если player кричит оскорбление — ВСЕ в таверне должны слышать")
        print(f"   → HEARING_RADIUS = 10.0 — это радиус обычной речи, не крика")
        print(f"   → ВОЗМОЖНЫЙ ДЕФЕКТ: can_observe не различает обычную речь и публичные события")
    else:
        print(f"   → Нужно больше данных (см. Проверку 1 и 2)")

    print(f"""
4. МИНИМАЛЬНОЕ ИЗМЕНЕНИЕ (если дефект существует):
""")

    if isinstance(ml_dist, (int, float)) and ml_dist > 10.0:
        print(f"   → В PerceptualKernel.can_observe:")
        print(f"     Если event имеет radius > HEARING_RADIUS (публичное событие):")
        print(f"       использовать event.radius вместо HEARING_RADIUS")
        print(f"     Это позволит публичным событиям (PLAYER_INSULTS с radius=999.0)")
        print(f"     быть услышанными всеми NPC в локации.")
    else:
        print(f"   → Зависит от результатов Проверки 1 (PerceptualKernel код)")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D1 SPATIAL PERCEPTION FORENSIC PROBE")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)

    captured: Dict[str, Any] = {}

    try:
        check1_perceptual_kernel()
    except Exception as e:
        print(f"[check1 error: {e}]")
        traceback.print_exc()

    try:
        result2 = check2_runtime_distance()
        captured = result2.get("captured", {})
    except Exception as e:
        print(f"[check2 error: {e}]")
        traceback.print_exc()

    try:
        check3_runtime_provider(captured)
    except Exception as e:
        print(f"[check3 error: {e}]")
        traceback.print_exc()

    try:
        check4_all_npcs(captured)
    except Exception as e:
        print(f"[check4 error: {e}]")
        traceback.print_exc()

    try:
        final_verdict(captured)
    except Exception as e:
        print(f"[final error: {e}]")
        traceback.print_exc()

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
