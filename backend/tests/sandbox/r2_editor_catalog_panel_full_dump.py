# backend/tests/sandbox/r2_editor_catalog_panel_full_dump.py
"""
R2-EDITOR-CATALOG-PANEL full dump — read-only.

Цель: получить полный код catalog_panel.py, чтобы:
  1. Установить имя метода, содержащего `self._store = AssetStore(...)`
  2. Проверить, вызывается ли этот метод из __init__ (или вынесен)
  3. Найти @property store (как EditorCore получает доступ)
  4. Проверить существование каталога frontend/map_editor/assets/

Также:
  - Все вызовы этого метода по всему проекту
  - Содержимое frontend/map_editor/assets/ (если каталог пустой — это объяснит None)

Запись в файл: r2_catalog_panel_full.txt
"""
from __future__ import annotations
import os, sys, traceback
from pathlib import Path
from typing import List, Tuple
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
CATALOG_PANEL = PROJECT_ROOT / "frontend/map_editor/ui/catalog_panel.py"
EDITOR_CORE = PROJECT_ROOT / "frontend/map_editor/editor_core.py"
ASSETS_DIR = PROJECT_ROOT / "frontend/map_editor/assets"
PIXELS_DIR = PROJECT_ROOT / "frontend/map_editor/pixels"

OUT_FILE_DIR = Path("/home/z/my-project/download")
if not OUT_FILE_DIR.exists() or not OUT_FILE_DIR.is_dir():
    OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
    try:
        OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        OUT_FILE_DIR = Path(os.getcwd())
OUT_FILE = OUT_FILE_DIR / "r2_catalog_panel_full.txt"


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


def _grep_in_dir(directory: Path, patterns: List[str], file_exts: List[str] = (".py",)) -> List[Tuple[Path, int, str]]:
    out: List[Tuple[Path, int, str]] = []
    if not directory.exists():
        return out
    for f in directory.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in file_exts:
            continue
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(src.split("\n"), 1):
            for pat in patterns:
                if pat in line:
                    out.append((f, i, line.rstrip()))
                    break
    return out


