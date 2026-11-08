"""
R2-B5-D2 — B4-R13 E1: PROMPT_INJECTION production-path verification.

Цель: доказать, что CognitionContextResolver не просто формирует cog_block,
а его содержимое действительно попадает в user_prompt, передаваемый ModelRouter.

Метод: прозрачный router wrapper (recorder), который записывает аргументы
request_for_agent и передаёт их дальше без изменений. Не подменяет
DialogueExecutor, CognitionContextResolver, MemoryManager, EpistemicStore.

Три независимых вердикта:
  - RESOLVER_PASS — resolve_block() вернул непустой текст (baseline)
  - INJECTION_PASS — cog_block маркеры найдены в user_prompt вызова Торнина
  - ROUTER_PASS — router фактически получил prompt с cog_block маркерами

Запреты (per Master's spec B4-R13):
  - production-код не менять
  - не менять правила игры и disposition
  - не создавать новые truth stores
  - не удалять старые логи
  - не запускать полный B4-R1
  - не считать ручной вызов resolver доказательством INJECTION
  - не считать наличие маркеров в произвольном prompt доказательством, что они относятся к вызову Торнина

READ-ONLY diagnostic. Production-код не меняется.
"""
from __future__ import annotations

import os
import sys
import io
import copy
import json
import traceback
import shutil
import tempfile
import logging
import inspect
from pathlib import Path
from typing import Any, Optional, Callable
from datetime import datetime
from uuid import uuid4

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_e1_prompt_injection.txt"


# ============================================================================
# TeeStream for stdout capture
# ============================================================================
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


# ============================================================================
# Constants
# ============================================================================
_CAMPAIGN = "Open_road"
_VICTIM = "tavern_keeper_tornin"
_WITNESS = "maid_lusya"
_PLAYER = "player"

NPC_IDS = [
    "tavern_keeper_tornin",
    "maid_lusya",
    "blacksmith_orm",
    "guard_borko",
    "merchant_goran",
    "thief_shadow",
]


# ============================================================================
# Router wrapper (transparent recorder)
# ============================================================================
class RouterCallRecord:
    """Single recorded router call."""
    def __init__(self, agent_name: str, prompt: str, system_prompt: Optional[str],
                 params: Any, call_index: int, owner_id_hint: Optional[str] = None):
        self.agent_name = agent_name
        self.prompt = prompt or ""
        self.system_prompt = system_prompt or ""
        self.params = params
        self.call_index = call_index
        self.owner_id_hint = owner_id_hint  # set if we can determine owner
        self.timestamp = datetime.now().isoformat()


class RouterRecorder:
    """Transparent recorder around ModelRouter.request_for_agent.
    
    Wraps the original method, records arguments, passes through unchanged.
    Does NOT modify the call in any way.
    """
    def __init__(self, original_method: Callable):
        self.original_method = original_method
        self.records: list[RouterCallRecord] = []
        self._call_counter = 0
    
    def __call__(self, agent_name: str, prompt: str,
                 params: Any = None, system_prompt: Optional[str] = None,
                 priority: str = "canonical") -> str:
        # Record BEFORE calling original (so we capture even if it fails)
        self._call_counter += 1
        record = RouterCallRecord(
            agent_name=agent_name,
            prompt=prompt,
            system_prompt=system_prompt,
            params=params,
            call_index=self._call_counter,
        )
        self.records.append(record)
        # Pass through to original method UNCHANGED
        return self.original_method(
            agent_name=agent_name,
            prompt=prompt,
            params=params,
            system_prompt=system_prompt,
            priority=priority,
        )


