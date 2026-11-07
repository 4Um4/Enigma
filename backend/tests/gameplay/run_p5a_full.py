"""
P5-A A/B Experiment Runner — self-contained automation.

Запуск (одна команда, Windows PowerShell):

    cd C:\\DDD\\Codex\\VSC_Enigma\\Enigma
    python backend\\tests\\gameplay\\run_p5a_full.py

Скрипт делает ВСЁ сам:
  1. Pre-flight checks (Python, venv, files exist).
  2. LLM-server health check (http://localhost:8181).
  3. Patches p5a_minimal_ab.py with expanded stub detection (backup .bak).
  4. Runs A and B subprocess scenarios.
  5. Parses summary.json + per-scenario JSONs.
  6. Extracts Tornin's speeches, cognition blocks, LLM-degraded info.
  7. Prints structured final report with verdict.
  8. Saves combined report to p5a_experiment_result.json.

Если LLM-сервер недоступен — скрипт выводит инструкцию по запуску и exit(2).
Никаких ручных шагов после запуска не требуется.

Выходные коды:
  0 — GREEN (эксперимент успешен, обе реплики получены)
  1 — YELLOW (частичный успех: stub/degraded, но не RED)
  2 — RED или infrastructure failure (LLM-server down, baseline polluted, и т.д.)
"""
from __future__ import annotations

import os
import re
import sys
import json
import time
import shutil
import argparse
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any


# ============================================================================
# Constants
# ============================================================================

# Path setup — script lives in backend/tests/gameplay/
_HERE = Path(os.path.dirname(os.path.abspath(__file__)))
_BACKEND_ROOT = _HERE.parent.parent                    # backend/
_PROJECT_ROOT = _BACKEND_ROOT.parent                    # Enigma/
SCENARIO_SCRIPT = _HERE / "p5a_minimal_ab.py"
SCENARIO_SCRIPT_BAK = _HERE / "p5a_minimal_ab.py.bak"
SUMMARY_JSON = _PROJECT_ROOT / "p5a_minimal_ab_summary.json"
SCENARIO_A_JSON = _PROJECT_ROOT / "p5a_minimal_ab_A.json"
SCENARIO_B_JSON = _PROJECT_ROOT / "p5a_minimal_ab_B.json"
SCENARIO_A_LOG = _PROJECT_ROOT / "p5a_minimal_ab_A.log"
SCENARIO_B_LOG = _PROJECT_ROOT / "p5a_minimal_ab_B.log"
FINAL_REPORT = _PROJECT_ROOT / "p5a_experiment_result.json"

LLM_HEALTH_URL = "http://localhost:8181/health"
LLM_HEALTH_TIMEOUT = 5
LLM_ROOT_URL = "http://localhost:8181/"
SCENARIO_TIMEOUT_SEC = 600


# ============================================================================
# Logging helpers
# ============================================================================

def _log(msg: str, *, level: str = "INFO") -> None:
    print(f"[{level}] {msg}", flush=True)


def _section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}", flush=True)


def _die(msg: str, exit_code: int = 2) -> None:
    _log(msg, level="ERROR")
    sys.exit(exit_code)


# ============================================================================
# Step 1: Pre-flight checks
# ============================================================================

