# backend/tests/sandbox/r2_b5_d1_wiring_forensics.py
"""
R2-B5-D1 PRODUCTION WIRING FORENSICS.

Цель: установить, почему ClaimEventSubscriber в production не использует
       SpatialQueryService при обработке PLAYER_INSULTS.

Этапы:
  A. Найти реальную регистрацию ClaimEventSubscriber
  B. Проверить реальный экземпляр (_get_spatial_query)
  C. Проследить production composition (build_game_loop)
  D. Подтвердить ветку listeners (runtime trace)
  E. Семантика радиуса (PerceptualKernel.can_observe)

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations
import os, sys, json, traceback, logging, math, copy, types
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
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
OUT_FILE = OUT_FILE_DIR / "r2_b5_d1_wiring_forensics.txt"


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


def _grep_in_dir(directory: Path, patterns: List[str], file_exts: List[str] = (".py",)) -> List[Tuple[Path, int, str]]:
    out: List[Tuple[Path, int, str]] = []
    if not directory.exists():
        return out
    for f in directory.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in file_exts:
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except:
            continue
        for i, line in enumerate(src.split("\n"), 1):
            for pat in patterns:
                if pat in line:
                    out.append((f, i, line.rstrip()))
                    break
    return out


# ============================================================================
# ЭТАП A: Найти реальную регистрацию ClaimEventSubscriber
# ============================================================================
def stage_a_find_registration() -> Dict[str, Any]:
    _print_section("ЭТАП A: Найти реальную регистрацию ClaimEventSubscriber")
    result = {"stage": "A", "pass": False}

    # 1. All places where ClaimEventSubscriber is created
    print("\n--- A.1: Все места создания ClaimEventSubscriber ---")
    results = _grep_in_dir(_BACKEND, ["ClaimEventSubscriber("])
    for path, ln, line in results:
        rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
        print(f"  {rel} L{ln}: {line}")

    # 2. All places where its handlers are registered in EventBus
    print("\n--- A.2: Все регистрации обработчиков в EventBus ---")
    results2 = _grep_in_dir(_BACKEND, ["subscribe.*CLAIM", "subscribe.*NPC_SPOKE", "subscribe.*PLAYER_INSULT",
                                        "subscribe.*COMMUNICATION_CLAIM", "subscribe.*PLAYER_SPOKE",
                                        "claim_subscriber", "on_claim_event", "on_npc_spoke", "on_player_spoke"])
    for path, ln, line in results2:
        if "test" not in str(path).lower() and "sandbox" not in str(path).lower():
            rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
            print(f"  {rel} L{ln}: {line}")

    # 3. Read context around each creation site
    print("\n--- A.3: Контекст создания ClaimEventSubscriber ---")
    for path, ln, line in results:
        if "test" in str(path).lower() or "sandbox" in str(path).lower():
            continue
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
            lines = src.split("\n")
            start = max(0, ln - 10)
            end = min(len(lines), ln + 15)
            print(f"\n  File: {path.relative_to(_BACKEND)}")
            for j in range(start, end):
                marker = " >>>" if j + 1 == ln else "    "
                print(f"  {marker} L{j+1}: {lines[j]}")
        except:
            pass

    result["pass"] = True
    return result


# ============================================================================
# ЭТАП B: Проверить реальный экземпляр
# ============================================================================
def stage_b_check_instance(loop) -> Dict[str, Any]:
    _print_section("ЭТАП B: Проверить реальный экземпляр ClaimEventSubscriber")
    result = {"stage": "B", "pass": False}

    try:
        from app.services.events.event_bus import get_event_bus
        from app.services.events.claim_event_subscriber import ClaimEventSubscriber

        bus = get_event_bus()

        # Search for ClaimEventSubscriber instances in event bus subscribers
        print("\n--- B.1: Поиск ClaimEventSubscriber в EventBus subscribers ---")

        # EventBus may store subscribers in different ways
        subscriber_attrs = ["_subscribers", "_handlers", "_callbacks", "_listeners", "subscribers"]
        found_subscribers = []

        for attr in subscriber_attrs:
            if hasattr(bus, attr):
                subs = getattr(bus, attr)
                print(f"  bus.{attr}: type={type(subs).__name__}, keys/len={len(subs) if hasattr(subs, '__len__') else '?'}")
                if isinstance(subs, dict):
                    for event_type, callbacks in subs.items():
                        print(f"    {event_type}: {len(callbacks) if hasattr(callbacks, '__len__') else 1} callbacks")
                        if hasattr(callbacks, '__iter__'):
                            for cb in callbacks:
                                cb_obj = getattr(cb, '__self__', None)
                                if cb_obj and isinstance(cb_obj, ClaimEventSubscriber):
                                    found_subscribers.append(cb_obj)
                                    print(f"      → ClaimEventSubscriber found! id={id(cb_obj)}")
                elif isinstance(subs, list):
                    for cb in subs:
                        cb_obj = getattr(cb, '__self__', None)
                        if cb_obj and isinstance(cb_obj, ClaimEventSubscriber):
                            found_subscribers.append(cb_obj)
                            print(f"  → ClaimEventSubscriber found! id={id(cb_obj)}")

        # Also search in loop attributes
        print("\n--- B.2: Поиск в атрибутах game_loop ---")
        for attr_name in sorted(dir(loop)):
            if attr_name.startswith("__"):
                continue
            try:
                val = getattr(loop, attr_name)
                if isinstance(val, ClaimEventSubscriber):
                    found_subscribers.append(val)
                    print(f"  loop.{attr_name}: ClaimEventSubscriber! id={id(val)}")
                elif hasattr(val, '__dict__'):
                    for k2, v2 in vars(val).items():
                        if isinstance(v2, ClaimEventSubscriber):
                            found_subscribers.append(v2)
                            print(f"  loop.{attr_name}.{k2}: ClaimEventSubscriber! id={id(v2)}")
            except:
                pass

        # Search in tick_orch
        print("\n--- B.3: Поиск в tick_orch ---")
        tick_orch = getattr(loop, "_tick_orch", None)
        if tick_orch:
            for attr_name in sorted(dir(tick_orch)):
                if attr_name.startswith("__"):
                    continue
                try:
                    val = getattr(tick_orch, attr_name)
                    if isinstance(val, ClaimEventSubscriber):
                        found_subscribers.append(val)
                        print(f"  tick_orch.{attr_name}: ClaimEventSubscriber! id={id(val)}")
                except:
                    pass

        # Also check ServiceFactory
        print("\n--- B.4: Поиск в ServiceFactory ---")
        svc_factory = getattr(loop, "_svc", None)
        if svc_factory:
            for attr_name in sorted(dir(svc_factory)):
                if attr_name.startswith("__"):
                    continue
                try:
                    val = getattr(svc_factory, attr_name)
                    if isinstance(val, ClaimEventSubscriber):
                        found_subscribers.append(val)
                        print(f"  _svc.{attr_name}: ClaimEventSubscriber! id={id(val)}")
                    elif hasattr(val, '__dict__'):
                        for k2, v2 in vars(val).items():
                            if isinstance(v2, ClaimEventSubscriber):
                                found_subscribers.append(v2)
                                print(f"  _svc.{attr_name}.{k2}: ClaimEventSubscriber! id={id(v2)}")
                except:
                    pass

        if found_subscribers:
            sub = found_subscribers[0]
            print(f"\n--- B.5: Реальный экземпляр ClaimEventSubscriber (id={id(sub)}) ---")

            # Check _get_spatial_query
            sq_provider = getattr(sub, "_get_spatial_query", "NOT_FOUND")
            print(f"  _get_spatial_query: {sq_provider}")
            print(f"  type: {type(sq_provider).__name__}")

            if sq_provider and sq_provider != "NOT_FOUND" and callable(sq_provider):
                print(f"  Calling _get_spatial_query()...")
                try:
                    sq = sq_provider()
                    print(f"  Result: {sq}")
                    print(f"  Type: {type(sq).__name__ if sq else 'None'}")
                    if sq:
                        _npc_pos = getattr(sq, "_npc_positions", {})
                        print(f"  _npc_positions keys: {list(_npc_pos.keys()) if _npc_pos else 'empty'}")
                        if _npc_pos:
                            print(f"  'player' in _npc_positions: {'player' in _npc_pos}")
                except Exception as e:
                    print(f"  ERROR: {e}")
            else:
                print(f"  _get_spatial_query is None or not callable → SPATIAL MEMBRANE DISABLED")
                print(f"  → on_claim_event fallback: only target_id added to listeners")

            # Check _engine and _store
            engine = getattr(sub, "_engine", None)
            store = getattr(sub, "_store", None)
            print(f"\n  _engine: {engine}")
            print(f"  _store: {store}")

            result["pass"] = True
            result["found"] = True
            result["sq_provider"] = str(sq_provider)
            result["sq_provider_is_none"] = sq_provider is None or sq_provider == "NOT_FOUND"
        else:
            print(f"\n  ClaimEventSubscriber NOT FOUND anywhere in runtime")
            print(f"  → Possibly created lazily or via different mechanism")
            result["found"] = False

        return result

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()
        result["error"] = str(e)
        return result


# ============================================================================
# ЭТАП C: Проследить production composition
# ============================================================================
def stage_c_production_composition() -> Dict[str, Any]:
    _print_section("ЭТАП C: Проследить production composition (build_game_loop)")
    result = {"stage": "C", "pass": False}

    # Read game_loop_builder.py
    glb_path = _BACKEND / "app/services/game_loop_builder.py"
    if not glb_path.exists():
        print(f"[file not found: {glb_path}]")
        result["error"] = "file not found"
        return result

    src = glb_path.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    print(f"\n--- C.1: Поиск ClaimEventSubscriber в game_loop_builder.py ---")
    for i, line in enumerate(lines, 1):
        if "claim" in line.lower() or "ClaimEvent" in line or "spatial_query" in line.lower():
            print(f"  L{i}: {line.rstrip()}")

    print(f"\n--- C.2: Поиск SpatialQueryService в game_loop_builder.py ---")
    for i, line in enumerate(lines, 1):
        if "spatial" in line.lower() and ("query" in line.lower() or "service" in line.lower()):
            print(f"  L{i}: {line.rstrip()}")

    # Also check scene_state_manager.py
    print(f"\n--- C.3: Поиск spatial_query в scene_state_manager.py ---")
    ssm_path = _BACKEND / "app/services/scene_state_manager.py"
    if ssm_path.exists():
        src2 = ssm_path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src2.split("\n"), 1):
            if "spatial" in line.lower() and ("query" in line.lower() or "claim" in line.lower() or "subscriber" in line.lower()):
                print(f"  L{i}: {line.rstrip()}")

    # Check tick_orchestrator.py for subscriber creation
    print(f"\n--- C.4: Поиск в tick_orchestrator.py ---")
    to_path = _BACKEND / "app/services/tick_orchestrator.py"
    if to_path.exists():
        src3 = to_path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(src3.split("\n"), 1):
            if "claim" in line.lower() and ("subscriber" in line.lower() or "import" in line.lower() or "create" in line.lower()):
                print(f"  L{i}: {line.rstrip()}")

    # Search broadly for spatial_query_provider assignment
    print(f"\n--- C.5: Поиск spatial_query_provider = / spatial_query_provider= ---")
    results = _grep_in_dir(_BACKEND, ["spatial_query_provider"])
    for path, ln, line in results:
        if "test" not in str(path).lower() and "sandbox" not in str(path).lower():
            rel = path.relative_to(_BACKEND) if path.is_relative_to(_BACKEND) else path
            print(f"  {rel} L{ln}: {line}")

    result["pass"] = True
    return result


# ============================================================================
# ЭТАП D: Подтвердить ветку listeners (runtime trace)
# ============================================================================
def stage_d_runtime_trace(loop) -> Dict[str, Any]:
    _print_section("ЭТАП D: Подтвердить ветку listeners (runtime trace)")
    result = {"stage": "D", "pass": False}

    try:
        from app.services.events.event_bus import get_event_bus
        from app.services.events.event_types import EventType
        from app.domain.events import EventDTO
        from app.services.events.claim_event_subscriber import ClaimEventSubscriber

        bus = get_event_bus()

        # Find the actual ClaimEventSubscriber instance
        sub = None
        # Check EventBus subscribers
        for attr in ["_subscribers", "_handlers", "_callbacks"]:
            if hasattr(bus, attr):
                subs = getattr(bus, attr)
                if isinstance(subs, dict):
                    for et, callbacks in subs.items():
                        if hasattr(callbacks, '__iter__'):
                            for cb in callbacks:
                                cb_obj = getattr(cb, '__self__', None)
                                if cb_obj and isinstance(cb_obj, ClaimEventSubscriber):
                                    sub = cb_obj
                                    break
                        if sub:
                            break
                if sub:
                    break

        if sub is None:
            # Search in loop._svc
            svc = getattr(loop, "_svc", None)
            if svc:
                for attr_name in dir(svc):
                    try:
                        val = getattr(svc, attr_name)
                        if isinstance(val, ClaimEventSubscriber):
                            sub = val
                            break
                        if hasattr(val, '__dict__'):
                            for k2, v2 in vars(val).items():
                                if isinstance(v2, ClaimEventSubscriber):
                                    sub = v2
                                    break
                        if sub:
                            break
                    except:
                        pass

        if sub is None:
            print("  [ClaimEventSubscriber not found — cannot trace runtime]")
            result["error"] = "subscriber not found"
            return result

        print(f"\n  Found ClaimEventSubscriber: id={id(sub)}")

        # Monkey-patch on_claim_event to trace
        captured: Dict[str, Any] = {}
        orig_on_claim = sub.on_claim_event

        def _tracing_on_claim(event):
            payload = getattr(event, "payload", {})

            # Capture state BEFORE processing
            captured["event_source"] = getattr(event, "source", "?")
            captured["payload_target_id"] = payload.get("target_id")
            captured["payload_radius"] = payload.get("radius")
            captured["has_proposition"] = bool(payload.get("proposition"))

            sq_provider = getattr(sub, "_get_spatial_query", None)
            captured["sq_provider"] = sq_provider
            captured["sq_provider_is_none"] = sq_provider is None

            if sq_provider and callable(sq_provider):
                try:
                    sq = sq_provider()
                    captured["sq_result"] = sq
                    captured["sq_npc_positions_keys"] = list(getattr(sq, "_npc_positions", {}).keys()) if sq else []
                except Exception as e:
                    captured["sq_error"] = str(e)
            else:
                captured["sq_result"] = None
                captured["branch"] = "else (no spatial_query → fallback to target_id only)"

            # Call original
            result_orig = orig_on_claim(event)

            # After processing, check EpistemicStore for maid_lusya
            store = getattr(sub, "_store", None)
            if store:
                lusya_records = store.get_all_for_agent("maid_lusya")
                captured["lusya_records_after"] = len(lusya_records)
                for r in lusya_records[:5]:
                    captured.setdefault("lusya_records_detail", []).append({
                        "proposition": str(r.proposition),
                        "confidence": r.confidence,
                        "source_id": r.source_id,
                    })

            return result_orig

        sub.on_claim_event = _tracing_on_claim

        # Clear bus and publish PLAYER_INSULTS
        try:
            bus.clear()
        except:
            pass

        payload = {
            "action_type": "player_insults", "target_id": "tavern_keeper_tornin",
            "content": "оскорбление", "event_tick": 1, "visibility": "public",
            "radius": 999.0, "location": "tavern", "campaign_id": "Open_road",
            "raw_input": "оскорбление",
        }
        evt = EventDTO.create(event_type=EventType.PLAYER_INSULTS, source="player",
                              payload=payload, persistence_level="working")
        bus.publish(evt)

        # Also need to trigger on_player_spoke (which calls on_claim_event)
        # The subscriber should be subscribed to PLAYER_INSULTS or PLAYER_SPOKE
        print(f"\n  Published PLAYER_INSULTS")

        # Print captured state
        print(f"\n--- D.1: Captured state from runtime trace ---")
        for k, v in captured.items():
            if k == "lusya_records_detail":
                print(f"  {k}:")
                for r in v:
                    print(f"    {r}")
            else:
                print(f"  {k}: {v}")

        # Restore
        sub.on_claim_event = orig_on_claim

        result["pass"] = True
        result["captured"] = captured
        return result

    except Exception as e:
        print(f"[FATAL: {e}]")
        traceback.print_exc()
        result["error"] = str(e)
        return result


# ============================================================================
# ЭТАП E: Семантика радиуса (PerceptualKernel.can_observe)
# ============================================================================
def stage_e_perceptual_kernel() -> Dict[str, Any]:
    _print_section("ЭТАП E: PerceptualKernel.can_observe — семантика радиуса")
    result = {"stage": "E", "pass": False}

    # Find PerceptualKernel
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
        result["error"] = "not found"
        return result

    print(f"\n  Found at: {pk_path.relative_to(_BACKEND)}")
    src = pk_path.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    # Print can_observe method
    print(f"\n--- can_observe method ---")
    in_method = False
    method_lines = []
    for i, line in enumerate(lines):
        if "def can_observe" in line:
            in_method = True
        if in_method:
            method_lines.append((i + 1, line))
            if line.strip() == "" and len(method_lines) > 3:
                # Check if next non-empty line is dedented
                break
            if len(method_lines) > 50:
                break

    # Better: find method bounds
    for i, line in enumerate(lines):
        if "def can_observe" in line:
            start = i
            # Find end
            indent = len(line) - len(line.lstrip())
            end = len(lines)
            for j in range(i + 1, len(lines)):
                if lines[j].strip() == "":
                    continue
                cur_indent = len(lines[j]) - len(lines[j].lstrip())
                if cur_indent <= indent and (lines[j].lstrip().startswith("def ") or lines[j].lstrip().startswith("class ")):
                    end = j
                    break
            print(f"  can_observe at L{start+1}–L{end}:")
            for j in range(start, end):
                print(f"  L{j+1}: {lines[j]}")
            break

    # Check for HEARING_RADIUS in this file
    print(f"\n--- HEARING_RADIUS / radius references ---")
    for i, line in enumerate(lines, 1):
        if "HEARING_RADIUS" in line or "hearing_radius" in line.lower():
            print(f"  L{i}: {line.rstrip()}")
        elif "radius" in line.lower() and ("event" in line.lower() or "payload" in line.lower()):
            print(f"  L{i}: {line.rstrip()}")

    result["pass"] = True
    return result


# ============================================================================
# ИТОГ
# ============================================================================
def final_verdict(stage_b_result: Dict, stage_c_result: Dict, stage_d_result: Dict, stage_e_result: Dict) -> None:
    _print_section("ИТОГ — один из трёх выводов")

    sq_provider_none = stage_b_result.get("sq_provider_is_none", True)
    subscriber_found = stage_b_result.get("found", False)
    captured = stage_d_result.get("captured", {})

    print(f"""
