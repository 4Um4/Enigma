# backend/tests/sandbox/r2_editor_store_init_archaeology_probe.py
"""
R2-EDITOR-STORE-INIT archaeology probe — READ-ONLY source survey.

Цель: установить причину AssertionError:
  frontend/map_editor/editor_core.py:400
  assert _store is not None, "CatalogPanel.store должен быть загружен до BlueprintEditor"

Этапы:
  1. Прочитать editor_core.py вокруг строки 400 (assertion + контекст).
  2. Найти класс CatalogPanel — где и как создаётся .store.
  3. Найти класс BlueprintEditor — как он получает store.
  4. Найти EditorCore.__init__ / _init_ui — порядок инициализации.
  5. Найти game_launcher.py _launch_editor — путь запуска.
  6. Проверить git log на недавние изменения editor_core.py, catalog_panel, blueprint_editor.
  7. Проверить циклические импорты (front-обёртки, lazy imports).
  8. Проверить условия загрузки каталога (try/except, raise на пустом каталоге).

Запрещено:
  - Менять production-код, тесты, карту.
  - Запускать сам game_launcher (он падает).
  - Создавать фиктивный store.
"""
from __future__ import annotations
import os, sys, subprocess, traceback
from pathlib import Path
from typing import Any, List, Optional, Tuple
import io
from contextlib import redirect_stdout, redirect_stderr

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from app.core.config import settings, BASE_DIR
except Exception as e:
    print(f"[FATAL] Cannot import app.core.config: {e}")
    sys.exit(2)

PROJECT_ROOT = _BACKEND.parent  # C:\DDD\Codex\VSC_Enigma\Enigma
EDITOR_CORE = PROJECT_ROOT / "frontend/map_editor/editor_core.py"
GAME_LAUNCHER = PROJECT_ROOT / "game_launcher.py"
MAP_EDITOR_DIR = PROJECT_ROOT / "frontend/map_editor"

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_editor_store_init_sources.txt"


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
_stderr_buf = io.StringIO()
_orig_stdout = sys.stdout
_orig_stderr = sys.stderr
sys.stdout = TeeStream(_orig_stdout, _stdout_buf)
sys.stderr = TeeStream(_orig_stderr, _stderr_buf)


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


def _grep_in_file(path: Path, patterns: List[str], context_before: int = 0, context_after: int = 0) -> List[Tuple[int, str, List[str]]]:
    """Search for patterns in a file. Returns list of (line_no, matched_line, context_lines)."""
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    except Exception:
        return []
    out = []
    for i, line in enumerate(lines):
        for pat in patterns:
            if pat in line:
                ctx = []
                for j in range(max(0, i - context_before), min(len(lines), i + context_after + 1)):
                    if j != i:
                        ctx.append(f"L{j+1:4d}: {lines[j]}")
                out.append((i + 1, line, ctx))
                break
    return out


def _find_function_bounds(src: str, func_name: str) -> Optional[Tuple[int, int]]:
    lines = src.split("\n")
    func_start = None
    for i, line in enumerate(lines):
        if line.startswith("def ") and func_name in line:
            func_start = i
            break
        if line.startswith("    def ") and func_name in line:
            func_start = i
            break
        if line.startswith("class ") and func_name in line:
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
# STEP 1: editor_core.py around L380-420 (assertion + context)
# ============================================================================
def step1_assertion_context() -> None:
    _print_section("STEP 1: editor_core.py around L380-420 (assertion + surrounding code)")
    print(f"File: {EDITOR_CORE}")
    for line in _read_lines(EDITOR_CORE, 380, 420):
        print(line)


