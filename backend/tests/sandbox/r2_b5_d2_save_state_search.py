"""
R2-B5-D2 — B4-R9 Stage 1: Find B4-R8 save state (read-only).

Цель: найти сохранение кампании Open_road, которое было активно во время B4-R8
(08/11/2026 14:29), проверить, содержит ли оно epistemic_records с убеждением
Торнина (player INSULTED tavern_keeper_tornin, conf~0.6212, source=blacksmith_orm,
original=player, type=testimony).

READ-ONLY. Не изменяет сохранения. Не меняет production-код.
"""
from __future__ import annotations

import os
import sys
import io
import json
import traceback
import shutil
import tempfile
import logging
import inspect
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

try:
    from app.core.config import settings
except Exception as e:
    print(f"[FATAL] Cannot import app.core.config: {e}")
    sys.exit(2)

OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_save_state_search.txt"


class TeeStream:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            try: s.write(data)
            except Exception: pass
    def flush(self):
        for s in self.streams:
            try: s.flush()
            except Exception: pass


_stdout_buf = io.StringIO()
_orig_stdout = sys.stdout
sys.stdout = TeeStream(_orig_stdout, _stdout_buf)


def _section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _safe_json_loads(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except Exception:
        return None


def _print_belief_record(r: Any, indent: str = "    ") -> None:
    try:
        if isinstance(r, dict):
            prop = r.get("proposition", {})
            subj = prop.get("subject_id", "?")
            pred = prop.get("predicate", "?")
            obj = prop.get("object_id", "?")
            polarity = prop.get("polarity", "?")
            conf = r.get("confidence", "?")
            source_id = r.get("source_id", "?")
            source_type = r.get("source_type", "?")
            original_source_id = r.get("original_source_id", "?")
            source_claim_id = r.get("source_claim_id", "?")
            first_observed = r.get("first_observed_tick", "?")
            last_updated = r.get("last_updated_tick", "?")
            agent_id = r.get("agent_id", "?")
        else:
            prop = r.proposition
            subj = getattr(prop, "subject_id", "?")
            pred = getattr(prop, "predicate", "?")
            if hasattr(pred, "value"):
                pred = pred.value
            obj = getattr(prop, "object_id", "?")
            polarity = getattr(prop, "polarity", "?")
            conf = getattr(r, "confidence", "?")
            source_id = getattr(r, "source_id", "?")
            source_type = getattr(r, "source_type", "?")
            original_source_id = getattr(r, "original_source_id", "?")
            source_claim_id = getattr(r, "source_claim_id", "?")
            first_observed = getattr(r, "first_observed_tick", "?")
            last_updated = getattr(r, "last_updated_tick", "?")
            agent_id = getattr(r, "agent_id", "?")
        print(f"{indent}agent_id={agent_id}")
        print(f"{indent}prop=({subj}, {pred}, {obj}, polarity={polarity})")
        print(f"{indent}  confidence={conf}")
        print(f"{indent}  source_id={source_id}")
        print(f"{indent}  source_type={source_type}")
        print(f"{indent}  original_source_id={original_source_id}")
        print(f"{indent}  source_claim_id={source_claim_id}")
        print(f"{indent}  first_observed_tick={first_observed}")
        print(f"{indent}  last_updated_tick={last_updated}")
    except Exception as e:
        print(f"{indent}<ERROR printing record: {e}>")


def _scan_dir_for_epistemic(d: Path, label: str, max_depth: int = 4) -> list[tuple[Path, dict]]:
    findings: list[tuple[Path, dict]] = []
    if not d.exists() or max_depth <= 0:
        return findings
    try:
        for entry in d.iterdir():
            if entry.is_dir():
                if entry.name in {"__pycache__", ".git", "node_modules", ".venv"}:
                    continue
                findings.extend(_scan_dir_for_epistemic(entry, label, max_depth - 1))
            elif entry.is_file() and entry.suffix.lower() in {".json", ".jsonl"}:
                try:
                    size = entry.stat().st_size
                    if size > 50 * 1024 * 1024:
                        continue
                except Exception:
                    continue
                try:
                    with open(entry, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except Exception:
                    continue
                if "epistemic" not in content.lower():
                    continue
                if entry.suffix.lower() == ".json":
                    obj = _safe_json_loads(content)
                    if obj and isinstance(obj, dict):
                        if "epistemic_records" in obj or "epistemic_store" in obj:
                            findings.append((entry, obj))
                            print(f"  [{label}] FOUND epistemic in: {entry}")
                            continue
                        for k1, v1 in obj.items():
                            if isinstance(v1, dict) and ("epistemic_records" in v1 or "epistemic_store" in v1):
                                findings.append((entry, v1))
                                print(f"  [{label}] FOUND epistemic (nested key={k1}) in: {entry}")
                                break
                            if isinstance(v1, dict):
                                for k2, v2 in v1.items():
                                    if isinstance(v2, dict) and ("epistemic_records" in v2 or "epistemic_store" in v2):
                                        findings.append((entry, v2))
                                        print(f"  [{label}] FOUND epistemic (nested2 k1={k1} k2={k2}) in: {entry}")
                                        break
                                if findings and findings[-1][0] == entry:
                                    break
                elif entry.suffix.lower() == ".jsonl":
                    try:
                        for line_num, line in enumerate(content.split("\n")[:1000]):
                            if not line.strip():
                                continue
                            obj = _safe_json_loads(line)
                            if obj and isinstance(obj, dict) and (
                                "epistemic_records" in obj or "epistemic_store" in obj
                            ):
                                findings.append((entry, obj))
                                print(f"  [{label}] FOUND epistemic in JSONL line {line_num+1}: {entry}")
                                break
                    except Exception:
                        pass
    except Exception as e:
        print(f"  [{label}] scan error in {d}: {e}")
    return findings


def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 — B4-R9 Stage 1: Find B4-R8 save state")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("Цель: найти сохранение Open_road, активное во время B4-R8")
    print("(08/11/2026 14:29), проверить, содержит ли оно epistemic_records")
    print("с убеждением Торнина.")
    print()
    print("READ-ONLY. Не изменяет сохранения.")
    print()

    project_root = _BACKEND.parent
    print(f"  project root: {project_root}")
    print(f"  backend dir:  {_BACKEND}")
    print(f"  settings.data_dir: {settings.data_dir}")
    print(f"  settings.saves_dir: {settings.saves_dir}")
    print()

    _section("STEP 1: List candidate save locations")

    candidate_dirs: list[tuple[str, Path]] = []
    candidate_dirs.append(("settings.saves_dir", Path(settings.saves_dir)))
    candidate_dirs.append(("settings.data_dir", Path(settings.data_dir)))
    candidate_dirs.append(("backend/saves", _BACKEND / "saves"))
    candidate_dirs.append(("backend/data/saves", _BACKEND / "data" / "saves"))
    candidate_dirs.append(("backend/data/sessions", _BACKEND / "data" / "sessions"))
    candidate_dirs.append(("backend/data/campaigns", _BACKEND / "data" / "campaigns"))
    candidate_dirs.append(("backend/data", _BACKEND / "data"))

    for label, p in candidate_dirs:
        exists = p.exists()
        print(f"  {label:30s}: {p} (exists={exists})")
        if exists:
            try:
                items = list(p.iterdir())
                print(f"    {len(items)} entries: {[i.name for i in items[:15]]}")
            except Exception as e:
                print(f"    ERROR listing: {e}")
    print()

    _section("STEP 2: Files modified on 08/11/2026 (B4-R8 day, 14:29±3h)")

    b4r8_window_start = datetime(2026, 11, 8, 11, 0)
    b4r8_window_end = datetime(2026, 11, 8, 17, 0)
    print(f"  Window: {b4r8_window_start} to {b4r8_window_end}")
    print()

    matching_files: list[tuple[Path, datetime, int]] = []
    for search_root in [_BACKEND / "saves", _BACKEND / "data", _BACKEND / "tests"]:
        if not search_root.exists():
            continue
        try:
            for entry in search_root.rglob("*"):
                if not entry.is_file():
                    continue
                if entry.suffix.lower() not in {".json", ".jsonl", ".sqlite", ".db"}:
                    continue
                try:
                    mtime = datetime.fromtimestamp(entry.stat().st_mtime)
                    if b4r8_window_start <= mtime <= b4r8_window_end:
                        matching_files.append((entry, mtime, entry.stat().st_size))
                except Exception:
                    continue
        except Exception as e:
            print(f"  ERROR scanning {search_root}: {e}")

    matching_files.sort(key=lambda x: x[1])
    print(f"  Found {len(matching_files)} files modified in B4-R8 window:")
    for f, mtime, size in matching_files:
        marker = " <<<" if "open_road" in str(f).lower() or "campaign" in str(f).lower() else ""
        print(f"    {mtime.strftime('%H:%M:%S')}  {size:>10} bytes  {f}{marker}")
    print()

    _section("STEP 3: Scan candidate dirs for 'epistemic_records' / 'epistemic_store'")

    all_findings: list[tuple[str, Path, dict]] = []
    for label, p in candidate_dirs:
        if not p.exists():
            continue
        print(f"\n  --- scanning {label}: {p} ---")
        findings = _scan_dir_for_epistemic(p, label, max_depth=4)
        for fpath, obj in findings:
            all_findings.append((label, fpath, obj))

    print()
    print(f"  TOTAL findings: {len(all_findings)}")
    print()

    _section("STEP 4: Inspect findings — look for Tornin's INSULTED belief")

    target_signature = {
        "subject_id": "player",
        "predicate": "insulted",
        "object_id": "tavern_keeper_tornin",
    }
    tornin_finds: list[tuple[str, Path, dict]] = []

    for label, fpath, obj in all_findings:
        print(f"\n  --- {label}: {fpath} ---")
        ep_data = obj.get("epistemic_records") or obj.get("epistemic_store")
        if ep_data is None:
            print(f"    (no epistemic data)")
            continue

        if isinstance(ep_data, list):
            print(f"    epistemic_records: list of {len(ep_data)} entries")
            for r in ep_data:
                if not isinstance(r, dict):
                    continue
                prop = r.get("proposition", {})
                if (prop.get("subject_id") == target_signature["subject_id"]
                    and prop.get("predicate") == target_signature["predicate"]
                    and prop.get("object_id") == target_signature["object_id"]):
                    print(f"    >>> MATCH! Tornin's INSULTED belief:")
                    _print_belief_record(r, indent="      ")
                    tornin_finds.append((label, fpath, r))
        elif isinstance(ep_data, dict):
            for agent_id, records in ep_data.items():
                if not isinstance(records, list):
                    continue
                for r in records:
                    if not isinstance(r, dict):
                        continue
                    prop = r.get("proposition", {})
                    if (prop.get("subject_id") == target_signature["subject_id"]
                        and prop.get("predicate") == target_signature["predicate"]
                        and prop.get("object_id") == target_signature["object_id"]):
                        print(f"    >>> MATCH (agent={agent_id})! Tornin's INSULTED belief:")
                        _print_belief_record(r, indent="      ")
                        tornin_finds.append((label, fpath, r))

    print()
    print(f"  TOTAL Tornin INSULTED finds: {len(tornin_finds)}")
    print()

    _section("STEP 5: Match against B4-R8 signature")

    print("  B4-R8 expected (from b4r1_results.json):")
    print("    agent_id: tavern_keeper_tornin")
    print("    proposition: (player, insulted, tavern_keeper_tornin, polarity=true)")
    print("    confidence: ~0.6212 (0.6212214285714286)")
    print("    source_id: blacksmith_orm")
    print("    original_source_id: player")
    print("    source_type: testimony")
    print("    first_observed_tick: 0")
    print("    last_updated_tick: 22")
    print()

    b4r8_match_count = 0
    for label, fpath, r in tornin_finds:
        print(f"\n  --- Checking {fpath} ---")
        conf = r.get("confidence")
        source_id = r.get("source_id")
        original = r.get("original_source_id")
        source_type = r.get("source_type")
        agent_id = r.get("agent_id")

        print(f"    agent_id: {agent_id}")
        print(f"    confidence: {conf}")
        print(f"    source_id: {source_id}")
        print(f"    original_source_id: {original}")
        print(f"    source_type: {source_type}")

        match_agent = agent_id == "tavern_keeper_tornin"
        match_source = source_id == "blacksmith_orm"
        match_original = original == "player"
        match_type = source_type == "testimony"
        try:
            match_conf = abs(float(conf) - 0.6212214285714286) < 0.01
        except Exception:
            match_conf = False

        all_match = match_agent and match_source and match_original and match_type and match_conf
        if all_match:
            b4r8_match_count += 1
            print(f"    >>> B4-R8 MATCH: ALL FIELDS CONFIRMED")
        else:
            print(f"    match_agent={match_agent} match_source={match_source} "
                  f"match_original={match_original} match_type={match_type} match_conf={match_conf}")
            if not all_match:
                print(f"    (partial match — but not exact B4-R8 signature)")

    print()
    print(f"  TOTAL B4-R8 exact matches: {b4r8_match_count}")
    print()

    _section("STEP 6: Check SQLite databases for epistemic_records")

    sqlite_dbs: list[Path] = []
    for search_root in [_BACKEND / "saves", _BACKEND / "data"]:
        if not search_root.exists():
            continue
        try:
            for entry in search_root.rglob("*.db"):
                if entry.is_file():
                    sqlite_dbs.append(entry)
            for entry in search_root.rglob("*.sqlite"):
                if entry.is_file():
                    sqlite_dbs.append(entry)
        except Exception:
            pass

    print(f"  Found {len(sqlite_dbs)} SQLite databases:")
    for db in sqlite_dbs:
        try:
            size = db.stat().st_size
            mtime = datetime.fromtimestamp(db.stat().st_mtime)
            print(f"    {mtime.strftime('%Y-%m-%d %H:%M:%S')}  {size:>10} bytes  {db}")
        except Exception as e:
            print(f"    ERROR: {db}: {e}")

    if sqlite_dbs:
        print()
        print("  --- Querying each DB for epistemic records ---")
        try:
            import sqlite3
            for db in sqlite_dbs:
                print(f"\n  Database: {db}")
                try:
                    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                    cur = conn.cursor()
                    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                    tables = [r[0] for r in cur.fetchall()]
                    print(f"    tables: {tables}")
                    if "state_kv" in tables:
                        cur.execute("SELECT key FROM state_kv ORDER BY key")
                        keys = [r[0] for r in cur.fetchall()]
                        print(f"    state_kv keys: {len(keys)} total")
                        epistemic_keys = [k for k in keys if "epistemic" in k.lower()]
                        print(f"    epistemic-related keys: {epistemic_keys}")
                        for k in epistemic_keys[:5]:
                            cur.execute("SELECT value FROM state_kv WHERE key = ?", (k,))
                            row = cur.fetchone()
                            if row:
                                val = row[0]
                                print(f"    key={k}: value length={len(val) if val else 0}")
                                if val and "tavern_keeper_tornin" in val and "insulted" in val.lower():
                                    print(f"      >>> Contains 'tavern_keeper_tornin' + 'insulted'!")
                                    print(f"      --- first 2000 chars ---")
                                    print(f"      {val[:2000]}")
                                    parsed = _safe_json_loads(val)
                                    if parsed is None:
                                        try:
                                            import ast
                                            parsed = ast.literal_eval(val)
                                        except Exception:
                                            pass
                                    if parsed:
                                        if isinstance(parsed, list):
                                            print(f"      parsed as list, len={len(parsed)}")
                                            for r in parsed:
                                                if isinstance(r, dict):
                                                    prop = r.get("proposition", {})
                                                    if (prop.get("object_id") == "tavern_keeper_tornin"
                                                        and prop.get("predicate") == "insulted"):
                                                        print(f"      >>> MATCH: Tornin's INSULTED belief")
                                                        _print_belief_record(r, indent="        ")
                                        elif isinstance(parsed, dict):
                                            print(f"      parsed as dict, keys={list(parsed.keys())[:10]}")
                                    else:
                                        print(f"      (cannot parse as JSON or Python literal)")
                    for tbl in tables:
                        if "epistemic" in tbl.lower():
                            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
                            cnt = cur.fetchone()[0]
                            print(f"    table {tbl}: {cnt} rows")
                    conn.close()
                except Exception as e:
                    print(f"    ERROR querying: {e}")
        except ImportError:
            print("  sqlite3 module not available")
    print()

    _section("STEP 7: Check scene_state keys in enigma_runtime.db")

    runtime_db = _BACKEND / "saves" / "enigma_runtime.db"
    if not runtime_db.exists():
        runtime_db = _BACKEND / "data" / "saves" / "enigma_runtime.db"
    if not runtime_db.exists():
        for d in [_BACKEND / "saves", _BACKEND / "data"]:
            if d.exists():
                for f in d.rglob("enigma_runtime*.db"):
                    runtime_db = f
                    break

    print(f"  runtime_db: {runtime_db}")
    print(f"  exists: {runtime_db.exists() if runtime_db else 'N/A'}")

    if runtime_db and runtime_db.exists():
        try:
            import sqlite3
            print(f"  Size: {runtime_db.stat().st_size} bytes")
            print(f"  Modified: {datetime.fromtimestamp(runtime_db.stat().st_mtime)}")
            print()
            conn = sqlite3.connect(f"file:{runtime_db}?mode=ro", uri=True)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [r[0] for r in cur.fetchall()]
            print(f"  tables: {tables}")

            if "state_kv" in tables:
                cur.execute("SELECT key, length(value) FROM state_kv ORDER BY key")
                rows = cur.fetchall()
                print(f"  state_kv entries: {len(rows)}")
                for k, vlen in rows[:50]:
                    marker = " <<<" if "epistemic" in k.lower() or "tavern" in k.lower() else ""
                    print(f"    {k}: {vlen} bytes{marker}")

                print()
                print("  --- Looking for Open_road scene state keys ---")
                cur.execute("SELECT key FROM state_kv WHERE key LIKE '%Open_road%' OR key LIKE '%open_road%'")
                keys = [r[0] for r in cur.fetchall()]
                print(f"  Open_road keys: {keys}")

                for key_pattern in ["scene:Open_road:tavern", "scene:open_road:tavern"]:
                    cur.execute("SELECT value FROM state_kv WHERE key = ?", (key_pattern,))
                    row = cur.fetchone()
                    if row:
                        val = row[0]
                        print(f"\n  key={key_pattern}: value length={len(val)}")
                        if "epistemic" in val.lower():
                            print(f"    >>> Contains 'epistemic'!")
                            lower_val = val.lower()
                            idx = lower_val.find("epistemic")
                            if idx >= 0:
                                start = max(0, idx - 100)
                                end = min(len(val), idx + 5000)
                                print(f"    --- context (chars {start}..{end}) ---")
                                print(f"    {val[start:end]}")

                        parsed = _safe_json_loads(val)
                        if parsed and isinstance(parsed, dict):
                            print(f"    parsed dict keys: {list(parsed.keys())[:15]}")
                            if "epistemic_records" in parsed:
                                er = parsed["epistemic_records"]
                                print(f"    epistemic_records type: {type(er).__name__}")
                                if isinstance(er, list):
                                    print(f"    epistemic_records count: {len(er)}")
                                    for r in er:
                                        if isinstance(r, dict):
                                            prop = r.get("proposition", {})
                                            if (prop.get("object_id") == "tavern_keeper_tornin"
                                                and prop.get("predicate") == "insulted"):
                                                print(f"    >>> MATCH: Tornin's INSULTED belief")
                                                _print_belief_record(r, indent="      ")

            conn.close()
        except Exception as e:
            print(f"  ERROR: {e}")
            traceback.print_exc()
    print()

    _section("STEP 8: Summary")

    print(f"""
  B4-R8 save state search results:
  - Tornin INSULTED belief finds: {len(tornin_finds)}
  - B4-R8 exact signature matches: {b4r8_match_count}

  Next steps depend on findings:
  - If exact match found → load via production-path, run resolve_block
  - If only partial matches → analyze differences
  - If no matches → fallback to Variant A (production-path scenario)
""")

    try:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(_stdout_buf.getvalue())
        size = OUT_FILE.stat().st_size
        print(f">>> Output written to: {OUT_FILE}")
        print(f">>> File size: {size} bytes ({size / 1024:.1f} KB)")
    except Exception as e:
        print(f">>> [ERROR writing output file: {e}]")
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