=============================================================================
ФАКТЫ
=============================================================================
""")

    print(f"  ClaimEventSubscriber найден в runtime: {subscriber_found}")
    if subscriber_found:
        print(f"  _get_spatial_query is None: {sq_provider_none}")
        print(f"  Runtime trace captured: {bool(captured)}")
        if captured:
            print(f"    event_source: {captured.get('event_source')}")
            print(f"    target_id: {captured.get('payload_target_id')}")
            print(f"    has_proposition: {captured.get('has_proposition')}")
            print(f"    sq_provider: {captured.get('sq_provider')}")
            print(f"    sq_result: {captured.get('sq_result')}")
            print(f"    branch: {captured.get('branch', 'if (spatial_query exists)')}")
            print(f"    lusya_records_after: {captured.get('lusya_records_after', 'N/A')}")

    print(f"""
=============================================================================
ВЕРДИКТ
=============================================================================
""")

    if not subscriber_found:
        print(f"  >>> ВЫВОД: 2. MISSING PRODUCTION SERVICE")
        print(f"  >>> ClaimEventSubscriber НЕ НАЙДЕН в production runtime")
        print(f"  >>> Возможно, создаётся лениво или через другой механизм")
        print(f"  >>> Нужно проверить EventBus subscriber registration")
    elif sq_provider_none:
        print(f"  >>> ВЫВОД: 1. WIRING DEFECT")
        print(f"  >>> ClaimEventSubscriber существует, но _get_spatial_query = None")
        print(f"  >>> spatial_query_provider не передан при создании подписчика")
        print(f"  >>> on_claim_event fallback: только target_id добавлен в listeners")
        print(f"  >>> maid_lusya НЕ target_id → НЕ в listeners → belief не создан")
        print(f"")
        print(f"  >>> МИНИМАЛЬНОЕ ИСПРАВЛЕНИЕ:")
        print(f"  >>> Найти, где ClaimEventSubscriber создаётся в production")
        print(f"  >>> Передать spatial_query_provider, который возвращает SpatialQueryService")
        print(f"  >>> SpatialQueryService должен иметь доступ к scene_state['npc_positions']")
        print(f"  >>>")
        print(f"  >>> ЗАТРАГИВАЕМЫЕ ФАЙЛЫ:")
        print(f"  >>> - app/services/game_loop_builder.py (или где создаётся подписчик)")
        print(f"  >>> - app/services/spatial/spatial_query_service.py (если нужно создать)")
        print(f"  >>>")
        print(f"  >>> РИСКИ:")
        print(f"  >>> - spatial membrane начнёт фильтровать слушателей по дистанции")
        print(f"  >>> - NPC слишком далеко (>10m) могут быть исключены")
        print(f"  >>> - player ↔ maid_lusya distance = 10.086m > HEARING_RADIUS 10.0m")
        print(f"  >>> - Даже с spatial_query, maid_lusya может быть исключена (на 9см)")
        print(f"  >>>")
        print(f"  >>> ТЕСТЫ:")
        print(f"  >>> 1. distance('player', 'maid_lusya') возвращает корректную дистанцию")
        print(f"  >>> 2. distance('player', 'tavern_keeper_tornin') возвращает корректную дистанцию")
        print(f"  >>> 3. NPC → NPC distance не регрессирует")
        print(f"  >>> 4. PLAYER_INSULTS при допустимой дистанции создаёт belief у Люси")
        print(f"  >>> 5. Provenance и confidence не изменяются неожиданным образом")
    elif captured.get("lusya_records_after", 0) > 0:
        print(f"  >>> ВЫВОД: 3. NOT A WIRING DEFECT")
        print(f"  >>> Provider существует и работает; maid_lusya получила belief")
        print(f"  >>> Причина отсутствия belief — в другом участке")
    else:
        print(f"  >>> ВЫВОД: НЕОПРЕДЕЛЁН")
        print(f"  >>> Provider существует, но maid_lusya всё ещё не получила belief")
        print(f"  >>> Нужно проверить can_observe (Этап E)")
        print(f"  >>> distance player ↔ maid_lusya = 10.086m > HEARING_RADIUS 10.0m")
        print(f"  >>> Возможно: can_observe использует HEARING_RADIUS, а не event.radius")

    print(f"""
