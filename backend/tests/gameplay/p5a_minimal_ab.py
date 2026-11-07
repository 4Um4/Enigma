"""
P5-A Minimal Real-LLM A/B Experiment.

Проверяет: влияет ли наличие INSULTED belief в cognition Tornin'а на его
реальную LLM-реплику в ответ на player_action("Торнин, привет, как дела?").

Production-код НЕ изменяется. Только диагностический тестовый скрипт.

A — Treatment:
  1. TavernGameplayHarness(seed=42, location="tavern")
  2. new_game()
  3. baseline check (Tornin без INSULTED)
  4. publish PLAYER_INSULTS(target=tornin, radius=50)
  5. EpistemicStore check (predicate=INSULTED, source_id=player, polarity=True)
  6. cognition block capture
  7. subscribe spy на NPC_SPOKE
  8. player_action("Торнин, привет, как дела?") — real LLM через production dm_agent.router
  9. capture NPC_SPOKE events (speaker_id, text, intent, tone)
  10. unsubscribe spy через EventBus.unsubscribe

B — Control:
  Идентично, но НЕ публиковать PLAYER_INSULTS.

Isolation:
  A и B запускаются в отдельных subprocess для изоляции ModelRouter/EventBus/ModelPool.
  Не использовать EventBus.clear() между сценариями.
  Не использовать: PassthroughVerifier, SyncPool, искусственные NPC_SPOKE,
  ручное добавление belief, forced disposition overrides, дополнительные тики.

Запуск (production-среда Мастера):
  cd C:\\DDD\\Codex\\VSC_Enigma\\Enigma
  python backend\\tests\\gameplay\\p5a_minimal_ab.py

  Альтернатива (pytest не нужен):
  python backend\\tests\\gameplay\\p5a_minimal_ab.py --timeout 600

Вывод:
  - STDOUT: verdict GREEN/YELLOW/RED + comparison table
  - p5a_minimal_ab_A.json — full result A
  - p5a_minimal_ab_B.json — full result B
  - p5a_minimal_ab_summary.json — combined + verdict
  - p5a_minimal_ab_A.log, p5a_minimal_ab_B.log — raw subprocess stdout/stderr
"""
from __future__ import annotations

