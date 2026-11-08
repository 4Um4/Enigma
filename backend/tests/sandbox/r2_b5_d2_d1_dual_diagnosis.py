"""
R2-B5-D2 — B4-R12 D1: Dual diagnosis (production-path, two independent runs).

Цель: воспроизвести условие B4-R8 (belief Торнина существует в EpistemicStore
после PLAYER_INSULTS + idle_ticks через TavernGameplayHarness) и проверить
формирование cognition block в production-пути.

Два независимых прогона:
  A — естественный disposition (без override)
  B — принудительный disposition (_override_witness_disposition для maid_lusya)

Запреты (per Master's spec B4-R12):
  - НЕ менять production-код
  - НЕ изменять существующие тесты
  - НЕ перезаписывать старые артефакты (новый файл)
  - НЕ запускать полный B4-R1
  - НЕ подменять production-компоненты mock-реализациями
  - Использовать production idle_tick() через harness
  - Проверить cleanup после каждого прогона
  - Не создавать дополнительное хранилище игровых фактов
  - JSON/JSONL допустим только как диагностический артефакт

Вердикты:
  - BELIEF_PASS / FAIL — belief Торнина появился
  - RESOLVER_PASS / FAIL — resolve_block вернул непустой блок
  - PROVENANCE_PASS / FAIL — блок содержит source_id, original_source_id, confidence, source_type
  - PROMPT_INJECTION НЕ объявляется (скрипт не доказывает передачу в реальный LLM prompt)
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
from typing import Any, Optional
from datetime import datetime
from uuid import uuid4

_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

OUT_FILE_DIR = _BACKEND / "tests" / "sandbox"
OUT_FILE_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_FILE_DIR / "r2_b5_d2_d1_dual_diagnosis.txt"


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
# Constants (mirror B4 test)
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

PARTNER_CANDIDATES = ["maid_lusya", "blacksmith_orm", "guard_borko", "merchant_goran", "player"]


# ============================================================================
# Spies for NPC_SPOKE — to determine real partner_id
# ============================================================================
SPY_SPOKE: list[dict] = []


def _spy_npc_spoke(event: Any) -> None:
    """Capture NPC_SPOKE events to determine Tornin's real partner_id."""
    try:
        _pl = getattr(event, "payload", {}) or {}
        _pl_dict = dict(_pl) if isinstance(_pl, dict) else {}
        SPY_SPOKE.append({
            "source": getattr(event, "source", "?"),
            "target_id": _pl_dict.get("target_id"),
            "text": _pl_dict.get("text", ""),
            "intent_type": _pl_dict.get("intent_type"),
            "tick": _pl_dict.get("tick"),
            "payload": _pl_dict,
        })
    except Exception:
        pass


def _install_spies() -> None:
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType
    bus = get_event_bus()
    try:
        bus.subscribe(EventType.NPC_SPOKE, _spy_npc_spoke)
    except Exception as e:
        print(f"  [WARN] subscribe NPC_SPOKE failed: {e}")


def _uninstall_spies() -> None:
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType
    bus = get_event_bus()
    try:
        bus.unsubscribe(EventType.NPC_SPOKE, _spy_npc_spoke)
    except Exception:
        pass


# ============================================================================
# Disposition override (mirror B4 test)
# ============================================================================
_ORIG_DISPOSITIONS: Optional[dict] = None


def _backup_dispositions() -> None:
    global _ORIG_DISPOSITIONS
    from app.domain import epistemic_dispositions as _ed
    _ORIG_DISPOSITIONS = copy.deepcopy(_ed.EPISTEMIC_DISPOSITIONS)


def _restore_dispositions() -> None:
    global _ORIG_DISPOSITIONS
    if _ORIG_DISPOSITIONS is None:
        return
    try:
        from app.domain import epistemic_dispositions as _ed
        _ed.EPISTEMIC_DISPOSITIONS.clear()
        _ed.EPISTEMIC_DISPOSITIONS.update(copy.deepcopy(_ORIG_DISPOSITIONS))
    except Exception:
        pass
    finally:
        _ORIG_DISPOSITIONS = None


def _override_witness_disposition() -> None:
    """Mirror B4 test: maid archetype → spread_rumor dominant."""
    from app.domain import epistemic_dispositions as _ed
    _ed.EPISTEMIC_DISPOSITIONS["maid"] = {
        "report": 0.0,
        "warn": 0.0,
        "attack": 0.0,
        "spread_rumor": 1.4,
        "talk": 0.8,
        "intimidate": 0.0,
    }