=============================================================================
ССЫЛКИ НА КОД
=============================================================================
""")
    # Print key references
    if subscriber_found:
        print(f"  ClaimEventSubscriber: id={stage_b_result.get('found', False)}")
        print(f"  _get_spatial_query: {stage_b_result.get('sq_provider', 'N/A')}")
    print(f"  claim_event_subscriber.py L244-278: spatial membrane (if/else)")
    print(f"  claim_event_subscriber.py L275-278: fallback (target_id only)")
    print(f"  PerceptualKernel.can_observe: {stage_e_result.get('pass', False)}")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D1 PRODUCTION WIRING FORENSICS")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)

    stage_a_result = {}
    stage_b_result = {}
    stage_c_result = {}
    stage_d_result = {}
    stage_e_result = {}

    try:
        stage_a_result = stage_a_find_registration()
    except Exception as e:
        print(f"[stage A error: {e}]")
        traceback.print_exc()

    try:
        # Build game loop for runtime checks
        from app.core.config import settings, BASE_DIR
        from app.services.game_loop_builder import build_game_loop
        import tempfile

        saves_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d1_wiring_"))
        settings.saves_dir = str(saves_dir)
        settings.environment = "development"

        loop = build_game_loop(data_dir=Path(settings.data_dir))
        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")

        try:
            stage_b_result = stage_b_check_instance(loop)
        except Exception as e:
            print(f"[stage B error: {e}]")
            traceback.print_exc()

        try:
            stage_c_result = stage_c_production_composition()
        except Exception as e:
            print(f"[stage C error: {e}]")
            traceback.print_exc()

        try:
            stage_d_result = stage_d_runtime_trace(loop)
        except Exception as e:
            print(f"[stage D error: {e}]")
            traceback.print_exc()

        try:
            stage_e_result = stage_e_perceptual_kernel()
        except Exception as e:
            print(f"[stage E error: {e}]")
            traceback.print_exc()

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

    try:
        final_verdict(stage_b_result, stage_c_result, stage_d_result, stage_e_result)
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