# ============================================================================
# STEP 2: CatalogPanel class — find definition + .store field
# ============================================================================
def step2_catalog_panel_class() -> None:
    _print_section("STEP 2: CatalogPanel class — find definition + .store field")

    # Search across all map_editor .py files for "class CatalogPanel" and "CatalogPanel.store"
    candidates = []
    if MAP_EDITOR_DIR.exists():
        for py_file in MAP_EDITOR_DIR.rglob("*.py"):
            try:
                src = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if "CatalogPanel" in src or "CatalogStore" in src or "catalog_store" in src:
                candidates.append(py_file)

    print(f"\nFiles containing CatalogPanel/CatalogStore/catalog_store: {len(candidates)}")
    for p in candidates:
        print(f"  {p.relative_to(PROJECT_ROOT)}")

    # For each candidate, search for class CatalogPanel, class CatalogStore, .store assignment
    for p in candidates:
        print(f"\n--- {p.relative_to(PROJECT_ROOT)} ---")
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"  [read error: {e}]")
            continue
        lines = src.split("\n")

        # Find class CatalogPanel definition + show 30 lines
        for i, line in enumerate(lines):
            if line.startswith("class CatalogPanel") or line.startswith("class CatalogStore"):
                print(f"\n  === {line.rstrip()} (at L{i+1}) ===")
                # Show next 30 lines
                for j in range(i, min(i + 40, len(lines))):
                    print(f"  L{j+1:4d}: {lines[j]}")
                break

        # Find .store = assignment
        print(f"\n  --- '.store =' assignments in {p.name} ---")
        store_assignments = _grep_in_file(p, [".store =", "store = ", "self.store"])
        for ln, line, ctx in store_assignments[:10]:
            print(f"  L{ln}: {line.rstrip()}")


# ============================================================================
# STEP 3: BlueprintEditor class — how it receives store
# ============================================================================
def step3_blueprint_editor_class() -> None:
    _print_section("STEP 3: BlueprintEditor class — how it receives store")

    if not MAP_EDITOR_DIR.exists():
        print(f"[map_editor dir not found: {MAP_EDITOR_DIR}]")
        return

    for py_file in MAP_EDITOR_DIR.rglob("*.py"):
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if "class BlueprintEditor" not in src:
            continue
        print(f"\n--- Found in {py_file.relative_to(PROJECT_ROOT)} ---")
        bounds = _find_function_bounds(src, "class BlueprintEditor")
        if not bounds:
            # Try without class prefix
            for i, line in enumerate(src.split("\n")):
                if "class BlueprintEditor" in line:
                    bounds = (i, min(i + 100, len(src.split("\n"))))
                    break
        if not bounds:
            continue
        start, end = bounds
        lines = src.split("\n")
        print(f"\nFull BlueprintEditor class (L{start+1}–L{end}):")
        for j in range(start, min(end, start + 100)):
            print(f"L{j+1:4d}: {lines[j]}")


# ============================================================================
# STEP 4: EditorCore.__init__ and _init_ui — initialization order
# ============================================================================
def step4_editor_core_init() -> None:
    _print_section("STEP 4: EditorCore.__init__ and _init_ui — initialization order")
    if not EDITOR_CORE.exists():
        print(f"[file not found: {EDITOR_CORE}]")
        return
    src = EDITOR_CORE.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")

    # Find EditorCore class definition
    editor_core_start = None
    for i, line in enumerate(lines):
        if line.startswith("class EditorCore"):
            editor_core_start = i
            break
    if editor_core_start is None:
        print("[class EditorCore not found]")
        return
    print(f"\nFound class EditorCore at L{editor_core_start + 1}")

    # Find __init__ and _init_ui methods within EditorCore
    for method_name in ("__init__", "_init_ui"):
        method_bounds = None
        for i in range(editor_core_start, len(lines)):
            line = lines[i]
            if f"def {method_name}" in line and not line.startswith("def "):
                # Found the method definition (it's a method, indented)
                method_bounds = _find_function_bounds(src, method_name)
                if method_bounds:
                    break
        if not method_bounds:
            print(f"\n[method {method_name} not found in EditorCore]")
            continue
        start, end = method_bounds
        print(f"\n--- method {method_name} (L{start+1}–L{end}) ---")
        for j in range(start, end):
            print(f"L{j+1:4d}: {lines[j]}")


