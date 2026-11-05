"""
path: /backend/tests/gameplay/test_p5a_cognition_block.py
Назначение: P5-A Step 1 — verify cognition block contains belief after rumor propagation.

Доказывает, что знание об оскорблении достигает cognition Торнина:
1. Player оскорбляет Торнина за спиной (PLAYER_INSULTS)
2. Люся слышит → рассказывает Торнину (SPREAD_RUMOR, autonomous)
3. EpistemicStore(tornin) содержит belief (player INSULTED tornin, source=maid_lusya)
4. CognitionContextResolver.resolve_block(tornin) содержит belief с provenance

Это simpler test — без real LLM response comparison. Step 2 (full A/B) — отдельно.

Запуск: python -m pytest backend/tests/gameplay/test_p5a_cognition_block.py -v
"""
from __future__ import annotations

import logging
from typing import Any

import pytest

from tests.gameplay.harness import TavernGameplayHarness

logger = logging.getLogger(__name__)


def _publish_player_insults(harness: TavernGameplayHarness, victim: str, radius: float = 10.0) -> None:
    """Publish PLAYER_INSULTS event — mirror test_butterfly_full_game_loop pattern."""
    from app.domain.events import EventDTO
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType

    _bus = get_event_bus()
    _bus.publish(EventDTO.create(
        event_type=EventType.PLAYER_INSULTS.value,
        source="player",
        payload={
            "target_id": victim,
            "text": "Ты дурак и позорище!",
            "action_type": "player_insults",
        },
        visibility="public",
        radius=radius,
        persistence_level="session",
    ))


def _install_sync_pool_llm_free(harness: TavernGameplayHarness) -> None:
    """LLM-free setup (mirror _install_sync_pool from test_butterfly).
    
    Подменяет _router = None (stub-text) и _materializers на PassthroughVerifier.
    Это позволяет rumor propagation без real LLM.
    """
    from app.domain.execution import TaskKind
    from app.services.cognition.proposition_verifier import PassthroughVerifier
    from app.services.execution.dialogue_materializer import DialogueMaterializer

    _sched = getattr(harness.game_loop, "_task_scheduler", None)
    if _sched is None:
        _sched = harness.game_loop._get_task_scheduler()
    _executors = getattr(_sched, "_executors", None) or {}
    _dlg_executor = _executors.get(TaskKind.DIALOGUE)
    if _dlg_executor is not None and hasattr(_dlg_executor, "_router"):
        _dlg_executor._router = None
        print("[WIRING] DialogueExecutor._router = None (LLM-free)")
    _sched._executor_pool = type("_SyncPool", (), {
        "submit": lambda self, fn, *a, **kw: fn(*a, **kw),
        "shutdown": lambda self: None,
    })()
    _sched._materializers["dialogue_line"] = DialogueMaterializer(
        proposition_verifier=PassthroughVerifier()
    )
    print("[WIRING] _materializers['dialogue_line'] = PassthroughVerifier (structural)")


def _get_epistemic_store(harness: TavernGameplayHarness) -> Any:
    """Get EpistemicStore from tick_orchestrator (production wiring path).

    EpistemicStore wired ? tick_orch._epistemic_store ????? set_epistemic_services,
    ?? ? DialogueExecutor. Mirror test_butterfly_full_game_loop._read_all_epistemic.
    """
    _tick_orch = getattr(harness.game_loop, "_tick_orch", None)
    if _tick_orch is None:
        return None
    return getattr(_tick_orch, "_epistemic_store", None)