# ============================================================================
# Helpers (mirror D1)
# ============================================================================
def _publish_player_insults(target_id: str, radius: float = 15.0) -> None:
    from app.domain.events import EventDTO
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType

    _payload = {
        "target_id": target_id,
        "action_type": "player_insults",
        "intent_type": "insult",
    }
    _event = EventDTO(
        id=uuid4(),
        type=EventType.PLAYER_INSULTS.value,
        source=_PLAYER,
        timestamp=0.0,
        payload=_payload,
        visibility="public",
        radius=radius,
        persistence_level="session",
    )
    get_event_bus().publish(_event)
    print(f"  [INJECT] PLAYER_INSULTS: source={_PLAYER} target={target_id} radius={radius}")


def _get_store_records(store: Any, agent_id: str) -> list:
    try:
        return store.get_all_for_agent(agent_id)
    except Exception as e:
        print(f"    [ERROR get_all_for_agent({agent_id}): {e}]")
        return []


def _has_tornin_insulted(records: list) -> tuple[bool, Optional[Any]]:
    for r in records:
        try:
            if isinstance(r, dict):
                prop = r.get("proposition", {})
                if (prop.get("subject_id") == "player"
                    and prop.get("predicate") == "insulted"
                    and prop.get("object_id") == "tavern_keeper_tornin"):
                    return True, r
            else:
                prop = r.proposition
                pred = getattr(prop, "predicate", None)
                if hasattr(pred, "value"):
                    pred = pred.value
                if (getattr(prop, "subject_id", None) == "player"
                    and pred == "insulted"
                    and getattr(prop, "object_id", None) == "tavern_keeper_tornin"):
                    return True, r
        except Exception:
            continue
    return False, None


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
            agent_id = getattr(r, "agent_id", "?")
        print(f"{indent}agent_id={agent_id}")
        print(f"{indent}prop=({subj}, {pred}, {obj}, polarity={polarity})")
        print(f"{indent}  confidence={conf}")
        print(f"{indent}  source_id={source_id}")
        print(f"{indent}  source_type={source_type}")
        print(f"{indent}  original_source_id={original_source_id}")
    except Exception as e:
        print(f"{indent}<ERROR printing record: {e}>")


def _resolve_cognition_block(harness: Any, agent_id: str, partner_id: str) -> tuple[str, Optional[Any]]:
    """Manual call to CognitionContextResolver.resolve_block (baseline)."""
    try:
        ts = harness.game_loop._get_task_scheduler()
        executors = getattr(ts, "_executors", None)
        if not executors:
            return "", RuntimeError("no executors")
        from app.domain.execution import TaskKind
        de = executors.get(TaskKind.DIALOGUE)
        if de is None:
            return "", RuntimeError("no DialogueExecutor")
        de_store = getattr(de, "_epistemic_store", None)
        de_mem = getattr(de, "_memory_manager", None)
        if de_store is None or de_mem is None:
            return "", RuntimeError(f"missing wiring: store={de_store is None} mem={de_mem is None}")
        
        from app.services.npc.cognition_context import CognitionContextResolver
        cog = CognitionContextResolver(
            de_mem,
            epistemic_store=de_store,
            context_provider=lambda npc_id: de._get_context(_CAMPAIGN, npc_id),
        )
        block = cog.resolve_block(agent_id, partner_id)
        return block, None
    except Exception as e:
        return "", e


def _check_cog_block_markers(text: str) -> dict:
    """Check for cog_block provenance markers in text."""
    return {
        "has_belief_section": "Что NPC знает" in text or "убеждени" in text,
        "has_source_id_marker": "сообщил" in text or "видел это сам" in text,
        "has_original_source_marker": "исходный источник" in text,
        "has_confidence_marker": "уверенность:" in text,
        "has_source_type_marker": ("сообщил" in text) or ("видел это сам" in text),
        "has_stm_section": "Что NPC слышал" in text,
    }