# ============================================================================
# STEP 5: game_launcher.py _launch_editor — launch path
# ============================================================================
def step5_game_launcher_launch_editor() -> None:
    _print_section("STEP 5: game_launcher.py _launch_editor — launch path")
    if not GAME_LAUNCHER.exists():
        print(f"[file not found: {GAME_LAUNCHER}]")
        return

    src = GAME_LAUNCHER.read_text(encoding="utf-8", errors="replace")
    bounds = _find_function_bounds(src, "_launch_editor")
    if not bounds:
        print("[_launch_editor not found in game_launcher.py]")
        # Show lines around 530 (where assertion stack mentions)
        print("\nFalling back to L500-540:")
        for line in _read_lines(GAME_LAUNCHER, 500, 540):
            print(line)
        return
    start, end = bounds
    print(f"\nFound _launch_editor at L{start+1}, ends at L{end}")
    lines = src.split("\n")
    for j in range(start, end):
        print(f"L{j+1:4d}: {lines[j]}")


# ============================================================================
# STEP 6: git log — recent changes to editor_core.py and related files
# ============================================================================
def step6_git_log_recent_changes() -> None:
    _print_section("STEP 6: git log — recent changes to editor_core.py and related files")

    if not (PROJECT_ROOT / ".git").exists():
        print("[not a git repository]")
        return

    # Get last 20 commits touching editor_core.py
    target_files = [
        "frontend/map_editor/editor_core.py",
        "frontend/map_editor",
    ]
    # Find CatalogPanel and BlueprintEditor file paths first
    if MAP_EDITOR_DIR.exists():
        for py_file in MAP_EDITOR_DIR.rglob("*.py"):
            try:
                src = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if "class CatalogPanel" in src:
                rel = py_file.relative_to(PROJECT_ROOT).as_posix()
                if rel not in target_files:
                    target_files.append(rel)
            if "class BlueprintEditor" in src:
                rel = py_file.relative_to(PROJECT_ROOT).as_posix()
                if rel not in target_files:
                    target_files.append(rel)

    print(f"\nTarget files for git log:")
    for tf in target_files:
        print(f"  - {tf}")

    for tf in target_files:
        print(f"\n--- git log for {tf} (last 20 commits) ---")
        try:
            # Try direct subprocess call
            cmd = ["git", "log", "--oneline", "--no-decorate", "-20", "--", tf]
            result = subprocess.run(
                cmd,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=30,
                shell=(os.name == "nt"),
            )
            if result.returncode == 0:
                print(result.stdout)
            else:
                print(f"  [git log error: {result.stderr}]")
        except Exception as e:
            print(f"  [git log exception: {e}]")

    # Also: full file listing recent changes (last 10 commits touching frontend/map_editor)
    print(f"\n--- git log for frontend/map_editor (last 15 commits) ---")
    try:
        cmd = ["git", "log", "--oneline", "--no-decorate", "-15", "--", "frontend/map_editor"]
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            shell=(os.name == "nt"),
        )
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"  [git log error: {result.stderr}]")
    except Exception as e:
        print(f"  [git log exception: {e}]")