# === sys.path bootstrap (must precede any project imports) ===
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_BACKEND_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
for _p in (_PROJECT_ROOT, _BACKEND_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
# === end sys.path bootstrap ===

import argparse
import json
import logging
import math
import subprocess
import time
import traceback
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# Helpers
# ============================================================================

def _divider(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}", flush=True)


def _describe_record(record: Any) -> dict:
    _prop = getattr(record, "proposition", None)
    _pred = getattr(_prop, "predicate", None) if _prop is not None else None
    _pred_val = None
    if _pred is not None:
        _pred_val = getattr(_pred, "value", _pred)
    return {
        "subject_id": getattr(_prop, "subject_id", None) if _prop is not None else None,
        "predicate": str(_pred_val) if _pred_val is not None else None,
        "object_id": getattr(_prop, "object_id", None) if _prop is not None else None,
        "polarity": getattr(_prop, "polarity", None) if _prop is not None else None,
        "confidence": getattr(record, "confidence", None),
        "source_id": getattr(record, "source_id", None),
        "provenance": getattr(record, "provenance", None),
        "record_type": type(record).__name__,
        "tick": getattr(record, "tick", None),
    }


def _is_target_insulted(record: Any) -> bool:
    _d = _describe_record(record)
    return (
        _d["subject_id"] == "player"
        and _d["predicate"] == "insulted"
        and _d["object_id"] == "tavern_keeper_tornin"
    )


def _get_epistemic_store(harness: Any) -> Any:
    _tick_orch = getattr(harness.game_loop, "_tick_orch", None)
    if _tick_orch is None:
        return None
    return getattr(_tick_orch, "_epistemic_store", None)


def _read_tornin_records(harness: Any) -> list:
    _store = _get_epistemic_store(harness)
    if _store is None:
        return []
    return list(_store.get_all_for_agent("tavern_keeper_tornin") or [])


def _get_cognition_block(harness: Any) -> str:
    from app.services.npc.cognition_context import CognitionContextResolver

    _store = _get_epistemic_store(harness)
    _sched = harness.game_loop._get_task_scheduler()
    _mm = getattr(_sched, "_memory_manager", None)
    _resolver = CognitionContextResolver(memory_manager=_mm, epistemic_store=_store)
    try:
        _block = _resolver.resolve_block("tavern_keeper_tornin", "player")
        return _block or ""
    except Exception as exc:
        return f"[ERROR resolve_block: {exc}]"


def _ensure_router() -> None:
    """Initialize ModelPool through production path (idempotent module-level)."""
    from app.services.llm.router import initialize_router
    initialize_router()


def _publish_player_insults(harness: Any, victim: str, radius: float) -> Any:
    from app.domain.events import EventDTO
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType

    _bus = get_event_bus()
    _event = EventDTO.create(
        event_type=EventType.PLAYER_INSULTS.value,
        source="player",
        payload={
            "target_id": victim,
            "text": "Ты дурак!",
            "action_type": "player_insults",
        },
        visibility="public",
        radius=radius,
        persistence_level="session",
    )
    _bus.publish(_event)
    return _event


def _safe_serialize(obj: Any, depth: int = 0) -> Any:
    """Best-effort JSON-serializable representation of any object."""
    if depth > 5:
        return "<truncated>"
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _safe_serialize(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_safe_serialize(x, depth + 1) for x in obj]
    if hasattr(obj, "model_dump"):
        try:
            return _safe_serialize(obj.model_dump(), depth + 1)
        except Exception:
            pass
    if hasattr(obj, "dict"):
        try:
            return _safe_serialize(obj.dict(), depth + 1)
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        try:
            _d = {k: _safe_serialize(v, depth + 1) for k, v in vars(obj).items()
                  if not k.startswith("_")}
            if _d:
                return _d
        except Exception:
            pass
    return str(obj)[:500]


# ============================================================================
# Single scenario execution (subprocess mode)
# ============================================================================

def run_scenario(scenario: str) -> dict:
    """Single A/B scenario. Returns JSON-serializable result dict."""
    result: dict = {
        "scenario": scenario,
        "errors": [],
        "started_at": time.time(),
    }

    _divider(f"P5-A MINIMAL A/B — SCENARIO {scenario}")

    # 1. Router init (production path)
    print(f"[{scenario}] _ensure_router()...", flush=True)
    try:
        _ensure_router()
        print(f"[{scenario}] router initialized", flush=True)
    except Exception as exc:
        result["errors"].append(f"initialize_router failed: {type(exc).__name__}: {exc}")
        result["router_init_error"] = str(exc)
        print(f"[{scenario}] ERROR: initialize_router failed: {exc}", flush=True)
        return result

    # 2. Harness + new_game
    print(f"[{scenario}] creating TavernGameplayHarness(seed=42, location='tavern')...", flush=True)
    from tests.gameplay.harness import TavernGameplayHarness
    _h = TavernGameplayHarness(seed=42, location="tavern")
    print(f"[{scenario}] new_game()...", flush=True)
    _h.new_game()
    print(f"[{scenario}] new_game done", flush=True)

    # 3. Baseline check
    print(f"[{scenario}] baseline check (Tornin's EpistemicStore)...", flush=True)
    _baseline_records = _read_tornin_records(_h)
    _baseline_target = [r for r in _baseline_records if _is_target_insulted(r)]
    result["baseline"] = {
        "tornin_records_count": len(_baseline_records),
        "target_belief_present": bool(_baseline_target),
        "records": [_describe_record(r) for r in _baseline_records],
    }
    print(f"[{scenario}] baseline: records={len(_baseline_records)}, "
          f"target_present={bool(_baseline_target)}", flush=True)

    if _baseline_target:
        result["errors"].append("BASELINE POLLUTED — target belief present before any event")
        return result

    # 4. Publish PLAYER_INSULTS (only A)
    if scenario == "A":
        print(f"[{scenario}] publishing PLAYER_INSULTS radius=50.0...", flush=True)
        _event = _publish_player_insults(_h, victim="tavern_keeper_tornin", radius=50.0)
        result["event_published"] = {
            "event_id": getattr(_event, "id", None),
            "event_type": getattr(_event, "type", None),
            "radius": 50.0,
        }
        print(f"[{scenario}] PLAYER_INSULTS published", flush=True)
    else:
        result["event_published"] = None
        print(f"[{scenario}] SKIP publish (control scenario)", flush=True)

    # 5. EpistemicStore check after publish
    print(f"[{scenario}] post-publish epistemic check...", flush=True)
    _post_records = _read_tornin_records(_h)
    _post_target = [r for r in _post_records if _is_target_insulted(r)]
    result["post_publish"] = {
        "tornin_records_count": len(_post_records),
        "target_belief_present": bool(_post_target),
        "target_record": _describe_record(_post_target[0]) if _post_target else None,
        "records": [_describe_record(r) for r in _post_records],
    }
    print(f"[{scenario}] post-publish: records={len(_post_records)}, "
          f"target_present={bool(_post_target)}", flush=True)

    # 6. Cognition block capture
    print(f"[{scenario}] cognition block capture...", flush=True)
    _cog = _get_cognition_block(_h)
    result["cognition_block"] = _cog
    result["cognition_block_length"] = len(_cog) if isinstance(_cog, str) else 0
    result["cognition_has_insult"] = (
        ("оскорб" in _cog.lower() or "insult" in _cog.lower())
        if isinstance(_cog, str) else False
    )
    print(f"[{scenario}] cognition block length={result['cognition_block_length']}, "
          f"has_insult={result['cognition_has_insult']}", flush=True)

    # 7. Subscribe spy on NPC_SPOKE
    print(f"[{scenario}] subscribing NPC_SPOKE spy...", flush=True)
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType

    _npc_spoke_events: list = []

    def _spy(event: Any) -> None:
        _src = getattr(event, "source", "")
        _pl = getattr(event, "payload", {}) or {}
        _entry = {
            "speaker_id": _src,
            "text": _pl.get("text", ""),
            "intent_type": _pl.get("intent_type", ""),
            "tone": _pl.get("tone", ""),
            "topic": _pl.get("topic", ""),
            "target_id": _pl.get("target_id", ""),
            "exposure": _pl.get("exposure", ""),
            "event_id": getattr(event, "id", None),
            "event_type": getattr(event, "type", None),
            "tick": _pl.get("tick") or getattr(event, "tick", None),
            "captured_at_monotonic": time.monotonic(),
        }
        _npc_spoke_events.append(_entry)
        print(f"[{scenario}] [NPC_SPOKE] speaker={_src} intent={_entry['intent_type']} "
              f"tone={_entry['tone']} text={_entry['text'][:120]!r}", flush=True)

    _bus = get_event_bus()
    _bus.subscribe(EventType.NPC_SPOKE, _spy)

    # 8. player_action — REAL LLM call through production dm_agent.router
    print(f"[{scenario}] player_action('Торнин, привет, как дела?')...", flush=True)
    pa_start = time.monotonic()
    pa_error: str | None = None
    pa_response: Any = None
    try:
        pa_response = _h.player_action("Торнин, привет, как дела?")
    except Exception as exc:
        pa_error = f"{type(exc).__name__}: {exc}"
        result["errors"].append(f"player_action raised: {pa_error}")
        print(f"[{scenario}] player_action EXCEPTION: {pa_error}", flush=True)
        traceback.print_exc()
    pa_end = time.monotonic()
    pa_duration = pa_end - pa_start

    result["player_action"] = {
        "start_monotonic": pa_start,
        "end_monotonic": pa_end,
        "duration_sec": pa_duration,
        "response": _safe_serialize(pa_response),
        "error": pa_error,
    }
    print(f"[{scenario}] player_action done in {pa_duration:.2f}s "
          f"(error={pa_error})", flush=True)

    # 9. Capture NPC_SPOKE events (already captured by spy)
    # 10. Unsubscribe spy
    try:
        _bus.unsubscribe(EventType.NPC_SPOKE, _spy)
        print(f"[{scenario}] spy unsubscribed", flush=True)
    except Exception as exc:
        result["errors"].append(f"unsubscribe failed: {exc}")
        print(f"[{scenario}] unsubscribe failed: {exc}", flush=True)

    result["all_npc_speeches"] = _npc_spoke_events
    result["tornin_speeches"] = [
        s for s in _npc_spoke_events if s["speaker_id"] == "tavern_keeper_tornin"
    ]

    # Stub detection
    _stub_markers = ["[Заглушка]", "[stub]", "Fallback to stub", "ModelRouter is None"]
    result["stub_detected_in_speeches"] = any(
        any(_m.lower() in s["text"].lower() for _m in _stub_markers)
        for s in result["tornin_speeches"]
    )
    # Also check log output for stub indicators (best-effort: check response)
    _pa_resp_str = json.dumps(_safe_serialize(pa_response), ensure_ascii=False).lower()
    result["stub_detected_in_response"] = any(
        _m.lower() in _pa_resp_str for _m in _stub_markers
    )
    result["stub_detected"] = (
        result["stub_detected_in_speeches"] or result["stub_detected_in_response"]
    )

    # Check speaker identity
    result["all_speakers"] = sorted({s["speaker_id"] for s in _npc_spoke_events})
    result["tornin_speech_count"] = len(result["tornin_speeches"])

    result["finished_at"] = time.time()
    result["total_duration_sec"] = result["finished_at"] - result["started_at"]

    _divider(f"SCENARIO {scenario} SUMMARY")
    print(f"baseline_target: {result['baseline']['target_belief_present']}", flush=True)
    print(f"post_publish_target: {result['post_publish']['target_belief_present']}", flush=True)
    print(f"cognition_has_insult: {result['cognition_has_insult']}", flush=True)
    print(f"player_action_duration: {pa_duration:.2f}s", flush=True)
    print(f"tornin_speech_count: {result['tornin_speech_count']}", flush=True)
    print(f"all_speakers: {result['all_speakers']}", flush=True)
    print(f"stub_detected: {result['stub_detected']}", flush=True)
    if result["tornin_speeches"]:
        for i, s in enumerate(result["tornin_speeches"]):
            print(f"  #{i}: intent={s['intent_type']} tone={s['tone']} "
                  f"text={s['text'][:200]!r}", flush=True)
    if result["errors"]:
        print(f"errors:", flush=True)
        for e in result["errors"]:
            print(f"  - {e}", flush=True)

    return result


# ============================================================================
# Verdict logic
# ============================================================================

def determine_verdict(a: dict, b: dict) -> tuple[str, str]:
    """GREEN / YELLOW / RED with reason."""
    # Subprocess-level errors
    if a.get("error") or a.get("router_init_error"):
        return "RED", f"A subprocess failed: {a.get('error') or a.get('router_init_error')}"
    if b.get("error") or b.get("router_init_error"):
        return "RED", f"B subprocess failed: {b.get('error') or b.get('router_init_error')}"

    # Baseline purity
    a_base = a.get("baseline", {})
    b_base = b.get("baseline", {})
    if a_base.get("target_belief_present", False):
        return "RED", "A baseline polluted — pre-existing INSULTED belief"
    if b_base.get("target_belief_present", False):
        return "RED", "B baseline polluted — pre-existing INSULTED belief"

    # Treatment effect
    a_post = a.get("post_publish", {})
    b_post = b.get("post_publish", {})
    if not a_post.get("target_belief_present", False):
        return "RED", "A target belief NOT created after PLAYER_INSULTS"
    if b_post.get("target_belief_present", False):
        return "RED", "B should NOT have target belief (control scenario)"

    # Cognition projection
    if not a.get("cognition_has_insult", False):
        return "RED", "A cognition block does NOT contain INSULTED belief"
    if b.get("cognition_has_insult", False):
        return "RED", "B cognition block should NOT contain INSULTED belief"

    # Speaker identity (Tornin's speech)
    a_speeches = a.get("tornin_speeches", [])
    b_speeches = b.get("tornin_speeches", [])

    if not a_speeches:
        return "YELLOW", "A — no Tornin NPC_SPOKE captured (player_action may have failed silently)"
    if not b_speeches:
        return "YELLOW", "B — no Tornin NPC_SPOKE captured"

    # Speaker verification
    for s in a_speeches:
        if s.get("speaker_id") != "tavern_keeper_tornin":
            return "YELLOW", f"A — unexpected speaker_id in Tornin-filtered speech: {s.get('speaker_id')}"
    for s in b_speeches:
        if s.get("speaker_id") != "tavern_keeper_tornin":
            return "YELLOW", f"B — unexpected speaker_id in Tornin-filtered speech: {s.get('speaker_id')}"

    # Text non-empty
    for i, s in enumerate(a_speeches):
        if not s.get("text", "").strip():
            return "YELLOW", f"A — Tornin speech #{i} text is empty"
    for i, s in enumerate(b_speeches):
        if not s.get("text", "").strip():
            return "YELLOW", f"B — Tornin speech #{i} text is empty"

    # Stub detection
    if a.get("stub_detected", False):
        return "YELLOW", f"A — stub/fallback text detected (stub_in_speeches={a.get('stub_detected_in_speeches')}, stub_in_response={a.get('stub_detected_in_response')})"
    if b.get("stub_detected", False):
        return "YELLOW", f"B — stub/fallback text detected (stub_in_speeches={b.get('stub_detected_in_speeches')}, stub_in_response={b.get('stub_detected_in_response')})"

    # player_action errors
    a_pa_err = a.get("player_action", {}).get("error")
    b_pa_err = b.get("player_action", {}).get("error")
    if a_pa_err:
        return "YELLOW", f"A — player_action error: {a_pa_err}"
    if b_pa_err:
        return "YELLOW", f"B — player_action error: {b_pa_err}"

    return "GREEN", "all checks passed — both scenarios produced real Tornin LLM speech without stubs"


# ============================================================================
# Runner (orchestrates A and B subprocesses)
# ============================================================================

def _run_subprocess(scenario: str, timeout_sec: int, out_dir: str) -> dict:
    """Run single scenario as subprocess, return parsed JSON result."""
    print(f"\n[Runner] Starting subprocess for scenario {scenario} (timeout={timeout_sec}s)...",
          flush=True)
    out_path = os.path.join(out_dir, f"p5a_minimal_ab_{scenario}.json")
    log_path = os.path.join(out_dir, f"p5a_minimal_ab_{scenario}.log")

    try:
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--scenario", scenario],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=_PROJECT_ROOT,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        print(f"[Runner] {scenario} TIMEOUT ({timeout_sec}s)", flush=True)
        _result = {
            "error": f"subprocess timeout ({timeout_sec}s)",
            "timeout": True,
            "stdout": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
        }
        with open(log_path, "w", encoding="utf-8") as _f:
            _f.write(f"=== TIMEOUT after {timeout_sec}s ===\n"
                     f"STDOUT (tail):\n{(exc.stdout or '')[-3000:]}\n\n"
                     f"STDERR (tail):\n{(exc.stderr or '')[-3000:]}")
        with open(out_path, "w", encoding="utf-8") as _f:
            json.dump(_result, _f, ensure_ascii=False, indent=2)
        return _result

    # Save raw logs
    with open(log_path, "w", encoding="utf-8") as _f:
        _f.write(f"=== RETURN CODE: {proc.returncode} ===\n\n")
        _f.write(f"=== STDOUT ===\n{proc.stdout}\n\n")
        _f.write(f"=== STDERR ===\n{proc.stderr}\n")

    if proc.returncode != 0:
        return {
            "error": f"subprocess exit code {proc.returncode}",
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:],
        }

    # Parse last JSON line from stdout
    lines = proc.stdout.strip().split("\n")
    json_lines = [l for l in lines if l.strip().startswith("{") and l.strip().endswith("}")]
    if not json_lines:
        return {
            "error": "no JSON line in stdout",
            "stdout_tail": proc.stdout[-2000:],
        }
    try:
        result = json.loads(json_lines[-1])
    except Exception as exc:
        return {
            "error": f"JSON parse failed: {exc}",
            "stdout_tail": proc.stdout[-2000:],
        }

    # Save scenario JSON
    with open(out_path, "w", encoding="utf-8") as _f:
        json.dump(result, _f, ensure_ascii=False, indent=2, default=str)
    print(f"[Runner] {scenario} subprocess done, JSON saved to {out_path}", flush=True)
    return result