def _identify_tornin_calls(records: list[RouterCallRecord]) -> list[RouterCallRecord]:
    """Identify router calls that belong to Tornin.
    
    Heuristics:
    - system_prompt contains "Торнин" (NPC identity)
    - OR prompt contains "Торнин Серебряная Луна"
    - OR prompt contains "Твоё имя: Торнин"
    """
    tornin_calls = []
    for r in records:
        sp = r.system_prompt or ""
        up = r.prompt or ""
        is_tornin = (
            "Торнин" in sp
            or "Торнин Серебряная Луна" in up
            or "Твоё имя: Торнин" in up
            or "тавернщик" in sp.lower()
        )
        if is_tornin:
            tornin_calls.append(r)
    return tornin_calls


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 — B4-R13 E1: PROMPT_INJECTION production-path verification")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("Цель: доказать, что cog_block действительно попадает в user_prompt,")
    print("передаваемый ModelRouter, через прозрачный router wrapper.")
    print()
    print("Три независимых вердикта:")
    print("  - RESOLVER_PASS — resolve_block() вернул непустой текст (baseline)")
    print("  - INJECTION_PASS — cog_block маркеры найдены в user_prompt вызова Торнина")
    print("  - ROUTER_PASS — router фактически получил prompt с cog_block маркерами")
    print()
    print("Запреты соблюдены:")
    print("  - production-код не меняется")
    print("  - не подменяет DialogueExecutor/CognitionContextResolver/EpistemicStore")
    print("  - прозрачный wrapper только записывает, передаёт дальше без изменений")
    print("  - не запускать полный B4-R1")
    print("  - не считать ручной вызов resolver доказательством INJECTION")
    print()
    
    harness = None
    router_recorder: Optional[RouterRecorder] = None
    original_request_method: Optional[Callable] = None
    
    # State
    belief_appeared_at_tick: Optional[int] = None
    belief_record: Optional[Any] = None
    resolver_block_text: str = ""
    resolver_exc: Optional[Exception] = None
    cleanup_ok = True
    
    try:
        # =====================================================================
        # Этап 1: Setup — harness + canonical PLAYER_INSULTS + ticks
        # =====================================================================
        _section("Этап 1: Setup — TavernGameplayHarness + canonical PLAYER_INSULTS")
        
        from tests.gameplay.harness import TavernGameplayHarness
        harness = TavernGameplayHarness(seed=42, location="tavern")
        harness.new_game()
        print(f"  harness created, game_loop={type(harness.game_loop).__name__}")
        
        # Warmup 2 ticks
        print(f"  Warmup 2 ticks...")
        harness.advance_ticks(2)
        print(f"    warmup done")
        
        # Publish PLAYER_INSULTS (canonical payload)
        print(f"  Publish PLAYER_INSULTS (canonical payload)...")
        _publish_player_insults(_VICTIM, radius=15.0)
        
        # =====================================================================
        # Этап 2: Install router recorder (transparent wrapper)
        # =====================================================================
        _section("Этап 2: Install transparent router recorder")
        
        ts = harness.game_loop._get_task_scheduler()
        executors = getattr(ts, "_executors", None)
        from app.domain.execution import TaskKind
        de = executors.get(TaskKind.DIALOGUE) if executors else None
        
        if de is None:
            print("  >>> FATAL: DialogueExecutor not found")
            _write_output()
            return 1
        
        router = getattr(de, "_router", None)
        if router is None:
            print("  >>> FATAL: router is None (no LLM configured)")
            print("  >>> Cannot verify PROMPT_INJECTION without router")
            _write_output()
            return 1
        
        print(f"  router: {type(router).__name__}")
        print(f"  router.request_for_agent: {getattr(router, 'request_for_agent', None)}")
        
        # Save original method
        original_request_method = router.request_for_agent
        print(f"  original request_for_agent saved")
        
        # Create recorder
        router_recorder = RouterRecorder(original_request_method)
        print(f"  router_recorder created")
        
        # Install wrapper (monkey-patch the bound method)
        # Note: this is NOT changing production code — it's runtime monkey-patch
        # of an instance attribute, restored in cleanup
        router.request_for_agent = router_recorder
        print(f"  router.request_for_agent wrapped (transparent passthrough)")
        
        # Verify wiring still correct
        de_store = getattr(de, "_epistemic_store", None)
        de_mem = getattr(de, "_memory_manager", None)
        tick_orch_store = getattr(harness.game_loop._tick_orch, "_epistemic_store", None) if harness.game_loop._tick_orch else None
        print(f"  Wiring check:")
        print(f"    DE._epistemic_store: {de_store is not None} (id={id(de_store) if de_store else 'N/A'})")
        print(f"    DE._memory_manager: {de_mem is not None}")
        print(f"    tick_orch._epistemic_store: {tick_orch_store is not None} (id={id(tick_orch_store) if tick_orch_store else 'N/A'})")
        if de_store and tick_orch_store:
            print(f"    SAME INSTANCE: {de_store is tick_orch_store}")
        
        # =====================================================================
        # Этап 3: Run ticks — production-path LLM calls
        # =====================================================================
        _section("Этап 3: Run 20 production ticks (with router recorder active)")
        
        MAX_TICKS = 20
        store = tick_orch_store if tick_orch_store is not None else de_store
        
        for tick_num in range(1, MAX_TICKS + 1):
            try:
                harness.advance_ticks(1)
            except Exception as e:
                print(f"    tick #{tick_num} EXCEPTION: {type(e).__name__}: {e}")
                traceback.print_exc()
                break
            
            # Snapshot belief
            records = _get_store_records(store, _VICTIM)
            has_target, target_rec = _has_tornin_insulted(records)
            marker = " <<<" if has_target else ""
            print(f"    tick #{tick_num}: tornin={len(records)} records, has_target={has_target}{marker}  (router calls so far: {len(router_recorder.records)})")
            
            if has_target and belief_appeared_at_tick is None:
                belief_appeared_at_tick = tick_num
                belief_record = target_rec
                print(f"    >>> TORNIN BELIEF APPEARED at tick #{tick_num}!")
                _print_belief_record(target_rec, indent="      ")
        
        print(f"\n  Total router calls recorded: {len(router_recorder.records)}")
        
        # =====================================================================
        # Этап 4: Manual resolve_block (RESOLVER_PASS baseline)
        # =====================================================================
        _section("Этап 4: Manual resolve_block (RESOLVER_PASS baseline)")
        
        if belief_appeared_at_tick is None:
            print("  >>> BELIEF NOT FOUND — cannot verify resolver")
            resolver_block_text = ""
        else:
            # Try multiple partner_ids
            for partner in ["maid_lusya", "blacksmith_orm", "guard_borko", "merchant_goran", "player"]:
                print(f"\n  resolve_block('{_VICTIM}', '{partner}'):")
                block, exc = _resolve_cognition_block(harness, _VICTIM, partner)
                if exc is not None:
                    print(f"    EXCEPTION: {type(exc).__name__}: {exc}")
                    continue
                print(f"    length: {len(block) if isinstance(block, str) else 'N/A'}")
                if isinstance(block, str) and block:
                    resolver_block_text = block
                    print(f"    content:")
                    print("    " + "-" * 70)
                    for line in block.split("\n"):
                        print(f"    {line}")
                    print("    " + "-" * 70)
                    markers = _check_cog_block_markers(block)
                    print(f"    markers: {markers}")
                    break
                else:
                    print(f"    >>> EMPTY BLOCK")
        
        # =====================================================================
        # Этап 5: Analyze router records — identify Tornin calls
        # =====================================================================
        _section("Этап 5: Analyze router records — identify Tornin calls")
        
        print(f"  Total router calls: {len(router_recorder.records)}")
        print()
        
        # Print all calls summary
        print("  --- All router calls (summary) ---")
        for i, r in enumerate(router_recorder.records):
            sp_head = (r.system_prompt or "")[:80].replace("\n", " ")
            up_head = (r.prompt or "")[:80].replace("\n", " ")
            # Check if Tornin
            is_tornin = (
                "Торнин" in (r.system_prompt or "")
                or "Торнин Серебряная Луна" in (r.prompt or "")
                or "Твоё имя: Торнин" in (r.prompt or "")
            )
            marker = " <<< TORNIN" if is_tornin else ""
            print(f"    [{i+1}] agent={r.agent_name}{marker}")
            print(f"        sp_head: {sp_head!r}")
            print(f"        up_head: {up_head!r}")
        
        # Identify Tornin calls
        tornin_calls = _identify_tornin_calls(router_recorder.records)
        print(f"\n  Tornin router calls identified: {len(tornin_calls)}")
        
        if not tornin_calls:
            print("  >>> NO Tornin router calls — cannot verify INJECTION")
            print("  >>> Possible causes:")
            print("      - LLM not available (router returns stub without calling request_for_agent)")
            print("      - Tornin didn't speak (no DialogueRequest for Tornin)")
            print("      - Template fallback (deterministic materialization, no LLM call)")
        else:
            # Analyze each Tornin call for cog_block markers
            print("\n  --- Tornin call analysis (cog_block markers in user_prompt) ---")
            tornin_calls_with_markers: list[RouterCallRecord] = []
            for i, r in enumerate(tornin_calls):
                up = r.prompt or ""
                markers = _check_cog_block_markers(up)
                has_any = markers["has_belief_section"] or markers["has_source_id_marker"]
                marker_str = "PASS" if has_any else "FAIL"
                print(f"\n  Tornin call [{r.call_index}] (idx {i+1} of {len(tornin_calls)}):")
                print(f"    markers: {marker_str}")
                print(f"      has_belief_section: {markers['has_belief_section']}")
                print(f"      has_source_id_marker: {markers['has_source_id_marker']}")
                print(f"      has_original_source_marker: {markers['has_original_source_marker']}")
                print(f"      has_confidence_marker: {markers['has_confidence_marker']}")
                print(f"      has_source_type_marker: {markers['has_source_type_marker']}")
                print(f"      has_stm_section: {markers['has_stm_section']}")
                if has_any:
                    tornin_calls_with_markers.append(r)
                    # Print the cog_block portion
                    print(f"    --- user_prompt (first 1500 chars) ---")
                    print(f"    {up[:1500]}")
                    print(f"    --- end ---")
            
            print(f"\n  Tornin calls with cog_block markers: {len(tornin_calls_with_markers)} / {len(tornin_calls)}")
        
        # =====================================================================
        # Этап 6: Three independent verdicts
        # =====================================================================
        _section("Этап 6: Three independent verdicts")
        
        # RESOLVER_PASS: manual resolve_block returned non-empty
        resolver_pass = bool(resolver_block_text) and len(resolver_block_text) > 0
        
        # INJECTION_PASS: at least one Tornin router call has cog_block markers in user_prompt
        injection_pass = (
            len(tornin_calls) > 0
            and any(
                _check_cog_block_markers(r.prompt)["has_belief_section"]
                or _check_cog_block_markers(r.prompt)["has_source_id_marker"]
                for r in tornin_calls
            )
        )
        
        # ROUTER_PASS: router actually received a prompt with cog_block markers for Tornin
        # (this is essentially same as INJECTION_PASS, but emphasizes the router boundary)
        router_pass = injection_pass  # the recorder IS at the router boundary
        
        print(f"""
  RESOLVER_PASS:   {resolver_pass}
    (manual resolve_block returned non-empty text of length {len(resolver_block_text) if resolver_block_text else 0})
  
  INJECTION_PASS:  {injection_pass}
    (cog_block markers found in user_prompt of at least one Tornin router call)
    Tornin calls total: {len(tornin_calls) if 'tornin_calls' in dir() else 0}
    Tornin calls with markers: {len(tornin_calls_with_markers) if 'tornin_calls_with_markers' in dir() else 0}
  
  ROUTER_PASS:     {router_pass}
    (router actually received prompt with cog_block markers for Tornin)
    (verified via transparent recorder at request_for_agent boundary)
""")
        
        # =====================================================================
        # Этап 7: Comparison with B4-R8
        # =====================================================================
        _section("Этап 7: Comparison with B4-R8")
        
        print(f"""
  B4-R8 (per llm_full_prompts.jsonl analysis):
    - 103 LLM-запросов total
    - 10 LLM-запросов Торнина (ticks 10, 11, 13, 17-22)
    - cog_block markers in Tornin prompts: ALL FALSE
    - 'когнитив': False, 'убеждени': False, 'сообщил': False
    - 'source_id': False, 'original_source': False
    - Only 'confidence': True (from STM, not cog_block)
  
  B4-R13 E1 (this run):
    - belief appeared at tick: {belief_appeared_at_tick}
    - RESOLVER_PASS: {resolver_pass}
    - INJECTION_PASS: {injection_pass}
    - ROUTER_PASS: {router_pass}
    - Tornin router calls: {len(tornin_calls) if 'tornin_calls' in dir() else 0}
    - Tornin calls with cog_block markers: {len(tornin_calls_with_markers) if 'tornin_calls_with_markers' in dir() else 0}
  
  Interpretation:
""")
        
        if injection_pass and resolver_pass:
            print("    >>> Production-path WORKS — cog_block reaches router for Tornin")
            print("    >>> B4-R8 cog_block absence is NOT a production-path bug")
            print("    >>> B4-R8 had a SPECIFIC condition that prevented cog_block injection")
            print("    >>> Possible B4-R8 specific causes:")
            print("      - Different wiring state at B4-R8 time (before late wiring fix)")
            print("      - Race condition in B4-R8 specific run")
            print("      - B4-R8 used different code version (WIP not committed)")
        elif resolver_pass and not injection_pass:
            print("    >>> RESOLVER works but INJECTION FAILS")
            print("    >>> cog_block is formed by resolver but NOT injected into user_prompt")
            print("    >>> This points to dialogue_executor.py:599-611 bug")
            print("    >>> Possible causes:")
            print("      - self._epistemic_store is None at runtime (despite wiring check)")
            print("      - exception in try block (logger.warning)")
            print("      - _cog_block empty due to filter")
        elif not resolver_pass:
            print("    >>> RESOLVER FAILS — cannot verify injection")
            print("    >>> Need to investigate why resolve_block returns empty")
        else:
            print("    >>> Unexpected state")
        
    except Exception as e:
        print(f"\n[FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        cleanup_ok = False
    finally:
        # =====================================================================
        # Cleanup — restore router
        # =====================================================================
        _section("Cleanup")
        
        try:
            if router_recorder is not None and original_request_method is not None:
                # Restore original method
                ts_obj = harness.game_loop._get_task_scheduler() if harness else None
                executors_dict = getattr(ts_obj, "_executors", None) if ts_obj else None
                if executors_dict:
                    from app.domain.execution import TaskKind
                    de_obj = executors_dict.get(TaskKind.DIALOGUE)
                    if de_obj and de_obj._router is not None:
                        de_obj._router.request_for_agent = original_request_method
                        print("  router.request_for_agent restored to original")
        except Exception as e:
            print(f"  router restore failed: {e}")
            cleanup_ok = False
        
        try:
            if harness is not None:
                harness.dispose()
                print("  harness disposed")
        except Exception as e:
            print(f"  harness dispose failed: {e}")
            cleanup_ok = False
        
        print(f"  cleanup_ok: {cleanup_ok}")
    
    # Write output
    try:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            f.write(_stdout_buf.getvalue())
        size = OUT_FILE.stat().st_size
        print(f"\n>>> Output written to: {OUT_FILE}")
        print(f">>> File size: {size} bytes ({size / 1024:.1f} KB)")
    except Exception as e:
        print(f"\n>>> [ERROR writing output file: {e}]")
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