# ============================================================================
# STEP 7: circular imports and lazy initialization
# ============================================================================
def step7_circular_imports_and_lazy_init() -> None:
    _print_section("STEP 7: circular imports and lazy initialization checks")

    # Search for imports of CatalogPanel, CatalogStore across map_editor
    print("\n--- 'import' lines referencing CatalogPanel / CatalogStore ---")
    if MAP_EDITOR_DIR.exists():
        for py_file in MAP_EDITOR_DIR.rglob("*.py"):
            try:
                src = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(src.split("\n"), 1):
                line_stripped = line.strip()
                if line_stripped.startswith("import ") or line_stripped.startswith("from "):
                    if "CatalogPanel" in line or "CatalogStore" in line or "catalog_store" in line or "catalog_panel" in line:
                        rel = py_file.relative_to(PROJECT_ROOT)
                        print(f"  {rel} L{i}: {line.rstrip()}")

    # Search for lazy initialization patterns: TYPE_CHECKING, lazy_load, lazy_import
    print("\n--- lazy initialization patterns (TYPE_CHECKING, lazy_*) ---")
    if MAP_EDITOR_DIR.exists():
        for py_file in MAP_EDITOR_DIR.rglob("*.py"):
            try:
                src = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(src.split("\n"), 1):
                if "TYPE_CHECKING" in line or "lazy_load" in line.lower() or "lazy_import" in line.lower():
                    rel = py_file.relative_to(PROJECT_ROOT)
                    print(f"  {rel} L{i}: {line.rstrip()}")

    # Search for try/except around catalog loading
    print("\n--- try/except around catalog loading ---")
    if MAP_EDITOR_DIR.exists():
        for py_file in MAP_EDITOR_DIR.rglob("*.py"):
            try:
                src = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            lines = src.split("\n")
            for i, line in enumerate(lines):
                if "catalog" in line.lower() and ("try:" in line or "except" in line or "raise" in line):
                    # Show 2 lines context
                    rel = py_file.relative_to(PROJECT_ROOT)
                    print(f"  {rel} L{i+1}: {line.rstrip()}")
                    for j in range(max(0, i - 1), min(len(lines), i + 2)):
                        if j != i:
                            print(f"  {rel} L{j+1}: {lines[j].rstrip()}")
                    print()


# ============================================================================
# STEP 8: catalog loading file/path discovery
# ============================================================================
def step8_catalog_loading_paths() -> None:
    _print_section("STEP 8: catalog loading file/path discovery")
    print("""
Looking for catalog data files (templates, blueprints) that CatalogPanel.store
might load. Common locations: frontend/map_editor/data, frontend/map_editor/catalog,
frontend/map_editor/templates, etc.
""")

    # Search for catalog data files
    catalog_extensions = (".json", ".yaml", ".yml", ".toml")
    catalog_keywords = ("catalog", "blueprint", "template", "objects", "items")

    print("--- candidate catalog data files ---")
    if MAP_EDITOR_DIR.exists():
        for f in MAP_EDITOR_DIR.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix.lower() not in catalog_extensions:
                continue
            name_lower = f.name.lower()
            if any(kw in name_lower for kw in catalog_keywords):
                try:
                    size = f.stat().st_size
                except OSError:
                    size = -1
                rel = f.relative_to(PROJECT_ROOT)
                print(f"  {rel} ({size} bytes)")

    # Search for "catalog_path" / "load_catalog" / "catalog_file" in code
    print("\n--- references to catalog_path / load_catalog / catalog_file in code ---")
    if MAP_EDITOR_DIR.exists():
        for py_file in MAP_EDITOR_DIR.rglob("*.py"):
            try:
                src = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(src.split("\n"), 1):
                if any(kw in line for kw in ["catalog_path", "load_catalog", "catalog_file",
                                              "CatalogStore(", "CatalogStore.load", "store.load",
                                              "store = ", "self.store ="]):
                    rel = py_file.relative_to(PROJECT_ROOT)
                    print(f"  {rel} L{i}: {line.rstrip()}")