def preflight() -> dict:
    """Verify environment before running anything."""
    _section("STEP 1: PRE-FLIGHT CHECKS")
    info: dict = {}

    # Project root
    info["project_root"] = str(_PROJECT_ROOT)
    _log(f"project_root = {_PROJECT_ROOT}")

    # Python version
    info["python_version"] = sys.version
    info["python_executable"] = sys.executable
    _log(f"python = {sys.executable} ({sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro})")

    # Scenario script exists?
    if not SCENARIO_SCRIPT.exists():
        _die(f"scenario script not found: {SCENARIO_SCRIPT}", exit_code=2)
    info["scenario_script"] = str(SCENARIO_SCRIPT)
    _log(f"scenario_script = {SCENARIO_SCRIPT}")

    # Backend dir exists?
    info["backend_root"] = str(_BACKEND_ROOT)
    if not _BACKEND_ROOT.exists():
        _die(f"backend dir not found: {_BACKEND_ROOT}", exit_code=2)

    # harness.py exists?
    _harness = _BACKEND_ROOT / "tests" / "gameplay" / "harness.py"
    info["harness_py_exists"] = _harness.exists()
    if not _harness.exists():
        _die(f"harness.py not found: {_harness}", exit_code=2)
    _log(f"harness.py = {_harness} (exists)")

    # app/services/llm/router.py exists?
    _router = _BACKEND_ROOT / "app" / "services" / "llm" / "router.py"
    info["router_py_exists"] = _router.exists()
    if not _router.exists():
        _die(f"router.py not found: {_router}", exit_code=2)
    _log(f"router.py = {_router} (exists)")

    # Import test — can we import app.services.llm.router?
    _log("testing import: app.services.llm.router...")
    try:
        # Add backend to sys.path
        if str(_BACKEND_ROOT) not in sys.path:
            sys.path.insert(0, str(_BACKEND_ROOT))
        if str(_PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(_PROJECT_ROOT))
        from app.services.llm.router import initialize_router  # noqa: F401
        _log("import OK: app.services.llm.router.initialize_router")
        info["import_router_ok"] = True
    except Exception as exc:
        _die(f"failed to import app.services.llm.router: {exc}", exit_code=2)

    return info


# ============================================================================
# Step 2: LLM-server health check
# ============================================================================

def check_llm_server() -> dict:
    """Probe localhost:8181 for LLM-server availability."""
    _section("STEP 2: LLM-SERVER HEALTH CHECK")
    info: dict = {"url": LLM_HEALTH_URL}

    # Try /health first
    for url in (LLM_HEALTH_URL, LLM_ROOT_URL):
        try:
            _log(f"GET {url} (timeout={LLM_HEALTH_TIMEOUT}s)...")
            req = urllib.request.Request(url, headers={"User-Agent": "p5a-runner"})
            with urllib.request.urlopen(req, timeout=LLM_HEALTH_TIMEOUT) as resp:
                _status = resp.status
                _body = resp.read(200).decode("utf-8", errors="replace")
                _log(f"  HTTP {_status}, body[:200]={_body!r}")
                info["health_url"] = url
                info["status"] = _status
                info["body"] = _body
                info["available"] = True
                return info
        except urllib.error.URLError as exc:
            _log(f"  URLError: {exc}")
            info["last_error"] = f"URLError: {exc}"
        except Exception as exc:
            _log(f"  error: {type(exc).__name__}: {exc}")
            info["last_error"] = f"{type(exc).__name__}: {exc}"

    info["available"] = False
    _log("", level="ERROR")
    _log("LLM-server is NOT reachable at http://localhost:8181", level="ERROR")
    _log("", level="ERROR")
    _log("To fix — start llama-server BEFORE running this script:", level="ERROR")
    _log("", level="ERROR")
    _log("  Option A (Hermes-3 / qwen_7b):", level="ERROR")
    _log("    llama-server --model C:\\path\\to\\qwen_7b.gguf --port 8181 --host 0.0.0.0", level="ERROR")
    _log("", level="ERROR")
    _log("  Option B (saiga_llama3_8b):", level="ERROR")
    _log("    llama-server --model C:\\path\\to\\saiga_llama3_8b.gguf --port 8181 --host 0.0.0.0", level="ERROR")
    _log("", level="ERROR")
    _log("  Verify:", level="ERROR")
    _log("    curl http://localhost:8181/health", level="ERROR")
    _log("    (or PowerShell: Invoke-WebRequest http://localhost:8181/health -UseBasicParsing)", level="ERROR")
    _log("", level="ERROR")
    _log("After server is up — re-run this script.", level="ERROR")
    return info


# ============================================================================
# Step 3: Patch p5a_minimal_ab.py with expanded stub detection
# ============================================================================