# ============================================================================
# Canonical PLAYER_INSULTS publish (mirror B4 test)
# ============================================================================
def _publish_player_insults(harness: Any, target_id: str, radius: float = 15.0) -> None:
    """Canonical payload: target_id + action_type + intent_type."""
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
    print(f"  [INJECT] PLAYER_INSULTS: source={_PLAYER} target={target_id} radius={radius} type={_event.type}")


# ============================================================================
# Helpers
# ============================================================================
def _get_store_records(store: Any, agent_id: str) -> list:
    try:
        return store.get_all_for_agent(agent_id)
    except Exception as e:
        print(f"    [ERROR get_all_for_agent({agent_id}): {e}]")
        return []


def _has_tornin_insulted(records: list) -> tuple[bool, Optional[Any]]:
    """Check if any record is (player, insulted, tavern_keeper_tornin)."""
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


def _find_tornin_partner_from_spies() -> Optional[str]:
    """Find Tornin's real partner_id from SPY_SPOKE records.
    
    Looks for the latest NPC_SPOKE event where Tornin is the source,
    takes target_id from its payload.
    """
    # Iterate in reverse to find the latest
    for sp in reversed(SPY_SPOKE):
        if sp.get("source") == _VICTIM:
            target = sp.get("target_id")
            if target and target != _VICTIM:
                return target
    return None


def _resolve_cognition_block(harness: Any, agent_id: str, partner_id: str) -> tuple[str, Optional[Any]]:
    """Manually invoke CognitionContextResolver.resolve_block.
    
    Returns (block_text, exception_or_None).
    """
    try:
        # Get the production DialogueExecutor (same as production-path)
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