# ============================================================================
# STEP 9: Compare launch paths — game_launcher vs other entry points
# ============================================================================
def step9_compare_launch_paths() -> None:
    _print_section("STEP 9: compare launch paths — game_launcher vs other entry points")

    print("""
Find ALL files that instantiate EditorCore or call _launch_editor:
""")
    if not PROJECT_ROOT.exists():
        return

    patterns_to_find = ["EditorCore(", "_launch_editor", "EditorCore.", "from frontend.map_editor"]
    exclude_dirs = {".venv", "node_modules", ".git", "__pycache__", ".pytest_cache", ".ruff_cache"}
    found_in: List[Tuple[Path, int, str]] = []

    for py_file in PROJECT_ROOT.rglob("*.py"):
        if any(part in exclude_dirs for part in py_file.parts):
            continue
        # Skip the probe itself
        if py_file == _THIS:
            continue
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(src.split("\n"), 1):
            for pat in patterns_to_find:
                if pat in line:
                    found_in.append((py_file, i, line.rstrip()))
                    break

    print(f"\nFound {len(found_in)} references:")
    for path, line_no, line in found_in[:30]:
        rel = path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path
        print(f"  {rel} L{line_no}: {line}")

    # Search for editor __main__.py / runner scripts
    print("\n--- editor entry points (__main__.py, run_editor.py, etc.) ---")
    main_candidates = []
    if MAP_EDITOR_DIR.exists():
        for f in MAP_EDITOR_DIR.rglob("*.py"):
            if f.name in ("__main__.py", "run_editor.py", "main.py", "launch.py", "start.py"):
                main_candidates.append(f)
    # also check project root
    for name in ("run_editor.py", "editor_main.py"):
        f = PROJECT_ROOT / name
        if f.exists():
            main_candidates.append(f)

    for f in main_candidates:
        print(f"  {f.relative_to(PROJECT_ROOT) if f.is_relative_to(PROJECT_ROOT) else f}")
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(src.split("\n")[:50], 1):
                print(f"  L{i}: {line.rstrip()}")
        except Exception as e:
            print(f"  [read error: {e}]")


# ============================================================================
# STEP 10: dump of editor_core.py imports section (top of file)
# ============================================================================
def step10_editor_core_imports() -> None:
    _print_section("STEP 10: editor_core.py imports section (L1-60)")
    for line in _read_lines(EDITOR_CORE, 1, 60):
        print(line)