# The expanded stub detection block we want to insert.
EXPANDED_STUB_BLOCK = '''    # Stub detection — expanded markers (auto-patched by run_p5a_full.py)
    _stub_markers = [
        "[Заглушка]", "[stub]", "Fallback to stub", "ModelRouter is None",
        "движок не ответил", "llm_degraded", "llm failed",
        "degraded", "все модели пула недоступны",
    ]
    result["stub_detected_in_speeches"] = any(
        any(_m.lower() in s["text"].lower() for _m in _stub_markers)
        for s in result["tornin_speeches"]
    )
    _pa_resp_str = json.dumps(_safe_serialize(pa_response), ensure_ascii=False).lower()
    result["stub_detected_in_response"] = any(
        _m.lower() in _pa_resp_str for _m in _stub_markers
    )
    # Explicit DM trace inspection for llm_degraded flag
    _dm_trace = None
    try:
        _traces = (_safe_serialize(pa_response).get("traces", []) or [])
        for _t in _traces:
            if isinstance(_t, dict) and _t.get("agent") == "dm":
                _dm_trace = _t
                break
    except Exception:
        pass
    result["dm_llm_degraded"] = bool(
        ((_dm_trace or {}).get("output", {}) or {}).get("llm_degraded", False)
    )
    result["dm_llm_degraded_reason"] = (
        ((_dm_trace or {}).get("output", {}) or {}).get("llm_degraded_reason")
        if _dm_trace else None
    )
    result["stub_detected"] = (
        result["stub_detected_in_speeches"]
        or result["stub_detected_in_response"]
        or result.get("dm_llm_degraded", False)
    )'''

# The original block pattern we want to replace.
# Match flexibly — original source uses "Stub detection" comment + 4-line block.
ORIGINAL_STUB_PATTERN = re.compile(
    r'    # Stub detection\n'
    r'    _stub_markers = \[.*?\]\n'
    r'    result\["stub_detected_in_speeches"\] = any\(\n'
    r'        any\(_m\.lower\(\) in s\["text"\]\.lower\(\) for _m in _stub_markers\)\n'
    r'        for s in result\["tornin_speeches"\]\n'
    r'    \)\n'
    r'    # Also check log output for stub indicators.*?\n'
    r'    _pa_resp_str = json\.dumps\(_safe_serialize\(pa_response\), ensure_ascii=False\)\.lower\(\)\n'
    r'    result\["stub_detected_in_response"\] = any\(\n'
    r'        _m\.lower\(\) in _pa_resp_str for _m in _stub_markers\n'
    r'    \)\n'
    r'    result\["stub_detected"\] = \(\n'
    r'        result\["stub_detected_in_speeches"\] or result\["stub_detected_in_response"\]\n'
    r'    \)',
    re.DOTALL,
)


def patch_scenario_script() -> dict:
    """Patch p5a_minimal_ab.py with expanded stub detection (backup first)."""
    _section("STEP 3: PATCH p5a_minimal_ab.py (expanded stub detection)")
    info: dict = {}

    if not SCENARIO_SCRIPT.exists():
        _die(f"cannot patch — file not found: {SCENARIO_SCRIPT}", exit_code=2)

    original = SCENARIO_SCRIPT.read_text(encoding="utf-8")
    info["original_size"] = len(original)

    # Check if already patched
    if "expanded markers (auto-patched by run_p5a_full.py)" in original:
        _log("script already patched — skipping")
        info["already_patched"] = True
        info["patched"] = False
        return info

    # Backup
    if not SCENARIO_SCRIPT_BAK.exists():
        shutil.copy2(SCENARIO_SCRIPT, SCENARIO_SCRIPT_BAK)
        _log(f"backup saved: {SCENARIO_SCRIPT_BAK}")
        info["backup_created"] = True
    else:
        _log(f"backup already exists: {SCENARIO_SCRIPT_BAK}")
        info["backup_already_existed"] = True

    # Match original block
    match = ORIGINAL_STUB_PATTERN.search(original)
    if not match:
        _log("WARNING: could not match original stub detection block — trying looser pattern",
             level="WARN")
        # Try a much looser pattern
        loose_match = re.search(
            r'    # Stub detection\n(?:.*?\n){5,20}?    result\["stub_detected"\] = \(\n'
            r'        result\["stub_detected_in_speeches"\] or result\["stub_detected_in_response"\]\n'
            r'    \)',
            original,
            re.DOTALL,
        )
        if not loose_match:
            _die("could not locate stub detection block to replace "
                 "(file structure changed?)", exit_code=2)
        match = loose_match

    _log(f"matched block at offset {match.start()}-{match.end()} ({match.end() - match.start()} chars)")
    info["match_offset"] = match.start()
    info["match_length"] = match.end() - match.start()

    # Replace
    patched = original[:match.start()] + EXPANDED_STUB_BLOCK + original[match.end():]
    SCENARIO_SCRIPT.write_text(patched, encoding="utf-8")
    info["patched_size"] = len(patched)
    info["patched"] = True
    _log(f"patched (size: {info['original_size']} → {info['patched_size']} bytes)")
    return info