def main() -> int:
    print("=" * 78)
    print("R2-EDITOR-CATALOG-PANEL full dump — read-only")
    print(f"PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"CATALOG_PANEL: {CATALOG_PANEL}")
    print(f"ASSETS_DIR: {ASSETS_DIR}")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)

    # === STEP 1: Full catalog_panel.py ===
    _print_section("STEP 1: catalog_panel.py — FULL DUMP (every line)")
    if not CATALOG_PANEL.exists():
        print(f"[file not found: {CATALOG_PANEL}]")
        return 1
    src = CATALOG_PANEL.read_text(encoding="utf-8", errors="replace")
    lines = src.split("\n")
    print(f"\nTotal lines: {len(lines)}")
    print(f"Total chars: {len(src)}")
    print()
    for i, line in enumerate(lines, 1):
        print(f"L{i:4d}: {line}")

    # === STEP 2: Find the method containing `self._store = AssetStore(...)` ===
    _print_section("STEP 2: Find method containing `self._store = AssetStore(...)` (L100)")
    target_line = None
    for i, line in enumerate(lines, 1):
        if "self._store = AssetStore" in line:
            target_line = i
            break
    if target_line is None:
        print("[L100 not found — file may have changed]")
    else:
        print(f"\nFound at L{target_line}: {lines[target_line - 1]}")
        # Walk backwards to find containing `def`
        containing_def_line = None
        containing_def_text = None
        for j in range(target_line - 1, -1, -1):
            line_j = lines[j]
            if line_j.lstrip().startswith("def ") or line_j.lstrip().startswith("async def "):
                containing_def_line = j + 1
                containing_def_text = line_j.rstrip()
                break
        if containing_def_line:
            print(f"\nContaining method: L{containing_def_line}: {containing_def_text}")
            # Show full method body
            print(f"\n--- Full method body (L{containing_def_line} onwards, ~30 lines) ---")
            for j in range(containing_def_line - 1, min(containing_def_line + 29, len(lines))):
                print(f"L{j+1:4d}: {lines[j]}")

    # === STEP 3: Check if this method is called from __init__ ===
    _print_section("STEP 3: Is the load/activate method called from __init__?")
    if containing_def_text:
        # Extract method name
        import re
        match = re.search(r"def\s+(\w+)\s*\(", containing_def_text)
        if match:
            method_name = match.group(1)
            print(f"\nMethod name: {method_name}")
            print(f"\nSearching for self.{method_name}() calls in catalog_panel.py __init__...")
            # Show __init__ lines (first 50 lines of class body, looking for self.method_name())
            for i, line in enumerate(lines, 1):
                if f"self.{method_name}(" in line or f"self.{method_name} ()" in line:
                    print(f"  L{i}: {line.rstrip()}")
            print()
            if not any(f"self.{method_name}(" in l for l in lines[:80]):
                print(f"  >>> '{method_name}()' is NOT called from catalog_panel.py __init__ or first 80 lines")
                print(f"  >>> This means: after CatalogPanel(...) constructor, _store is STILL None")
                print(f"  >>> Editor must explicitly call catalog_panel.{method_name}() to load store")

            # Search across all frontend/map_editor for callers
            print(f"\n--- All callers of self.{method_name}() / catalog_panel.{method_name}() across project ---")
            caller_patterns = [f".{method_name}()"]
            results = _grep_in_dir(PROJECT_ROOT / "frontend", caller_patterns)
            for path, ln, line in results:
                # Skip self-calls inside catalog_panel.py
                if path == CATALOG_PANEL:
                    continue
                rel = path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path
                print(f"  {rel} L{ln}: {line}")

    # === STEP 4: Find @property store ===
    _print_section("STEP 4: @property store — how EditorCore accesses self.catalog_panel.store")
    print("\nSearching for `def store` or `@property` near `store` in catalog_panel.py...")
    for i, line in enumerate(lines, 1):
        if "@property" in line:
            # Check next 3 lines for `def store`
            for j in range(i, min(i + 4, len(lines) + 1)):
                if "def store" in lines[j - 1] if j - 1 < len(lines) else "":
                    print(f"\nFound @property at L{i}: {line.rstrip()}")
                    for k in range(i - 1, min(i + 6, len(lines))):
                        print(f"L{k+1:4d}: {lines[k]}")
                    break
        elif "def store" in line and "@property" in (lines[i - 2] if i >= 2 else ""):
            print(f"\nFound def store at L{i}: {line.rstrip()}")

    # Also: explicit `store` attribute access
    print("\n--- `def store` (any decorator) in catalog_panel.py ---")
    for i, line in enumerate(lines, 1):
        if "def store" in line:
            print(f"  L{i}: {line.rstrip()}")
            # Show 5 lines around
            for j in range(max(0, i - 2), min(len(lines), i + 5)):
                if j != i - 1:
                    print(f"  L{j+1}: {lines[j].rstrip()}")

    # === STEP 5: Check assets/ directory exists & is non-empty ===
    _print_section("STEP 5: Check frontend/map_editor/assets/ directory")
    if not ASSETS_DIR.exists():
        print(f"[assets/ directory does NOT exist: {ASSETS_DIR}]")
        print(">>> This would explain store.load() doing nothing or raising.")
    else:
        print(f"Found: {ASSETS_DIR}")
        items = sorted(ASSETS_DIR.iterdir())
        print(f"Items in assets/: {len(items)}")
        for item in items[:30]:
            print(f"  {item.name}/{'(dir)' if item.is_dir() else ''}")
        if len(items) > 30:
            print(f"  ... and {len(items) - 30} more")

        # Look for catalog/blueprint JSON files
        print("\n--- JSON files in assets/ (catalog/blueprint candidates) ---")
        json_files = sorted(ASSETS_DIR.rglob("*.json"))
        print(f"Total JSON files: {len(json_files)}")
        for jf in json_files[:20]:
            try:
                size = jf.stat().st_size
            except OSError:
                size = -1
            rel = jf.relative_to(PROJECT_ROOT) if jf.is_relative_to(PROJECT_ROOT) else jf
            print(f"  {rel} ({size} bytes)")
        if len(json_files) > 20:
            print(f"  ... and {len(json_files) - 20} more")

    # === STEP 6: editor_core.py lines around L380-410 (assertion context) ===
    _print_section("STEP 6: editor_core.py L370-410 (assertion + immediate context)")
    if EDITOR_CORE.exists():
        ecore_src = EDITOR_CORE.read_text(encoding="utf-8", errors="replace")
        elines = ecore_src.split("\n")
        for j in range(370, min(410, len(elines))):
            print(f"L{j+1:4d}: {elines[j]}")

    # === STEP 7: All callers of AssetStore() constructor in frontend/map_editor ===
    _print_section("STEP 7: All AssetStore() constructor calls in frontend/map_editor")
    print("\nSearching for `AssetStore(` instantiations...")
    results = _grep_in_dir(PROJECT_ROOT / "frontend/map_editor", ["AssetStore("])
    for path, ln, line in results:
        rel = path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path
        print(f"  {rel} L{ln}: {line}")

    # === STEP 8: VERDICT ===
    _print_section("STEP 8: VERDICT — root cause analysis")

    print(f"""
ANALYSIS:

  1. CatalogPanel.__init__ sets self._store = None  (catalog_panel.py L40)
  2. Real store loading happens on L100-101 in method: '{containing_def_text if containing_def_text else "(unknown)"}'
  3. The load method is {'NOT' if not any(f'self.{method_name}(' in l for l in lines[:80]) else ''} called from __init__
  4. editor_core.py L385-392 calls CatalogPanel(...) but does NOT call the load method
  5. editor_core.py L399 accesses self.catalog_panel.store → returns None
  6. L400 assertion fails

ROOT CAUSE (hypothesis to confirm):
  CatalogPanel was refactored (likely in commits 556d239e, cb3febad, or 72fc49e3)
  to move store.load() out of __init__ into a separate method (e.g. load() or activate()).
  editor_core.py was NOT updated to call this method explicitly.
  Therefore, when EditorCore creates CatalogPanel and immediately reads .store,
  _store is still None.

PROPOSED FIX (will detail after method name confirmation):
  Add explicit call in editor_core.py between L392 (CatalogPanel created) and L399 (read .store):
    self.catalog_panel.<method_name>()   # ← ADD THIS LINE
  This is a one-line fix that restores the contract:
  store MUST be loaded before BlueprintEditor reads it.

  The assertion at L400 should NOT be removed — it correctly enforces the invariant.
  No dummy store, no fake catalog.
""")

    # Write to file
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