def _print_summary(a: dict, b: dict, verdict: str, reason: str) -> None:
    _divider("P5-A MINIMAL A/B EXPERIMENT — VERDICT")
    print(f"\nVerdict: {verdict}")
    print(f"Reason:  {reason}")

    _divider("BASELINE CHECK")
    print(f"A baseline_target_present: {a.get('baseline', {}).get('target_belief_present', '?')}")
    print(f"B baseline_target_present: {b.get('baseline', {}).get('target_belief_present', '?')}")

    _divider("POST-PUBLISH EPISTEMIC CHECK")
    a_rec = a.get("post_publish", {}).get("target_record") or {}
    print(f"A target_belief_present: {a.get('post_publish', {}).get('target_belief_present', '?')}")
    if a_rec:
        print(f"  source_id={a_rec.get('source_id')!r}, "
              f"predicate={a_rec.get('predicate')!r}, "
              f"confidence={a_rec.get('confidence')!r}, "
              f"polarity={a_rec.get('polarity')!r}")
    print(f"B target_belief_present: {b.get('post_publish', {}).get('target_belief_present', '?')}")

    _divider("COGNITION BLOCK — A")
    print(f"length: {a.get('cognition_block_length', 0)}")
    print(f"has_insult: {a.get('cognition_has_insult', '?')}")
    print("--- A COGNITION BLOCK ---")
    print(a.get("cognition_block", ""))
    print("--- END ---")

    _divider("COGNITION BLOCK — B")
    print(f"length: {b.get('cognition_block_length', 0)}")
    print(f"has_insult: {b.get('cognition_has_insult', '?')}")
    print("--- B COGNITION BLOCK ---")
    print(b.get("cognition_block", ""))
    print("--- END ---")

    _divider("PLAYER_ACTION TIMING")
    a_pa = a.get("player_action", {}) or {}
    b_pa = b.get("player_action", {}) or {}
    print(f"A: duration={a_pa.get('duration_sec', 0):.2f}s, error={a_pa.get('error')}")
    print(f"B: duration={b_pa.get('duration_sec', 0):.2f}s, error={b_pa.get('error')}")

    _divider("TORNIN SPEECHES — A")
    a_sp = a.get("tornin_speeches", [])
    print(f"count: {len(a_sp)}")
    for i, s in enumerate(a_sp):
        print(f"  #{i}: speaker={s.get('speaker_id')!r}")
        print(f"       intent={s.get('intent_type')!r}, tone={s.get('tone')!r}")
        print(f"       target_id={s.get('target_id')!r}")
        print(f"       text={s.get('text')!r}")

    _divider("TORNIN SPEECHES — B")
    b_sp = b.get("tornin_speeches", [])
    print(f"count: {len(b_sp)}")
    for i, s in enumerate(b_sp):
        print(f"  #{i}: speaker={s.get('speaker_id')!r}")
        print(f"       intent={s.get('intent_type')!r}, tone={s.get('tone')!r}")
        print(f"       target_id={s.get('target_id')!r}")
        print(f"       text={s.get('text')!r}")

    _divider("STUB DETECTION")
    print(f"A stub_detected: {a.get('stub_detected', '?')} "
          f"(in_speeches={a.get('stub_detected_in_speeches', '?')}, "
          f"in_response={a.get('stub_detected_in_response', '?')})")
    print(f"B stub_detected: {b.get('stub_detected', '?')} "
          f"(in_speeches={b.get('stub_detected_in_speeches', '?')}, "
          f"in_response={b.get('stub_detected_in_response', '?')})")

    _divider("ALL SPEAKERS")
    print(f"A all_speakers: {a.get('all_speakers', [])}")
    print(f"B all_speakers: {b.get('all_speakers', [])}")

    _divider("DIFFERENCES TABLE")
    print(f"{'Metric':<40} {'A':<35} {'B':<35}")
    print("-" * 110)
    _row = lambda name, av, bv: print(f"{name:<40} {str(av)[:35]:<35} {str(bv)[:35]:<35}")
    _row("baseline_target_present",
         a.get("baseline", {}).get("target_belief_present", "?"),
         b.get("baseline", {}).get("target_belief_present", "?"))
    _row("post_publish_target_present",
         a.get("post_publish", {}).get("target_belief_present", "?"),
         b.get("post_publish", {}).get("target_belief_present", "?"))
    _row("cognition_has_insult",
         a.get("cognition_has_insult", "?"),
         b.get("cognition_has_insult", "?"))
    _row("cognition_block_length",
         a.get("cognition_block_length", 0),
         b.get("cognition_block_length", 0))
    _row("player_action_duration_sec",
         f"{a_pa.get('duration_sec', 0):.2f}",
         f"{b_pa.get('duration_sec', 0):.2f}")
    _row("player_action_error",
         a_pa.get("error", "None"),
         b_pa.get("error", "None"))
    _row("tornin_speech_count",
         a.get("tornin_speech_count", 0),
         b.get("tornin_speech_count", 0))
    _row("stub_detected",
         a.get("stub_detected", "?"),
         b.get("stub_detected", "?"))
    _row("total_duration_sec",
         f"{a.get('total_duration_sec', 0):.2f}",
         f"{b.get('total_duration_sec', 0):.2f}")

    _divider("INTERPRETATION (Master reads)")
    print("Single A/B pair proves contrast run only.")
    print("Does NOT prove statistical significance of the effect.")
    print("Does NOT close autonomous rumor transmission via maid_lusya.")
    print("Master interprets: do A and B differ meaningfully?")