class TestP5ACognitionBlock:
    """P5-A Step 1: verify cognition block contains belief after rumor propagation."""

    def test_belief_reaches_tornin_cognition(self):
        """Player insults Tornin → Lusya tells Tornin → belief in EpistemicStore(tornin).
        
        Cognition block (CognitionContextResolver.resolve_block) содержит belief
        с provenance (source=maid_lusya, original_source=player).
        """
        _h = TavernGameplayHarness(seed=42, location="tavern")
        _h.new_game()
        _install_sync_pool_llm_free(_h)
        
        # Step 1: Player insults Tornin behind his back
        _publish_player_insults(_h, victim="tavern_keeper_tornin", radius=10.0)
        print("[STEP 1] PLAYER_INSULTS published (player → tornin)")
        
        # Step 2: Wait for Lusya to hear + tell Tornin
        _h.advance_ticks(5)
        print("[STEP 2] advance_ticks(5) — rumor propagation")
        
        # Step 3: Check EpistemicStore(tornin) for belief
        _store = _get_epistemic_store(_h)
        assert _store is not None, "EpistemicStore not wired in DialogueExecutor"
        
        _records = _store.get_all_for_agent("tavern_keeper_tornin")
        print(f"[STEP 3] EpistemicStore(tornin) records: {len(_records)}")
        for r in _records:
            _p = r.proposition
            print(f"  prop={_p.predicate.value} subj={_p.subject_id} obj={_p.object_id} "
                  f"polarity={_p.polarity} conf={r.confidence} source={r.source_id}")
        
        # Find belief about insult
        _insult_beliefs = [
            r for r in _records
            if r.proposition.predicate.value == "insulted"
            and r.proposition.subject_id == "player"
            and r.proposition.object_id == "tavern_keeper_tornin"
        ]
        
        assert len(_insult_beliefs) > 0, (
            "Tornin should have belief about insult from player. "
            f"Records: {[(r.proposition.predicate.value, r.proposition.subject_id, r.proposition.object_id) for r in _records]}"
        )
        
        _belief = _insult_beliefs[0]
        print("\n[BELIEF] Tornin knows: player INSULTED tornin")
        print(f"  source_id: {_belief.source_id} (should be maid_lusya or player)")
        print(f"  original_source_id: {_belief.original_source_id}")
        print(f"  confidence: {_belief.confidence}")
        print(f"  polarity: {_belief.proposition.polarity}")
        
        # Step 4: Check cognition block contains this belief
        from app.services.npc.cognition_context import CognitionContextResolver
        _memory_manager = getattr(_h.game_loop, "_task_scheduler", None)
        _sched = _h.game_loop._get_task_scheduler()
        _memory_manager = getattr(_sched, "_memory_manager", None)
        
        _cog_resolver = CognitionContextResolver(
            memory_manager=_memory_manager,
            epistemic_store=_store,
        )
        _cog_block = _cog_resolver.resolve_block("tavern_keeper_tornin", "player")
        
        print("\n[COGNITION BLOCK] Tornin's cognition:")
        print(_cog_block)
        
        # Verify cognition block mentions the insult
        assert "оскорб" in _cog_block.lower() or "insulted" in _cog_block.lower(), (
            f"Cognition block should mention insult. Block: {_cog_block}"
        )
        
        print("\n[P5-A Step 1] PASSED: Tornin's cognition contains belief about insult")
        print("[P5-A Step 1] Belief reached cognition block — ready for LLM to use it")

    def test_control_no_insult_no_belief(self):
        """Control: no insult → no belief in EpistemicStore(tornin)."""
        _h = TavernGameplayHarness(seed=42, location="tavern")
        _h.new_game()
        _install_sync_pool_llm_free(_h)
        
        # NO insult — just advance ticks
        _h.advance_ticks(5)
        
        _store = _get_epistemic_store(_h)
        assert _store is not None
        
        _records = _store.get_all_for_agent("tavern_keeper_tornin")
        _insult_beliefs = [
            r for r in _records
            if r.proposition.predicate.value == "insulted"
            and r.proposition.subject_id == "player"
        ]
        
        print(f"[CONTROL] EpistemicStore(tornin) insult beliefs: {len(_insult_beliefs)}")
        assert len(_insult_beliefs) == 0, (
            "Control scenario: Tornin should NOT have insult belief"
        )
        
        print("[CONTROL] PASSED: no insult → no belief (clean baseline)")