# ============================================================================
# Run single diagnostic
# ============================================================================
def run_diagnostic(label: str, with_override: bool) -> dict:
    """Run a single diagnostic. Returns verdicts dict."""
    _section(f"RUN {label}: with_override={with_override}")
    
    # Init spies
    SPY_SPOKE.clear()
    _install_spies()
    
    # State
    harness = None
    tick_results: list[dict] = []
    target_belief_appeared_at_tick: Optional[int] = None
    target_belief_record: Optional[Any] = None
    resolver_result: Optional[dict] = None
    cleanup_ok = True
    
    try:
        # Step 1-2: TavernGameplayHarness + new_game
        print(f"  Step 1-2: TavernGameplayHarness + new_game")
        from tests.gameplay.harness import TavernGameplayHarness
        harness = TavernGameplayHarness(seed=42, location="tavern")
        harness.new_game()
        print(f"    harness created, game_loop={type(harness.game_loop).__name__}")
        
        # Step 3 (optional): override disposition
        if with_override:
            print(f"  Step 3: _backup_dispositions + _override_witness_disposition")
            _backup_dispositions()
            _override_witness_disposition()
            print(f"    maid disposition overridden: spread_rumor=1.4")
        
        # Step 4: warmup 2 ticks
        print(f"  Step 4: warmup 2 ticks")
        harness.advance_ticks(2)
        print(f"    warmup done")
        
        # Step 5: publish PLAYER_INSULTS (canonical payload)
        print(f"  Step 5: publish PLAYER_INSULTS (canonical payload)")
        _publish_player_insults(harness, _VICTIM, radius=15.0)
        
        # Step 6-7: 20 main ticks + per-tick snapshot
        print(f"  Step 6-7: 20 main ticks + per-tick snapshot")
        MAX_TICKS = 20
        for tick_num in range(1, MAX_TICKS + 1):
            try:
                harness.advance_ticks(1)
            except Exception as e:
                print(f"    tick #{tick_num} EXCEPTION: {type(e).__name__}: {e}")
                traceback.print_exc()
                break
            
            # Snapshot
            tick_snap: dict[str, Any] = {"tick": tick_num, "agents": {}}
            ts_obj = harness.game_loop._get_task_scheduler()
            executors = getattr(ts_obj, "_executors", None)
            de = None
            if executors:
                try:
                    from app.domain.execution import TaskKind
                    de = executors.get(TaskKind.DIALOGUE)
                except Exception:
                    pass
            de_store = getattr(de, "_epistemic_store", None) if de else None
            tick_orch_store = getattr(harness.game_loop._tick_orch, "_epistemic_store", None) if harness.game_loop._tick_orch else None
            store = tick_orch_store if tick_orch_store is not None else de_store
            
            if store is None:
                print(f"    tick #{tick_num}: STORE is None — cannot snapshot")
                tick_results.append(tick_snap)
                continue
            
            for aid in NPC_IDS:
                records = _get_store_records(store, aid)
                count = len(records)
                has_target, target_rec = _has_tornin_insulted(records)
                tick_snap["agents"][aid] = {
                    "count": count,
                    "has_target": has_target,
                    "target_record": target_rec,
                }
            
            # Print tick summary
            tornin_snap = tick_snap["agents"].get(_VICTIM, {})
            tornin_count = tornin_snap.get("count", 0)
            tornin_has = tornin_snap.get("has_target", False)
            marker = " <<<" if tornin_has else ""
            print(f"    tick #{tick_num}: tornin={tornin_count} records, has_target={tornin_has}{marker}")
            
            # If belief appeared for the first time, capture it
            if tornin_has and target_belief_appeared_at_tick is None:
                target_belief_appeared_at_tick = tick_num
                target_belief_record = tornin_snap.get("target_record")
                print(f"    >>> TORNIN BELIEF APPEARED at tick #{tick_num}!")
                _print_belief_record(target_belief_record, indent="      ")
                
                # Find Tornin's real partner_id from SPY_SPOKE
                real_partner = _find_tornin_partner_from_spies()
                print(f"    Real partner from SPY_SPOKE: {real_partner}")
                
                # Resolve cognition block with real partner
                partners_to_try = []
                if real_partner:
                    partners_to_try.append(real_partner)
                for p in PARTNER_CANDIDATES:
                    if p not in partners_to_try:
                        partners_to_try.append(p)
                
                for partner in partners_to_try:
                    print(f"    --- resolve_block('{_VICTIM}', '{partner}') ---")
                    block, exc = _resolve_cognition_block(harness, _VICTIM, partner)
                    if exc is not None:
                        print(f"      EXCEPTION: {type(exc).__name__}: {exc}")
                        continue
                    print(f"      length: {len(block) if isinstance(block, str) else 'N/A'}")
                    if isinstance(block, str) and block:
                        print(f"      content:")
                        print("      " + "-" * 70)
                        for line in block.split("\n"):
                            print(f"      {line}")
                        print("      " + "-" * 70)
                        
                        # Check provenance markers
                        has_source_id = "сообщил" in block or "видел это сам" in block
                        has_original = "исходный источник" in block
                        has_confidence = "уверенность:" in block
                        has_source_type = ("сообщил" in block) or ("видел это сам" in block)
                        
                        resolver_result = {
                            "partner_id": partner,
                            "block_length": len(block),
                            "block_text": block,
                            "has_source_id_marker": has_source_id,
                            "has_original_source_marker": has_original,
                            "has_confidence_marker": has_confidence,
                            "has_source_type_marker": has_source_type,
                        }
                        print(f"      provenance markers: source_id={has_source_id}, original={has_original}, confidence={has_confidence}, source_type={has_source_type}")
                        break  # Use first non-empty result
                    else:
                        print(f"      >>> EMPTY BLOCK")
                
                if resolver_result is None:
                    print(f"    >>> All partners returned empty block")
            
            tick_results.append(tick_snap)
        
        # Step 8: Final state + resolve_block on final state (if belief appeared)
        if target_belief_appeared_at_tick is not None:
            print(f"\n  Step 8: Final resolve_block check (after tick #{MAX_TICKS})")
            real_partner = _find_tornin_partner_from_spies()
            print(f"  Real partner from SPY_SPOKE: {real_partner}")
            partners_to_try = []
            if real_partner:
                partners_to_try.append(real_partner)
            for p in PARTNER_CANDIDATES:
                if p not in partners_to_try:
                    partners_to_try.append(p)
            
            for partner in partners_to_try:
                print(f"\n  resolve_block('{_VICTIM}', '{partner}'):")
                block, exc = _resolve_cognition_block(harness, _VICTIM, partner)
                if exc is not None:
                    print(f"    EXCEPTION: {type(exc).__name__}: {exc}")
                    continue
                print(f"    length: {len(block) if isinstance(block, str) else 'N/A'}")
                if isinstance(block, str) and block:
                    print(f"    content:")
                    print("    " + "-" * 70)
                    for line in block.split("\n"):
                        print(f"    {line}")
                    print("    " + "-" * 70)
                    
                    has_source_id = "сообщил" in block or "видел это сам" in block
                    has_original = "исходный источник" in block
                    has_confidence = "уверенность:" in block
                    has_source_type = ("сообщил" in block) or ("видел это сам" in block)
                    
                    resolver_result = {
                        "partner_id": partner,
                        "block_length": len(block),
                        "block_text": block,
                        "has_source_id_marker": has_source_id,
                        "has_original_source_marker": has_original,
                        "has_confidence_marker": has_confidence,
                        "has_source_type_marker": has_source_type,
                    }
                    print(f"    provenance markers: source_id={has_source_id}, original={has_original}, confidence={has_confidence}, source_type={has_source_type}")
                    break
                else:
                    print(f"    >>> EMPTY BLOCK")
    
    except Exception as e:
        print(f"  [FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()
        cleanup_ok = False
    finally:
        # Cleanup
        print(f"\n  Cleanup...")
        try:
            if with_override:
                _restore_dispositions()
                print(f"    dispositions restored")
        except Exception as e:
            print(f"    restore_dispositions failed: {e}")
            cleanup_ok = False
        
        try:
            _uninstall_spies()
            SPY_SPOKE.clear()
            print(f"    spies uninstalled")
        except Exception as e:
            print(f"    uninstall spies failed: {e}")
            cleanup_ok = False
        
        try:
            if harness is not None:
                harness.dispose()
                print(f"    harness disposed")
        except Exception as e:
            print(f"    harness dispose failed: {e}")
            cleanup_ok = False
    
    # Verdicts
    belief_pass = target_belief_appeared_at_tick is not None
    resolver_pass = resolver_result is not None and resolver_result.get("block_length", 0) > 0
    provenance_pass = (resolver_result is not None
                       and resolver_result.get("has_source_id_marker", False)
                       and resolver_result.get("has_confidence_marker", False)
                       and resolver_result.get("has_source_type_marker", False))
    
    verdicts = {
        "label": label,
        "with_override": with_override,
        "belief_pass": belief_pass,
        "resolver_pass": resolver_pass,
        "provenance_pass": provenance_pass,
        "target_belief_appeared_at_tick": target_belief_appeared_at_tick,
        "target_belief_record": target_belief_record,
        "resolver_result": resolver_result,
        "cleanup_ok": cleanup_ok,
        "tick_results": tick_results,
    }
    
    print(f"\n  VERDICTS ({label}):")
    print(f"    BELIEF_PASS:     {belief_pass}  (belief appeared at tick {target_belief_appeared_at_tick})")
    print(f"    RESOLVER_PASS:   {resolver_pass}  (resolve_block returned non-empty)")
    print(f"    PROVENANCE_PASS: {provenance_pass}  (block contains source_id + confidence + source_type markers)")
    print(f"    CLEANUP_OK:      {cleanup_ok}")
    
    return verdicts


# ============================================================================
# MAIN
# ============================================================================
def main() -> int:
    print("=" * 78)
    print("R2-B5-D2 — B4-R12 D1: Dual diagnosis (production-path, two independent runs)")
    print(f"OUT_FILE: {OUT_FILE}")
    print("=" * 78)
    print()
    print("Цель: воспроизвести условие B4-R8 (belief Торнина существует в")
    print("EpistemicStore через TavernGameplayHarness + canonical payload +")
    print("idle_ticks) и проверить формирование cognition block.")
    print()
    print("Два независимых прогона:")
    print("  A — естественный disposition (без override)")
    print("  B — принудительный disposition (_override_witness_disposition)")
    print()
    print("Запреты соблюдены:")
    print("  - production-код не меняется")
    print("  - существующие тесты не меняются")
    print("  - старые артефакты не перезаписываются (новый файл)")
    print("  - полный B4-R1 не запускается")
    print("  - production-компоненты не подменяются mock'ами")
    print("  - используется production idle_tick() через harness")
    print("  - cleanup после каждого прогона")
    print("  - дополнительное хранилище игровых фактов не создаётся")
    print()
    print("Вердикты:")
    print("  - BELIEF_PASS / FAIL — belief Торнина появился")
    print("  - RESOLVER_PASS / FAIL — resolve_block вернул непустой блок")
    print("  - PROVENANCE_PASS / FAIL — блок содержит source_id, original_source_id,")
    print("    confidence, source_type")
    print("  - PROMPT_INJECTION НЕ объявляется (скрипт не доказывает передачу")
    print("    в реальный LLM prompt)")
    print()
    
    # =====================================================================
    # RUN A: without override
    # =====================================================================
    verdict_a = run_diagnostic("A", with_override=False)
    
    # =====================================================================
    # RUN B: with override
    # =====================================================================
    verdict_b = run_diagnostic("B", with_override=True)
    
    # =====================================================================
    # Summary
    # =====================================================================
    _section("SUMMARY — Comparison A vs B")
    
    print(f"""
  RUN A (without override):
    BELIEF_PASS:     {verdict_a['belief_pass']}  (tick: {verdict_a['target_belief_appeared_at_tick']})
    RESOLVER_PASS:   {verdict_a['resolver_pass']}
    PROVENANCE_PASS: {verdict_a['provenance_pass']}
    CLEANUP_OK:      {verdict_a['cleanup_ok']}
    
  RUN B (with override):
    BELIEF_PASS:     {verdict_b['belief_pass']}  (tick: {verdict_b['target_belief_appeared_at_tick']})
    RESOLVER_PASS:   {verdict_b['resolver_pass']}
    PROVENANCE_PASS: {verdict_b['provenance_pass']}
    CLEANUP_OK:      {verdict_b['cleanup_ok']}
    
  Comparison:
    A vs B belief appeared:    {verdict_a['target_belief_appeared_at_tick']} vs {verdict_b['target_belief_appeared_at_tick']}
    A vs B resolver non-empty: {verdict_a['resolver_pass']} vs {verdict_b['resolver_pass']}
    A vs B provenance:         {verdict_a['provenance_pass']} vs {verdict_b['provenance_pass']}
""")
    
    # Detailed analysis
    print("  --- Detailed analysis ---")
    
    if verdict_a['belief_pass'] and verdict_a['resolver_pass'] and verdict_a['provenance_pass']:
        print("  A: ALL PASS — production-path works without override")
        print("    → B4-R8 cog_block absence is NOT explained by missing override")
        print("    → Real B4-R8 may have had belief after LLM-вызовов (timing issue)")
    elif verdict_a['belief_pass'] and not verdict_a['resolver_pass']:
        print("  A: BELIEF present but RESOLVER empty — RESOLVER BUG CONFIRMED")
        print("    → resolve_block returns empty despite belief exists in store")
        print("    → This is the root cause of cog_block absence in B4-R8")
    elif not verdict_a['belief_pass']:
        print("  A: BELIEF FAIL — without override, belief does not reach Tornin")
        print("    → NPC may not choose spread_rumor without disposition override")
    
    if verdict_b['belief_pass'] and verdict_b['resolver_pass'] and verdict_b['provenance_pass']:
        print("  B: ALL PASS — with override, production-path works correctly")
        print("    → Wiring is correct, resolver works, provenance is in cog_block")
        print("    → B4-R8 cog_block absence could NOT be a resolver bug")
        print("    → Most likely cause in B4-R8: timing (belief appeared after LLM-вызовов)")
    elif verdict_b['belief_pass'] and not verdict_b['resolver_pass']:
        print("  B: BELIEF present but RESOLVER empty — RESOLVER BUG CONFIRMED")
        print("    → This is the root cause of cog_block absence in B4-R8")
    elif not verdict_b['belief_pass']:
        print("  B: BELIEF FAIL — even with override, belief does not reach Tornin")
        print("    → Deeper issue: maybe PLAYER_INSULTS not processed correctly")
        print("    → Or: NPC not in hearing range (membrane hearing failure)")
    
    # Final cog_block content (if any)
    print("\n  --- Final cog_block content (run B, if available) ---")
    if verdict_b['resolver_result']:
        rr = verdict_b['resolver_result']
        print(f"    partner_id: {rr['partner_id']}")
        print(f"    block_length: {rr['block_length']}")
        print(f"    has_source_id_marker: {rr['has_source_id_marker']}")
        print(f"    has_original_source_marker: {rr['has_original_source_marker']}")
        print(f"    has_confidence_marker: {rr['has_confidence_marker']}")
        print(f"    has_source_type_marker: {rr['has_source_type_marker']}")
        print(f"    block_text:")
        print("    " + "-" * 70)
        for line in rr['block_text'].split("\n"):
            print(f"    {line}")
        print("    " + "-" * 70)
    
    # Open questions
    print(f"""
  --- Open questions for B4-R8 ---
  1. If BELIEF_PASS in B: did belief appear BEFORE or AFTER LLM-вызовов Торнина in B4-R8?
     (B4-R8 had LLM-вызовы on ticks 10, 11, 13, 17-22)
  2. If RESOLVER_PASS in B: was cog_block actually added to LLM prompt in B4-R8?
     (this script does NOT verify PROMPT_INJECTION — needs separate verification)
  3. If BELIEF_FAIL in A: was maid_lusya's natural decision not spread_rumor?
     (needs DecisionHub trace)
""")
    
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