# ============================================================================
# Step 4: Run A/B experiment
# ============================================================================

def run_experiment() -> dict:
    """Run p5a_minimal_ab.py via subprocess."""
    _section("STEP 4: RUN A/B EXPERIMENT (subprocess)")
    info: dict = {
        "command": [sys.executable, str(SCENARIO_SCRIPT), "--timeout", str(SCENARIO_TIMEOUT_SEC)],
        "cwd": str(_PROJECT_ROOT),
    }
    _log(f"command: {' '.join(info['command'])}")
    _log(f"cwd: {info['cwd']}")
    _log(f"timeout: {SCENARIO_TIMEOUT_SEC}s")

    start_monotonic = time.monotonic()
    try:
        proc = subprocess.run(
            info["command"],
            capture_output=True,
            text=True,
            cwd=str(_PROJECT_ROOT),
            timeout=SCENARIO_TIMEOUT_SEC + 120,  # outer timeout > inner
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        info["timeout"] = True
        info["duration_sec"] = SCENARIO_TIMEOUT_SEC + 120
        _log(f"OUTER TIMEOUT after {info['duration_sec']}s", level="ERROR")
        info["stdout_tail"] = (exc.stdout or "")[-3000:] if isinstance(exc.stdout, str) else ""
        info["stderr_tail"] = (exc.stderr or "")[-3000:] if isinstance(exc.stderr, str) else ""
        return info
    except Exception as exc:
        info["error"] = f"{type(exc).__name__}: {exc}"
        _log(f"runner error: {info['error']}", level="ERROR")
        return info

    info["returncode"] = proc.returncode
    info["duration_sec"] = time.monotonic() - start_monotonic
    info["stdout"] = proc.stdout
    info["stderr"] = proc.stderr
    _log(f"subprocess exit code: {proc.returncode}, duration: {info['duration_sec']:.2f}s")

    # Save full stdout/stderr
    _stdout_log = _PROJECT_ROOT / "p5a_runner_stdout.log"
    _stderr_log = _PROJECT_ROOT / "p5a_runner_stderr.log"
    _stdout_log.write_text(proc.stdout, encoding="utf-8")
    _stderr_log.write_text(proc.stderr, encoding="utf-8")
    _log(f"runner stdout saved: {_stdout_log}")
    _log(f"runner stderr saved: {_stderr_log}")
    info["stdout_log"] = str(_stdout_log)
    info["stderr_log"] = str(_stderr_log)

    return info


# ============================================================================
# Step 5: Parse results
# ============================================================================

def _try_load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_parse_error": f"{type(exc).__name__}: {exc}", "_path": str(path)}


def _extract_tornin_speeches(scenario_data: dict) -> list:
    if not scenario_data:
        return []
    return scenario_data.get("tornin_speeches", []) or []


def _extract_dm_degraded(scenario_data: dict) -> dict:
    if not scenario_data:
        return {}
    return {
        "dm_llm_degraded": scenario_data.get("dm_llm_degraded", False),
        "dm_llm_degraded_reason": scenario_data.get("dm_llm_degraded_reason"),
        "stub_detected": scenario_data.get("stub_detected", False),
        "stub_detected_in_speeches": scenario_data.get("stub_detected_in_speeches", False),
        "stub_detected_in_response": scenario_data.get("stub_detected_in_response", False),
    }


def _extract_player_action(scenario_data: dict) -> dict:
    if not scenario_data:
        return {}
    pa = scenario_data.get("player_action", {}) or {}
    return {
        "duration_sec": pa.get("duration_sec"),
        "error": pa.get("error"),
        "response_dm_response": _dig(pa, "response", "dm_response"),
        "response_npc_reactions": _dig(pa, "response", "npc_reactions"),
    }


def _dig(obj: Any, *keys: str, default: Any = None) -> Any:
    cur = obj
    for k in keys:
        if cur is None:
            return default
        if isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return default
    return cur if cur is not None else default


def parse_results() -> dict:
    """Load all JSON outputs and extract key fields."""
    _section("STEP 5: PARSE RESULTS")
    info: dict = {}

    info["summary_json_path"] = str(SUMMARY_JSON)
    info["summary_json_exists"] = SUMMARY_JSON.exists()
    info["scenario_a_json_path"] = str(SCENARIO_A_JSON)
    info["scenario_a_json_exists"] = SCENARIO_A_JSON.exists()
    info["scenario_b_json_path"] = str(SCENARIO_B_JSON)
    info["scenario_b_json_exists"] = SCENARIO_B_JSON.exists()

    info["summary"] = _try_load_json(SUMMARY_JSON)
    info["A"] = _try_load_json(SCENARIO_A_JSON)
    info["B"] = _try_load_json(SCENARIO_B_JSON)

    if info["summary"]:
        _log(f"summary loaded — verdict: {info['summary'].get('verdict', '?')}")
        _log(f"  reason: {info['summary'].get('reason', '?')}")
    else:
        _log("summary.json NOT FOUND — experiment may not have completed", level="WARN")

    # Extract Tornin speeches
    a_speeches = _extract_tornin_speeches(info["A"])
    b_speeches = _extract_tornin_speeches(info["B"])
    info["a_tornin_speeches"] = a_speeches
    info["b_tornin_speeches"] = b_speeches
    _log(f"A tornin_speeches count: {len(a_speeches)}")
    _log(f"B tornin_speeches count: {len(b_speeches)}")

    # Extract DM degraded info
    info["a_dm_degraded"] = _extract_dm_degraded(info["A"])
    info["b_dm_degraded"] = _extract_dm_degraded(info["B"])
    _log(f"A dm_llm_degraded: {info['a_dm_degraded'].get('dm_llm_degraded')}")
    _log(f"B dm_llm_degraded: {info['b_dm_degraded'].get('dm_llm_degraded')}")

    # Extract player_action info
    info["a_player_action"] = _extract_player_action(info["A"])
    info["b_player_action"] = _extract_player_action(info["B"])
    _log(f"A player_action duration: {info['a_player_action'].get('duration_sec')}s, "
         f"error: {info['a_player_action'].get('error')}")
    _log(f"B player_action duration: {info['b_player_action'].get('duration_sec')}s, "
         f"error: {info['b_player_action'].get('error')}")

    return info


# ============================================================================
# Step 6: Final verdict + report
# ============================================================================

def compute_final_verdict(parsed: dict) -> tuple[str, str]:
    """Compute final GREEN/YELLOW/RED from parsed results."""
    summary = parsed.get("summary") or {}
    a = parsed.get("A") or {}
    b = parsed.get("B") or {}

    if not a:
        return "RED", "A scenario JSON missing — experiment did not complete"
    if not b:
        return "RED", "B scenario JSON missing — experiment did not complete"

    # Subprocess-level errors
    if a.get("error"):
        return "RED", f"A subprocess error: {a.get('error')}"
    if b.get("error"):
        return "RED", f"B subprocess error: {b.get('error')}"

    # Baseline purity
    a_baseline = a.get("baseline", {}) or {}
    b_baseline = b.get("baseline", {}) or {}
    if a_baseline.get("target_belief_present", False):
        return "RED", "A baseline polluted — pre-existing INSULTED belief"
    if b_baseline.get("target_belief_present", False):
        return "RED", "B baseline polluted — pre-existing INSULTED belief"

    # Treatment effect
    a_post = a.get("post_publish", {}) or {}
    b_post = b.get("post_publish", {}) or {}
    if not a_post.get("target_belief_present", False):
        return "RED", "A target belief NOT created after PLAYER_INSULTS"
    if b_post.get("target_belief_present", False):
        return "RED", "B should NOT have target belief (control scenario)"

    # Cognition projection
    if not a.get("cognition_has_insult", False):
        return "RED", "A cognition block does NOT contain INSULTED belief"
    if b.get("cognition_has_insult", False):
        return "RED", "B cognition block should NOT contain INSULTED belief"

    # DM LLM degraded
    a_dm_degraded = (parsed.get("a_dm_degraded") or {}).get("dm_llm_degraded", False)
    b_dm_degraded = (parsed.get("b_dm_degraded") or {}).get("dm_llm_degraded", False)
    if a_dm_degraded:
        reason = (parsed.get("a_dm_degraded") or {}).get("dm_llm_degraded_reason")
        return "YELLOW", f"A — DM agent LLM degraded: {reason}"
    if b_dm_degraded:
        reason = (parsed.get("b_dm_degraded") or {}).get("dm_llm_degraded_reason")
        return "YELLOW", f"B — DM agent LLM degraded: {reason}"

    # Tornin speeches
    a_speeches = parsed.get("a_tornin_speeches") or []
    b_speeches = parsed.get("b_tornin_speeches") or []
    if not a_speeches:
        return "YELLOW", "A — no Tornin NPC_SPOKE captured"
    if not b_speeches:
        return "YELLOW", "B — no Tornin NPC_SPOKE captured"

    # Stub detection
    a_stub = (parsed.get("a_dm_degraded") or {}).get("stub_detected", False)
    b_stub = (parsed.get("b_dm_degraded") or {}).get("stub_detected", False)
    if a_stub:
        return "YELLOW", "A — stub/degraded text detected"
    if b_stub:
        return "YELLOW", "B — stub/degraded text detected"

    # Speaker verification
    for s in a_speeches:
        if s.get("speaker_id") != "tavern_keeper_tornin":
            return "YELLOW", f"A — unexpected speaker_id: {s.get('speaker_id')}"
    for s in b_speeches:
        if s.get("speaker_id") != "tavern_keeper_tornin":
            return "YELLOW", f"B — unexpected speaker_id: {s.get('speaker_id')}"

    # Empty text
    for i, s in enumerate(a_speeches):
        if not s.get("text", "").strip():
            return "YELLOW", f"A — Tornin speech #{i} text is empty"
    for i, s in enumerate(b_speeches):
        if not s.get("text", "").strip():
            return "YELLOW", f"B — Tornin speech #{i} text is empty"

    return "GREEN", "all checks passed — both scenarios produced real Tornin LLM speech"


def print_final_report(parsed: dict, verdict: str, reason: str) -> None:
    _section("FINAL REPORT")

    print(f"VERDICT: {verdict}")
    print(f"REASON:  {reason}")

    a = parsed.get("A") or {}
    b = parsed.get("B") or {}

    # Epistemic baseline
    _section("BASELINE / POST-PUBLISH / COGNITION")
    print(f"{'Metric':<40} {'A':<30} {'B':<30}")
    print("-" * 100)
    _row = lambda name, av, bv: print(f"{name:<40} {str(av)[:30]:<30} {str(bv)[:30]:<30}")
    _row("baseline_target_present",
         (a.get("baseline", {}) or {}).get("target_belief_present", "?"),
         (b.get("baseline", {}) or {}).get("target_belief_present", "?"))
    _row("post_publish_target_present",
         (a.get("post_publish", {}) or {}).get("target_belief_present", "?"),
         (b.get("post_publish", {}) or {}).get("target_belief_present", "?"))
    _row("cognition_has_insult",
         a.get("cognition_has_insult", "?"),
         b.get("cognition_has_insult", "?"))
    _row("cognition_block_length",
         a.get("cognition_block_length", 0),
         b.get("cognition_block_length", 0))

    # Cognition block A
    _section("COGNITION BLOCK — A")
    print(f"length: {a.get('cognition_block_length', 0)}")
    print("--- A COGNITION ---")
    print(a.get("cognition_block", ""))
    print("--- END ---")

    # Cognition block B
    _section("COGNITION BLOCK — B")
    print(f"length: {b.get('cognition_block_length', 0)}")
    print("--- B COGNITION ---")
    print(b.get("cognition_block", ""))
    print("--- END ---")

    # Player action timing
    _section("PLAYER_ACTION")
    a_pa = parsed.get("a_player_action") or {}
    b_pa = parsed.get("b_player_action") or {}
    print(f"A: duration={a_pa.get('duration_sec')}, error={a_pa.get('error')}")
    print(f"    dm_response={a_pa.get('response_dm_response')!r}")
    print(f"    npc_reactions_count={len(a_pa.get('response_npc_reactions') or [])}")
    print(f"B: duration={b_pa.get('duration_sec')}, error={b_pa.get('error')}")
    print(f"    dm_response={b_pa.get('response_dm_response')!r}")
    print(f"    npc_reactions_count={len(b_pa.get('response_npc_reactions') or [])}")

    # DM degraded
    _section("DM LLM DEGRADATION")
    a_dm = parsed.get("a_dm_degraded") or {}
    b_dm = parsed.get("b_dm_degraded") or {}
    print(f"A dm_llm_degraded: {a_dm.get('dm_llm_degraded')}")
    print(f"A dm_llm_degraded_reason: {a_dm.get('dm_llm_degraded_reason')}")
    print(f"A stub_detected: {a_dm.get('stub_detected')}")
    print(f"B dm_llm_degraded: {b_dm.get('dm_llm_degraded')}")
    print(f"B dm_llm_degraded_reason: {b_dm.get('dm_llm_degraded_reason')}")
    print(f"B stub_detected: {b_dm.get('stub_detected')}")

    # Tornin speeches
    _section("TORNIN SPEECHES — A")
    a_sp = parsed.get("a_tornin_speeches") or []
    print(f"count: {len(a_sp)}")
    for i, s in enumerate(a_sp):
        print(f"  #{i}: speaker={s.get('speaker_id')!r}")
        print(f"       intent={s.get('intent_type')!r}, tone={s.get('tone')!r}")
        print(f"       target_id={s.get('target_id')!r}")
        print(f"       text={s.get('text')!r}")

    _section("TORNIN SPEECHES — B")
    b_sp = parsed.get("b_tornin_speeches") or []
    print(f"count: {len(b_sp)}")
    for i, s in enumerate(b_sp):
        print(f"  #{i}: speaker={s.get('speaker_id')!r}")
        print(f"       intent={s.get('intent_type')!r}, tone={s.get('tone')!r}")
        print(f"       target_id={s.get('target_id')!r}")
        print(f"       text={s.get('text')!r}")

    # All speakers
    _section("ALL SPEAKERS")
    print(f"A all_speakers: {a.get('all_speakers', [])}")
    print(f"B all_speakers: {b.get('all_speakers', [])}")

    # Diff table
    _section("DIFFERENCES TABLE")
    print(f"{'Metric':<40} {'A':<35} {'B':<35}")
    print("-" * 110)
    _row("baseline_target_present",
         (a.get("baseline", {}) or {}).get("target_belief_present", "?"),
         (b.get("baseline", {}) or {}).get("target_belief_present", "?"))
    _row("post_publish_target_present",
         (a.get("post_publish", {}) or {}).get("target_belief_present", "?"),
         (b.get("post_publish", {}) or {}).get("target_belief_present", "?"))
    _row("cognition_has_insult",
         a.get("cognition_has_insult", "?"),
         b.get("cognition_has_insult", "?"))
    _row("cognition_block_length",
         a.get("cognition_block_length", 0),
         b.get("cognition_block_length", 0))
    _row("player_action_duration_sec",
         f"{a_pa.get('duration_sec') or 0:.2f}",
         f"{b_pa.get('duration_sec') or 0:.2f}")
    _row("player_action_error",
         a_pa.get('error') or "None",
         b_pa.get('error') or "None")
    _row("tornin_speech_count",
         a.get("tornin_speech_count", 0),
         b.get("tornin_speech_count", 0))
    _row("dm_llm_degraded",
         a_dm.get("dm_llm_degraded", "?"),
         b_dm.get("dm_llm_degraded", "?"))
    _row("stub_detected",
         a_dm.get("stub_detected", "?"),
         b_dm.get("stub_detected", "?"))

    # Interpretation
    _section("INTERPRETATION")
    print("Single A/B pair proves contrast run only.")
    print("Does NOT prove statistical significance.")
    print("Does NOT close autonomous rumor transmission via maid_lusya.")
    print("Master interprets: do A and B differ meaningfully?")


# ============================================================================
# Main entry
# ============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="P5-A A/B Experiment Runner")
    parser.add_argument("--skip-llm-check", action="store_true",
                        help="Skip LLM-server health check (use with caution).")
    parser.add_argument("--skip-patch", action="store_true",
                        help="Skip patching p5a_minimal_ab.py (if already patched).")
    parser.add_argument("--timeout", type=int, default=SCENARIO_TIMEOUT_SEC,
                        help=f"Per-scenario subprocess timeout (default: {SCENARIO_TIMEOUT_SEC}).")
    args = parser.parse_args()

    global SCENARIO_TIMEOUT_SEC
    SCENARIO_TIMEOUT_SEC = args.timeout

    _section("P5-A A/B EXPERIMENT — SELF-CONTAINED AUTOMATION")

    # Step 1: pre-flight
    pf = preflight()

    # Step 2: LLM-server check
    llm_info: dict = {"available": True}
    if not args.skip_llm_check:
        llm_info = check_llm_server()
        if not llm_info.get("available"):
            _die("LLM-server not available — start it first, then re-run.", exit_code=2)
    else:
        _log("LLM-server health check SKIPPED (--skip-llm-check)", level="WARN")

    # Step 3: patch
    patch_info: dict = {"patched": False, "already_patched": True}
    if not args.skip_patch:
        patch_info = patch_scenario_script()
    else:
        _log("patch step SKIPPED (--skip-patch)", level="WARN")

    # Step 4: run experiment
    run_info = run_experiment()

    # Step 5: parse
    parsed = parse_results()

    # Step 6: verdict
    verdict, reason = compute_final_verdict(parsed)
    print_final_report(parsed, verdict, reason)

    # Save combined report
    combined = {
        "verdict": verdict,
        "reason": reason,
        "timestamp": time.time(),
        "preflight": pf,
        "llm_check": llm_info,
        "patch": patch_info,
        "runner": {
            "duration_sec": run_info.get("duration_sec"),
            "returncode": run_info.get("returncode"),
            "timeout": run_info.get("timeout", False),
            "error": run_info.get("error"),
            "stdout_log": run_info.get("stdout_log"),
            "stderr_log": run_info.get("stderr_log"),
        },
        "A": parsed.get("A"),
        "B": parsed.get("B"),
        "summary": parsed.get("summary"),
    }
    FINAL_REPORT.write_text(
        json.dumps(combined, ensure_ascii=False, default=str, indent=2),
        encoding="utf-8",
    )
    print(f"\n[FINAL] Combined report saved: {FINAL_REPORT}", flush=True)
    print(f"[FINAL] Verdict: {verdict}", flush=True)

    # Exit code by verdict
    exit_code = {"GREEN": 0, "YELLOW": 1, "RED": 2}.get(verdict, 2)
    sys.exit(exit_code)


if __name__ == "__main__":
    sys.exit(main())