# ============================================================================
# STEP 11: verdict — root cause analysis
# ============================================================================
def step11_verdict_root_cause() -> None:
    _print_section("STEP 11: VERDICT — root cause analysis (PROPOSAL based on findings)")

    print("""
Based on findings above, the root cause analysis should answer:

1. WHERE CatalogPanel.store is created:
   - Search Step 2 for ".store = " assignments
   - Search Step 8 for "CatalogStore(" instantiations

2. WHO owns the store:
   - Is it a global module-level variable?
   - Is it created in EditorCore.__init__?
   - Is it created in CatalogPanel.__init__?
   - Is it passed from game_launcher.py?

3. HOW BlueprintEditor receives store:
   - Step 3 shows BlueprintEditor.__init__ signature
   - Step 1 shows L400 assertion + how _store is obtained

4. WHY store is None when launched via game_launcher.py:
   - Step 5 shows _launch_editor code
   - If game_launcher instantiates EditorCore without prior CatalogPanel setup → store=None
   - Step 9 may reveal other launch paths that DO set up store properly

5. WHETHER recent git changes caused the regression:
   - Step 6 shows git log for editor_core.py and related files

6. CIRCULAR IMPORTS / lazy init:
   - Step 7 shows TYPE_CHECKING and lazy patterns

7. DIFFERENCE between launcher and other launch paths:
   - Step 9 compares all EditorCore instantiation points

INSPECT THE FINDINGS ABOVE AND DERIVE THE ROOT CAUSE.

A common pattern in such bugs:
  - EditorCore.__init__ calls _init_ui() which creates BlueprintEditor
  - BlueprintEditor expects CatalogPanel.store to be set
  - CatalogPanel is created BEFORE BlueprintEditor in _init_ui
  - But if CatalogPanel.store assignment is conditional (try/except, or
    depends on a file that doesn't exist, or depends on a path that
    differs when run via game_launcher vs. directly), then store=None
    → AssertionError at L400

PROPOSED FIX STRUCTURE (will be detailed after root cause confirmation):
  - Identify the exact line where .store should be assigned
  - Identify the failure mode (file not found? path resolution? conditional?)
  - Fix the contract: ensure store is ALWAYS loaded before BlueprintEditor
  - Do NOT remove the assertion (it's a valid invariant)
  - Do NOT use dummy store
""")


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-EDITOR-STORE-INIT archaeology probe — READ-ONLY")
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"EDITOR_CORE: {EDITOR_CORE}")
    print(f"GAME_LAUNCHER: {GAME_LAUNCHER}")
    print(f"MAP_EDITOR_DIR: {MAP_EDITOR_DIR}")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)

    try:
        step1_assertion_context()
    except Exception as e:
        print(f"[step1 error: {e}]")
        traceback.print_exc()

    try:
        step2_catalog_panel_class()
    except Exception as e:
        print(f"[step2 error: {e}]")
        traceback.print_exc()

    try:
        step3_blueprint_editor_class()
    except Exception as e:
        print(f"[step3 error: {e}]")
        traceback.print_exc()

    try:
        step4_editor_core_init()
    except Exception as e:
        print(f"[step4 error: {e}]")
        traceback.print_exc()

    try:
        step5_game_launcher_launch_editor()
    except Exception as e:
        print(f"[step5 error: {e}]")
        traceback.print_exc()

    try:
        step6_git_log_recent_changes()
    except Exception as e:
        print(f"[step6 error: {e}]")
        traceback.print_exc()

    try:
        step7_circular_imports_and_lazy_init()
    except Exception as e:
        print(f"[step7 error: {e}]")
        traceback.print_exc()

    try:
        step8_catalog_loading_paths()
    except Exception as e:
        print(f"[step8 error: {e}]")
        traceback.print_exc()

    try:
        step9_compare_launch_paths()
    except Exception as e:
        print(f"[step9 error: {e}]")
        traceback.print_exc()

    try:
        step10_editor_core_imports()
    except Exception as e:
        print(f"[step10 error: {e}]")
        traceback.print_exc()

    try:
        step11_verdict_root_cause()
    except Exception as e:
        print(f"[step11 error: {e}]")
        traceback.print_exc()

    # Integrity check
    print()
    print("=" * 78)
    print("INTEGRITY CHECK — verifying all Steps 1-11 present in output buffer")
    print("=" * 78)

    captured = _stdout_buf.getvalue()
    required_sections = [
        "STEP 1: editor_core.py around L380-420",
        "STEP 2: CatalogPanel class",
        "STEP 3: BlueprintEditor class",
        "STEP 4: EditorCore.__init__ and _init_ui",
        "STEP 5: game_launcher.py _launch_editor",
        "STEP 6: git log",
        "STEP 7: circular imports and lazy initialization",
        "STEP 8: catalog loading file/path discovery",
        "STEP 9: compare launch paths",
        "STEP 10: editor_core.py imports section",
        "STEP 11: VERDICT",
    ]
    print(f"\nCaptured stdout buffer: {len(captured)} chars, {len(captured.split(chr(10)))} lines")
    print()
    print("Section presence check:")
    all_present = True
    for sec in required_sections:
        present = sec in captured
        marker = "✓" if present else "✗ MISSING"
        print(f"  {marker}  {sec}")
        if not present:
            all_present = False

    print()
    if all_present:
        print(">>> ALL STEPS PRESENT IN OUTPUT FILE <<<")
    else:
        print(">>> SOME STEPS MISSING — investigate probe execution <<<")

    try:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(captured)
            f.write("\n\n")
            f.write("=" * 78 + "\n")
            f.write("STDERR (probe-level errors / traceback only):\n")
            f.write("=" * 78 + "\n")
            f.write(_stderr_buf.getvalue())
        size = OUT_FILE.stat().st_size
        print(f"\n>>> Output written to: {OUT_FILE}")
        print(f">>> File size: {size} bytes ({size / 1024:.1f} KB)")
    except Exception as e:
        print(f"\n[ERROR writing output file: {e}]")
        traceback.print_exc()

    return 0 if all_present else 1


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        rc = 1
    finally:
        sys.stdout = _orig_stdout
        sys.stderr = _orig_stderr
    sys.exit(rc)