# ============================================================================
# Entry point
# ============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="P5-A Minimal Real-LLM A/B Experiment")
    parser.add_argument("--scenario", choices=["A", "B"], default=None,
                        help="Run single scenario (subprocess mode). If omitted, runs both as subprocesses.")
    parser.add_argument("--timeout", type=int, default=600,
                        help="Per-scenario subprocess timeout in seconds (default: 600).")
    parser.add_argument("--out-dir", default=".",
                        help="Directory for JSON/log output files (default: cwd).")
    args = parser.parse_args()

    if args.scenario:
        # Subprocess mode — single scenario, JSON to stdout
        logging.basicConfig(
            level=logging.WARNING,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        try:
            _result = run_scenario(args.scenario)
            print(json.dumps(_result, ensure_ascii=False, default=str))
            sys.exit(0)
        except Exception:
            traceback.print_exc()
            sys.exit(1)

    # Runner mode
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    _divider("P5-A MINIMAL A/B EXPERIMENT — RUNNER")
    print(f"out_dir: {out_dir}")
    print(f"timeout: {args.timeout}s per scenario")
    print(f"python: {sys.executable}")
    print(f"script: {os.path.abspath(__file__)}")
    print(f"cwd:    {_PROJECT_ROOT}")

    results: dict = {}
    for scenario in ("A", "B"):
        results[scenario] = _run_subprocess(scenario, args.timeout, out_dir)

    a, b = results["A"], results["B"]
    verdict, reason = determine_verdict(a, b)

    _print_summary(a, b, verdict, reason)

    # Save combined summary
    summary_path = os.path.join(out_dir, "p5a_minimal_ab_summary.json")
    with open(summary_path, "w", encoding="utf-8") as _f:
        json.dump({
            "verdict": verdict,
            "reason": reason,
            "timestamp": time.time(),
            "timeout_sec": args.timeout,
            "A": a,
            "B": b,
        }, _f, ensure_ascii=False, default=str, indent=2)
    print(f"\n[Runner] Combined summary saved to {summary_path}", flush=True)

    sys.exit(0 if verdict == "GREEN" else 1)


if __name__ == "__main__":
    sys.exit(main())

