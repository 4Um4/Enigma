# backend/tests/sandbox/r2_b5_d2_router_investigation.py
"""
R2-B5-D2 — ModelRouter investigation (read-only).

Master's 5 questions:
  1. Does ModelRouter already have a method to check model availability?
  2. If yes — does it actually check endpoint availability, not just object presence?
  3. Can the check run without blocking HTTP request?
  4. What happens when LLM server is unavailable?
  5. Can spread_rumor + proposition safely switch to stub while preserving LLM branch when available?

ALSO investigate (Master's requirement):
  - If LLM was available at check time but request fails/times out —
    is there a fallback to stub?
  - "If such mechanism doesn't exist, compare cost of minimal extension vs Option 2"

READ-ONLY. Production-код не менять.
"""
from __future__ import annotations

import os
import sys
import json
import re
import shutil
import traceback
import io
import logging
import tempfile
import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from app.core.config import settings, BASE_DIR
except Exception as e:
    print(f"[FATAL] Cannot import app.core.config: {e}")
    sys.exit(2)

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_router_investigation.txt"


class TeeStream:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
            except Exception:
                pass

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass


_stdout_buf = io.StringIO()
_orig_stdout = sys.stdout
sys.stdout = TeeStream(_orig_stdout, _stdout_buf)


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


# ============================================================================
# Source readers
# ============================================================================
def _read_file_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[read error: {e}]"


def _find_function_bounds(src: str, func_name: str) -> Optional[Tuple[int, int]]:
    lines = src.split("\n")
    func_start = None
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("def ") and func_name in stripped.split("(")[0]:
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
        if cur_indent <= indent_of_def and (
            line.lstrip().startswith("def ")
            or line.lstrip().startswith("class ")
            or line.lstrip().startswith("@")
        ):
            func_end = j
            break
    return func_start, func_end


def _read_function_full(path: Path, func_name: str, max_lines: int = 300) -> None:
    if not path.exists():
        print(f"  [file not found: {path}]")
        return
    src = _read_file_text(path)
    lines = src.split("\n")
    bounds = _find_function_bounds(src, func_name)
    if bounds:
        s, e = bounds
        actual_end = min(e, s + max_lines)
        print(f"  {func_name}() at L{s+1}..L{e} (showing L{s+1}..L{actual_end}):")
        for j in range(s, actual_end):
            print(f"  L{j+1:4d}: {lines[j]}")
        if actual_end < e:
            print(f"  ... ({e - actual_end} more lines)")
    else:
        print(f"  [{func_name} not found]")


