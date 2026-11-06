"""
path: /backend/tests/gameplay/test_p5a_step2_ab_experiment.py
Назначение: P5-A Step 2 — A/B experiment с real LLM.

Master directive: проверить, превращается ли знание в самостоятельное поведение NPC.

A: player оскорбляет Торнина → Люся рассказывает → Торнин знает → player говорит с Торнином
B: control (no insult) → Торнин не знает → player говорит с Торнином

5 парных повторов (10 диалогов), чередовать порядок A/B.

Не предписывать реакцию — сравнивать различия:
- NPC_SPOKE.text (Tornin's actual speech)
- intent_type (what intention Tornin chose)
- tone (how expressed attitude)
- cognition block (knowledge before generation)

Запуск: P5A_LIVE_LLM=1 python -m pytest backend/tests/gameplay/test_p5a_step2_ab_experiment.py -v -s
"""
from __future__ import annotations

import logging
import os
from typing import Any

import pytest

from tests.gameplay.harness import TavernGameplayHarness

logger = logging.getLogger(__name__)

_LLM_LIVE = os.environ.get("P5A_LIVE_LLM") == "1"

pytestmark = pytest.mark.skipif(
    not _LLM_LIVE,
    reason="Set P5A_LIVE_LLM=1 to run P5-A Step 2 (requires Hermes-3 server on localhost:8181).",
)

# Initialize router ONCE at module level (safe ? initialize_router() is idempotent)
_ROUTER_INITIALIZED = False
def _ensure_router():
    global _ROUTER_INITIALIZED
    if not _ROUTER_INITIALIZED:
        from app.services.llm.router import initialize_router
        initialize_router()
        _ROUTER_INITIALIZED = True


def _publish_player_insults(harness, victim: str, radius: float = 10.0) -> None:
    from app.domain.events import EventDTO
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType
    _bus = get_event_bus()
    _bus.publish(EventDTO.create(
        event_type=EventType.PLAYER_INSULTS.value,
        source="player",
        payload={"target_id": victim, "text": "Ты дурак!", "action_type": "player_insults"},
        visibility="public", radius=radius, persistence_level="session",
    ))


def _get_epistemic_store(harness):
    _tick_orch = getattr(harness.game_loop, "_tick_orch", None)
    if _tick_orch is None:
        return None
    return getattr(_tick_orch, "_epistemic_store", None)


def _capture_tornin_speeches(harness) -> list:
    """Spy на NPC_SPOKE from tavern_keeper_tornin specifically."""
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType
    _tornin_speeches: list = []

    def _spy(event: Any) -> None:
        _source = getattr(event, "source", "")
        if _source == "tavern_keeper_tornin":
            _pl = getattr(event, "payload", {}) or {}
            _tornin_speeches.append({
                "text": _pl.get("text", ""),
                "intent_type": _pl.get("intent_type", ""),
                "tone": _pl.get("tone", ""),
                "topic": _pl.get("topic", ""),
            })

    _bus = get_event_bus()
    _bus.subscribe(EventType.NPC_SPOKE, _spy)
    return _tornin_speeches


def _get_cognition_block(harness, npc_id: str = "tavern_keeper_tornin") -> str:
    """Get cognition block for Tornin (what he knows before dialogue)."""
    from app.services.npc.cognition_context import CognitionContextResolver
    _store = _get_epistemic_store(harness)
    if _store is None:
        return ""
    _sched = harness.game_loop._get_task_scheduler()
    _mm = getattr(_sched, "_memory_manager", None)
    _resolver = CognitionContextResolver(memory_manager=_mm, epistemic_store=_store)
    return _resolver.resolve_block(npc_id, "player")