def _grep_in_file(path: Path, pattern: str, context: int = 5, max_matches: int = 10) -> None:
    if not path.exists():
        print(f"  [file not found: {path}]")
        return
    src = _read_file_text(path)
    lines = src.split("\n")
    matches = []
    for i, line in enumerate(lines):
        if pattern.lower() in line.lower():
            matches.append(i)
    if not matches:
        print(f"  no matches for '{pattern}' in {path.name}")
        return
    print(f"  Found {len(matches)} matches for '{pattern}' in {path.name}:")
    seen_ranges = set()
    for i in matches[:max_matches]:
        ctx_start = max(0, i - context)
        ctx_end = min(len(lines), i + context + 1)
        if any(r in seen_ranges for r in range(ctx_start, ctx_end)):
            continue
        for r in range(ctx_start, ctx_end):
            seen_ranges.add(r)
        print(f"\n  >>> L{i+1}: {lines[i].rstrip()}")
        for j in range(ctx_start, ctx_end):
            marker = ">>>" if j + 1 == i + 1 else "   "
            print(f"  {marker} L{j+1:4d}: {lines[j]}")


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 — ModelRouter investigation (read-only)")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("Master's 5 questions:")
    print("  1. Does ModelRouter have a method to check model availability?")
    print("  2. If yes — does it actually check endpoint, not just object presence?")
    print("  3. Can the check run without blocking HTTP request?")
    print("  4. What happens when LLM server is unavailable?")
    print("  5. Can spread_rumor+proposition safely switch to stub, preserving LLM?")
    print()
    print("Additional: Does LLM failure/timesout fall back to stub?")
    print()

    # =====================================================================
    # STEP 1: Find ModelRouter source file
    # =====================================================================
    _print_section("STEP 1: Find ModelRouter source file")
    router_path = _BACKEND / "app" / "services" / "llm" / "router.py"
    print(f"  expected: {router_path}")
    if router_path.exists():
        src = _read_file_text(router_path)
        print(f"  file exists, {len(src.split(chr(10)))} lines")
    else:
        print(f"  [file not found — searching]")
        for f in _BACKEND.rglob("*.py"):
            if any(part in {".venv", "node_modules", ".git", "__pycache__", "site-packages", "tests", "sandbox"} for part in f.parts):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                if "class ModelRouter" in content:
                    router_path = f
                    print(f"  found: {f}")
                    src = content
                    break
            except Exception:
                continue

    # =====================================================================
    # STEP 2: Read full ModelRouter class
    # =====================================================================
    _print_section("STEP 2: Read full ModelRouter class")
    if router_path.exists():
        src = _read_file_text(router_path)
        lines = src.split("\n")
        # Print all lines (it should be reasonably small)
        print(f"  file: {router_path}")
        print(f"  total lines: {len(lines)}")
        max_print = min(len(lines), 400)
        for i, line in enumerate(lines[:max_print], 1):
            print(f"  L{i:4d}: {line}")
        if len(lines) > max_print:
            print(f"  ... ({len(lines) - max_print} more lines)")
    else:
        print(f"  [file not found]")
        return 1

    # =====================================================================
    # STEP 3: List all public methods of ModelRouter
    # =====================================================================
    _print_section("STEP 3: List all ModelRouter methods")
    try:
        from app.services.llm.router import ModelRouter
        print(f"  ModelRouter class: {ModelRouter}")
        print(f"  module: {ModelRouter.__module__}")
        print(f"  file: {inspect.getfile(ModelRouter)}")
        print()
        print(f"  Methods (including inherited):")
        for name in sorted(dir(ModelRouter)):
            if name.startswith("__"):
                continue
            attr = getattr(ModelRouter, name, None)
            if callable(attr):
                try:
                    sig = inspect.signature(attr)
                    print(f"    {name}{sig}")
                except (ValueError, TypeError):
                    print(f"    {name}(...)")
            else:
                print(f"    [attr] {name} = {repr(attr)[:100]}")
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()

    # =====================================================================
    # STEP 4: Search for availability-related methods
    # =====================================================================
    _print_section("STEP 4: Search for availability-related methods")
    availability_keywords = ["available", "is_available", "is_llm_available",
                             "is_ready", "is_alive", "health", "ping",
                             "check", "test_connection", "can_connect"]
    for kw in availability_keywords:
        print(f"\n  --- search for '{kw}' ---")
        _grep_in_file(router_path, kw, context=3, max_matches=5)

    # =====================================================================
    # STEP 5: Read request_for_agent + _abort_generation
    # =====================================================================
    _print_section("STEP 5: Read request_for_agent + _abort_generation")
    _read_function_full(router_path, "request_for_agent", max_lines=200)
    print(f"\n  --- _abort_generation ---")
    _read_function_full(router_path, "_abort_generation", max_lines=100)

    # =====================================================================
    # STEP 6: Read __init__ to understand router construction
    # =====================================================================
    _print_section("STEP 6: Read ModelRouter.__init__")
    _read_function_full(router_path, "__init__", max_lines=200)

    # =====================================================================
    # STEP 7: Search for timeout, retry, fallback mechanisms
    # =====================================================================
    _print_section("STEP 7: Search for timeout, retry, fallback mechanisms")
    for kw in ["timeout", "retry", "fallback", "except", "ConnectionError",
               "requests.exceptions", "httpx", "aiohttp", "openai"]:
        print(f"\n  --- search for '{kw}' ---")
        _grep_in_file(router_path, kw, context=3, max_matches=5)

    # =====================================================================
    # STEP 8: Check DialogueExecutor for existing fallback on LLM failure
    # =====================================================================
    _print_section("STEP 8: Check DialogueExecutor existing LLM failure handling")
    de_path = _BACKEND / "app" / "services" / "execution" / "dialogue_executor.py"
    if de_path.exists():
        src = _read_file_text(de_path)
        lines = src.split("\n")
        # Print L150-207 (LLM branch with exception handling)
        print(f"  --- dialogue_executor.py L150-207 (LLM branch + exception handling) ---")
        for j in range(149, min(207, len(lines))):
            print(f"  L{j+1:4d}: {lines[j]}")

    # =====================================================================
    # STEP 9: Search for LLM client/provider
    # =====================================================================
    _print_section("STEP 9: Search for LLM client/provider classes")
    llm_dir = _BACKEND / "app" / "services" / "llm"
    if llm_dir.exists():
        print(f"  LLM directory: {llm_dir}")
        for f in sorted(llm_dir.rglob("*.py")):
            if f.name == "__init__.py":
                continue
            try:
                rel = f.relative_to(_BACKEND)
            except Exception:
                rel = f
            print(f"  file: {rel}")

    # =====================================================================
    # STEP 10: Read LLM client (find what makes HTTP calls)
    # =====================================================================
    _print_section("STEP 10: Read LLM client files")
    # Look for common LLM client patterns
    for f in sorted(llm_dir.rglob("*.py")):
        if f.name == "__init__.py":
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if any(kw in content for kw in ["requests.post", "httpx", "aiohttp", "openai", "llama"]):
            try:
                rel = f.relative_to(_BACKEND)
            except Exception:
                rel = f
            print(f"\n  --- {rel} (contains HTTP/LLM client code) ---")
            lines = content.split("\n")
            for i, line in enumerate(lines[:100], 1):
                print(f"  L{i:4d}: {line}")
            if len(lines) > 100:
                print(f"  ... ({len(lines) - 100} more lines)")

    # =====================================================================
    # STEP 11: Build loop, inspect ModelRouter instance at runtime
    # =====================================================================
    _print_section("STEP 11: Build loop, inspect runtime ModelRouter instance")

    orig_saves_dir = settings.saves_dir
    orig_env = settings.environment
    temp_dir = Path(tempfile.mkdtemp(prefix="r2_b5_d2_router_"))

    try:
        from app.services.game_loop_builder import build_game_loop
        settings.saves_dir = str(temp_dir)
        settings.environment = "development"
        loop = build_game_loop(data_dir=Path(settings.data_dir))

        scene = loop.scene_manager.get_scene_state("Open_road", "tavern")
        if scene is None:
            scene = loop.scene_manager.initialize_scene("Open_road", "tavern", "12:00")
        loaded = loop._load_npcs_with_runtime("Open_road")

        # Find DialogueExecutor
        ts_obj = loop._get_task_scheduler()
        executors_dict = getattr(ts_obj, "_executors", None)
        from app.domain.execution import TaskKind
        dialogue_executor = executors_dict.get(TaskKind.DIALOGUE) if executors_dict else None

        if dialogue_executor is None:
            print(f"  [DialogueExecutor not found]")
            return 1

        router = getattr(dialogue_executor, "_router", None)
        print(f"  DialogueExecutor: {dialogue_executor}")
        print(f"  router: {router}")
        print(f"  router is None: {router is None}")
        if router is not None:
            print(f"  router type: {type(router).__name__}")
            print(f"  router module: {type(router).__module__}")
            print(f"  router file: {inspect.getfile(type(router))}")
            print()
            print(f"  --- router instance attributes ---")
            try:
                for k, v in vars(router).items():
                    if k.startswith("__"):
                        continue
                    print(f"    {k}: {repr(v)[:200]}")
            except Exception:
                for attr in sorted(dir(router)):
                    if attr.startswith("__"):
                        continue
                    try:
                        val = getattr(router, attr)
                        if callable(val):
                            continue
                        print(f"    {attr}: {repr(val)[:200]}")
                    except Exception:
                        continue

            print()
            print(f"  --- router methods (callable) ---")
            for attr in sorted(dir(router)):
                if attr.startswith("__"):
                    continue
                try:
                    val = getattr(router, attr)
                    if callable(val):
                        try:
                            sig = inspect.signature(val)
                            print(f"    {attr}{sig}")
                        except (ValueError, TypeError):
                            print(f"    {attr}(...)")
                except Exception:
                    continue

            # =====================================================================
            # STEP 12: Try to call availability-related methods (if any)
            # =====================================================================
            _print_section("STEP 12: Try availability-related methods on router instance")
            for method_name in ["is_available", "is_llm_available", "is_ready",
                                "is_alive", "health_check", "ping", "check_connection",
                                "can_connect", "is_connected"]:
                method = getattr(router, method_name, None)
                if method is not None and callable(method):
                    print(f"\n  --- {method_name}() exists! ---")
                    try:
                        result = method()
                        print(f"  result: {result}")
                        print(f"  type: {type(result).__name__}")
                    except Exception as e:
                        print(f"  ERROR calling {method_name}: {type(e).__name__}: {e}")
                        traceback.print_exc()
                else:
                    print(f"  {method_name}: NOT found on router")

            # =====================================================================
            # STEP 13: Inspect router internals — what does it use for HTTP?
            # =====================================================================
            _print_section("STEP 13: Inspect router internals — HTTP client")
            # Check for common HTTP client attributes
            for attr_name in ["_client", "_http_client", "_session", "client",
                              "session", "_aiohttp_session", "_httpx_client",
                              "_openai_client", "base_url", "endpoint", "url",
                              "_endpoint", "_base_url", "_url"]:
                val = getattr(router, attr_name, "NOT_FOUND")
                if val != "NOT_FOUND":
                    print(f"  router.{attr_name}: {repr(val)[:200]}")

            # Check for timeout setting
            for attr_name in ["_timeout", "timeout", "_request_timeout",
                              "TIMEOUT", "_llm_timeout"]:
                val = getattr(router, attr_name, "NOT_FOUND")
                if val != "NOT_FOUND":
                    print(f"  router.{attr_name}: {repr(val)[:200]}")

        # Cleanup
        try:
            ts = loop._get_task_scheduler()
            if hasattr(ts, "_executor_pool"):
                ts._executor_pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        del loop
        import gc
        gc.collect()

    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
    finally:
        settings.saves_dir = orig_saves_dir
        settings.environment = orig_env
        shutil.rmtree(temp_dir, ignore_errors=True)

    # =====================================================================
    # STEP 14: Analysis — answer 5 questions
    # =====================================================================
    _print_section("STEP 14: Analysis — answer Master's 5 questions")

    print(f"""
  Q1: Does ModelRouter already have a method to check model availability?
  >>>
  >>> See Steps 3, 4, 12 — search for availability methods.
  >>> If is_available/is_llm_available/health_check/ping exist → YES
  >>> If not → NO (need to add or use Option 2)

  Q2: If yes — does it actually check endpoint, not just object presence?
  >>>
  >>> See Step 5 — read the method body.
  >>> If it makes HTTP request → real check
  >>> If it returns self._client is not None → object presence only

  Q3: Can the check run without blocking HTTP request?
  >>>
  >>> If method does HTTP GET /health → BLOCKING
  >>> If method reads cached status → NON-BLOCKING
  >>> If no method → N/A

  Q4: What happens when LLM server is unavailable?
  >>>
  >>> See Steps 5, 7, 8:
  >>> - request_for_agent likely raises ConnectionError/TimeoutError
  >>> - DialogueExecutor L172-195 catches Exception, yields error Artifact
  >>> - BUT: error Artifact does NOT create NPC_SPOKE (materializer checks success)
  >>> - So: LLM unavailable → error Artifact → NO NPC_SPOKE → no social event

  Q5: Can spread_rumor+proposition safely switch to stub, preserving LLM?
  >>>
  >>> If router has reliable is_available() → YES, use Option 1
  >>> If not → need to add is_available() (minimal extension) OR use Option 2
  >>>
  >>> CRITICAL: even with is_available() check, race condition exists:
  >>>   - is_available() returns True at check time
  >>>   - request_for_agent fails at call time (server went down)
  >>>   - Exception caught, error Artifact yielded, NO NPC_SPOKE
  >>>   - Need: catch exception → fallback to stub text → yield success Artifact
  >>>   - This is the "fallback on failure" Master requires

  Additional: Does LLM failure fall back to stub?
  >>>
  >>> CURRENTLY: NO
  >>> - L172-195: catches Exception, yields error Artifact (success=False)
  >>> - materializer L62: `if not artifact.success: return []`
  >>> - No NPC_SPOKE created
  >>> - Need: in except block, fall back to deterministic stub text
  >>> - Then yield SUCCESS Artifact with stub text + proposition
""")

    # =====================================================================
    # STEP 15: Recommended diff options
    # =====================================================================
    _print_section("STEP 15: Recommended diff options (based on findings)")

    print(f"""
  Based on investigation, three options:

  Option A (if is_available() exists and is reliable):
    Add condition to L145-149:
      elif not requires_llm_materialization(req.intent_type) and not (
          req.intent_type == "spread_rumor" and _proposition is not None
          and self._router is not None and self._router.is_available()
      ):
          text = f"[{{req.intent_type}}] {{task.owner_id}} -> {{req.target_id}}: {{req.topic}}"

    Plus: in L172-195 except block, add fallback:
      except Exception as e:
          if req.intent_type == "spread_rumor" and _proposition is not None:
              # B5-D2 FIX: LLM failure fallback to stub
              text = f"[spread_rumor] {{task.owner_id}} -> {{req.target_id}}: {{req.topic}}"
              # Continue to yield success Artifact (don't return)
          else:
              # Original error handling
              yield Artifact(...)
              return

  Option B (if is_available() doesn't exist — minimal extension):
    Add is_available() to ModelRouter (returns bool, non-blocking):
      def is_available(self) -> bool:
          # Check cached connection status, or return True if endpoint configured
          return self._endpoint is not None

    Then use Option A condition.

  Option C (Option 2 from previous investigation — always stub):
    Remove special case entirely:
      elif not requires_llm_materialization(req.intent_type):
          text = f"[{{req.intent_type}}] {{task.owner_id}} -> {{req.target_id}}: {{req.topic}}"

    Loses LLM text for spread_rumor, but simplest diff (1 line).

  Recommendation depends on what Steps 3-13 found.
""")

    # Write output file
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