def _run_scenario(with_insult: bool, seed: int) -> dict:
    """Single A/B run — capture Tornin's behavior."""
    _ensure_router()
    import time as _time
    _t_start = _time.monotonic()
    _h = TavernGameplayHarness(seed=seed, location="tavern")
    _h.new_game()
    # DON'T call _install_sync_pool — keep real router (LLM)

    if with_insult:
        _publish_player_insults(_h, victim="tavern_keeper_tornin")
        print("  [A] PLAYER_INSULTS published")
    else:
        print("  [B] no insult (control)")

    _t_before_ticks = _time.monotonic()
    _h.advance_ticks(5)
    _t_after_ticks = _time.monotonic()
    print(f"  ticks_time={_t_after_ticks - _t_before_ticks:.1f}s")

    # Verify belief presence/absence
    _store = _get_epistemic_store(_h)
    _beliefs = _store.get_all_for_agent("tavern_keeper_tornin") if _store else []
    _has_belief = any(
        r.proposition.predicate.value == "insulted"
        and r.proposition.subject_id == "player"
        for r in _beliefs
    )
    print(f"  belief_present={_has_belief} (records={len(_beliefs)})")

    # Capture cognition block BEFORE dialogue
    _cog_block = _get_cognition_block(_h)
    print(f"  cognition_block_head={_cog_block[:120]!r}")

    # Spy на Tornin's NPC_SPOKE
    _tornin_speeches = _capture_tornin_speeches(_h)

    # Player talks to Tornin
    print("  player_action: 'Торнин, привет, как дела?'")
    _resp = _h.player_action("Торнин, привет, как дела?")

    # Collect results
    _result = {
        "with_insult": with_insult,
        "seed": seed,
        "has_belief": _has_belief,
        "cognition_block": _cog_block,
        "tornin_speeches": list(_tornin_speeches),
        "speech_count": len(_tornin_speeches),
        "total_time": _time.monotonic() - _t_start,
    }

    if _tornin_speeches:
        for i, s in enumerate(_tornin_speeches):
            print(f"  [TORNIN {i}] text={s['text'][:100]!r} intent={s['intent_type']} tone={s['tone']}")
    else:
        print("  [TORNIN] no NPC_SPOKE from tornin captured")

    _h.dispose()
    return _result


class TestP5AStep2ABExperiment:
    """P5-A Step 2: A/B experiment — does knowledge change Tornin's behavior?"""

    def test_ab_experiment_5_pairs(self):
        """5 парных A/B повторов, чередовать порядок A/B."""
        results_a = []
        results_b = []

        for i in range(5):
            print(f"\n{'='*60}")
            print(f"PAIR {i+1}/5")
            print(f"{'='*60}")

            # Alternate order: even pairs A first, odd pairs B first
            if i % 2 == 0:
                print("\n--- Run A (with insult) ---")
                results_a.append(_run_scenario(with_insult=True, seed=42+i))
                print("\n--- Run B (control) ---")
                results_b.append(_run_scenario(with_insult=False, seed=42+i))
            else:
                print("\n--- Run B (control) ---")
                results_b.append(_run_scenario(with_insult=False, seed=42+i))
                print("\n--- Run A (with insult) ---")
                results_a.append(_run_scenario(with_insult=True, seed=42+i))

        # Summary
        print(f"\n{'='*60}")
        print("A/B EXPERIMENT SUMMARY (5 pairs)")
        print(f"{'='*60}")

        for i in range(5):
            _a = results_a[i]
            _b = results_b[i]
            print(f"\nPair {i+1}:")
            print(f"  A (insult): belief={_a['has_belief']}, speeches={_a['speech_count']}")
            if _a['tornin_speeches']:
                print(f"    text={_a['tornin_speeches'][0]['text'][:100]!r}")
            print(f"  B (control): belief={_b['has_belief']}, speeches={_b['speech_count']}")
            if _b['tornin_speeches']:
                print(f"    text={_b['tornin_speeches'][0]['text'][:100]!r}")

        # Assertions (structural, not prescriptive)
        # A should have belief, B should not
        for i, _a in enumerate(results_a):
            assert _a["has_belief"], f"Pair {i+1} A: Tornin should have insult belief"
        for i, _b in enumerate(results_b):
            assert not _b["has_belief"], f"Pair {i+1} B: Tornin should NOT have insult belief"

        # At least some speeches should be captured
        _a_speeches = sum(r["speech_count"] for r in results_a)
        _b_speeches = sum(r["speech_count"] for r in results_b)
        print(f"\nTotal speeches: A={_a_speeches}, B={_b_speeches}")

        # Log all A vs B texts for qualitative comparison
        print(f"\n{'='*60}")
        print("QUALITATIVE COMPARISON (Master interprets)")
        print(f"{'='*60}")
        for i in range(5):
            print(f"\nPair {i+1}:")
            _a_texts = [s["text"] for s in results_a[i]["tornin_speeches"]]
            _b_texts = [s["text"] for s in results_b[i]["tornin_speeches"]]
            print(f"  A: {_a_texts}")
            print(f"  B: {_b_texts}")

        print("\n[P5-A Step 2] Experiment complete — 5 pairs collected")
        print("[P5-A Step 2] Master interprets: do A and B differ meaningfully?")
